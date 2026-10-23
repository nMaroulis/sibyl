"""Opt-in account-value risk limits and passive retained valuation evidence."""

from fastapi import APIRouter, Query, Response

from sibyl.alerts.contracts import AlertAction
from sibyl.alerts.risk.contracts import RiskAlertCreate, RiskAlertUpdate
from sibyl.alerts.risk.example import risk_alert_example
from sibyl.api.routes import S

router = APIRouter(prefix="/api/v1/risk-alerts", tags=["Alerts"])


@router.get("")
def rules(
    s: S, response: Response, include_archived: bool = False, offset: int = Query(0, ge=0, le=1_000_000)
):
    """List saved rules without fetching balances, quotes or an AI answer."""
    response.headers["Cache-Control"] = "no-store"
    return s.portfolio.risk_alerts.rules(include_archived, offset)


@router.get("/example")
def example(response: Response):
    """Read an isolated preview without activating or modifying any account."""
    response.headers["Cache-Control"] = "no-store"
    return risk_alert_example()


@router.post("", status_code=201)
def create(body: RiskAlertCreate, s: S, response: Response):
    """Arm a reviewed fixed set; the background watcher may then read balances/quotes."""
    response.headers["Cache-Control"] = "no-store"
    return s.portfolio.risk_alerts.create(body)


@router.post("/{rule_id}/edit")
def edit(rule_id: str, body: RiskAlertUpdate, s: S, response: Response):
    """Save new settings paused; original evidence remains attributed to its revision."""
    response.headers["Cache-Control"] = "no-store"
    return s.portfolio.risk_alerts.edit(rule_id, body)


@router.post("/{rule_id}/action")
def action(rule_id: str, body: AlertAction, s: S, response: Response):
    """Control only the watch; Resume starts a new observed-value peak window."""
    response.headers["Cache-Control"] = "no-store"
    return s.portfolio.risk_alerts.change(rule_id, body)


@router.post("/{rule_id}/check")
def check(rule_id: str, s: S, response: Response):
    """Request a due check, respecting the same schedule/backoff and read limits."""
    response.headers["Cache-Control"] = "no-store"
    return s.portfolio.risk_alerts.check(rule_id)


@router.get("/{rule_id}/evidence")
def evidence(rule_id: str, s: S, response: Response, sample_id: int | None = Query(None, ge=1)):
    """Inspect retained complete snapshots locally; this never causes account reads."""
    response.headers["Cache-Control"] = "no-store"
    return s.portfolio.risk_alerts.journal.evidence(rule_id, sample_id)
