"""Authenticated settings and metadata receipts for implemented private channels."""

from fastapi import APIRouter, Depends, Path, Query, Response
from pydantic import Field

from sibyl.api.routes import S
from sibyl.messaging.activity import TimelineWindow, activity_timeline, list_message_logs, message_log
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


def _binding(channel, s):
    return s.messaging.settings.profile() if channel == "telegram" else s.private_channels.profile(channel)


@router.get("/{channel}/timeline")
def timeline(channel: str, s: S, window: TimelineWindow = "all"):
    """Read activity counts and recent events for a saved connection and time range."""
    profile = _binding(channel, s)
    with s.store.db() as db:
        db.execute("BEGIN")
        return activity_timeline(db, channel, profile, window)


@router.get("/{channel}/logs")
def logs(channel: str, s: S, limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0)):
    """List stored message logs without displaying connection or message contents."""
    revision = _binding(channel, s).get("revision")
    with s.store.db() as db:
        db.execute("BEGIN")
        return list_message_logs(db, channel, revision, limit, offset)


@router.delete("/{channel}/logs")
def clear_logs(channel: str, s: S, revision: str = Query(pattern=r"^[a-f0-9]{32}$")):
    """Clear settled message diagnostics for the connection the operator selected."""
    if channel == "telegram":
        return s.messaging.clear_logs(revision)
    return s.private_channels.clear_logs(channel, revision)


@router.get("/{channel}/activity/{sequence}")
def activity_log(channel: str, s: S, sequence: int = Path(ge=1, le=2**63 - 1)):
    """Read the retained processing and delivery details for an accepted private message."""
    revision = _binding(channel, s).get("revision")
    with s.store.db() as db:
        db.execute("BEGIN")
        return message_log(db, channel, revision, sequence, run_store=s.agents.network.run_store)
