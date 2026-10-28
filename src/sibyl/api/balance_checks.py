"""Explicit balance observations and local checkpoint reports; no exchange writes."""

from fastapi import APIRouter, Response

from sibyl.accounting.balance_checks.contracts import CompareBalances, SaveCheckpoint
from sibyl.api.routes import S

router = APIRouter(prefix="/api/v1/account/balance-checks", tags=["Accountant"])


@router.get("")
def accounts(s: S, response: Response, scope: str = "all"):
    """List active accounts in the page's funds scope without reading a provider."""
    response.headers["Cache-Control"] = "no-store"
    return s.balance_checks.accounts(scope)


@router.get("/{account_id}")
def saved(account_id: str, s: S, response: Response):
    """Read saved checkpoints and comparison reports, never live account balances."""
    response.headers["Cache-Control"] = "no-store"
    return s.balance_checks.journal.state(account_id)


@router.post("/{account_id}/checkpoint")
def checkpoint(account_id: str, body: SaveCheckpoint, s: S, response: Response):
    """Read native balances and retain an explicit starting checkpoint locally."""
    response.headers["Cache-Control"] = "no-store"
    return s.balance_checks.capture(account_id, body.replace_id)


@router.get("/{account_id}/reports/{report_id}")
def report(account_id: str, report_id: str, s: S, response: Response):
    """Read one historical comparison; no other reports or provider data are fetched."""
    response.headers["Cache-Control"] = "no-store"
    return s.balance_checks.journal.report(account_id, report_id)


@router.post("/{account_id}/compare")
def compare(account_id: str, body: CompareBalances, s: S, response: Response):
    """Read fresh native balances and save a comparison against the selected checkpoint."""
    response.headers["Cache-Control"] = "no-store"
    return s.balance_checks.check(account_id, body.checkpoint_id)
