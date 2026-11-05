"""Atomic execution receipts, future-only cursors and existing Telegram delivery admission."""

import json
from datetime import UTC, datetime

import pytest
from test_alert_delivery import delivery as delivery
from test_alert_delivery import outgoing as outgoing

from sibyl.alerts.contracts import AlertAction, AlertConflict
from sibyl.alerts.orders.service import OrderAlertCreate, OrderAlerts, OrderAlertUpdate
from sibyl.services.accounts.ledger import AccountLedger, ledger_fill
from sibyl.services.trading.lifecycle import OrderLifecycle


@pytest.fixture
def execution(client):
    services = client.app.state.services
    services.trading.alerts.close()
    alerts = OrderAlerts(services.store)
    order = dict(
        id="1" * 32,
        exchange="demo",
        environment="demo",
        status="open",
        filled=0,
        request=dict(connection_id="demo", symbol="BTC/USDT", side="buy", quantity=1),
        exchange_order_id="native",
        created_at=datetime.now(UTC).isoformat(),
    )
    with services.store.db() as db:
        db.execute("INSERT INTO exchange_orders VALUES(?,?,?)", (order["id"], "KEY", json.dumps(order)))
    return services, alerts, order


def update(services, order, **values):
    result = {**order, **values}
    with services.store.db() as db:
        OrderLifecycle.write(db, result)
    return result


def inbox(alerts):
    return [row for row in alerts.inbox.page()["items"] if row["kind"] == "order"]


def test_partial_fill_cancel_and_idempotent_order_observations(execution):
    services, alerts, order = execution
    alerts.create(OrderAlertCreate(account_id="demo"))
    partial = update(services, order, filled=0.2)
    alerts.tick()
    rows = inbox(alerts)
    assert len(rows) == 1 and rows[0]["action"] == "partial_fill" and rows[0]["filled"] == 0.2
    update(services, partial)
    alerts.tick()
    assert len(inbox(alerts)) == 1
    update(services, partial, status="canceled")
    alerts.tick()
    assert len(inbox(alerts)) == 2 and inbox(alerts)[0]["action"] == "canceled"
    assert inbox(alerts)[0]["account_id"] == "demo" and inbox(alerts)[0]["environment"] == "demo"


def test_historical_fills_and_fee_corrections_are_explicit_and_atomic(execution):
    services, alerts, order = execution
    alerts.create(OrderAlertCreate(account_id="demo"))
    row = ledger_fill(
        {
            "id": "fill1",
            "order": "native",
            "symbol": "BTC/USDT",
            "side": "buy",
            "timestamp": 1700000000000,
            "amount": 0.2,
            "price": 100,
            "fees": [{"currency": "USDT", "cost": 0.01}],
        },
        {
            "account_id": "demo",
            "account": "Demo",
            "exchange": "demo",
            "environment": "demo",
            "symbol": "BTC/USDT",
        },
    )
    with services.store.db() as db:
        AccountLedger.upsert_fills(db, [row], datetime.now(UTC).isoformat())
    alerts.tick()
    assert inbox(alerts)[0]["action"] == "fill_imported" and inbox(alerts)[0]["execution_at"] == 1700000000000
    with services.store.db() as db:
        AccountLedger.upsert_fills(db, [row], datetime.now(UTC).isoformat())
    alerts.tick()
    assert len(inbox(alerts)) == 1
    corrected = {**row, "fees": [{"currency": "USDT", "cost": 0.02}]}
    with services.store.db() as db:
        AccountLedger.upsert_fills(db, [corrected], datetime.now(UTC).isoformat())
    alerts.tick()
    assert inbox(alerts)[0]["action"] == "fill_corrected" and len(inbox(alerts)) == 2
    displayed = {**corrected, "account": "Renamed Demo"}
    with services.store.db() as db:
        AccountLedger.upsert_fills(db, [displayed], datetime.now(UTC).isoformat())
    alerts.tick()
    assert len(inbox(alerts)) == 2
    with pytest.raises(RuntimeError), services.store.db() as db:
        AccountLedger.upsert_fills(db, [{**row, "price": 101}], datetime.now(UTC).isoformat())
        raise RuntimeError("rollback")
    alerts.tick()
    assert len(inbox(alerts)) == 2


def test_future_only_resume_restart_and_stale_edits(execution):
    services, alerts, order = execution
    partial = update(services, order, filled=0.1)
    rule = alerts.create(OrderAlertCreate(account_id="demo"))
    alerts.tick()
    assert not inbox(alerts)
    rule = alerts.change(rule["id"], AlertAction(revision=rule["revision"], action="pause"))
    partial = update(services, partial, filled=0.2)
    rule = alerts.change(rule["id"], AlertAction(revision=rule["revision"], action="arm"))
    alerts.tick()
    assert not inbox(alerts)
    partial = update(services, partial, filled=0.3)
    reopened = OrderAlerts(services.store)
    reopened.tick()
    assert len(inbox(alerts)) == 1
    reopened.tick()
    assert len(inbox(alerts)) == 1
    with pytest.raises(AlertConflict):
        alerts.edit(rule["id"], OrderAlertUpdate(account_id="demo", revision=1))


def test_native_status_only_and_account_scope_do_not_broaden(execution):
    services, alerts, order = execution
    alerts.create(OrderAlertCreate(account_id="demo", events=["attention"]))
    update(services, order, filled=0.2)
    alerts.tick()
    assert not inbox(alerts)
    update(services, order, status="unknown")
    alerts.tick()
    assert len(inbox(alerts)) == 1
    assert "credentials" not in str(inbox(alerts)) and "api_key" not in str(inbox(alerts))


def test_http_rule_revision_and_delivery_kind(execution, client):
    services, alerts, order = execution
    response = client.post("/api/v1/order-alerts", json={"account_id": "demo"})
    assert response.status_code == 201 and response.headers["Cache-Control"] == "no-store"
    rule = response.json()
    assert client.get(f"/api/v1/alert-delivery/order/{rule['id']}").status_code == 200
    assert (
        client.post(
            f"/api/v1/order-alerts/{rule['id']}/action", json={"revision": True, "action": "pause"}
        ).status_code
        == 422
    )
    assert client.post("/api/v1/order-alerts", json={"account_id": "demo"}).status_code == 409


def test_retention_gap_pauses_subscription_instead_of_skipping_evidence(execution):
    services, alerts, order = execution
    alerts.create(OrderAlertCreate(account_id="demo"))
    with services.store.db() as db:
        db.execute("INSERT INTO execution_events(id,account_id,payload) VALUES(100001,'demo','{}')")
    alerts.tick()
    saved = alerts.rules()["items"][0]
    assert saved["status"] == "paused" and "retention" in saved["error"].lower()
    assert not inbox(alerts)


async def test_execution_notice_uses_existing_mock_telegram_delivery(delivery):
    from test_alert_delivery import select
    from test_briefing_delivery import sends

    from sibyl.alerts.orders.events import order_changed

    service, prices, state, clock = delivery
    alerts = OrderAlerts(service.store)
    rule = alerts.create(OrderAlertCreate(account_id="demo"))
    select(service, rule, kind="order")
    order = dict(
        id="9" * 32,
        request=dict(connection_id="demo", symbol="BTC/USDT", side="buy", quantity=1),
        status="open",
        filled=0.2,
        exchange="demo",
        exchange_order_id="mock-native",
    )
    with service.store.db() as db:
        order_changed(db, {**order, "filled": 0}, order)
    alerts.tick()
    service.tick()
    await service.outbox.deliver(service.messaging.settings.profile())
    assert len(sends(state)) == 1
    assert "partial fill" in sends(state)[0]["text"]
    assert "demo" in sends(state)[0]["text"]
    service.tick()
    await service.outbox.deliver(service.messaging.settings.profile())
    assert len(sends(state)) == 1
