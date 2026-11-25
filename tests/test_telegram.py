"""Native Telegram HTTP contracts and durable, private, read-only Sibyl routing."""

import asyncio
import json
import time
from datetime import UTC, datetime

import httpx
import pytest

from sibyl.messaging.activity import activity_timeline
from sibyl.messaging.message_logs import add_message_log
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


async def test_activity_counts_complete_replies_separately_from_message_parts(service):
    await service.enable()
    profile = service.settings.profile()
    service.ingest(profile, [message(), message(2, user=444)])
    queued, checked = service.public()["telegram"]["activity"]
    assert (queued["kind"], queued["state"], checked["kind"]) == ("message", "queued", "check")
    with service.store.db() as db:
        service._complete(db, profile["revision"], 1, USER, "a" * 5000)
    assert service.public()["telegram"]["summary"] == {
        "messages_received": 1,
        "replies_delivered": 0,
        "replies_waiting": 1,
    }
    await service.deliver(profile)
    midway = service.public()["telegram"]
    assert midway["delivery"]["sent"] == 1
    assert midway["summary"]["replies_delivered"] == 0
    assert midway["summary"]["replies_waiting"] == 1
    assert midway["activity"][0] == {**queued, "state": "pending", "accepted_parts": 1, "total_parts": 2}
    await service.deliver(profile)
    final = service.public()["telegram"]
    assert final["delivery"]["sent"] == 2
    assert final["activity"][0] == {**queued, "state": "sent", "accepted_parts": 2, "total_parts": 2}
    assert final["summary"] == {
        "messages_received": 1,
        "replies_delivered": 1,
        "replies_waiting": 0,
    }


async def test_activity_includes_only_recent_receipts_for_the_current_channel(service):
    await service.enable()
    profile = service.settings.profile()
    for identity in range(20):
        service.ingest(service.settings.profile(), [message(identity)])
    now = datetime.now(UTC)
    # Seed stored outcomes for both the active binding and unrelated bindings.
    for index, kind, channel, revision in (
        (1, "alert", "telegram", profile["revision"]),
        (2, "briefing", "telegram", profile["revision"]),
        (3, "alert", "discord", profile["revision"]),
        (4, "briefing", "telegram", "old-connection"),
    ):
        with service.store.db() as db:
            db.execute(
                "INSERT INTO message_deliveries VALUES(?,?,?,?,?)",
                (
                    f"delivery-{index}",
                    f"origin-{index}",
                    "skipped",
                    json.dumps(
                        dict(
                            kind=kind,
                            channel=channel,
                            connection_revision=revision,
                            updated_at=now.isoformat(),
                            preview="PRIVATE-DELIVERY-BODY",
                            target_id="PRIVATE-RECIPIENT",
                        )
                    ),
                    now.isoformat(),
                ),
            )
    before_calls = list(service.calls)
    activity = service.public()["telegram"]["activity"]
    assert len(activity) == 8
    assert [item["kind"] for item in activity[:2]] == ["briefing", "alert"]
    assert all(item["state"] == "skipped" for item in activity[:2])
    assert all(item["kind"] == "message" for item in activity[2:])
    assert [item["at"] for item in activity] == sorted((item["at"] for item in activity), reverse=True)
    public = json.dumps(activity)
    assert all(
        value not in public for value in ("PRIVATE-DELIVERY-BODY", "PRIVATE-RECIPIENT", "Explain my strategy")
    )
    assert service.calls == before_calls
    service.pause()
    assert service.public()["telegram"]["activity"] == activity
    service.save(TelegramSettingsRequest(allowed_user_id=USER + 1))
    await service.enable()
    assert [item["kind"] for item in service.public()["telegram"]["activity"]] == ["check"]


async def test_stop_clears_unstarted_work_and_pause_keeps_it(service):
    await service.enable()
    profile = service.settings.profile()
    service.ingest(profile, [message(1), message(2)])
    assert await service.process(profile)
    before = service.public()["telegram"]
    assert before["updates"] == {"completed": 1, "queued": 1}
    assert before["delivery"] == {"pending": 1}

    service.pause()
    assert not await service.process(profile)
    assert not await service.deliver(profile)
    assert service.public()["telegram"]["delivery"] == {"pending": 1}
    await service.enable()
    assert service.public()["telegram"]["updates"]["queued"] == 1
    stopped = service.stop()
    telegram = next(row for row in stopped["channels"] if row["id"] == "telegram")
    assert telegram["stopped"] and not telegram["enabled"] and telegram["has_token"]
    assert stopped["telegram"]["delivery"] == {"skipped": 1}
    assert stopped["telegram"]["updates"] == {"completed": 1, "withdrawn": 1}

    await service.enable()
    current = service.settings.profile()
    assert current["enabled_at"] > current["stopped_at"]
    assert not await service.process(current)
    assert not await service.deliver(current)
    assert not any(method == "sendMessage" for method, _ in service.calls)


async def test_stop_prevents_an_inflight_rate_limit_from_requeuing_a_send(service, monkeypatch):
    await service.enable()
    profile = service.settings.profile()
    service.ingest(profile, [message()])
    assert await service.process(profile)
    entered, release = asyncio.Event(), asyncio.Event()

    async def rate_limited_send(self, *_args):
        entered.set()
        await release.wait()
        raise TelegramError("Telegram rate limited this connection.", retry_after=2)

    monkeypatch.setattr(TelegramClient, "send", rate_limited_send)
    delivery = asyncio.create_task(service.deliver(profile))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        service.stop()
        await service.enable()
    finally:
        release.set()
        await delivery
    assert service.public()["telegram"]["delivery"] == {"skipped": 1}
    assert not await service.deliver(service.settings.profile())


def test_message_log_is_scoped_to_current_binding_and_excludes_private_text(client, monkeypatch):
    service = client.app.state.services.messaging
    service.save(TelegramSettingsRequest(bot_token=TOKEN, allowed_user_id=USER))
    profile = service.settings.profile()
    network = client.app.state.services.agents.network
    session = network.conversations.create()["id"]
    request = network.requests.start(session, "private input", "ollama", "fixture", None)
    network.requests.update(request["id"], run_id="retained-run")
    network.requests.finish(request["id"], "failed")
    from protolink import RunReport

    report = RunReport(
        final_task={
            "metadata": {
                "error": "Protected model input needs about 5601 tokens; prompt allowance is 2048. private output"
            }
        }
    )
    monkeypatch.setattr(
        network.run_store, "get_report", lambda identity: report if identity == "retained-run" else None
    )
    received_at = time.time()
    with service.store.db() as db:
        sequence = db.execute(
            "INSERT INTO telegram_updates VALUES(?,?,?,?)",
            (
                profile["revision"],
                1,
                "failed",
                json.dumps(
                    {"received_at": received_at, "text": "private input", "request_id": request["id"]}
                ),
            ),
        ).lastrowid
        add_message_log(db, "telegram", profile["revision"], sequence, received_at)
    url = f"/api/v1/settings/messaging/channels/telegram/activity/{sequence}"
    response = client.get(url)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    result = response.json()
    assert result["state"] == "failed" and result["parts"] == []
    assert result["selected_model"] == {"provider": "ollama", "id": "fixture"}
    assert result["failure"] == {
        "code": "context_limit",
        "provider": "ollama",
        "estimated_tokens": 5601,
        "prompt_tokens": 2048,
    }
    assert all(
        secret not in response.text for secret in (TOKEN, str(USER), "private input", "private output")
    )

    service.save(TelegramSettingsRequest(allowed_user_id=USER + 1))
    assert client.get(url).status_code == 404
    assert client.get(url.replace("/telegram/", "/discord/")).status_code == 404


async def test_clear_logs_keeps_delivery_and_dedup_and_does_not_reimport_on_restart(service):
    await service.enable()
    profile = service.settings.profile()
    service.ingest(profile, [message(1), message(2), message(3)])
    assert await service.process(profile)
    assert await service.deliver(profile)
    assert await service.process(profile)
    before = service.public()["telegram"]
    assert before["logs"]["entries"] == 3
    assert before["logs"]["bytes"] > 0
    with pytest.raises(ValueError, match="saved connection changed"):
        service.clear_logs("stale")
    result = service.clear_logs(profile["revision"])
    assert result["cleared"] == 1 and result["entries"] == 2
    assert 0 < result["bytes"] < before["logs"]["bytes"]
    assert service.public()["telegram"]["summary"] == before["summary"]
    assert service.replies.history()["total"] == 2

    service.ingest(service.settings.profile(), [message(1)])
    assert service.public()["telegram"]["logs"]["entries"] == 2
    restored = TelegramService(service.store, service.network, service.http)
    assert restored.public()["telegram"]["logs"]["entries"] == 2
    assert len([item for item in restored.public()["telegram"]["activity"] if item["kind"] == "message"]) == 2


async def test_timeline_ranges_count_all_retained_activity_and_keep_recent_rows_bounded(service):
    await service.enable()
    profile = service.settings.profile()
    now = time.time() + 1
    with service.store.db() as db:
        for index, age in enumerate([5] * 10 + [7200, 2 * 86400, 10 * 86400, 40 * 86400], start=1):
            cursor = db.execute(
                "INSERT INTO telegram_updates VALUES (?,?,?,?)",
                (profile["revision"], index, "failed" if index == 14 else "completed", "{}"),
            )
            add_message_log(db, "telegram", profile["revision"], cursor.lastrowid, now - age)
        stamp = datetime.fromtimestamp(now - 3 * 86400, UTC).isoformat()
        db.execute(
            "INSERT INTO message_deliveries VALUES (?,?,?,?,?)",
            (
                "timeline-alert",
                "timeline-alert",
                "uncertain",
                json.dumps({"kind": "alert", "connection_revision": profile["revision"]}),
                stamp,
            ),
        )

        for window, count in (("1h", 11), ("1d", 12), ("1w", 14), ("30d", 15), ("all", 16)):
            timeline = activity_timeline(db, "telegram", profile, window, now=now)
            assert timeline["window"] == window
            assert sum(bucket["count"] for bucket in timeline["bins"]) == count
            assert len(timeline["events"]) == 8
            assert all(timeline["start"] <= item["at"] <= now for item in timeline["events"])
        assert timeline["start"] == now - 40 * 86400
        assert sum(bucket["attention"] for bucket in timeline["bins"]) == 2


async def test_public_lifecycle_keeps_saved_credentials_and_last_poll_after_pause(service):
    def channel():
        return next(item for item in service.public()["channels"] if item["id"] == "telegram")

    initial = channel()
    assert initial["has_token"] and not initial["has_started"]
    assert initial["last_poll_at"] is None
    await service.enable()
    service.ingest(service.settings.profile(), [])
    running = channel()
    assert running["enabled"] and running["has_started"]
    assert running["last_poll_at"] > 0
    service.pause()
    paused = channel()
    assert not paused["enabled"] and paused["has_started"] and paused["has_token"]
    assert paused["last_poll_at"] == running["last_poll_at"]
    assert TOKEN not in json.dumps(service.public())


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
