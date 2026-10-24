"""Native Telegram HTTP contracts and durable, private, read-only Sibyl routing."""

import json
import time

import httpx
import pytest

from sibyl.messaging.service import TelegramService
from sibyl.messaging.settings import TelegramSettingsRequest
from sibyl.messaging.telegram import TelegramClient, TelegramError

TOKEN = "123456789:" + "s" * 35
USER = 987654321


def message(identity=1, user=USER, **changes):
    return {
        "update_id": identity,
        "message": {
            "from": {"id": user, "is_bot": False},
            "chat": {"id": user, "type": "private"},
            "date": int(time.time()),
            "text": "Explain my strategy",
            **changes,
        },
    }


class FakeConversations:
    def create(self):
        return {"id": "a" * 32}


class FakeNetwork:
    def __init__(self):
        self.conversations = FakeConversations()
        self.calls = []

    def status(self):
        return {"ready": True, "provider": "mock", "model": "mock"}

    async def ask(self, request):
        self.calls.append(request)
        return {"answer": "A grounded strategy explanation."}


@pytest.fixture
async def service(store):
    calls = []

    def transport(request):
        method = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content)
        calls.append((method, body))
        result = {
            "getMe": {"id": 12345, "is_bot": True, "username": "sibyl_test_bot"},
            "getWebhookInfo": {"url": ""},
            "getUpdates": [],
            "sendMessage": {"message_id": 12},
        }[method]
        return httpx.Response(200, json={"ok": True, "result": result})

    http = httpx.AsyncClient(transport=httpx.MockTransport(transport))
    # In production these tables belong to the native conversation runtime.
    with store.db() as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS sibyl_turns(id TEXT, session_id TEXT,payload TEXT,created_at TEXT)"
        )
    result = TelegramService(store, FakeNetwork(), http)
    result.calls = calls
    result.save(TelegramSettingsRequest(bot_token=TOKEN, allowed_user_id=USER))
    yield result
    await result.close()


async def test_save_encrypts_token_enable_checks_bot_and_private_chat_routes_once(service, store, caplog):
    caplog.set_level("INFO", logger="httpx")
    assert TOKEN not in json.dumps(service.public())
    with store.db() as db:
        raw = db.execute(
            "SELECT value FROM workspace_settings WHERE key='data:messaging:telegram'"
        ).fetchone()[0]
    assert TOKEN.encode() not in raw
    await service.enable()
    profile = service.settings.profile()
    service.ingest(profile, [message()])
    service.ingest(service.settings.profile(), [message()])
    await service.tick()
    await service.tick()
    assert len(service.network.calls) == 1
    assert service.network.calls[0].session_id == "a" * 32
    assert service.public()["telegram"]["delivery"]["sent"] == 1
    assert service.settings.profile()["offset"] == 2
    assert [c[0] for c in service.calls] == ["getMe", "getWebhookInfo", "sendMessage"]
    sent = service.calls[-1][1]
    assert sent["chat_id"] == USER and "parse_mode" not in sent and sent["protect_content"] is True
    assert TOKEN not in caplog.text


async def test_unbound_users_groups_forwarded_and_old_messages_never_reach_sibyl(service):
    await service.enable()
    profile = service.settings.profile()
    service.ingest(
        profile,
        [
            message(1, 444),
            message(2, chat={"id": USER, "type": "group"}),
            message(3, forward_origin={"type": "user"}),
            message(4, date=1),
        ],
    )
    await service.tick()
    assert service.network.calls == []
    assert service.public()["telegram"]["updates"]["ignored"] == 4
    assert service.settings.profile()["offset"] == 5


async def test_setup_enable_and_commands_work_without_model_then_ai_answers_without_reconnecting(
    service, monkeypatch
):
    ready = [False]
    monkeypatch.setattr(
        service.network,
        "status",
        lambda: {
            "ready": ready[0],
            "provider": "mock" if ready[0] else "none",
            "model": "mock" if ready[0] else "",
        },
    )
    service.save(TelegramSettingsRequest(bot_token=TOKEN, allowed_user_id=USER))
    await service.check()
    await service.enable()
    profile = service.settings.profile()
    assert profile["enabled"]
    assert service.public()["telegram"]["llm_ready"] is False
    for identity, text in [(1, "/status"), (2, "Explain my strategy")]:
        service.ingest(service.settings.profile(), [message(identity, text=text)])
        await service.process(service.settings.profile())
        await service.deliver(service.settings.profile())
    replies = [body["text"] for method, body in service.calls if method == "sendMessage"]
    assert "not ready" in replies[0]
    assert "Configure an AI model" in replies[1]
    assert service.network.calls == []
    ready[0] = True
    service.ingest(service.settings.profile(), [message(3)])
    await service.process(service.settings.profile())
    await service.deliver(service.settings.profile())
    assert service.settings.profile()["revision"] == profile["revision"]
    assert len(service.network.calls) == 1
    assert service.calls[-1][1]["text"] == "A grounded strategy explanation."


async def test_pause_and_disconnect_perform_no_polls_or_sends(service):
    await service.enable()
    service.pause()
    before = len(service.calls)
    await service.tick()
    service.disconnect()
    await service.tick()
    assert len(service.calls) == before
    assert not service.public()["channels"][1]["has_token"]


async def test_ambiguous_send_is_retained_and_not_retried(service, monkeypatch):
    await service.enable()
    profile = service.settings.profile()
    service.ingest(profile, [message()])
    await service.process(profile)
    attempts = []

    async def fail(*args):
        attempts.append(True)
        raise TelegramError("Unconfirmed response.", ambiguous=True)

    monkeypatch.setattr(TelegramClient, "send", fail)
    await service.deliver(profile)
    await service.deliver(profile)
    assert len(attempts) == 1
    assert service.public()["telegram"]["delivery"]["uncertain"] == 1


async def test_rate_limit_retries_only_after_delay_and_preserves_chunk_order(service, monkeypatch):
    await service.enable()
    profile = service.settings.profile()
    with service.store.db() as db:
        service._complete(db, profile["revision"], 1, USER, "a" * 5000)

    async def limited(*args):
        raise TelegramError("Rate limited.", retry_after=30)

    monkeypatch.setattr(TelegramClient, "send", limited)
    await service.deliver(profile)
    await service.deliver(profile)
    with service.store.db() as db:
        rows = db.execute("SELECT attempts,state FROM telegram_outbox ORDER BY part").fetchall()
    assert [tuple(r) for r in rows] == [(1, "pending"), (0, "pending")]


async def test_webhook_conflict_is_not_deleted_or_replaced():
    seen = []

    def read(request):
        method = request.url.path.rsplit("/", 1)[-1]
        seen.append(method)
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {"id": 123, "is_bot": True}
                if method == "getMe"
                else {"url": "https://existing.example/hook"},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(read)) as http:
        with pytest.raises(TelegramError, match="webhook"):
            await TelegramClient(TOKEN, http).identity()
    assert seen == ["getMe", "getWebhookInfo"]


def test_configuration_api_has_real_controls_and_no_secret_echo(client):
    reply = client.post(
        "/api/v1/settings/messaging/telegram", json={"bot_token": TOKEN, "allowed_user_id": USER}
    )
    assert reply.status_code == 200 and TOKEN not in reply.text
    assert reply.json()["telegram"]["llm_ready"] is False
    telegram = next(c for c in reply.json()["channels"] if c["id"] == "telegram")
    assert telegram["status"] == "available" and telegram["has_token"] and not telegram["enabled"]
    assert (
        client.post("/api/v1/settings/messaging/telegram", json={"allowed_user_id": True}).status_code == 422
    )
    assert client.delete("/api/v1/settings/messaging/telegram").status_code == 200


async def test_restart_recovers_committed_native_answer_without_repeating_inference(service):
    await service.enable()
    profile = service.settings.profile()
    service.ingest(profile, [message()])
    with service.store.db() as db:
        row = db.execute("SELECT payload FROM telegram_updates WHERE update_id=1").fetchone()
        question = json.loads(row[0])
        db.execute("UPDATE telegram_updates SET state='processing' WHERE update_id=1")
        db.execute(
            "INSERT INTO sibyl_turns VALUES(?,?,?,?)",
            (
                "answer",
                "a" * 32,
                json.dumps({"request_id": question["request_id"], "answer": "Already committed answer"}),
                "now",
            ),
        )
    restarted = TelegramService(
        service.store,
        service.network,
        httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: pytest.fail("No transport during recovery"))
        ),
    )
    try:
        assert restarted.public()["telegram"]["delivery"]["pending"] == 1
        assert service.network.calls == []
    finally:
        await restarted.close()


async def test_pause_during_slow_enable_cannot_be_overwritten(service, monkeypatch):
    import asyncio

    entered, release = asyncio.Event(), asyncio.Event()
    original = TelegramClient.identity

    async def delayed(client):
        entered.set()
        await release.wait()
        return await original(client)

    monkeypatch.setattr(TelegramClient, "identity", delayed)
    task = asyncio.create_task(service.enable())
    await entered.wait()
    service.pause()
    release.set()
    with pytest.raises(ValueError, match="changed"):
        await task
    assert not service.settings.profile()["enabled"]
