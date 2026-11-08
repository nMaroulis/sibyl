"""Manual review never manufactures native acknowledgments or resends uncertain messages."""

import asyncio
import json

import httpx
import pytest
from test_briefing_delivery import TOKEN, queue, sends
from test_briefing_delivery import outgoing as outgoing

from sibyl.messaging.review import DeliveryDecision, delivery_evidence


def decision(service, item, kind="received"):
    detail = service.notifications.review.get(item["id"])
    return DeliveryDecision(token=detail["review_token"], decision=kind, note="Checked the private chat.")


async def test_user_acknowledgment_preserves_uncertain_native_outcome_and_no_resend(outgoing):
    service, state = outgoing
    service.notifications.authorize = lambda row: True

    async def timeout(request, body):
        raise httpx.ReadTimeout("Lost acknowledgment")

    state["send"] = timeout
    item = queue(service, "Private message " + "x" * 8000)
    await service.notifications.deliver(service.settings.profile())
    original = service.notifications.get(item["id"])
    assert original["status"] == "uncertain"
    detail = service.notifications.review.get(item["id"])
    assert "".join(p["text"] for p in detail["text_parts"]) == "Private message " + "x" * 8000
    assert TOKEN not in json.dumps(detail)
    count = len(sends(state))
    reviewed = service.notifications.review.decide(item["id"], decision(service, item))
    assert reviewed["status"] == "uncertain" and reviewed["parts"] == original["parts"]
    assert reviewed["reviews"][-1]["native_confirmation"] is False
    assert reviewed["reviews"][-1]["decision"] == "received"
    assert not await service.notifications.deliver(service.settings.profile())
    assert len(sends(state)) == count
    agent = delivery_evidence(service.store)
    assert "Private message" not in json.dumps(agent) and TOKEN not in json.dumps(agent)
    assert agent["items"][0]["user_review"][0]["decision"] == "received"


async def test_withdraw_pending_remainder_preserves_confirmed_parts_and_stale_token_rejected(outgoing):
    service, state = outgoing
    service.notifications.authorize = lambda row: True
    item = queue(service, "x" * 8000)
    before = decision(service, item, "withdraw")
    await service.notifications.deliver(service.settings.profile())
    with pytest.raises(ValueError, match="changed"):
        service.notifications.review.decide(item["id"], before)
    after = service.notifications.review.decide(item["id"], decision(service, item, "withdraw"))
    assert after["status"] == "partial" and after["sent_parts"] == 1
    assert after["parts"][0]["native_id"] and after["parts"][1]["state"] == "skipped"
    assert not await service.notifications.deliver(service.settings.profile())
    assert len(sends(state)) == 1


async def test_admitted_send_blocks_review_until_outcome_without_hiding_target(outgoing):
    service, state = outgoing
    service.notifications.authorize = lambda row: True
    entered, release = asyncio.Event(), asyncio.Event()

    async def sending(request, body):
        entered.set()
        await release.wait()
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 333}})

    state["send"] = sending
    item = queue(service)
    task = asyncio.create_task(service.notifications.deliver(service.settings.profile()))
    await asyncio.wait_for(entered.wait(), 5)
    detail = service.notifications.review.get(item["id"])
    assert detail["status"] == "sending" and not detail["can_withdraw"] and not detail["can_acknowledge"]
    assert detail["recipient_id"] and detail["bot_username"]
    with pytest.raises(ValueError):
        service.notifications.review.decide(item["id"], decision(service, item, "withdraw"))
    release.set()
    await task
    with pytest.raises(ValueError):
        service.notifications.review.decide(item["id"], decision(service, item))


def test_review_api_private_cache_headers_and_foreign_identity(manual_client):
    response = manual_client.get("/api/v1/settings/messaging/telegram/deliveries")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert manual_client.get("/api/v1/settings/messaging/telegram/deliveries/not-found").status_code == 404
    assert (
        manual_client.post(
            "/api/v1/settings/messaging/telegram/deliveries/absent/review",
            json={"decision": "resend", "token": "a" * 64},
        ).status_code
        == 422
    )


def test_native_technician_explains_review_without_reading_private_messages(manual_client):
    from test_agent_guidance import tool_call

    result = tool_call(manual_client, "technician", "telegram_delivery_review")
    assert result["items"] == [] and result["url"] == "/settings?tab=messaging"
