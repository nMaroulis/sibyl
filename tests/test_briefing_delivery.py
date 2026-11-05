"""Mock-HTTP Telegram briefing delivery, with no real bot or private destination."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from sibyl.messaging.outbound import NotificationOutbox, chunks
from sibyl.messaging.service import TelegramService
from sibyl.messaging.settings import TelegramSettingsRequest

TOKEN = "123456789:" + "b" * 35
USER = 765432123


class UnusedNetwork:
    def status(self):
        return {"ready": False}


@pytest.fixture
async def outgoing(store):
    state = {"calls": [], "send": None, "bot_id": 12345}

    async def transport(request):
        method = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content)
        state["calls"].append((method, body))
        if method == "sendMessage" and state["send"]:
            return await state["send"](request, body)
        result = {
            "getMe": {"id": state["bot_id"], "is_bot": True, "username": "briefing_test_bot"},
            "getWebhookInfo": {"url": ""},
            "getUpdates": [],
            "sendMessage": {"message_id": len(state["calls"]) + 10},
        }[method]
        return httpx.Response(200, json={"ok": True, "result": result})

    service = TelegramService(
        store, UnusedNetwork(), httpx.AsyncClient(transport=httpx.MockTransport(transport))
    )
    service.save(TelegramSettingsRequest(bot_token=TOKEN, allowed_user_id=USER))
    await service.enable()
    yield service, state
    await service.close()


def queue(service, text="A completed briefing.", origin=None, finished=None, policy=None):
    profile = service.settings.profile()
    schedule = policy or {
        "id": "c" * 32,
        "revision": 1,
        "telegram_binding": {
            "bot_id": profile["bot_id"],
            "recipient_id": profile["allowed_user_id"],
            "bot_username": profile["bot_username"],
        },
    }
    run = {
        "id": "b" * 32,
        "investigation_id": "a" * 32,
        "finished_at": (finished or datetime.now(UTC)).isoformat(),
    }
    return service.notifications.enqueue(origin or uuid4().hex, schedule, run, text, datetime.now(UTC))


def sends(state):
    return [body for method, body in state["calls"] if method == "sendMessage"]


def test_utf16_chunking_preserves_text_and_emoji_boundaries():
    text = "a" * 3999 + "😀" + "漢字" * 4000 + "🪄" * 2500
    parts = chunks(text)
    assert "".join(parts) == text
    assert all(len(part.encode("utf-16-le")) // 2 <= 4000 for part in parts)


async def test_queue_is_idempotent_and_reports_parts_separately_from_replies(outgoing):
    service, state = outgoing
    service.notifications.authorize = lambda row: True
    origin = uuid4().hex
    delivery = queue(service, "x" * 9000, origin)
    assert queue(service, "Same origin must not submit a second message", origin)["id"] == delivery["id"]
    assert sends(state) == []
    for _ in range(3):
        assert await service.notifications.deliver(service.settings.profile())
    assert not await service.notifications.deliver(service.settings.profile())
    final = service.notifications.get(delivery["id"])
    assert final["status"] == "sent" and final["sent_parts"] == final["total_parts"] == 3
    assert "".join(body["text"] for body in sends(state)) == "x" * 9000
    assert all(
        body["chat_id"] == USER and body["protect_content"] and "parse_mode" not in body
        for body in sends(state)
    )
    assert service.public()["telegram"]["briefings"] == {"sent": 1}
    assert service.public()["telegram"]["summary"]["replies_delivered"] == 0
    assert TOKEN not in json.dumps(final)


async def test_missing_policy_authorization_fails_closed_without_http(outgoing):
    service, state = outgoing
    delivery = queue(service)
    await service.notifications.deliver(service.settings.profile())
    assert service.notifications.get(delivery["id"])["status"] == "skipped"
    assert sends(state) == []


async def test_expired_reports_are_not_queued_for_late_delivery(outgoing):
    service, state = outgoing
    service.notifications.authorize = lambda row: True
    delivery = queue(service, finished=datetime.now(UTC) - timedelta(hours=2))
    assert delivery["status"] == "skipped" and delivery["total_parts"] == 0
    assert "hour" in delivery["error"]
    assert not await service.notifications.deliver(service.settings.profile())
    assert sends(state) == []


async def test_pause_before_send_withdraws_messages_and_enable_does_not_replay_them(outgoing):
    service, state = outgoing
    service.notifications.authorize = lambda row: True
    delivery = queue(service)
    service.pause()
    assert service.notifications.get(delivery["id"])["status"] == "skipped"
    await service.enable()
    assert not await service.notifications.deliver(service.settings.profile())
    assert sends(state) == []


async def test_pause_during_an_admitted_send_preserves_confirmation_and_skips_remaining_parts(outgoing):
    service, state = outgoing
    entered, release = asyncio.Event(), asyncio.Event()
    service.notifications.authorize = lambda row: True

    async def send(request, body):
        entered.set()
        await release.wait()
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 55}})

    state["send"] = send
    delivery = queue(service, "x" * 8000)
    task = asyncio.create_task(service.notifications.deliver(service.settings.profile()))
    await asyncio.wait_for(entered.wait(), 2)
    service.pause()
    release.set()
    await task
    final = service.notifications.get(delivery["id"])
    assert final["status"] == "partial" and final["sent_parts"] == 1
    assert final["parts"][1]["state"] == "skipped"
    assert len(sends(state)) == 1


@pytest.mark.parametrize("status,expected", [(403, "failed"), (500, "uncertain")])
async def test_provider_rejections_and_ambiguous_writes_never_retry_automatically(outgoing, status, expected):
    service, state = outgoing
    service.notifications.authorize = lambda row: True

    async def fail(request, body):
        return httpx.Response(status, json={"ok": False, "description": TOKEN})

    state["send"] = fail
    delivery = queue(service, "x" * 8000)
    await service.notifications.deliver(service.settings.profile())
    assert not await service.notifications.deliver(service.settings.profile())
    final = service.notifications.get(delivery["id"])
    assert final["status"] == expected
    assert final["parts"][1]["state"] == "blocked"
    assert len(sends(state)) == 1 and TOKEN not in json.dumps(final)


async def test_transport_timeouts_are_uncertain_and_not_replayed(outgoing):
    service, state = outgoing
    service.notifications.authorize = lambda row: True

    async def timeout(request, body):
        raise httpx.ReadTimeout(TOKEN, request=request)

    state["send"] = timeout
    delivery = queue(service)
    await service.notifications.deliver(service.settings.profile())
    final = service.notifications.get(delivery["id"])
    assert final["status"] == "uncertain" and TOKEN not in final["error"]
    assert not await service.notifications.deliver(service.settings.profile())


async def test_only_explicit_rate_limits_retry_and_attempts_are_bounded(outgoing):
    service, state = outgoing
    service.notifications.authorize = lambda row: True

    async def rate_limit(request, body):
        return httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 1}})

    state["send"] = rate_limit
    delivery = queue(service)
    for attempt in range(5):
        with service.store.db() as db:
            db.execute(
                "UPDATE message_delivery_parts SET next_attempt=0 WHERE delivery_id=?", (delivery["id"],)
            )
        await service.notifications.deliver(service.settings.profile())
        final = service.notifications.get(delivery["id"])
        assert final["parts"][0]["attempts"] == attempt + 1
        assert final["status"] == ("failed" if attempt == 4 else "retrying")
    assert len(sends(state)) == 5
    assert not await service.notifications.deliver(service.settings.profile())


async def test_connection_rotation_keeps_the_same_verified_recipient_but_never_redirects(outgoing):
    service, state = outgoing
    service.notifications.authorize = lambda row: True
    old = service.settings.profile()
    policy = {
        "id": "c" * 32,
        "revision": 1,
        "telegram_binding": {
            "bot_id": old["bot_id"],
            "recipient_id": old["allowed_user_id"],
            "bot_username": old["bot_username"],
        },
    }
    service.pause()
    service.save(TelegramSettingsRequest(bot_token="999999999:" + "n" * 35, allowed_user_id=USER))
    await service.enable()
    assert service.settings.profile()["revision"] != old["revision"]
    delivery = queue(service, policy=policy)
    await service.notifications.deliver(service.settings.profile())
    assert service.notifications.get(delivery["id"])["status"] == "sent"
    service.pause()
    state["bot_id"] = 54321
    service.save(TelegramSettingsRequest(bot_token="111111111:" + "m" * 35, allowed_user_id=USER))
    await service.enable()
    redirected = queue(service, policy=policy)
    assert redirected["status"] == "skipped"
    assert len(sends(state)) == 1


async def test_restart_recovers_unconfirmed_sending_parts_without_another_write(outgoing):
    service, state = outgoing
    service.notifications.authorize = lambda row: True
    delivery = queue(service, "x" * 9000)
    await service.notifications.deliver(service.settings.profile())
    with service.store.db() as db:
        db.execute(
            "UPDATE message_delivery_parts SET state='sending' WHERE delivery_id=? AND part=1",
            (delivery["id"],),
        )
    restarted = NotificationOutbox(
        service.store, service.settings, service.client, service._notification_error
    )
    restarted.authorize = lambda row: True
    final = restarted.get(delivery["id"])
    assert final["status"] == "uncertain" and final["sent_parts"] == 1
    assert final["parts"][2]["state"] == "blocked"
    assert not await restarted.deliver(service.settings.profile())
    assert len(sends(state)) == 1


async def test_concurrent_claims_cannot_send_the_same_part_twice(outgoing):
    service, state = outgoing
    entered, release = asyncio.Event(), asyncio.Event()
    service.notifications.authorize = lambda row: True

    async def send(request, body):
        entered.set()
        await release.wait()
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 66}})

    state["send"] = send
    delivery = queue(service)
    first = asyncio.create_task(service.notifications.deliver(service.settings.profile()))
    await asyncio.wait_for(entered.wait(), 2)
    assert not await service.notifications.deliver(service.settings.profile())
    release.set()
    await first
    assert service.notifications.get(delivery["id"])["status"] == "sent"
    assert len(sends(state)) == 1
