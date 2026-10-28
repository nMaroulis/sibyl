"""Journal-only alert subscriptions: atomic evidence, lifecycle races and restart cursors."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from protolink import Task
from pydantic import ValidationError

from sibyl.alerts.contracts import (
    AlertConflict,
    StrategyAlertAction,
    StrategyAlertCreate,
    StrategyAlertUpdate,
)
from sibyl.alerts.strategies import StrategyAlerts, event_kind, strategy_alert_example
from sibyl.models import BacktestRequest
from sibyl.services.market import Market
from sibyl.strategies import Strategies


@pytest.fixture
def setup(settings, store):
    strategies = Strategies(Market(settings, store), store)
    job = strategies.start(BacktestRequest(), source="demo")
    return strategies, strategies.alerts, job


def watch(alerts, job, **values):
    return alerts.create(StrategyAlertCreate(job_id=job["id"], **values))


def fire(strategies, job, action="PAUSE", state="paused", reason="Evaluation paused."):
    current = strategies.journal.job(job["id"])
    current["status"] = state
    strategies.journal.save(current, strategies._event(current, action, reason))


def due(alerts, rule):
    with alerts.store.db() as db:
        current = alerts._read(db, rule["id"])
        current["next_check"] = 0
        alerts._write(db, current)


def current(alerts, rule):
    with alerts.store.db() as db:
        return alerts._read(db, rule["id"])


def change(alerts, rule, action):
    return alerts.change(
        rule["id"], StrategyAlertAction(action=action, revision=current(alerts, rule)["revision"])
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"job_id": "../../bad"},
        {"events": []},
        {"events": ["fills"]},
        {"events": ["attention", "attention"]},
        {"label": "bad\nname"},
        {"threshold": 1},
        {"recipient": "a@example.com"},
        {"execute": True},
    ],
)
def test_subscription_accepts_no_execution_or_delivery_fields(changes):
    with pytest.raises(ValidationError):
        StrategyAlertCreate(**{"job_id": "a" * 32, **changes})


def test_create_and_reads_are_local_and_skip_existing_events(setup, monkeypatch):
    strategies, alerts, job = setup
    fire(strategies, job)
    monkeypatch.setattr(strategies.market, "client", lambda *a: pytest.fail("Provider read"))
    before = strategies.journal.job(job["id"])
    rule = watch(alerts, job)
    assert rule["status"] == "armed" and rule["cursor"] > 0
    assert alerts.rules()["count"] == 1
    alerts.tick()
    assert alerts.inbox.page()["total"] == 0
    assert strategies.journal.job(job["id"]) == before
    assert alerts.rules(job_id="b" * 32)["items"] == []
    with pytest.raises(LookupError):
        alerts.create(StrategyAlertCreate(job_id="b" * 32))


def test_attention_events_notify_once_with_original_evidence(setup):
    strategies, alerts, job = setup
    rule = watch(alerts, job, label=" My run ")
    fire(strategies, job, "ERROR", "running", "Evaluation failed. Check source.")
    alerts.tick()
    item = alerts.inbox.page()["items"][0]
    assert item["kind"] == "strategy" and item["action"] == "ERROR"
    assert item["job_id"] == job["id"] and item["environment"] == "demo"
    assert item["mode"] == "paper" and item["label"] == "My run"
    assert item["rule_revision"] == 1 and item["cycle"] == item["event_id"]
    assert item["reason"] == "Evaluation failed. Check source."
    assert item["job_status"] == "running"
    assert item["read_at"] is None
    due(alerts, rule)
    alerts.tick()
    assert alerts.inbox.page()["total"] == 1
    assert current(alerts, rule)["notifications"] == 1


@pytest.mark.parametrize(
    "action,group",
    [
        ("PAUSE", "attention"),
        ("ERROR", "attention"),
        ("RECOVERED", "attention"),
        ("RESUME", "lifecycle"),
        ("STOP", "lifecycle"),
        ("STOP_CANCEL", "lifecycle"),
    ],
)
def test_explicit_category_filters(setup, action, group):
    strategies, alerts, job = setup
    watch(alerts, job, events=[group])
    fire(strategies, job, "HOLD", "running")
    fire(strategies, job, "BUY", "running")
    fire(strategies, job, action, "paused" if action == "PAUSE" else "running")
    alerts.tick()
    items = alerts.inbox.page()["items"]
    assert len(items) == 1 and items[0]["action"] == action
    assert items[0]["group"] == group


def test_completion_is_a_state_transition_even_when_last_action_is_sell(setup):
    strategies, alerts, job = setup
    rule = watch(alerts, job, events=["lifecycle"])
    fire(strategies, job, "SELL", "completed", "Round-trip limit reached; run completed.")
    fire(strategies, job, "SELL", "completed", "A later execution observation.")
    alerts.tick()
    items = alerts.inbox.page()["items"]
    assert len(items) == 1 and items[0]["action"] == "COMPLETED"
    assert items[0]["journal_action"] == "SELL"
    assert current(alerts, rule)["last_status"] == "completed"


def test_pause_resume_and_edit_do_not_replay_unwatched_events(setup):
    strategies, alerts, job = setup
    rule = watch(alerts, job, events=["attention", "lifecycle"])
    fire(strategies, job)
    change(alerts, rule, "pause")
    alerts.tick()
    assert alerts.inbox.page()["total"] == 0
    change(alerts, rule, "arm")
    alerts.tick()
    assert alerts.inbox.page()["total"] == 0
    fire(strategies, job, "RESUME", "running")
    due(alerts, rule)
    alerts.tick()
    old = alerts.inbox.page()["items"][0]
    edited = alerts.edit(
        rule["id"],
        StrategyAlertUpdate(job_id=job["id"], events=["attention"], label="New name", revision=1 + 2),
    )
    assert edited["status"] == "paused"
    assert alerts.inbox.page()["items"][0] == old
    fire(strategies, job)
    change(alerts, rule, "arm")
    alerts.tick()
    assert alerts.inbox.page()["total"] == 1
    fire(strategies, job, "ERROR", "paused", "Different error.")
    due(alerts, rule)
    alerts.tick()
    newest = alerts.inbox.page()["items"][0]
    assert newest["label"] == "New name" and newest["rule_revision"] > old["rule_revision"]


def test_restart_catches_up_armed_rule_without_duplicates(setup):
    strategies, alerts, job = setup
    rule = watch(alerts, job)
    fire(strategies, job)
    restarted = StrategyAlerts(alerts.store)
    restarted.tick()
    assert restarted.inbox.page()["total"] == 1
    fire(strategies, job, "RECOVERED", "running")
    due(restarted, rule)
    StrategyAlerts(alerts.store).tick()
    assert restarted.inbox.page()["total"] == 2
    due(restarted, rule)
    StrategyAlerts(alerts.store).tick()
    assert restarted.inbox.page()["total"] == 2


def test_cursor_and_notifications_rollback_together(setup, monkeypatch):
    strategies, alerts, job = setup
    rule = watch(alerts, job)
    fire(strategies, job)
    original = alerts._write
    monkeypatch.setattr(
        alerts, "_write", lambda *a: (_ for _ in ()).throw(RuntimeError("crash before commit"))
    )
    with pytest.raises(RuntimeError):
        alerts.tick()
    assert alerts.inbox.page()["total"] == 0
    assert current(alerts, rule)["cursor"] == rule["cursor"]
    monkeypatch.setattr(alerts, "_write", original)
    alerts.tick()
    assert alerts.inbox.page()["total"] == 1


def test_two_consumers_serialize_and_cannot_duplicate_a_notification(setup):
    strategies, alerts, job = setup
    rule = watch(alerts, job)
    fire(strategies, job)
    other = StrategyAlerts(alerts.store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda service: service.tick(), [alerts, other]))
    assert alerts.inbox.page()["total"] == 1
    assert current(alerts, rule)["notifications"] == 1


def test_bounded_backlog_preserves_unmatched_and_matching_cursor_progress(setup):
    strategies, alerts, job = setup
    rule = watch(alerts, job)
    for _ in range(105):
        fire(strategies, job, "HOLD", "running")
    fire(strategies, job)
    alerts.tick()
    assert current(alerts, rule)["cursor"] == rule["cursor"] + 100
    assert alerts.inbox.page()["total"] == 0
    alerts.tick()
    assert current(alerts, rule)["cursor"] == rule["cursor"] + 106
    assert alerts.inbox.page()["total"] == 1


def test_archived_rules_restore_paused_and_cannot_duplicate_existing_subscription(setup):
    strategies, alerts, job = setup
    rule = watch(alerts, job)
    with pytest.raises(AlertConflict):
        watch(alerts, job)
    change(alerts, rule, "archive")
    assert alerts.rules()["total"] == 0
    assert alerts.rules(True)["items"][0]["status"] == "archived"
    replacement = watch(alerts, job)
    with pytest.raises(AlertConflict):
        change(alerts, rule, "restore")
    change(alerts, replacement, "archive")
    assert change(alerts, rule, "restore")["status"] == "paused"
    with pytest.raises(AlertConflict):
        alerts.change(rule["id"], StrategyAlertAction(action="arm", revision=1))


def test_capacity_pagination_and_cross_rule_revision_safety(setup):
    strategies, alerts, job = setup
    first = watch(alerts, job)
    second_job = strategies.start(BacktestRequest(), source="demo")
    second = watch(alerts, second_job)
    with pytest.raises(AlertConflict):
        alerts.edit(first["id"], StrategyAlertUpdate(job_id=second_job["id"], revision=1))
    change(alerts, second, "archive")
    assert alerts.rules(True, 1)["items"][0]["id"] == first["id"]
    assert alerts.rules(job_id=job["id"])["total"] == 1
    alerts.limit = 1
    with pytest.raises(ValueError, match="at most"):
        watch(alerts, second_job)
    assert alerts.rules()["count"] == 1


def test_shared_inbox_acknowledgment_and_legacy_price_rows(setup):
    strategies, alerts, job = setup
    watch(alerts, job)
    fire(strategies, job)
    alerts.tick()
    with alerts.store.db() as db:
        db.execute(
            "INSERT INTO alert_notifications VALUES(?,?,?,?,NULL,?)",
            ("old", "old-rule", 1, "2026-01-01", json.dumps({"symbol": "BTC/USDT"})),
        )
    assert {row["kind"] for row in alerts.inbox.page()["items"]} == {"price", "strategy"}
    item = alerts.inbox.page()["items"][0]
    alerts.inbox.mark_read(item["id"])
    first_read = alerts.inbox.page()["items"][0]["read_at"]
    alerts.inbox.mark_read(item["id"])
    assert alerts.inbox.page()["items"][0]["read_at"] == first_read
    assert alerts.inbox.page()["unread"] == 1
    alerts.inbox.mark_read()
    assert alerts.inbox.page()["unread"] == 0
    assert alerts.inbox.page()["total"] == 2


def test_closed_worker_and_examples_have_no_effect(setup):
    strategies, alerts, job = setup
    watch(alerts, job)
    fire(strategies, job)
    alerts.close()
    alerts.tick()
    assert alerts.inbox.page()["total"] == 0
    example = strategy_alert_example()
    assert example["inbox"]["items"][0]["kind"] == "strategy"
    assert alerts.rules()["count"] == 1
    assert event_kind({"action": "UNKNOWN"}, "running")[0] is None


def test_http_contract_and_broker_evidence_use_real_local_journal(client):
    strategies = client.app.state.services.strategies
    job = strategies.start(BacktestRequest(), source="demo")
    response = client.post("/api/v1/strategy-alerts", json={"job_id": job["id"], "events": ["attention"]})
    assert response.status_code == 201 and response.headers["cache-control"] == "no-store"
    rule = response.json()
    assert client.post("/api/v1/strategy-alerts", json={"job_id": job["id"]}).status_code == 409
    strategies.status(job["id"], "paused")
    # The lifespan worker may have checked the empty stream and scheduled five seconds ahead.
    # Make this explicit check due instead of racing the real polling clock in CI.
    due(strategies.alerts, rule)
    strategies.alerts.tick()
    inbox = client.get("/api/v1/notifications").json()
    assert len(inbox["items"]) == 1 and inbox["items"][0]["kind"] == "strategy"
    assert inbox["items"][0]["job_id"] == job["id"]
    listing = client.get(f"/api/v1/strategy-alerts?job_id={job['id']}")
    assert listing.status_code == 200 and listing.json()["total"] == 1
    assert (
        client.post(
            f"/api/v1/strategy-alerts/{rule['id']}/action", json={"action": "pause", "revision": 99}
        ).status_code
        == 409
    )
    assert (
        client.get("/api/v1/strategy-alerts/example").json()["rules"]["items"][0]["job_id"] == "example-run"
    )
    network = client.app.state.services.agents.network
    result = client.portal.call(
        network.client.send_task,
        network.cards["broker"].url,
        Task.create_tool_call("strategy_alerts", {"job_id": job["id"]}),
    )
    result.raise_for_status()
    evidence = result.get_last_item().parts[-1].as_tool_output().result
    assert evidence["rules"]["items"][0]["id"] == rule["id"]
    assert evidence["recent_notifications"][0]["job_id"] == job["id"]
    assert strategies.journal.job(job["id"])["status"] == "paused"


def test_real_paper_round_trip_completion_reaches_the_inbox(setup, monkeypatch):
    import pandas as pd

    strategies, alerts, _ = setup
    # Use two actual closed Demo intervals. Only signal choice/quote values are controlled.
    history = strategies.market.candles(limit=100)
    visible, direction, price = [history[:-1]], [1], [100]
    monkeypatch.setattr(strategies.market, "candles", lambda *a: visible[0])
    monkeypatch.setattr(strategies.market, "price", lambda *a: price[0])
    monkeypatch.setattr(
        "sibyl.strategies.paper.signals", lambda frame, *a: pd.Series([direction[0]] * len(frame))
    )
    job = strategies.start(BacktestRequest(max_trades=1), source="demo")
    watch(alerts, job, events=["lifecycle"])
    strategies.tick()
    assert strategies.journal.job(job["id"])["quantity"] > 0
    visible[0], direction[0], price[0] = history, -1, 120
    strategies.tick()
    assert strategies.journal.job(job["id"])["status"] == "completed"
    alerts.tick()
    items = alerts.inbox.page()["items"]
    assert len(items) == 1 and items[0]["action"] == "COMPLETED"
    assert items[0]["journal_action"] == "SELL"


def test_exchange_test_attribution_copies_only_allowlisted_metadata(setup):
    strategies, alerts, job = setup
    job.update(
        mode="exchange",
        environment="test",
        source="connection:test-account",
        account="Test desk",
        credentials={"apiKey": "PRIVATE-KEY"},
    )
    strategies.journal.save(job)
    watch(alerts, job)
    fire(strategies, job, "PAUSE", "paused", "Safety pause on restart.")
    alerts.tick()
    item = alerts.inbox.page()["items"][0]
    assert item["mode"] == "exchange" and item["environment"] == "test"
    assert item["account"] == "Test desk"
    assert "PRIVATE-KEY" not in json.dumps(alerts.rules()) + json.dumps(item)
    assert "cash" not in item and "quantity" not in item
