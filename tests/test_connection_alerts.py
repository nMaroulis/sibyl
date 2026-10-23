"""Connection alerts from real local transport evidence; no exchange or external delivery."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from protolink import Task

from sibyl.alerts.connection_conditions import assess_connection
from sibyl.alerts.connections import ConnectionAlerts
from sibyl.alerts.contracts import (
    AlertConflict,
    ConnectionAlertCreate,
    ConnectionAlertUpdate,
    StrategyAlertAction,
)
from sibyl.market_data.control import ProviderControl, ProviderDeferred
from sibyl.market_data.health_history import ProviderHistory


def source(identity="binance"):
    return dict(
        id=identity,
        name=identity.title(),
        kind="exchange",
        provider=identity,
        environment="production",
        available=True,
    )


@pytest.fixture
def setup(store):
    clock = [datetime.now(UTC).timestamp()]
    history = ProviderHistory(store, clock=lambda: datetime.fromtimestamp(clock[0], UTC))
    market = SimpleNamespace(
        read_history=history, provider_health=lambda: {"items": [source(), source("kraken"), source("demo")]}
    )
    alerts = ConnectionAlerts(market, store, clock=lambda: clock[0])
    return alerts, history, clock


def watch(alerts, **kwargs):
    return alerts.create(ConnectionAlertCreate(source="binance", **kwargs))


def record(history, kind="network", operation="fetch_ticker", generation="profile", **kwargs):
    history.record(source(), generation, 10, kind, operation=operation, **kwargs)


def current(alerts, rule):
    return next(item for item in alerts.rules(True)["items"] if item["id"] == rule["id"])


def due(alerts):
    with alerts.store.db() as db:
        db.execute("UPDATE connection_alerts SET next_check=0")


def change(alerts, rule, action):
    return alerts.change(
        rule["id"], StrategyAlertAction(action=action, revision=current(alerts, rule)["revision"])
    )


def test_consecutive_per_operation_failure_recovery_and_deduplication(setup):
    alerts, history, clock = setup
    for _ in range(4):
        record(history)  # Already observed: not replayed on creation.
    rule = watch(alerts)
    assert alerts.inbox.page()["total"] == 0
    for _ in range(3):
        record(history, operation="fetch_balance")
        record(history, None)  # Quotes cannot recover a balance incident.
    alerts.tick()
    item = alerts.inbox.page()["items"][0]
    assert item["kind"] == "connection" and item["operation"] == "fetch_balance"
    assert item["action"] == "failing" and item["failures"] == 3
    assert item["rule_revision"] == 1 and item["environment"] == "production"
    for _ in range(4):
        record(history, None)
        record(history, operation="fetch_balance")
    due(alerts)
    alerts.tick()
    assert alerts.inbox.page()["total"] == 1
    record(history, None, operation="fetch_balance")
    due(alerts)
    alerts.tick()
    assert alerts.inbox.page()["total"] == 1
    record(history, None, operation="fetch_balance")
    due(alerts)
    alerts.tick()
    assert alerts.inbox.page()["total"] == 2
    assert {item["action"] for item in alerts.inbox.page()["items"]} == {"failing", "recovered"}
    assert not current(alerts, rule)["operations"]["fetch_balance"]["incident"]
    due(alerts)
    alerts.tick()
    assert alerts.inbox.page()["total"] == 2


def test_success_and_request_errors_break_streaks_without_false_recovery(setup):
    alerts, history, _ = setup
    rule = watch(alerts, failures_required=2)
    for kind in ["network", None, "network", "request", "network"]:
        record(history, kind)
    alerts.tick()
    assert alerts.inbox.page()["total"] == 0
    record(history)
    due(alerts)
    alerts.tick()
    assert alerts.inbox.page()["total"] == 1
    for kind in [None, "request", None]:
        record(history, kind)
    due(alerts)
    alerts.tick()
    assert current(alerts, rule)["operations"]["fetch_ticker"]["incident"]
    assert alerts.inbox.page()["total"] == 1


def test_recovery_can_be_silent_then_another_incident_notifies(setup):
    alerts, history, _ = setup
    rule = watch(alerts, failures_required=1, successes_required=1, notify_recovery=False)
    for kind in ["authentication", None, "rate_limit"]:
        record(history, kind)
    alerts.tick()
    assert alerts.inbox.page()["total"] == 2
    assert current(alerts, rule)["operations"]["fetch_ticker"]["incident"]


@pytest.mark.parametrize(
    "discontinuity", ["session", "generation", "gap", "backwards", "sequence", "out_of_order", "future"]
)
def test_uncertain_continuity_restarts_failure_count(setup, discontinuity):
    alerts, history, clock = setup
    rule = watch(alerts, failures_required=2)
    record(history)
    alerts.tick()
    if discontinuity == "session":
        history.events.session = "restarted"
    elif discontinuity == "generation":
        record(history, generation="replaced")
    elif discontinuity == "gap":
        clock[0] += 301
    elif discontinuity == "backwards":
        clock[0] -= 1
    elif discontinuity in {"sequence", "out_of_order"}:
        with history.events._lock:
            key = ("binance", "profile", "fetch_ticker")
            _, stream = history.events._streams[key]
            history.events._streams[key] = (6 if discontinuity == "sequence" else 0, stream)
    elif discontinuity == "future":
        history.clock = lambda: datetime.fromtimestamp(clock[0] + 120, UTC)
    if discontinuity != "generation":
        record(history)
    due(alerts)
    alerts.tick()
    assert alerts.inbox.page()["total"] == 0
    assert current(alerts, rule)["tracking_note"]


def test_restart_keeps_incident_but_needs_new_session_successes(setup):
    alerts, history, clock = setup
    rule = watch(alerts, failures_required=1)
    record(history)
    record(history, None)
    alerts.tick()
    new_history = ProviderHistory(alerts.store, clock=history.clock)
    alerts.market.read_history = new_history
    restarted = ConnectionAlerts(alerts.market, alerts.store, clock=lambda: clock[0])
    record(new_history, None)
    due(restarted)
    restarted.tick()
    assert restarted.inbox.page()["total"] == 1
    record(new_history, None)
    due(restarted)
    restarted.tick()
    assert restarted.inbox.page()["total"] == 2
    assert not current(restarted, rule)["operations"]["fetch_ticker"]["incident"]


def test_retired_observations_and_other_source_cannot_trigger_or_recover(setup):
    alerts, history, _ = setup
    watch(alerts, failures_required=1, successes_required=1)
    record(history, retired=True)
    history.record(source("kraken"), "other", 1, "network", operation="fetch_ticker")
    alerts.tick()
    assert alerts.inbox.page()["total"] == 0
    record(history)
    due(alerts)
    alerts.tick()
    record(history, None, retired=True)
    due(alerts)
    alerts.tick()
    assert alerts.inbox.page()["total"] == 1


def test_recording_failure_creates_sequence_gap_not_false_consecutiveness(setup):
    alerts, history, _ = setup
    watch(alerts, failures_required=2)
    record(history)
    alerts.tick()
    with alerts.store.db() as db:
        db.execute("BEGIN IMMEDIATE")
        record(history)  # Best-effort telemetry times out, sequence still advances.
    assert history.recording()["dropped_observations"] == 1
    record(history)
    due(alerts)
    alerts.tick()
    assert alerts.inbox.page()["total"] == 0
    record(history)
    due(alerts)
    alerts.tick()
    assert alerts.inbox.page()["total"] == 1


def test_bounded_journal_pruning_resets_streaks_and_discloses_gap(setup, monkeypatch):
    alerts, history, _ = setup
    rule = watch(alerts, failures_required=3)
    record(history)
    record(history)
    alerts.tick()
    monkeypatch.setattr("sibyl.market_data.read_events.MAX_EVENTS", 2)
    for _ in range(4):
        record(history)
    due(alerts)
    alerts.tick()
    assert alerts.inbox.page()["total"] == 0
    assert "expired" in current(alerts, rule)["tracking_note"]
    with alerts.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM provider_read_events").fetchone()[0] == 2
        tail = history.events.tail(db)
        db.execute("DELETE FROM provider_read_events")
        history.events._watermark(db, tail)
        assert history.events.tail(db) == tail


def test_pause_edit_resume_archive_and_revision_controls(setup):
    alerts, history, _ = setup
    rule = watch(alerts, failures_required=1)
    with pytest.raises(AlertConflict):
        watch(alerts)
    record(history)
    change(alerts, rule, "pause")
    alerts.tick()
    change(alerts, rule, "arm")
    alerts.tick()
    assert alerts.inbox.page()["total"] == 0
    record(history)
    due(alerts)
    alerts.tick()
    old = alerts.inbox.page()["items"][0]
    edited = alerts.edit(rule["id"], ConnectionAlertUpdate(source="binance", label="New name", revision=3))
    assert edited["status"] == "paused"
    with pytest.raises(AlertConflict):
        alerts.change(rule["id"], StrategyAlertAction(action="arm", revision=3))
    assert alerts.inbox.page()["items"][0] == old
    change(alerts, rule, "archive")
    replacement = watch(alerts)
    with pytest.raises(AlertConflict):
        change(alerts, rule, "restore")
    change(alerts, replacement, "archive")
    assert change(alerts, rule, "restore")["status"] == "paused"
    assert alerts.rules()["count"] == 1
    assert alerts.rules(True, 1)["items"][0]["id"] == rule["id"]
    alerts.limit = 1
    with pytest.raises(ValueError):
        alerts.create(ConnectionAlertCreate(source="kraken"))
    for identity in ["demo", "unknown"]:
        with pytest.raises(ValueError):
            alerts.create(ConnectionAlertCreate(source=identity))


def test_atomic_notification_cursor_and_two_consumers(setup, monkeypatch):
    alerts, history, clock = setup
    rule = watch(alerts, failures_required=1)
    record(history)
    original = alerts._write
    monkeypatch.setattr(alerts, "_write", lambda *_: (_ for _ in ()).throw(RuntimeError("crash")))
    with pytest.raises(RuntimeError):
        alerts.tick()
    assert current(alerts, rule)["cursor"] == rule["cursor"] and alerts.inbox.page()["total"] == 0
    monkeypatch.setattr(alerts, "_write", original)
    other = ConnectionAlerts(alerts.market, alerts.store, clock=lambda: clock[0])
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda service: service.tick(), [alerts, other]))
    assert alerts.inbox.page()["total"] == 1


def test_backlog_is_bounded_and_passive_reads_do_not_advance_it(setup):
    alerts, history, _ = setup
    rule = watch(alerts, failures_required=1)
    for _ in range(105):
        record(history)
    assert current(alerts, rule)["cursor"] == 0
    alerts.tick()
    assert current(alerts, rule)["cursor"] == 100
    alerts.tick()
    assert current(alerts, rule)["cursor"] == 105
    assert alerts.inbox.page()["total"] == 1
    alerts.close()
    record(history, None)
    due(alerts)
    alerts.tick()
    assert current(alerts, rule)["cursor"] == 105


def test_transport_journal_is_allowlisted_and_excludes_demo_cache_writes_deferral(setup):
    alerts, history, _ = setup
    control = ProviderControl(min_interval=0, max_wait=0.01, history=history)
    with control.operation(source(), "fetch_balance", read=True):
        assert control.transport(lambda: {"secret": "PRIVATE"})
    control.cache_hit(source())
    with control.mutation(), control.operation(source(), "fetch_balance", read=True):
        control.transport(lambda: {})
    with control.operation(source(), "create_order", read=False):
        control.transport(lambda: {})
    history.record(source("demo"), "demo", 1, None)
    with control._condition:
        control._bucket(source())["cooldown"] = time.monotonic() + 60
    with pytest.raises(ProviderDeferred), control.operation(source(), "fetch_ticker", read=True):
        control.transport(lambda: {})
    with alerts.store.db() as db:
        rows = [dict(row) for row in db.execute("SELECT * FROM provider_read_events")]
    assert len(rows) == 1 and rows[0]["operation"] == "fetch_balance"
    assert "PRIVATE" not in json.dumps(rows)
    old = {**source(), "_state": control.register(source())}
    control.reset("binance")
    control.register(source())
    with control._condition:
        control._bucket(source())["cooldown"] = 0
    with control.operation(old, "fetch_ticker", read=True):
        control.transport(lambda: {})
    with alerts.store.db() as db:
        assert (
            db.execute("SELECT retired FROM provider_read_events ORDER BY id DESC LIMIT 1").fetchone()[0] == 1
        )


def test_http_contract_shared_inbox_and_native_technician_tool(client, monkeypatch):
    market = client.app.state.services.market
    monkeypatch.setattr(market, "client", lambda *_: pytest.fail("Unexpected provider probe"))
    response = client.post("/api/v1/connection-alerts", json={"source": "binance", "failures_required": 1})
    assert response.status_code == 201 and response.headers["cache-control"] == "no-store"
    rule = response.json()
    record(market.read_history)
    due(market.connection_alerts)
    market.connection_alerts.tick()
    assert client.get("/api/v1/notifications").json()["items"][0]["kind"] == "connection"
    assert client.get("/api/v1/connection-alerts").headers["cache-control"] == "no-store"
    assert (
        client.get("/api/v1/connection-alerts/example").json()["rules"]["items"][0]["id"]
        == "example-connection-alert"
    )
    assert client.post("/api/v1/connection-alerts", json={"source": "binance"}).status_code == 409
    assert client.post("/api/v1/connection-alerts", json={"source": "demo"}).status_code == 400
    for fields in [
        {"failures_required": True},
        {"failures_required": 0},
        {"successes_required": 6},
        {"notify_recovery": "false"},
        {"extra": 1},
        {"label": "two\nlines"},
    ]:
        assert (
            client.post("/api/v1/connection-alerts", json={"source": "kraken", **fields}).status_code == 422
        )
    assert (
        client.post(
            f"/api/v1/connection-alerts/{rule['id']}/action", json={"action": "pause", "revision": 99}
        ).status_code
        == 409
    )
    network = client.app.state.services.agents.network
    result = client.portal.call(
        network.client.send_task,
        network.cards["technician"].url,
        Task.create_tool_call("connection_alerts", {}),
    )
    result.raise_for_status()
    evidence = result.get_last_item().parts[-1].as_tool_output().result
    assert evidence["rules"]["items"][0]["id"] == rule["id"]
    assert evidence["recent_notifications"][0]["kind"] == "connection"
    assert [row.id for row in client.app.state.services.store.connections() if row.active] == ["demo"]


def test_age_retention_preserves_watermark_and_stream_eviction_is_conservative(setup, monkeypatch):
    alerts, history, clock = setup
    rule = watch(alerts, failures_required=2)
    record(history)
    alerts.tick()
    monkeypatch.setattr("sibyl.market_data.read_events.MAX_STREAMS", 1)
    history.record(source("kraken"), "other", 1, None, operation="fetch_ticker")
    record(history)  # Eviction restarts sequence, not an adjacent failed read.
    due(alerts)
    alerts.tick()
    assert alerts.inbox.page()["total"] == 0
    clock[0] += 15 * 86400
    record(history)
    due(alerts)
    alerts.tick()
    with alerts.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM provider_read_events").fetchone()[0] == 1
        assert db.execute("SELECT pruned_through FROM provider_event_retention").fetchone()[0] == 3
    assert current(alerts, rule)["tracking_note"]
    assert alerts.inbox.page()["total"] == 0


@pytest.mark.parametrize("bad_time", ["invalid", "2026-10-23T12:00:00"])
def test_untrusted_timestamps_do_not_establish_failure_or_recovery(bad_time):
    rule = dict(operations={}, failures_required=1, successes_required=1, notify_recovery=True)
    event = dict(
        retired=False,
        at=bad_time,
        operation="fetch_ticker",
        error_kind="network",
        session="a",
        generation="a",
        sequence=1,
    )
    assert assess_connection(rule, event, time.time()) is None
    assert rule["operations"] == {} and "could not be trusted" in rule["tracking_note"]


def test_api_access_and_actions_leave_accounts_and_source_selection_unchanged(client):
    before = client.get("/api/v1/settings/market").json()
    rule = client.post("/api/v1/connection-alerts", json={"source": "kraken"}).json()
    for action in ("pause", "arm", "archive", "restore"):
        response = client.post(
            f"/api/v1/connection-alerts/{rule['id']}/action",
            json={"action": action, "revision": rule["revision"]},
        )
        assert response.status_code == 200
        rule = response.json()
    assert rule["status"] == "paused"
    assert client.get("/api/v1/settings/market").json() == before
    assert client.get("/api/v1/connection-alerts?offset=-1").status_code == 422
    assert client.get("/api/v1/connection-alerts?include_archived=true").json()["total"] == 1


def test_one_batch_orders_the_inbox_by_recorded_insert_order_not_random_uuids(setup):
    alerts, history, _ = setup
    watch(alerts, failures_required=1, successes_required=1)
    for kind in ["network", None, "authentication"]:
        record(history, kind)
    alerts.tick()
    page = alerts.inbox.page()
    assert [item["event_id"] for item in page["items"]] == [3, 2, 1]
    assert [item["action"] for item in page["items"]] == ["failing", "recovered", "failing"]
    alerts.inbox.mark_read(page["items"][0]["id"])
    assert alerts.inbox.page(1, 1)["items"][0]["event_id"] == 2


def test_evicted_stream_can_start_a_new_streak_without_catching_up_old_sequence(setup, monkeypatch):
    alerts, history, _ = setup
    watch(alerts, failures_required=2)
    for _ in range(8):
        record(history, None)
    record(history)
    alerts.tick()
    monkeypatch.setattr("sibyl.market_data.read_events.MAX_STREAMS", 1)
    history.record(source("kraken"), "other", 1, None, operation="fetch_ticker")
    record(history)
    due(alerts)
    alerts.tick()
    assert alerts.inbox.page()["total"] == 0
    record(history)
    due(alerts)
    alerts.tick()
    assert alerts.inbox.page()["total"] == 1
