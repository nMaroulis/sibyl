"""Explicit local controls for private order signals; no order execution endpoints."""

from fastapi import APIRouter, Response

from sibyl.api.routes import S
from sibyl.exchanges.streams.service import StreamAction

router = APIRouter(prefix="/api/v1/account-streams", tags=["Accounts"])


@router.get("")
def streams(s: S, response: Response):
    """Read actual signal/retry/wakeup observations without opening a private socket."""
    response.headers["Cache-Control"] = "no-store"
    return s.account_streams.snapshot()


@router.put("/{account_id}")
def configure(account_id: str, body: StreamAction, s: S, response: Response):
    """Explicitly opt in or pause this saved account's read-only order observer."""
    response.headers["Cache-Control"] = "no-store"
    return s.account_streams.configure(account_id, body)
