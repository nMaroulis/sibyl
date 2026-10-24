"""Subscriptions to saved read outcomes, without active probes or account actions."""

from fastapi import APIRouter, Query, Response

from sibyl.alerts.connection_example import connection_alert_example
from sibyl.alerts.contracts import AlertAction, ConnectionAlertCreate, ConnectionAlertUpdate
from sibyl.api.routes import S

router = APIRouter(prefix="/api/v1/connection-alerts", tags=["Alerts"])


@router.get("")
def rules(
    s: S, response: Response, include_archived: bool = False, offset: int = Query(0, ge=0, le=1_000_000)
):
    """Read local rules and safe source choices without checking their connections."""
    response.headers["Cache-Control"] = "no-store"
    return s.market.connection_alerts.rules(include_archived, offset)


@router.get("/example")
def example(response: Response):
    """Inspect a read-only illustration, separate from saved rules and evidence."""
    response.headers["Cache-Control"] = "no-store"
    return connection_alert_example()


@router.post("", status_code=201)
def create(body: ConnectionAlertCreate, s: S, response: Response):
    """Subscribe to future recorded reads; no source is probed or activated."""
    response.headers["Cache-Control"] = "no-store"
    return s.market.connection_alerts.create(body)


@router.post("/{rule_id}/edit")
def edit(rule_id: str, body: ConnectionAlertUpdate, s: S, response: Response):
    """Reject stale editors and save new settings paused."""
    response.headers["Cache-Control"] = "no-store"
    return s.market.connection_alerts.edit(rule_id, body)


@router.post("/{rule_id}/action")
def action(rule_id: str, body: AlertAction, s: S, response: Response):
    """Pause/resume/archive/restore notifications, without changing the connection."""
    response.headers["Cache-Control"] = "no-store"
    return s.market.connection_alerts.change(rule_id, body)
