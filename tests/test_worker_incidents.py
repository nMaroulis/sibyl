"""Retained local stalls, genuine progress recovery and observation gaps without fake uptime."""

import asyncio
import json
import threading
import time

from sibyl.alerts.inbox import NotificationInbox
from sibyl.operations.health import WorkerHealth
from sibyl.operations.watchdog import WorkerWatchdog


def row(state="stalled", iterations=3, **patch):
    return {
        "id": "orders",
        "label": "PRIVATE-IGNORE",
        "state": state,
        "iterations": iterations,
        "failures": 1,
        "deadline_seconds": 120,
        "interval_seconds": 1,
        "elapsed_seconds": 140,
        "last_started_at": "2026-11-08T12:00:00+00:00",
        "last_finished_at": None,
        "last_error": "API-KEY-SHOULD-NEVER-APPEAR",
        **patch,
    }


def test_passive_reads_never_create_samples_and_incident_is_deduplicated_until_actual_progress(store):
    now = [0.0]
    observed = [row()]
    watch = WorkerWatchdog(store, lambda: observed, clock=lambda: now[0])
    assert watch.snapshot()["items"] == [] and watch.status()["last_sample_at"] is None
    watch.sample()
    now[0] = 2
    watch.sample()
    result = watch.snapshot()
    assert result["total"] == 1 and result["items"][0]["evidence"]["observations"] == 2
    assert result["items"][0]["state"] == "active"
    assert "API-KEY" not in json.dumps(result) and "PRIVATE-IGNORE" not in json.dumps(result)
    observed[0] = row("running", 3)
    now[0] = 4
    watch.sample()
    assert watch.snapshot()["items"][0]["state"] == "active"
    observed[0] = row("waiting", 4, last_finished_at="2026-11-08T12:02:30+00:00")
    now[0] = 6
    watch.sample()
    completed = watch.snapshot()["items"][0]
    assert completed["state"] == "recovered" and completed["ended_at"]
    watch.sample()
    notices = NotificationInbox(store).page()["items"]
    assert len(notices) == 2 and {notice["action"] for notice in notices} == {"attention", "recovered"}
    assert all(
        notice["kind"] == "workspace" and notice["incident_id"] == completed["id"] for notice in notices
    )
    # Acknowledging a notice cannot create progress or change incident evidence.
    NotificationInbox(store).mark_read(notices[0]["id"])
    assert watch.snapshot()["items"][0] == completed
    exported = NotificationInbox(store).history.export(kind="workspace")
    assert len(exported["items"]) == 2
    watch.close()


def test_restarting_or_stopping_observation_never_claims_recovery(store):
    watch = WorkerWatchdog(store, lambda: [row("failed")])
    watch.sample()
    identity = watch.snapshot()["items"][0]["id"]
    # Simulate a new process observing storage left by an unclean old process.
    later = WorkerWatchdog(store, lambda: [row("waiting", 50)])
    later.sample()
    old = later.snapshot()["items"][0]
    assert old["id"] == identity and old["state"] == "observation_ended" and old["ended_at"] is None
    assert NotificationInbox(store).page()["total"] == 1
    later.close()
    watch.close()


def test_observer_gap_is_recorded_without_inventing_worker_outage(store):
    now = [0.0]
    watch = WorkerWatchdog(store, lambda: [row("waiting")], clock=lambda: now[0])
    watch.sample()
    now[0] = 65
    watch.sample()
    result = watch.snapshot()
    assert result["total"] == 0 and result["gaps"][0]["seconds"] == 65
    assert NotificationInbox(store).page()["total"] == 0
    watch.close()


async def test_independent_watchdog_records_an_actually_blocked_event_loop_without_browser_reads(store):
    health = WorkerHealth(store)
    health.watchdog.interval = 0.01
    release = threading.Event()
    sampled = threading.Event()
    original = health.watchdog.sample

    def observe():
        original()
        if health.watchdog.snapshot()["items"]:
            sampled.set()
            release.set()

    health.watchdog.sample = observe

    async def blocked():
        # Deliberate bad async action: the separate observer must still run.
        assert release.wait(5), "The independent observer did not detect stalled work."

    health.start("orders", "Order maintenance", blocked, interval=30, deadline=0.03)
    health.watchdog.start()
    try:
        deadline = time.monotonic() + 6
        while not sampled.is_set() and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        assert sampled.is_set()
        incident = health.watchdog.snapshot()["items"][0]
        assert incident["worker_id"] == "orders" and incident["evidence"]["first_phase"] == "stalled"
        assert health.workers["orders"]["iterations"] == 1
        health.watchdog.sample()
        assert health.watchdog.snapshot()["items"][0]["state"] == "recovered"
    finally:
        release.set()
        await health.close()
    assert not health.watchdog.thread.is_alive()


async def test_failed_observer_exposes_only_failure_count_then_resumes_sampling(store):
    calls = [0]

    def observations():
        calls[0] += 1
        if calls[0] < 3:
            raise RuntimeError("PROVIDER-PRIVATE-DIAGNOSTICS")
        return [row("waiting")]

    watch = WorkerWatchdog(store, observations, interval=0.01)
    watch.start()
    try:
        deadline = time.monotonic() + 3
        while watch.status()["last_sample_at"] is None and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        result = watch.snapshot()
        assert result["observer"]["failed_samples"] == 2 and result["observer"]["last_sample_at"]
        assert "PRIVATE" not in json.dumps(result)
    finally:
        await asyncio.to_thread(watch.close)


def test_history_is_bounded_but_active_incidents_are_not_evicted(store):
    current = [row("failed")]
    watch = WorkerWatchdog(store, lambda: current)
    for _ in range(205):
        watch.sample()
        current[0] = row("waiting", 4)
        watch.sample()
        current[0] = row("failed")
    watch.sample()
    result = watch.snapshot()
    assert result["total"] <= 201 and result["items"][0]["state"] == "active"
    watch.close()


def test_workspace_incident_endpoint_is_passive_and_private(manual_client):
    watch = manual_client.app.state.services.workers.watchdog
    before = watch.status()["last_sample_at"]
    response = manual_client.get("/api/v1/workspace/incidents")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()["observer"]["last_sample_at"] == before
    assert manual_client.get("/api/v1/workspace/incidents?offset=-1").status_code == 422
