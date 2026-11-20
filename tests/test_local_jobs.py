"""Durable scheduling, explicit replay boundaries and late-result/cancellation races."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from sibyl.operations.jobs.contracts import CreateJob, JobAction, NoArguments
from sibyl.operations.jobs.handlers import Handler
from sibyl.operations.jobs.service import LocalJobs


@pytest.fixture
def queue(store):
    now, calls = [1_800_000_000.0], []
    handler = Handler(
        "test.read",
        "Read",
        "An isolated domain read.",
        NoArguments,
        lambda args: calls.append(args) or {"ok": True},
    )
    jobs = LocalJobs(store, [handler], clock=lambda: now[0])
    return jobs, now, calls


def create(jobs, **fields):
    return jobs.create(CreateJob(label="My task", kind="test.read", **fields))


def test_paused_default_explicit_run_and_idempotent_receipt(queue):
    jobs, _, calls = queue
    job = create(jobs)
    jobs.tick()
    assert calls == []
    request_id = uuid4().hex
    run = jobs.start(job["id"], request_id)
    assert jobs.start(job["id"], request_id)["id"] == run["id"]
    jobs.tick()
    assert calls == [{}]
    assert jobs.run(job["id"], run["id"])["state"] == "completed"
    assert jobs.start(job["id"], request_id)["state"] == "completed"
    jobs.tick()
    assert len(calls) == 1


@pytest.mark.parametrize("policy,expected_calls,skipped", [("skip", 0, 6), ("once", 1, 5)])
def test_missed_recurring_work_never_bursts(queue, policy, expected_calls, skipped):
    jobs, now, calls = queue
    job = create(jobs, interval_seconds=60, enabled=True, missed=policy)
    now[0] += 301
    jobs.tick()
    assert len(calls) == expected_calls
    saved = jobs.state()["items"][0]
    assert saved["next_due"] == job["next_due"] + 360
    assert saved["skipped_occurrences"] == skipped
    jobs.tick()
    assert len(calls) == expected_calls


def test_schedule_pausing_does_not_cancel_already_accepted_run(queue):
    jobs, _, calls = queue
    job = create(jobs, enabled=True, interval_seconds=60)
    run = jobs.start(job["id"], uuid4().hex)
    jobs.action(job["id"], JobAction(action="pause", revision=job["revision"]))
    jobs.tick()
    assert len(calls) == 1
    assert jobs.run(job["id"], run["id"])["state"] == "completed"
    assert jobs.state()["items"][0]["state"] == "paused"


def test_revision_guard_and_unknown_handler_arguments_are_not_persisted(queue):
    jobs, _, _ = queue
    job = create(jobs)
    jobs.action(job["id"], JobAction(action="resume", revision=job["revision"]))
    with pytest.raises(ValueError, match="changed"):
        jobs.action(job["id"], JobAction(action="pause", revision=job["revision"]))
    with pytest.raises(ValueError):
        create(jobs, arguments={"api_key": "NEVER-SAVE-ME"})
    with jobs.store.db() as db:
        assert "NEVER-SAVE-ME" not in str(db.execute("SELECT payload FROM local_jobs").fetchall())


def test_cancelled_queued_work_is_not_dispatched(queue):
    jobs, _, calls = queue
    job = create(jobs)
    run = jobs.start(job["id"], uuid4().hex)
    jobs.cancel(job["id"], run["id"])
    jobs.tick()
    assert calls == []
    assert jobs.run(job["id"], run["id"])["state"] == "cancelled"


def test_late_domain_result_cannot_overwrite_cancellation(store):
    entered, release = threading.Event(), threading.Event()

    def blocked(_args):
        entered.set()
        assert release.wait(timeout=10)
        return {"safe": True}

    jobs = LocalJobs(store, [Handler("test.read", "Read", "Controlled blocking read.", NoArguments, blocked)])
    job = create(jobs)
    run = jobs.start(job["id"], uuid4().hex)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(jobs.tick)
        try:
            assert entered.wait(timeout=3)
            jobs.cancel(job["id"], run["id"])
            jobs.tick()  # A second local tick cannot admit overlapping work.
        finally:
            release.set()
        future.result(timeout=5)
    saved = jobs.run(job["id"], run["id"])
    assert saved["state"] == "cancelled"
    assert saved["result"] is None


@pytest.mark.parametrize("restart_safe,expected", [(True, "queued"), (False, "interrupted")])
def test_restart_requeues_only_declared_read_only_work(queue, restart_safe, expected):
    jobs, _, calls = queue
    job = create(jobs)
    run = jobs.start(job["id"], uuid4().hex)
    with jobs.store.db() as db:
        run["state"] = "running"
        LocalJobs._write_run(db, run)
    recovered = LocalJobs(
        jobs.store,
        [
            Handler(
                "test.read",
                "Read",
                "Reviewed replay scope.",
                NoArguments,
                lambda args: calls.append(args) or {},
                restart_safe=restart_safe,
            )
        ],
    )
    assert recovered.run(job["id"], run["id"])["state"] == expected
    recovered.tick()
    assert len(calls) == int(restart_safe)


def test_retention_does_not_erase_submission_identity(queue):
    jobs, _, calls = queue
    job = create(jobs)
    first_id = uuid4().hex
    for index in range(23):
        jobs.start(job["id"], first_id if index == 0 else uuid4().hex)
        jobs.tick()
    assert len(jobs.runs(job["id"])["items"]) == 20
    assert len(calls) == 23
    with pytest.raises(ValueError, match="already accepted"):
        jobs.start(job["id"], first_id)
    assert len(calls) == 23


def test_failures_retain_codes_without_private_diagnostics(store):
    def fail(_args):
        raise RuntimeError("PRIVATE-MODEL-KEY https://private-host")

    jobs = LocalJobs(store, [Handler("test.read", "Read", "Failure fixture.", NoArguments, fail)])
    job = create(jobs)
    run = jobs.start(job["id"], uuid4().hex)
    jobs.tick()
    saved = jobs.run(job["id"], run["id"])
    assert saved["state"] == "failed"
    assert saved["error"] == "RuntimeError"
    assert "PRIVATE" not in json.dumps(saved)


def test_api_health_job_runs_without_model_or_exchange_access(manual_client, monkeypatch):
    client = manual_client
    services = client.app.state.services

    def forbidden(*_args, **_kwargs):
        pytest.fail("Health job contacted a provider")

    monkeypatch.setattr(services.market, "adapter", forbidden)
    response = client.post(
        "/api/v1/workspace/jobs", json={"label": "Local health", "kind": "workspace.health"}
    )
    assert response.status_code == 201, response.text
    job = response.json()
    queued = client.post(f"/api/v1/workspace/jobs/{job['id']}/runs", json={"request_id": uuid4().hex})
    assert queued.status_code == 202
    services.jobs.tick()
    result = client.get(f"/api/v1/workspace/jobs/{job['id']}/runs/{queued.json()['id']}")
    assert result.status_code == 200
    assert result.json()["state"] == "completed"
    assert result.json()["result"]["database"]["status"] == "passed"
    assert result.headers["cache-control"] == "no-store"
    assert (
        client.post("/api/v1/workspace/jobs", json={"label": "Bad", "kind": "shell.exec"}).status_code == 400
    )


def test_queued_training_requires_pinned_input_and_never_arms_repeat(manual_client):
    client = manual_client
    payload = {"label": "Training", "kind": "forecast.train", "arguments": {"input_kind": "current_feed"}}
    assert client.post("/api/v1/workspace/jobs", json=payload).status_code == 400
    payload["arguments"] = {"input_kind": "saved_dataset", "dataset_id": "a" * 64}
    payload["interval_seconds"] = 60
    assert client.post("/api/v1/workspace/jobs", json=payload).status_code == 400


def test_restore_quarantines_jobs_and_accepted_runs(queue):
    from sibyl.operations.recovery import prepare_recovery

    jobs, _, calls = queue
    job = create(jobs, enabled=True)
    run = jobs.start(job["id"], uuid4().hex)
    prepare_recovery(jobs.store, "controlled-backup")
    assert jobs.state()["items"][0]["state"] == "paused"
    assert jobs.run(job["id"], run["id"])["state"] == "interrupted"
    jobs.tick()
    assert calls == []
