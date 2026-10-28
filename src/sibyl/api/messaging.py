"""Explicit Telegram connection controls; credentials never enter agent tools."""

from fastapi import APIRouter

from sibyl.api.routes import S
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
