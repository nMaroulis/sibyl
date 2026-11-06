"""Explicit Telegram connection controls; credentials never enter agent tools."""

from typing import Literal

from fastapi import APIRouter, Query, Response

from sibyl.api.routes import S
from sibyl.messaging.review import DeliveryDecision
from sibyl.messaging.settings import TelegramSettingsRequest

router = APIRouter(prefix="/api/v1/settings/messaging/telegram", tags=["Settings"])


@router.post("")
def save(body: TelegramSettingsRequest, s: S):
    """Encrypt the bot credential and bind the sole permitted private user."""
    return s.messaging.save(body)


@router.post("/check")
async def check(s: S):
    """Check the bot identity and webhook conflict without sending a message."""
    return await s.messaging.check()


@router.post("/enable")
async def enable(s: S):
    """Enable authenticated private polling and replies while this backend is running."""
    return await s.messaging.enable()


@router.post("/pause")
def pause(s: S):
    """Pause new work; an already submitted Telegram send may finish."""
    return s.messaging.pause()


@router.delete("")
def disconnect(s: S):
    """Remove the local bot credential; retain Sibyl conversation history."""
    return s.messaging.disconnect()


@router.get("/deliveries")
def deliveries(
    s: S,
    response: Response,
    kind: Literal["alert", "briefing", "reply"] = "alert",
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0, le=100000),
):
    """Page actual app-origin receipts separately from Telegram conversation replies."""
    response.headers["Cache-Control"] = "no-store"
    return (
        s.messaging.replies.history(limit, offset)
        if kind == "reply"
        else s.messaging.notifications.history(kind=kind, limit=limit, offset=offset)
    )


@router.get("/deliveries/{identity}")
def delivery_details(identity: str, s: S, response: Response):
    """Explicitly inspect the exact queued text and target before a local review decision."""
    response.headers["Cache-Control"] = "no-store"
    return (s.messaging.replies if identity.startswith("reply-") else s.messaging.notifications.review).get(
        identity
    )


@router.post("/deliveries/{identity}/review")
def delivery_review(identity: str, body: DeliveryDecision, s: S, response: Response):
    """Withdraw unsent work or record a separate user acknowledgment; never resend."""
    response.headers["Cache-Control"] = "no-store"
    return (
        s.messaging.replies if identity.startswith("reply-") else s.messaging.notifications.review
    ).decide(identity, body)
