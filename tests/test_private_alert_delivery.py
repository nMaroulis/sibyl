"""App-origin notifications over actual native clients with offline provider transports.

Only identity/send responses and SMTP servers are simulated. The real policy,
cursor, outbox, native serializers, receipt persistence and worker routing run.
"""

import asyncio
import json
import time
from datetime import UTC, datetime

import httpx
import pytest
from pydantic import ValidationError
from test_alert_delivery import inject
from test_briefing_delivery import outgoing as outgoing
from test_telegram import FakeNetwork
from test_whatsapp_email import MAIL, WA
from test_whatsapp_email import mail_servers as mail_servers

from sibyl.alerts.contracts import AlertConflict
from sibyl.alerts.delivery.contracts import DeliverySettings
from sibyl.alerts.delivery.service import AlertDelivery
from sibyl.messaging.channels.contracts import ChannelAction
from sibyl.messaging.channels.service import PrivateChannels
from sibyl.messaging.outbound import NotificationOutbox
from sibyl.messaging.review import DeliveryDecision, delivery_evidence
from sibyl.services.alerts.service import PriceAlertCreate, PriceAlerts
from sibyl.services.markets.service import Market

OWNER = "987654321012345678"
BOT = "123456789012345678"
TARGET = "456789012345678901"
ACI = "a1234567-1234-1234-1234-123456789abc"
SLACK_ID = "1799999999.1234567890123"


@pytest.fixture
async def routing(settings, store, outgoing, mail_servers):
    messaging, telegram = outgoing
    state = {"requests": [], "mode": None}

    async def transport(request):
        state["requests"].append(request)
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        is_send = request.method == "POST" and (
            "content" in body or "text" in body or body.get("method") == "send" or path.endswith("/messages")
        )
        if is_send and state["mode"]:
            return await state["mode"](request, body)
        if path == "/api/v10/users/@me":
            result = {"id": BOT, "username": "Sibyl Discord", "bot": True}
        elif path == "/api/v10/oauth2/applications/@me":
            result = {"id": BOT}
        elif path == "/api/v10/users/@me/channels":
            result = {"id": TARGET, "type": 1, "recipients": [{"id": OWNER}]}
        elif path.endswith("/messages") and request.url.host == "discord.com":
            result = {"id": "777777777777777777", "channel_id": TARGET} if request.method == "POST" else []
        elif path.endswith("/auth.test"):
            result = {
                "ok": True,
                "bot_id": "B123456789",
                "user_id": "U123456789",
                "team_id": "T123456789",
                "user": "sibyl",
            }
        elif path.endswith("/apps.connections.open"):
            result = {"ok": True, "url": "wss://wss-primary.slack.com/test-ticket"}
        elif path.endswith("/conversations.open"):
            result = {"ok": True, "channel": {"id": "D123456789"}}
        elif path.endswith("/chat.postMessage"):
            result = {"ok": True, "channel": "D123456789", "ts": SLACK_ID}
        elif path.endswith("/rpc"):
            result = {
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": [{"number": "+15551230000"}]
                if body["method"] == "listAccounts"
                else {"timestamp": 1799999999123},
            }
        elif path.endswith("/messages"):
            result = {"messages": [{"id": "wamid.accepted"}]}
        else:
            result = {"id": WA["phone_number_id"], "verified_name": "Sibyl test phone"}
        return httpx.Response(200, json=result)

    channels = PrivateChannels(
        store, FakeNetwork(), httpx.AsyncClient(transport=httpx.MockTransport(transport))
    )
    messaging.notifications.use_channels(channels)
    profiles = {
        "discord": dict(bot_token="PRIVATE-DISCORD-TOKEN", application_id=BOT, allowed_user_id=OWNER),
        "slack": dict(
            bot_token="PRIVATE-SLACK-TOKEN", app_token="PRIVATE-SLACK-APP", allowed_user_id="U987654321"
        ),
        "signal": dict(bridge_url="http://127.0.0.1:8080", account="+15551230000", allowed_sender_aci=ACI),
        "whatsapp": WA,
        "email": MAIL,
    }
    for channel, values in profiles.items():
        channels.save(channel, values)
        await channels.action(
            channel, ChannelAction(revision=channels.profile(channel)["revision"], action="enable")
        )
    channels._update("whatsapp", channels.profile("whatsapp")["revision"], last_inbound_at=time.time())
    market = Market(settings, store)
    prices = PriceAlerts(market, store)
    delivery = AlertDelivery(store, messaging)
    yield delivery, prices, channels, state, mail_servers, telegram
    delivery.close()
    prices.close()
    market.close()
    await channels.close()


def create(prices):
    return prices.create(PriceAlertCreate(source="demo", symbol="BTC/USDT", condition="above", threshold=1))


def select(service, rule, channel, **values):
    target = next(row for row in service.outbox.routes.targets()["items"] if row["channel"] == channel)
    previous = service.detail("price", rule["id"])
    return service.save(
        "price",
        rule["id"],
        DeliverySettings(
            **{
                "revision": previous["policy"]["revision"],
                "rule_revision": previous["rule"]["revision"],
                "enabled": True,
                "channel": channel,
                "private_target": target["target"] if channel != "telegram" else None,
                "telegram_target": target["target"] if channel == "telegram" else None,
                **values,
            }
        ),
    )


def receipt(service, rule):
    return service.outbox.history(kind="alert", rule_id=rule["id"])["items"][0]


async def deliver(service, channels, channel):
    async with channels.locks[channel]:
        return await service.outbox.deliver(service.outbox.routes.profile(channel), channel=channel)


@pytest.mark.parametrize("channel", ["discord", "slack", "signal", "whatsapp", "email"])
async def test_future_real_alert_uses_actual_native_serializer_and_exact_provider_id(routing, channel):
    service, prices, channels, state, mail, telegram = routing
    rule = create(prices)
    saved = select(service, rule, channel)
    assert saved["policy"]["channel"] == channel and saved["policy"]["telegram_binding"] is None
    assert prices.check(rule["id"])["status"] == "triggered"
    service.tick()
    queued = receipt(service, rule)
    assert queued["status"] == "pending" and queued["channel"] == channel
    assert not await service.outbox.deliver(
        service.messaging.settings.profile()
    )  # Telegram cannot steal another route.
    await deliver(service, channels, channel)
    await deliver(service, channels, channel)
    item = receipt(service, rule)
    assert item["status"] == "sent" and item["parts"][0]["native_id"] is None
    assert isinstance(item["parts"][0]["provider_id"], str)
    assert channels.network.calls == [] and not any(
        method == "sendMessage" for method, _ in telegram["calls"]
    )
    if channel == "slack":
        assert item["parts"][0]["provider_id"] == SLACK_ID  # No INTEGER/REAL timestamp conversion.
        body = json.loads(
            next(
                request.content
                for request in state["requests"]
                if request.url.path.endswith("chat.postMessage")
            )
        )
        assert body["mrkdwn"] is False and body["parse"] == "none" and body["channel"] == "D123456789"
    if channel == "discord":
        body = json.loads(
            next(
                request.content
                for request in state["requests"]
                if request.url.path.endswith("/messages") and request.method == "POST"
            )
        )
        assert body["allowed_mentions"] == {"parse": []}
    if channel == "email":
        assert len(mail.sent) == 1 and mail.sent[0]["To"] == MAIL["allowed_sender"]
        assert (
            mail.sent[0]["Subject"] == "Sibyl notification"
            and mail.sent[0]["Auto-Submitted"] == "auto-generated"
        )
        assert MAIL["reply_code"] not in mail.sent[0].as_string()
    assert channels.public(channel)["notifications"] == {"sent": 1}
    assert service.outbox.summary(service.messaging.settings.profile()["revision"], kind="alert") == {}
    assert delivery_evidence(service.store)["items"][0]["channel"] == channel
    public = json.dumps(service.detail("price", rule["id"]))
    for secret in [
        "PRIVATE-DISCORD-TOKEN",
        "PRIVATE-SLACK-TOKEN",
        "PRIVATE-META-TOKEN",
        MAIL["reply_code"],
        MAIL["smtp_password"],
    ]:
        assert secret not in public


async def test_save_does_not_probe_or_send_and_old_notices_never_backfill(routing):
    service, prices, channels, state, _, _ = routing
    rule = create(prices)
    prices.check(rule["id"])
    count = len(state["requests"])
    select(service, rule, "discord")
    service.tick()
    assert service.outbox.history(kind="alert")["total"] == 0 and len(state["requests"]) == count
    inject(service, rule, datetime.now(UTC))
    service.tick()
    await channels.tick("discord")  # Existing owned worker dispatches the app-origin part.
    assert receipt(service, rule)["status"] == "sent" and channels.network.calls == []


async def test_policy_switch_keeps_new_recipient_future_only_and_withdraws_old_queue(routing):
    service, prices, channels, _, _, _ = routing
    rule = create(prices)
    select(service, rule, "discord")
    old_notice = inject(service, rule, datetime.now(UTC))
    service.tick()
    old = receipt(service, rule)
    select(service, rule, "slack")
    assert service.outbox.get(old["id"])["status"] == "skipped"
    service.tick()
    assert service.outbox.history(kind="alert")["total"] == 1
    inject(service, rule, datetime.now(UTC))
    service.tick()
    await deliver(service, channels, "slack")
    assert (
        receipt(service, rule)["status"] == "sent" and receipt(service, rule)["notification_id"] != old_notice
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("revision", "f" * 32),
        ("recipient_id", "someone-else"),
        ("target_id", "another-room"),
        ("bot_id", "other-bot"),
        ("channel", "slack"),
    ],
)
async def test_stale_or_arbitrary_recipient_consent_is_rejected(routing, field, value):
    service, prices, _, _, _, _ = routing
    rule = create(prices)
    target = next(
        row["target"] for row in service.outbox.routes.targets()["items"] if row["channel"] == "discord"
    )
    target = {**target, field: value}
    with pytest.raises((AlertConflict, ValidationError), match="changed|checked private"):
        service.save(
            "price",
            rule["id"],
            DeliverySettings(rule_revision=1, enabled=True, channel="discord", private_target=target),
        )


async def test_pause_and_replacement_withdraw_old_control_and_require_current_binding(routing):
    service, prices, channels, state, _, _ = routing
    rule = create(prices)
    select(service, rule, "discord")
    inject(service, rule, datetime.now(UTC))
    service.tick()
    old = receipt(service, rule)
    profile = channels.profile("discord")
    old_target = next(
        row["target"] for row in service.outbox.routes.targets()["items"] if row["channel"] == "discord"
    )
    await channels.action("discord", ChannelAction(revision=profile["revision"], action="pause"))
    assert service.outbox.get(old["id"])["status"] == "skipped"
    channels.save(
        "discord",
        dict(bot_token="CHANGED-PRIVATE-TOKEN", application_id=BOT, allowed_user_id=OWNER),
        revision=profile["revision"],
    )
    await channels.action(
        "discord", ChannelAction(revision=channels.profile("discord")["revision"], action="enable")
    )
    current = service.detail("price", rule["id"])
    with pytest.raises(AlertConflict, match="changed"):
        service.save(
            "price",
            rule["id"],
            DeliverySettings(
                revision=current["policy"]["revision"],
                rule_revision=1,
                enabled=True,
                channel="discord",
                private_target=old_target,
            ),
        )
    inject(service, rule, datetime.now(UTC))
    service.tick()
    assert receipt(service, rule)["status"] == "skipped"
    assert not [
        row for row in state["requests"] if row.url.path.endswith("/messages") and row.method == "POST"
    ]


async def test_whatsapp_window_is_checked_at_admission_and_again_before_sending(routing):
    service, prices, channels, _, _, _ = routing
    rule = create(prices)
    select(service, rule, "whatsapp")
    profile = channels.profile("whatsapp")
    channels._update("whatsapp", profile["revision"], last_inbound_at=time.time() - 86400)
    inject(service, rule, datetime.now(UTC))
    service.tick()
    assert receipt(service, rule)["status"] == "skipped" and "reply window" in receipt(service, rule)["error"]
    select(service, rule, "whatsapp")
    channels._update("whatsapp", profile["revision"], last_inbound_at=time.time())
    inject(service, rule, datetime.now(UTC))
    service.tick()
    pending = receipt(service, rule)
    assert pending["status"] == "pending"
    channels._update("whatsapp", profile["revision"], last_inbound_at=time.time() - 86400)
    await deliver(service, channels, "whatsapp")
    assert service.outbox.get(pending["id"])["status"] == "skipped"


async def test_unknown_write_blocks_later_parts_restart_and_manual_review_do_not_retry(routing):
    service, prices, channels, state, _, _ = routing
    rule = create(prices)
    select(service, rule, "discord")
    inject(service, rule, datetime.now(UTC), label="x" * 5000)
    service.tick()

    async def timeout(request, body):
        raise httpx.ReadTimeout("Private unsafe diagnostics must not escape")

    state["mode"] = timeout
    await deliver(service, channels, "discord")
    item = receipt(service, rule)
    assert item["status"] == "uncertain" and item["parts"][1]["state"] == "blocked"
    calls = len(state["requests"])
    reviewed = service.outbox.review.get(item["id"])
    service.outbox.review.decide(
        item["id"],
        DeliveryDecision(token=reviewed["review_token"], decision="received", note="Checked private chat"),
    )
    assert service.outbox.get(item["id"])["status"] == "uncertain"
    restored = NotificationOutbox(
        service.store,
        service.messaging.settings,
        service.messaging.client,
        service.messaging._notification_error,
    )
    restored.use_channels(channels)
    restored.authorizers["alert"] = service.allowed
    assert not await restored.deliver(restored.routes.profile("discord"), channel="discord")
    assert len(state["requests"]) == calls


async def test_only_explicit_rate_rejection_retries_and_preserves_exact_chunks(routing):
    service, prices, channels, state, _, _ = routing
    rule = create(prices)
    select(service, rule, "discord")
    inject(service, rule, datetime.now(UTC), label="🪄" * 1300)
    service.tick()

    async def rejected(request, body):
        return httpx.Response(429, headers={"retry-after": "1"}, json={})

    state["mode"] = rejected
    await deliver(service, channels, "discord")
    item = receipt(service, rule)
    assert item["status"] == "retrying" and item["parts"][0]["attempts"] == 1
    assert not await deliver(
        service, channels, "discord"
    )  # Other receiver work can proceed during retry delay.
    with service.store.db() as db:
        db.execute("UPDATE message_delivery_parts SET next_attempt=0")
    state["mode"] = None
    for _ in range(item["total_parts"]):
        await deliver(service, channels, "discord")
    item = receipt(service, rule)
    assert item["status"] == "sent" and item["parts"][0]["attempts"] == 2
    assert all(part["provider_id"] for part in item["parts"])


async def test_pause_while_send_in_flight_records_admitted_acceptance_only(routing):
    service, prices, channels, state, _, _ = routing
    rule = create(prices)
    select(service, rule, "discord")
    inject(service, rule, datetime.now(UTC), label="x" * 5000)
    service.tick()
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow(request, body):
        entered.set()
        await release.wait()
        return httpx.Response(200, json={"id": "777777777777777777", "channel_id": TARGET})

    state["mode"] = slow
    work = asyncio.create_task(deliver(service, channels, "discord"))
    await entered.wait()
    profile = channels.profile("discord")
    await asyncio.wait_for(
        channels.action("discord", ChannelAction(revision=profile["revision"], action="pause")), 1
    )
    release.set()
    await work
    item = receipt(service, rule)
    assert item["status"] == "partial" and item["sent_parts"] == 1
    assert all(part["state"] == "skipped" for part in item["parts"][1:])


async def test_cancel_during_send_is_uncertain_immediately_without_late_success(routing):
    service, prices, channels, state, _, _ = routing
    rule = create(prices)
    select(service, rule, "slack")
    inject(service, rule, datetime.now(UTC))
    service.tick()
    entered = asyncio.Event()

    async def slow(request, body):
        entered.set()
        await asyncio.Event().wait()

    state["mode"] = slow
    work = asyncio.create_task(deliver(service, channels, "slack"))
    await entered.wait()
    work.cancel()
    with pytest.raises(asyncio.CancelledError):
        await work
    item = receipt(service, rule)
    assert item["status"] == "uncertain" and item["parts"][0]["provider_id"] is None
    assert not await deliver(service, channels, "slack")


async def test_pause_during_async_client_preparation_prevents_a_native_send(routing):
    service, prices, channels, state, _, _ = routing
    rule = create(prices)
    select(service, rule, "discord")
    inject(service, rule, datetime.now(UTC))
    service.tick()
    original = channels.client
    entered, release = asyncio.Event(), asyncio.Event()

    async def preparing(channel, profile):
        entered.set()
        await release.wait()
        return await original(channel, profile)

    channels.client = preparing
    work = asyncio.create_task(deliver(service, channels, "discord"))
    await entered.wait()
    profile = channels.profile("discord")
    await channels.action("discord", ChannelAction(revision=profile["revision"], action="pause"))
    release.set()
    await work
    assert not [
        row for row in state["requests"] if row.url.path.endswith("/messages") and row.method == "POST"
    ]
    assert receipt(service, rule)["status"] == "failed"


def test_http_destination_and_generic_receipt_routes_are_private_without_probes(client, monkeypatch):
    services = client.app.state.services
    monkeypatch.setattr(
        services.private_channels, "client", lambda *_: pytest.fail("Destination read probed provider")
    )
    result = client.get("/api/v1/alert-delivery/targets")
    assert result.status_code == 200 and result.headers["Cache-Control"] == "no-store"
    assert {row["channel"] for row in result.json()["items"]} == {
        "telegram",
        "discord",
        "slack",
        "signal",
        "whatsapp",
        "email",
    }
    assert all(not row["checked"] for row in result.json()["items"])
    assert client.get("/api/v1/message-deliveries/missing").status_code == 404
    areas = {row["id"]: row for row in client.get("/api/v1/roadmap").json()["areas"]}
    for channel in ("Telegram", "Discord", "Slack", "Signal", "WhatsApp", "email"):
        assert channel in areas["operations"]["working"]
    assert not any("Additional external alert channels" in item for item in areas["operations"]["pending"])


def test_full_http_policy_targets_and_private_receipt_aliases(client, monkeypatch):
    services = client.app.state.services
    private = services.private_channels
    private.save(
        "discord", dict(bot_token="PRIVATE-LOCAL-ONLY-TOKEN", application_id=BOT, allowed_user_id=OWNER)
    )
    profile = private.profile("discord")
    private._update(
        "discord",
        profile["revision"],
        verified=True,
        bot_id=BOT,
        target=TARGET,
        bot_username="Checked fixture",
    )
    monkeypatch.setattr(private, "client", lambda *_: pytest.fail("Saving a policy contacted a provider"))
    rule = services.alerts.create(
        PriceAlertCreate(source="demo", symbol="BTC/USDT", condition="above", threshold=1)
    )
    target = next(
        row["target"]
        for row in client.get("/api/v1/alert-delivery/targets").json()["items"]
        if row["channel"] == "discord"
    )
    response = client.post(
        f"/api/v1/alert-delivery/price/{rule['id']}",
        json={
            "revision": 0,
            "rule_revision": 1,
            "enabled": True,
            "channel": "discord",
            "private_target": target,
        },
    )
    assert response.status_code == 200, response.text
    assert client.get("/api/v1/alert-delivery/policies").json()[0]["channel"] == "discord"
    services.alerts.check(rule["id"])
    services.alert_delivery.tick()
    rows = client.get(f"/api/v1/alert-delivery/history?rule_id={rule['id']}").json()
    assert rows["items"][0]["channel"] == "discord" and rows["items"][0]["status"] == "skipped"
    generic = client.get("/api/v1/message-deliveries?kind=alert")
    assert generic.status_code == 200 and generic.headers["Cache-Control"] == "no-store"
    assert generic.json()["items"][0]["channel"] == "discord"
    assert client.get("/api/v1/message-deliveries?kind=reply").json()["total"] == 0
    identity = rows["items"][0]["id"]
    detail = client.get(f"/api/v1/message-deliveries/{identity}")
    assert detail.status_code == 200 and detail.headers["Cache-Control"] == "no-store"
    assert detail.json()["recipient_id"] == OWNER and "PRIVATE-LOCAL-ONLY-TOKEN" not in detail.text
    assert (
        client.post(
            f"/api/v1/message-deliveries/{identity}/review", json={"token": "a" * 64, "decision": "received"}
        ).status_code
        == 400
    )


async def test_worker_bounds_notification_burst_and_receives_without_starvation(routing):
    service, prices, channels, state, _, _ = routing
    rule = create(prices)
    select(service, rule, "discord", cooldown_seconds=60)
    # Explicitly queue six already-authorized messages to exercise burst fairness,
    # independently of the per-rule trigger cooldown.
    profile = service.outbox.routes.profile("discord")
    binding = service.detail("price", rule["id"])["policy"]["delivery_binding"]
    service.outbox.authorize = lambda _: True
    for index in range(6):
        service.outbox.enqueue_message(
            str(index),
            binding,
            "One bounded app notice",
            datetime.now(UTC),
            time.time() + 60,
            {"kind": "alert", "rule_id": rule["id"]},
            channel="discord",
        )
    start = len(state["requests"])
    for _ in range(5):
        await channels.tick("discord")
    calls = state["requests"][start:]
    assert [request.method for request in calls if request.url.path.endswith("/messages")] == [
        "POST",
        "POST",
        "POST",
        "POST",
        "GET",
    ]
    assert profile["revision"] == channels.profile("discord")["revision"]


async def test_admission_waiting_for_vault_does_not_hold_sqlite_writer(routing, monkeypatch):
    """A wrapping-key owner can enter its DB transaction while admission waits for the key."""
    import sqlite3
    import threading
    from concurrent.futures import ThreadPoolExecutor

    service, prices, _, _, _, _ = routing
    rule = create(prices)
    select(service, rule, "discord")
    inject(service, rule, datetime.now(UTC))
    original = service.outbox.routes.profile
    entered_profile = threading.Event()
    started = threading.Event()

    def profile(*args, **kwargs):
        entered_profile.set()
        return original(*args, **kwargs)

    monkeypatch.setattr(service.outbox.routes, "profile", profile)

    def admit():
        started.set()
        service.tick()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with service.store.vault.lock:
            future = pool.submit(admit)
            assert started.wait(1)
            assert not entered_profile.wait(0.05)
            with sqlite3.connect(service.store.path, timeout=0.1) as db:
                db.execute("BEGIN IMMEDIATE")
                db.rollback()
        future.result(timeout=2)
    assert receipt(service, rule)["status"] == "pending"
