"""Authenticated settings and metadata receipts for implemented private channels."""

from fastapi import APIRouter, Depends, Query, Response
from pydantic import Field

from sibyl.api.routes import S
from sibyl.messaging.channels.contracts import ChannelAction
from sibyl.models import Request


class ChannelSave(Request):
    revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    settings: dict = Field(max_length=25)


def private(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/api/v1/settings/messaging/channels", tags=["Messaging"], dependencies=[Depends(private)]
)


@router.get("/{channel}")
def state(channel: str, s: S):
    """Read actual connection/worker state without saved credential values."""
    return s.private_channels.public(channel)


@router.put("/{channel}")
def save(channel: str, body: ChannelSave, s: S):
    """Encrypt a complete connection and bind its sole private recipient, paused."""
    return s.private_channels.save(channel, body.settings, body.revision)


@router.post("/{channel}/action")
async def action(channel: str, body: ChannelAction, s: S):
    """Check identity, enable, pause or remove the displayed connection revision."""
    return await s.private_channels.action(channel, body)


@router.get("/{channel}/receipts")
def receipts(channel: str, s: S, offset: int = Query(0, ge=0, le=100000)):
    """Page actual local send outcomes without rerunning inference or sending again."""
    return s.private_channels.receipts(channel, offset)
