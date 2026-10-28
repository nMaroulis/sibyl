"""User-controlled, read-only pending funding updates; no deposit/withdrawal endpoints."""

from typing import Literal

from fastapi import APIRouter, Response

from sibyl.api.routes import S, account_connection
from sibyl.services.funding.contracts import RefreshFunding

router = APIRouter(prefix="/api/v1/connections", tags=["Accountant"])


@router.post("/{account_id}/funding-refresh/{stream}")
def configure(
    account_id: str,
    stream: Literal["deposit", "withdrawal", "transfer"],
    body: RefreshFunding,
    s: S,
    response: Response,
):
    """Save explicit opt-in controls or request a bounded check of retained unfinished records."""
    response.headers["Cache-Control"] = "no-store"
    return s.funding_sync.refresh.configure(account_connection(s, account_id), stream, body)
