"""Native saved-report workflows delivered only to an offline mock Telegram transport."""

import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from protolink import Task
from test_briefing_schedules import definition, finish, model

from sibyl.investigations.scheduling.contracts import BriefingAction, RunBriefing
from sibyl.messaging.settings import TelegramSettingsRequest

TOKEN = "123456789:" + "w" * 35
USER = 123987654


@pytest.fixture
def wired(client):
    service = client.app.state.services.briefings
    clock = [datetime.now(UTC).replace(microsecond=0)]
    service.clock = lambda: clock[0]
    messaging = client.app.state.services.messaging
    calls = []

    def transport(request):
        method = request.url.path.rsplit("/", 1)[-1]
        payload = json.loads(request.content)
        calls.append((method, payload))
        result = {
            "getMe": {"id": 12345, "is_bot": True, "username": "offline_briefing_bot"},
            "getWebhookInfo": {"url": ""},
            "getUpdates": [],
            "sendMessage": {"message_id": len(calls) + 200},
        }[method]
        return httpx.Response(200, json={"ok": True, "result": result})

    async def connect():
        original = messaging.http
        messaging.http = httpx.AsyncClient(transport=httpx.MockTransport(transport))
        await original.aclose()
        messaging.save(TelegramSettingsRequest(bot_token=TOKEN, allowed_user_id=USER))
        await messaging.enable()

    client.portal.call(connect)
    return service, messaging, calls


def create_policy(client, entry, user=USER):
    response = client.post(
        f"/api/v1/investigations/{entry['id']}/schedules",
        json={"telegram": True, "telegram_target": {"bot_id": 12345, "user_id": user}},
    )
    assert response.status_code == 201, response.text
    return response.json()


def sent(calls):
    return [payload for method, payload in calls if method == "sendMessage"]


def test_complete_native_report_is_delivered_once_with_private_outcomes(client, wired, monkeypatch):
    scheduler, messaging, calls = wired
    model(client, monkeypatch)
    entry = definition(client)
    policy = create_policy(client, entry)
    client.portal.call(scheduler.run_now, policy["id"], RunBriefing(revision=1, request_id=uuid4().hex))
    occurrence = finish(client, scheduler, policy)
    client.portal.call(messaging.notifications.deliver, messaging.settings.profile())
    history = client.get(f"/api/v1/briefing-schedules/{policy['id']}").json()
    latest = history["occurrences"][0]
    assert latest["status"] == "completed" and latest["report_available"]
    assert latest["delivery"]["status"] == "sent" and latest["delivery"]["sent_parts"] == 1
    assert occurrence["run_id"] == latest["run_id"]
    assert sent(calls)[0]["chat_id"] == USER and "Sibyl briefing" in sent(calls)[0]["text"]
    assert "Simulated model" in sent(calls)[0]["text"]
    assert TOKEN not in json.dumps(history)
    for _ in range(3):
        client.portal.call(scheduler.tick)
        client.portal.call(messaging.notifications.deliver, messaging.settings.profile())
    assert len(sent(calls)) == 1


def test_editing_delivery_never_silently_accepts_a_different_private_user(client, wired, monkeypatch):
    scheduler, messaging, calls = wired
    model(client, monkeypatch)
    entry = definition(client)
    policy = create_policy(client, entry)

    async def change_recipient():
        messaging.pause()
        messaging.save(TelegramSettingsRequest(allowed_user_id=USER + 1))
        await messaging.enable()

    client.portal.call(change_recipient)
    response = client.post(
        f"/api/v1/briefing-schedules/{policy['id']}",
        json={"revision": 1, "telegram": True, "telegram_target": {"bot_id": 12345, "user_id": USER}},
    )
    assert response.status_code == 409 and "changed" in response.text
    client.portal.call(scheduler.run_now, policy["id"], RunBriefing(revision=1, request_id=uuid4().hex))
    result = finish(client, scheduler, policy)
    assert result["status"] == "completed" and result["delivery"]["status"] == "skipped"
    assert sent(calls) == []
    reviewed = client.post(
        f"/api/v1/briefing-schedules/{policy['id']}",
        json={"revision": 1, "telegram": True, "telegram_target": {"bot_id": 12345, "user_id": USER + 1}},
    )
    assert reviewed.status_code == 200, reviewed.text
    client.portal.call(
        scheduler.run_now,
        policy["id"],
        RunBriefing(revision=reviewed.json()["revision"], request_id=uuid4().hex),
    )
    finish(client, scheduler, policy)
    client.portal.call(messaging.notifications.deliver, messaging.settings.profile())
    assert len(sent(calls)) == 1 and sent(calls)[0]["chat_id"] == USER + 1


def test_schedule_pause_withdraws_a_queued_delivery_but_keeps_the_report(client, wired, monkeypatch):
    scheduler, messaging, calls = wired
    model(client, monkeypatch)
    entry = definition(client)
    policy = create_policy(client, entry)

    async def pause_before_send():
        async with messaging._tick_lock:
            await scheduler.run_now(policy["id"], RunBriefing(revision=1, request_id=uuid4().hex))
            for _ in range(300):
                await scheduler.tick()
                history = scheduler.detail(policy["id"])["occurrences"]
                if history and history[0]["status"] == "completed":
                    scheduler.change(policy["id"], BriefingAction(revision=1, action="pause"))
                    return scheduler.detail(policy["id"])["occurrences"][0]
                await asyncio.sleep(0.01)
            pytest.fail("Native report did not finish.")

    result = client.portal.call(pause_before_send)
    assert result["report_available"] and result["status"] == "completed"
    assert result["delivery"]["status"] == "skipped"
    assert sent(calls) == []


def test_checked_target_must_match_request_and_native_schedule_tool_omits_secrets(client, wired):
    scheduler, _, calls = wired
    entry = definition(client)
    wrong = client.post(
        f"/api/v1/investigations/{entry['id']}/schedules",
        json={"telegram": True, "telegram_target": {"bot_id": 54321, "user_id": USER}},
    )
    assert wrong.status_code == 409
    policy = create_policy(client, entry)
    network = client.app.state.services.agents.network
    result = client.portal.call(
        network.client.send_task,
        network.cards["sibyl"].url,
        Task.create_tool_call("briefing_schedules", {"schedule_id": policy["id"]}),
    )
    result.raise_for_status()
    evidence = result.get_last_item().parts[-1].as_tool_output().result
    assert evidence["schedules"][0]["status"] == "armed"
    assert evidence["schedules"][0]["telegram_bot"] == "offline_briefing_bot"
    assert TOKEN not in json.dumps(evidence) and "recipient_id" not in json.dumps(evidence)
    assert evidence["help"]["steps"] and sent(calls) == []
