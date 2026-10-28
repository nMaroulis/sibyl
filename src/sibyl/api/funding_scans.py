"""Local opt-in recent funding imports and observed source-revision reads."""

from typing import Literal

from fastapi import APIRouter, Response

from sibyl.accounting.funding.versions import FundingVersions
from sibyl.api.routes import S, account_connection
from sibyl.services.funding.contracts import ScanFunding

router = APIRouter(prefix="/api/v1", tags=["Accountant"])


@router.post("/connections/{account_id}/funding-scans/{stream}")
def configure(
    account_id: str,
    stream: Literal["deposit", "withdrawal", "transfer"],
    body: ScanFunding,
    s: S,
    response: Response,
):
    """Save rolling-window controls or queue a recent scan; native reads happen later."""
    response.headers["Cache-Control"] = "no-store"
    return s.funding_sync.scans.configure(account_connection(s, account_id), stream, body)


@router.get("/account-ledger/funding/{event_id}/versions")
def versions(event_id: str, s: S, response: Response):
    """Read twenty observed native-fact changes without importing history or contacting an exchange."""
    response.headers["Cache-Control"] = "no-store"
    return FundingVersions(s.store).history(event_id)


@router.get("/connections/{account_id}/funding-scans/{stream}/reports")
def reports(account_id: str, stream: Literal["deposit", "withdrawal", "transfer"], s: S, response: Response):
    """Read retained recent-window reports without fetching native history or account credentials."""
    response.headers["Cache-Control"] = "no-store"
    return s.funding_sync.scans.ledger.history(account_id, stream)
