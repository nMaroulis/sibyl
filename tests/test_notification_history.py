"""Retention is opt-in and must preserve inbox delivery cursors and unfinished evidence."""

import csv
import io
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from sibyl.alerts.history.contracts import RetentionPolicy
from sibyl.alerts.history.service import csv_document
from sibyl.alerts.inbox import NotificationInbox


def notice(store, *, read=True, age=100, rule="rule", kind="price", symbol="BTC/USDT"):
    identity = uuid4().hex
    at = (datetime.now(UTC) - timedelta(days=age)).isoformat()
    with store.db() as db:
        db.execute(
            "INSERT INTO alert_notifications(id,rule_id,cycle,created_at,read_at,payload) VALUES(?,?,?,?,?,?)",
            (
                identity,
                rule,
                int(identity[:10], 16),
                at,
                at if read else None,
                json.dumps({"kind": kind, "symbol": symbol}),
            ),
        )
        sequence = db.execute("SELECT rowid FROM alert_notifications WHERE id=?", (identity,)).fetchone()[0]
    return identity, sequence


def test_legacy_upgrade_preserves_rowids_and_never_reuses_deleted_sequence(store):
    with store.db() as db:
        db.execute(
            "CREATE TABLE alert_notifications(id TEXT PRIMARY KEY,rule_id TEXT,cycle INTEGER,created_at TEXT,read_at TEXT,payload TEXT,UNIQUE(rule_id,cycle))"
        )
        db.execute("INSERT INTO alert_notifications VALUES('old','rule',1,'2020-01-01','2020-01-01','{}')")
    inbox = NotificationInbox(store)
    assert inbox.page()["items"][0]["id"] == "old"
    with store.db() as db:
        assert db.execute("SELECT sequence FROM alert_notifications").fetchone()[0] == 1
    assert inbox.history.clear(0)["result"]["deleted"] == 1
    assert notice(store)[1] == 2
    NotificationInbox(store)  # upgrade/restart is idempotent
    assert notice(store)[1] == 3


def test_cleanup_off_by_default_bounded_and_protects_unread_and_young(store):
    history = NotificationInbox(store).history
    for _ in range(502):
        notice(store)
    unread = notice(store, read=False)[0]
    young = notice(store, age=1)[0]
    history.tick()
    assert history.status()["preview"]["eligible"] == 502
    first = history.clear(0)["result"]
    assert first["deleted"] == 500 and first["remaining_eligible"] == 2
    history.clear(0)
    assert {item["id"] for item in history.export()["items"]} == {unread, young}
    assert len(history.status()["runs"]) == 2
    history.save(RetentionPolicy(enabled=True, days=7, revision=0))
    with pytest.raises(ValueError, match="changed"):
        history.clear(0)
    with pytest.raises(ValueError, match="changed"):
        history.save(RetentionPolicy(enabled=False, revision=0))


def test_retention_protects_unfinished_delivery_and_unprocessed_enabled_cursor(store):
    inbox = NotificationInbox(store)
    first, cursor = notice(store, rule="one")
    queued, _ = notice(store, rule="two")
    completed, _ = notice(store, rule="three")
    with store.db() as db:
        db.execute("CREATE TABLE alert_delivery_policies(rule_id TEXT,enabled INTEGER,cursor INTEGER)")
        db.execute("INSERT INTO alert_delivery_policies VALUES(?,?,?)", ("one", 1, cursor - 1))
        db.execute("CREATE TABLE message_deliveries(state TEXT,payload TEXT)")
        db.executemany(
            "INSERT INTO message_deliveries VALUES(?,?)",
            [
                ("uncertain", json.dumps({"notification_id": queued})),
                ("sent", json.dumps({"notification_id": completed})),
            ],
        )
    state = inbox.history.clear(0)
    assert state["result"]["deleted"] == 1 and state["preview"]["delivery_protected"] == 2
    assert {item["id"] for item in inbox.page()["items"]} == {first, queued}
    with store.db() as db:
        db.execute("UPDATE alert_delivery_policies SET cursor=?", (cursor,))
        db.execute("UPDATE message_deliveries SET state='failed'")
    assert inbox.history.clear(0)["result"]["deleted"] == 2


def test_history_export_filters_bounds_formula_safety_and_does_not_acknowledge(client):
    history = client.app.state.services.alerts._inbox.history
    notice(history.store, kind="order", read=False, symbol="=UNTRUSTED()")
    notice(history.store, kind="risk")
    response = client.get("/api/v1/notifications/export?kind=order")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    document = response.json()
    assert document["total"] == 1 and document["items"][0]["read_at"] is None
    rows = list(csv.reader(io.StringIO(csv_document(document))))
    assert rows[1][5] == "'=UNTRUSTED()"
    assert client.get("/api/v1/notifications/export?start=2020-01-01").status_code == 400
    assert (
        client.get(
            "/api/v1/notifications/export?start=2026-01-01T00:00:00Z&end=2025-01-01T00:00:00Z"
        ).status_code
        == 400
    )
    state = client.get("/api/v1/notifications/retention").json()
    assert state["policy"]["enabled"] is False
    assert (
        client.post(
            "/api/v1/notifications/retention", json={"enabled": True, "days": 90, "revision": 0}
        ).status_code
        == 200
    )
    assert client.post("/api/v1/notifications/retention/clear", json={"revision": 0}).status_code == 400


def test_auto_cleanup_runs_only_when_due_and_export_reports_truncation(store, monkeypatch):
    inbox = NotificationInbox(store)
    history = inbox.history
    now = datetime.now(UTC)
    history.clock = lambda: now
    notice(store)
    history.save(RetentionPolicy(enabled=True, days=90, revision=0))
    history.tick()
    assert inbox.page()["total"] == 0
    assert len(history.status()["runs"]) == 1
    history.tick()
    assert len(history.status()["runs"]) == 1
    notice(store, kind="order")
    notice(store, kind="risk")
    monkeypatch.setattr("sibyl.alerts.history.service.MAX_EXPORT", 1)
    exported = history.export()
    assert exported["truncated"] and exported["total"] == 2 and exported["exported"] == 1
    history.close()
    with pytest.raises(ValueError, match="shutting down"):
        history.clear(1)
