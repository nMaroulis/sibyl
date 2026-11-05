"""Deterministic calendar admission with real native ProtoLink report execution."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from agent_helpers import coordinator_factory, delegate
from fastapi.testclient import TestClient
from protolink import create_llm

from sibyl.api.app import create_app
from sibyl.investigations.contracts import InvestigationRun
from sibyl.investigations.scheduling.calendar import next_occurrence
from sibyl.investigations.scheduling.contracts import (
    BriefingAction,
    CreateBriefing,
    EditBriefing,
    RunBriefing,
)
from sibyl.investigations.scheduling.repository import BriefingConflict, BriefingRepository
from sibyl.services.workspace.llm_settings import ModelSettingsRequest


def definition(client, title="A scheduled question"):
    response = client.post(
        "/api/v1/investigations",
        json={
            "title": title,
            "question": "Explain RSI using the glossary evidence.",
            "context": {"market_source": "demo", "news_mode": "demo"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def model(client, monkeypatch):
    assert client.post("/api/v1/settings/llm", json={"provider": "mock"}).status_code == 200
    report = json.dumps(
        {
            "summary": "A scheduled interpretation of retained glossary evidence.",
            "findings": [
                {
                    "title": "RSI",
                    "detail": "A glossary explanation, not a current market observation.",
                    "sources": ["wiki.search_knowledge"],
                }
            ],
            "uncertainties": ["This is a controlled model test."],
            "next_questions": [],
        }
    )
    coordinator_factory(
        monkeypatch,
        lambda *a, **kw: create_llm("mock", sequential_responses=[delegate("wiki", "Explain RSI"), report]),
    )


@pytest.fixture
def clocked(client):
    service = client.app.state.services.briefings
    clock = [datetime.now(UTC).replace(microsecond=0)]
    service.clock = lambda: clock[0]
    return service, clock


def schedule(client, entry, **patch):
    response = client.post(
        f"/api/v1/investigations/{entry['id']}/schedules",
        json={"frequency": "daily", "local_time": "08:00", "timezone": "UTC", **patch},
    )
    assert response.status_code == 201, response.text
    return response.json()


def finish(client, service, policy):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        client.portal.call(service.tick)
        data = service.detail(policy["id"])
        if data["occurrences"] and data["occurrences"][0]["status"] not in {"waiting", "running"}:
            return data["occurrences"][0]
        time.sleep(0.01)
    pytest.fail("The scheduled native investigation did not finish.")


@pytest.mark.parametrize(
    "values,after,expected",
    [
        ({}, "2026-11-01T07:59:00+00:00", "2026-11-01T08:00:00+00:00"),
        ({}, "2026-11-01T08:00:00+00:00", "2026-11-02T08:00:00+00:00"),
        ({"frequency": "weekly", "weekday": 0}, "2026-11-01T09:00:00+00:00", "2026-11-02T08:00:00+00:00"),
        (
            {"timezone": "Europe/Zurich", "local_time": "02:30"},
            "2026-03-28T03:00:00+00:00",
            "2026-03-30T00:30:00+00:00",
        ),
        (
            {"timezone": "Europe/Zurich", "local_time": "02:30"},
            "2026-10-25T00:00:00+00:00",
            "2026-10-25T00:30:00+00:00",
        ),
        (
            {"timezone": "Europe/Zurich", "local_time": "02:30"},
            "2026-10-25T00:31:00+00:00",
            "2026-10-26T01:30:00+00:00",
        ),
        (
            {"timezone": "Europe/Zurich", "local_time": "02:30", "frequency": "weekly", "weekday": 6},
            "2026-03-28T03:00:00+00:00",
            "2026-04-05T00:30:00+00:00",
        ),
    ],
)
def test_next_calendar_time_handles_boundaries_and_dst(values, after, expected):
    assert (
        next_occurrence(CreateBriefing(**values).model_dump(), datetime.fromisoformat(after)).isoformat()
        == expected
    )


@pytest.mark.parametrize(
    "patch",
    [
        {"local_time": "24:00"},
        {"local_time": "08:00:00"},
        {"timezone": "../etc/passwd"},
        {"timezone": "Not/AZone"},
        {"weekday": True},
        {"telegram": "yes"},
        {"keep_reports": 1},
        {"delivery_format": "html"},
        {"execute_order": True},
    ],
)
def test_invalid_policy_is_rejected_without_saving(client, clocked, patch):
    entry = definition(client)
    response = client.post(f"/api/v1/investigations/{entry['id']}/schedules", json=patch)
    assert response.status_code == 422
    assert client.get(f"/api/v1/investigations/{entry['id']}/schedules").json() == []


def test_saving_calendar_is_lazy_and_private_without_llm_or_telegram(client, clocked, monkeypatch):
    service, _ = clocked
    coordinator_factory(monkeypatch, lambda *a, **kw: pytest.fail("Provider contacted by calendar setup"))
    entry = definition(client)
    policy = schedule(client, entry)
    assert policy["status"] == "armed" and policy["next_run_at"]
    assert service.detail(policy["id"])["occurrences"] == []
    response = client.get(f"/api/v1/briefing-schedules/{policy['id']}")
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/briefing-schedules/status").json()["catch_up"] is False
    assert client.post(f"/api/v1/investigations/{entry['id']}/schedules", json={}).status_code == 409
    assert client.delete(f"/api/v1/investigations/{entry['id']}").status_code == 409


def test_due_time_runs_real_specialists_once_and_advances_calendar(client, clocked, monkeypatch):
    service, clock = clocked
    model(client, monkeypatch)
    entry = definition(client)
    policy = schedule(client, entry)
    clock[0] = datetime.fromisoformat(policy["next_run_at"]) + timedelta(seconds=1)
    result = finish(client, service, policy)
    assert result["status"] == "completed" and result["run_id"] == result["id"]
    report = client.app.state.services.investigations.repository.run(entry["id"], result["run_id"])
    assert report["origin"] == f"schedule:{policy['id']}"
    assert report["sources"][0]["key"] == "wiki.search_knowledge"
    for _ in range(3):
        client.portal.call(service.tick)
    assert len(service.detail(policy["id"])["occurrences"]) == 1
    assert service.repository.get(policy["id"])["next_run_at"] > policy["next_run_at"]


def test_two_calendar_claims_serialize_without_duplicate_occurrences(client, clocked):
    service, clock = clocked
    entry = definition(client)
    policy = schedule(client, entry)
    other = BriefingRepository(service.store)

    async def claim_together():
        async with service._tick_lock:
            clock[0] = datetime.fromisoformat(policy["next_run_at"])
            with ThreadPoolExecutor(2) as pool:
                return list(pool.map(lambda repo: repo.claim_due(clock[0]), [service.repository, other]))

    results = client.portal.call(claim_together)
    assert sum(result is not None for result in results) == 1
    assert len(service.repository.history(policy["id"])) == 1


def test_late_or_restart_times_are_summarized_without_catch_up(client, clocked, settings, monkeypatch):
    service, clock = clocked
    coordinator_factory(monkeypatch, lambda *a, **kw: pytest.fail("Missed occurrence called provider"))
    entry = definition(client)
    policy = schedule(client, entry)
    clock[0] = datetime.fromisoformat(policy["next_run_at"]) + timedelta(days=3)
    client.portal.call(service.tick)
    missed = service.detail(policy["id"])["occurrences"][0]
    assert missed["status"] == "missed" and missed["run_id"] is None
    assert missed["missed_until"] == clock[0].isoformat()
    # A persisted calendar from before the actual current time must also skip at startup.
    with service.store.db() as db:
        db.execute("BEGIN IMMEDIATE")
        row = service.repository._read(db, policy["id"])
        row["next_run_at"] = "2020-01-01T08:00:00+00:00"
        service.repository._write(db, row)
    with TestClient(create_app(settings)) as restarted:
        history = restarted.get(f"/api/v1/briefing-schedules/{policy['id']}").json()
        assert history["occurrences"][0]["status"] == "missed"
        assert datetime.fromisoformat(history["next_run_at"]) > datetime.now(UTC)


def test_run_now_is_idempotent_and_uses_a_frozen_team_while_waiting(client, clocked, monkeypatch):
    service, clock = clocked
    model(client, monkeypatch)
    entry = definition(client)
    policy = schedule(client, entry)
    investigations = client.app.state.services.investigations
    blocked = []
    for _ in range(4):
        other = definition(client, "Occupied")
        run, _ = investigations.repository.reserve(other["id"], uuid4().hex, other["context"], {})
        blocked.append(run)
    request = RunBriefing(revision=policy["revision"], request_id=uuid4().hex)
    occurrence = client.portal.call(service.run_now, policy["id"], request)
    assert client.portal.call(service.run_now, policy["id"], request)["id"] == occurrence["id"]
    client.portal.call(service.tick)
    assert service.detail(policy["id"])["occurrences"][0]["status"] == "waiting"
    client.app.state.services.agents.models.save(ModelSettingsRequest(provider="none"))
    for run in blocked:
        investigations.repository.update(run["investigation_id"], run["id"], status="cancelled")
    clock[0] += timedelta(seconds=6)
    result = finish(client, service, policy)
    assert result["status"] == "completed", result
    report = investigations.repository.run(entry["id"], result["run_id"])
    assert report["models"]["sibyl"]["provider"] == "mock"
    assert report["models"]["wiki"]["provider"] == "mock"
    assert service.repository.get(policy["id"])["next_run_at"] == policy["next_run_at"]


def test_pause_edit_and_revision_checks_withdraw_waiting_work(client, clocked, monkeypatch):
    service, _ = clocked
    model(client, monkeypatch)
    entry = definition(client)
    policy = schedule(client, entry)

    # Keep the explicit run waiting; no tick is needed to authorize a future pause.
    async def pause_before_tick():
        async with service._tick_lock:
            queued = await service.run_now(policy["id"], RunBriefing(revision=1, request_id=uuid4().hex))
            paused = service.change(policy["id"], BriefingAction(revision=1, action="pause"))
            return queued, paused

    queued, paused = client.portal.call(pause_before_tick)
    assert paused["status"] == "paused" and paused["next_run_at"] is None
    assert service.detail(policy["id"])["occurrences"][0]["id"] == queued["id"]
    assert service.detail(policy["id"])["occurrences"][0]["status"] == "cancelled"
    assert queued["id"] not in service._models
    with pytest.raises(BriefingConflict):
        service.change(policy["id"], BriefingAction(revision=1, action="resume"))
    changed = service.edit(
        policy["id"],
        EditBriefing(
            revision=paused["revision"],
            frequency="weekly",
            weekday=4,
            timezone="Europe/Zurich",
            local_time="09:30",
        ),
    )
    assert changed["status"] == "paused"
    resumed = service.change(policy["id"], BriefingAction(revision=changed["revision"], action="resume"))
    assert resumed["next_run_at"] and resumed["status"] == "armed"
    archived = service.change(policy["id"], BriefingAction(revision=resumed["revision"], action="archive"))
    assert archived["status"] == "archived"
    assert client.delete(f"/api/v1/investigations/{entry['id']}").status_code == 204


def test_missing_model_records_blocked_run_instead_of_silent_demo_fallback(client, clocked):
    service, clock = clocked
    entry = definition(client)
    policy = schedule(client, entry)
    clock[0] = datetime.fromisoformat(policy["next_run_at"])
    client.portal.call(service.tick)
    result = service.detail(policy["id"])["occurrences"][0]
    assert result["status"] == "blocked" and result["run_id"] is None
    assert "AI model" in result["error"]


def test_waiting_without_capacity_expires_without_inference(client, clocked, monkeypatch):
    service, clock = clocked
    model(client, monkeypatch)
    entry = definition(client)
    policy = schedule(client, entry)

    async def expire_before_tick():
        async with service._tick_lock:
            await service.run_now(policy["id"], RunBriefing(revision=1, request_id=uuid4().hex))
            clock[0] += timedelta(minutes=16)

    client.portal.call(expire_before_tick)
    client.portal.call(service.tick)
    result = service.detail(policy["id"])["occurrences"][0]
    assert result["status"] == "missed" and result["run_id"] is None


def test_retention_preserves_manual_reports_and_monotonic_versions(client, clocked, monkeypatch):
    service, _ = clocked
    model(client, monkeypatch)
    entry = definition(client)
    policy = schedule(client, entry, keep_reports=5)
    investigations = client.app.state.services.investigations
    manual = client.portal.call(investigations.start, entry["id"], InvestigationRun(request_id=uuid4().hex))
    deadline = time.monotonic() + 5
    while (
        investigations.repository.run(entry["id"], manual["id"])["status"] in {"queued", "running"}
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    generated = []
    for index in range(7):
        client.portal.call(service.run_now, policy["id"], RunBriefing(revision=1, request_id=uuid4().hex))
        completed = finish(client, service, policy)
        saved = investigations.repository.run(entry["id"], completed["run_id"])
        generated.append(saved["session_id"])
        if index == 0:
            # A user's unsuccessful follow-up is still a continuation, even with only one turn.
            requests = investigations.network.requests
            follow_up = requests.start(saved["session_id"], "My follow-up", "mock", "mock", uuid4().hex)
            requests.update(follow_up["id"], status="failed", error="Controlled failure")
    retained = investigations.repository.get(entry["id"])["runs"]
    assert len(retained) == 6
    assert manual["id"] in {run["id"] for run in retained}
    assert retained[0]["version"] == 8
    assert all(run["version"] >= 4 or run["id"] == manual["id"] for run in retained)
    assert investigations.network.conversation(generated[0])["turns"]
    with pytest.raises(LookupError):
        investigations.network.conversation(generated[1])


def test_repeated_resume_and_stale_run_retry_do_not_create_or_discard_work(client, clocked, monkeypatch):
    service, _ = clocked
    model(client, monkeypatch)
    policy = schedule(client, definition(client))
    request = RunBriefing(revision=1, request_id=uuid4().hex)

    async def check_before_admission():
        async with service._tick_lock:
            await service.run_now(policy["id"], request)
            unchanged = service.change(policy["id"], BriefingAction(revision=1, action="resume"))
            assert unchanged["revision"] == 1 and request.request_id in service._models
            service.change(policy["id"], BriefingAction(revision=1, action="pause"))
            retried = await service.run_now(policy["id"], request)
            assert retried["status"] == "cancelled"
            assert request.request_id not in service._models

    client.portal.call(check_before_admission)
    assert len(service.detail(policy["id"])["occurrences"]) == 1


def test_calendar_clock_rollback_never_repeats_a_retained_due_time(client, clocked):
    service, clock = clocked
    policy = schedule(client, definition(client))
    due = datetime.fromisoformat(policy["next_run_at"])
    first = service.repository.claim_due(due, startup=True)
    assert first["status"] == "missed"
    # A backwards clock followed by an edit can recalculate an already observed due time.
    clock[0] = due - timedelta(minutes=1)
    service.edit(policy["id"], EditBriefing(revision=1))
    replay = service.repository.claim_due(due)
    assert replay["id"] == first["id"] and replay["status"] == "missed"
    assert service.repository.get(policy["id"])["next_run_at"] > due.isoformat()
    assert len(service.repository.history(policy["id"])) == 1
