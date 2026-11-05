"""Real alert transitions into the shared outbox, with HTTP restricted to a mock transport."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from test_briefing_delivery import outgoing as outgoing
from test_briefing_delivery import sends

from sibyl.alerts.contracts import AlertConflict, StrategyAlertCreate
from sibyl.alerts.delivery.contracts import DeliverySettings
from sibyl.alerts.delivery.service import AlertDelivery
from sibyl.alerts.risk.contracts import RiskAlertCreate
from sibyl.alerts.risk.service import RiskAlerts
from sibyl.models import BacktestRequest
from sibyl.services.alerts.service import PriceAlertCreate, PriceAlerts
from sibyl.services.markets.service import Market
from sibyl.strategies import Strategies


@pytest.fixture
async def delivery(settings, store, outgoing):
    messaging, state = outgoing
    market = Market(settings, store)
    prices = PriceAlerts(market, store)
    service = AlertDelivery(store, messaging)
    clock = [datetime.now(UTC)]
    service.clock = lambda: clock[0]
    yield service, prices, state, clock
    prices.close()
    market.close()


def create(prices, **values):
    return prices.create(
        PriceAlertCreate(source="demo", symbol="BTC/USDT", condition="above", threshold=1, **values)
    )


def select(service, rule, kind="price", **values):
    profile = service.messaging.settings.profile()
    previous = service.detail(kind, rule["id"])
    return service.save(
        kind,
        rule["id"],
        DeliverySettings(
            revision=previous["policy"]["revision"],
            rule_revision=previous["rule"]["revision"],
            enabled=True,
            telegram_target={"bot_id": profile["bot_id"], "user_id": profile["allowed_user_id"]},
            **values,
        ),
    )


def receipts(service, rule):
    return service.outbox.history(kind="alert", rule_id=rule["id"])["items"]


def inject(service, rule, at, *, kind="price", **values):
    """Create additional retained notices to exercise queue/cursor boundaries independently of quotes."""
    identity = uuid4().hex
    payload = {
        "kind": kind,
        "rule_id": rule["id"],
        "rule_revision": rule["revision"],
        "label": "Test trigger",
        "symbol": "BTC/USDT",
        "condition": "above",
        "threshold": 1,
        "price": 100,
        "source_label": "Sibyl Demo",
        "environment": "demo",
        "observed_at": at.isoformat(),
        **values,
    }
    with service.store.db() as db:
        db.execute(
            "INSERT INTO alert_notifications VALUES(?,?,?,?,NULL,?)",
            (identity, rule["id"], int(uuid4().hex[:12], 16), at.isoformat(), json.dumps(payload)),
        )
    return identity


async def test_real_one_shot_price_trigger_delivers_once_without_an_llm(delivery):
    service, prices, state, _ = delivery
    rule = create(prices)
    select(service, rule)
    assert sends(state) == []
    assert prices.check(rule["id"])["status"] == "triggered"
    service.tick()
    for _ in range(3):
        service.tick()
        await service.outbox.deliver(service.messaging.settings.profile())
    result = receipts(service, rule)
    assert len(result) == 1 and result[0]["status"] == "sent"
    assert "BTC/USDT" in sends(state)[0]["text"] and "demo" in sends(state)[0]["text"]
    assert service.messaging.public()["telegram"]["alerts"] == {"sent": 1}
    assert service.messaging.public()["telegram"]["briefings"] == {}
    assert prices.inbox()["unread"] == 1
    prices.mark_read()
    service.tick()
    assert len(sends(state)) == 1


async def test_opt_in_and_resume_skip_existing_notices(delivery):
    service, prices, state, clock = delivery
    rule = create(prices)
    prices.check(rule["id"])
    service.tick()
    assert receipts(service, rule) == []
    select(service, rule)
    service.tick()
    assert receipts(service, rule) == []
    paused = service.save("price", rule["id"], DeliverySettings(revision=1, rule_revision=1, enabled=False))
    inject(service, rule, clock[0])
    select(service, rule)
    service.tick()
    assert paused["policy"]["enabled"] is False and receipts(service, rule) == [] and sends(state) == []


async def test_cooldown_suppresses_instead_of_delaying_and_stale_events_never_catch_up(delivery):
    service, prices, _, clock = delivery
    rule = create(prices)
    select(service, rule, cooldown_seconds=120)
    inject(service, rule, clock[0])
    inject(service, rule, clock[0])
    service.tick()
    assert sorted(row["status"] for row in receipts(service, rule)) == ["pending", "skipped"]
    assert "cooldown" in receipts(service, rule)[0]["error"]
    clock[0] += timedelta(minutes=3)
    inject(service, rule, clock[0])
    service.tick()
    assert receipts(service, rule)[0]["status"] == "pending"
    inject(service, rule, clock[0] - timedelta(hours=1))
    service.tick()
    assert receipts(service, rule)[0]["status"] == "skipped"
    assert "stale" in receipts(service, rule)[0]["error"]


async def test_pause_rule_or_policy_fences_unsent_parts_and_preserves_inbox(delivery):
    service, prices, state, _ = delivery
    rule = create(prices, repeat="after_reset")
    select(service, rule)
    prices.check(rule["id"])
    service.tick()
    prices.change(rule["id"], "pause")
    await service.outbox.deliver(service.messaging.settings.profile())
    assert receipts(service, rule)[0]["status"] == "skipped" and sends(state) == []
    prices.change(rule["id"], "arm")
    prices.check(rule["id"])
    service.tick()
    current = service.detail("price", rule["id"])
    service.save(
        "price",
        rule["id"],
        DeliverySettings(
            revision=current["policy"]["revision"], rule_revision=current["rule"]["revision"], enabled=False
        ),
    )
    assert all(row["status"] == "skipped" for row in receipts(service, rule))
    assert prices.inbox()["total"] == 2


async def test_cursor_and_outbox_recover_atomically_and_parallel_claims_do_not_duplicate(delivery):
    service, prices, state, _ = delivery
    rule = create(prices)
    select(service, rule)
    prices.check(rule["id"])
    other = AlertDelivery(service.store, service.messaging)
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lambda instance: instance.tick(), [service, other]))
    restarted = AlertDelivery(service.store, service.messaging)
    restarted.tick()
    await restarted.outbox.deliver(service.messaging.settings.profile())
    assert len(receipts(service, rule)) == 1 and len(sends(state)) == 1


async def test_failed_cursor_transaction_cannot_leave_an_orphan_delivery(delivery, monkeypatch):
    service, prices, _, _ = delivery
    rule = create(prices)
    select(service, rule)
    prices.check(rule["id"])
    write = service._write
    monkeypatch.setattr(
        service, "_write", lambda *a: (_ for _ in ()).throw(RuntimeError("Controlled rollback"))
    )
    with pytest.raises(RuntimeError):
        service.tick()
    assert receipts(service, rule) == []
    monkeypatch.setattr(service, "_write", write)
    service.tick()
    assert len(receipts(service, rule)) == 1


async def test_current_target_and_editor_revisions_are_required(delivery):
    service, prices, _, _ = delivery
    rule = create(prices)
    with pytest.raises(AlertConflict):
        service.save(
            "price",
            rule["id"],
            DeliverySettings(rule_revision=1, enabled=True, telegram_target={"bot_id": 1, "user_id": 2}),
        )
    select(service, rule)
    with pytest.raises(AlertConflict):
        service.save("price", rule["id"], DeliverySettings(rule_revision=1, revision=0))
    prices.change(rule["id"], "pause")
    with pytest.raises(AlertConflict):
        service.save("price", rule["id"], DeliverySettings(rule_revision=1, revision=1))


async def test_paused_connection_records_skips_and_future_same_bot_rotation_works(delivery):
    service, prices, state, clock = delivery
    rule = create(prices)
    select(service, rule)
    service.messaging.pause()
    inject(service, rule, clock[0])
    service.tick()
    assert receipts(service, rule)[0]["status"] == "skipped"
    await service.messaging.enable()
    inject(service, rule, clock[0])
    service.tick()
    await service.outbox.deliver(service.messaging.settings.profile())
    assert len(sends(state)) == 1


async def test_uncertain_http_is_never_replayed_and_later_events_observe_cooldown(delivery):
    service, prices, state, clock = delivery

    async def timeout(request, body):
        raise httpx.ReadTimeout("Private failure", request=request)

    state["send"] = timeout
    rule = create(prices)
    select(service, rule)
    prices.check(rule["id"])
    service.tick()
    await service.outbox.deliver(service.messaging.settings.profile())
    assert receipts(service, rule)[0]["status"] == "uncertain"
    inject(service, rule, clock[0])
    service.tick()
    await service.outbox.deliver(service.messaging.settings.profile())
    assert len(sends(state)) == 1 and receipts(service, rule)[0]["status"] == "skipped"


async def test_real_strategy_and_account_risk_events_use_the_same_delivery_path(delivery, settings):
    service, prices, state, _ = delivery
    strategies = Strategies(prices.market, service.store)
    job = strategies.start(BacktestRequest(), source="demo")
    watched = strategies.alerts.create(StrategyAlertCreate(job_id=job["id"]))
    select(service, watched, "strategy")
    saved = strategies.journal.job(job["id"])
    saved["status"] = "paused"
    strategies.journal.save(saved, strategies._event(saved, "PAUSE", "Controlled strategy event"))
    strategies.alerts.tick()
    service.tick()
    await service.outbox.deliver(service.messaging.settings.profile())
    risk = RiskAlerts(prices.market, service.store)
    rule = risk.create(
        RiskAlertCreate(account_ids=["demo"], source="demo", metric="value_floor", threshold=1e9)
    )
    select(service, rule, "risk")
    risk.tick()
    service.tick()
    await service.outbox.deliver(service.messaging.settings.profile())
    assert len(sends(state)) == 2
    assert "paper" in sends(state)[0]["text"] and "Account value floor" in sends(state)[1]["text"]


def test_api_defaults_validation_privacy_and_history_filtering(client):
    rule = client.post(
        "/api/v1/alerts",
        json={"source": "demo", "symbol": "BTC/USDT", "condition": "above", "threshold": 1e9},
    ).json()
    url = f"/api/v1/alert-delivery/price/{rule['id']}"
    default = client.get(url)
    assert default.status_code == 200 and default.headers["cache-control"] == "no-store"
    assert default.json()["policy"]["enabled"] is False
    assert client.post(url, json={"rule_revision": 1, "enabled": True}).status_code == 422
    assert client.post(url, json={"rule_revision": 1, "cooldown_seconds": False}).status_code == 422
    assert (
        client.post(
            url, json={"rule_revision": 1, "enabled": True, "telegram_target": {"bot_id": 1, "user_id": 2}}
        ).status_code
        == 409
    )
    assert client.get("/api/v1/alert-delivery/history?limit=51").status_code == 422
    assert client.get(f"/api/v1/alert-delivery/history?rule_id={rule['id']}").json()["items"] == []
    assert client.get("/api/v1/alert-delivery/unknown/id").status_code == 422
    assert client.get("/api/v1/alert-delivery/price/missing").status_code == 404


async def test_real_connection_incident_can_deliver_without_any_extra_provider_read(delivery):
    from types import SimpleNamespace

    from test_connection_alerts import source

    from sibyl.alerts.connections import ConnectionAlerts
    from sibyl.alerts.contracts import ConnectionAlertCreate
    from sibyl.market_data.health_history import ProviderHistory

    service, _, state, _ = delivery
    history = ProviderHistory(service.store)
    alerts = ConnectionAlerts(
        SimpleNamespace(read_history=history, provider_health=lambda: {"items": [source()]}), service.store
    )
    rule = alerts.create(ConnectionAlertCreate(source="binance", failures_required=1))
    select(service, rule, "connection")
    history.record(source(), "profile", 10, "network", operation="fetch_ticker")
    alerts.tick()
    service.tick()
    await service.outbox.deliver(service.messaging.settings.profile())
    assert len(sends(state)) == 1
    assert "Read failures observed" in sends(state)[0]["text"]
    assert "production" in sends(state)[0]["text"]


@pytest.mark.parametrize("age", [timedelta(hours=1), timedelta(seconds=-61)])
async def test_fresh_receipt_cannot_hide_an_old_or_future_observation(delivery, age):
    service, prices, state, clock = delivery
    rule = create(prices)
    select(service, rule)
    inject(service, rule, clock[0], observed_at=(clock[0] - age).isoformat())
    service.tick()
    assert receipts(service, rule)[0]["status"] == "skipped"
    assert sends(state) == []


async def test_recipient_change_cannot_redirect_messages_without_explicit_policy_review(delivery):
    from sibyl.messaging.settings import TelegramSettingsRequest

    service, prices, state, clock = delivery
    rule = create(prices)
    select(service, rule)
    service.messaging.pause()
    service.messaging.save(TelegramSettingsRequest(allowed_user_id=555666777))
    await service.messaging.enable()
    inject(service, rule, clock[0])
    service.tick()
    assert receipts(service, rule)[0]["status"] == "skipped" and sends(state) == []
    select(service, rule)
    inject(service, rule, clock[0])
    service.tick()
    await service.outbox.deliver(service.messaging.settings.profile())
    assert len(sends(state)) == 1 and sends(state)[0]["chat_id"] == 555666777


async def test_expiry_is_checked_again_after_queueing(delivery):
    service, prices, state, clock = delivery
    rule = create(prices)
    select(service, rule, expiry_seconds=60)
    inject(service, rule, clock[0])
    service.tick()
    with service.store.db() as db:
        row = db.execute("SELECT id,payload FROM message_deliveries").fetchone()
        item = json.loads(row["payload"])
        item["expires_at"] = 1
        db.execute("UPDATE message_deliveries SET payload=? WHERE id=?", (json.dumps(item), row["id"]))
    await service.outbox.deliver(service.messaging.settings.profile())
    assert receipts(service, rule)[0]["status"] == "skipped" and sends(state) == []


async def test_shutdown_stops_future_admission_without_losing_trigger_evidence(delivery):
    service, prices, state, _ = delivery
    rule = create(prices)
    select(service, rule)
    prices.check(rule["id"])
    service.close()
    service.tick()
    assert receipts(service, rule) == [] and prices.inbox()["total"] == 1
    assert sends(state) == []


async def test_outbound_bursts_cannot_starve_incoming_telegram_polls(outgoing):
    from test_briefing_delivery import queue

    messaging, state = outgoing
    messaging.notifications.authorize = lambda receipt: True
    queue(messaging, text="x" * 12000)
    queue(messaging, text="y" * 12000)
    for _ in range(5):
        await messaging.tick()
    assert len(sends(state)) == 4
    polls = [payload for method, payload in state["calls"] if method == "getUpdates"]
    assert len(polls) == 1 and polls[0]["timeout"] == 0
    await messaging.tick()
    assert len(sends(state)) == 5
