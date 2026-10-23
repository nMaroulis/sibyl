"""Local strategy journal subscriptions; no provider or execution endpoints."""

from fastapi import APIRouter, Query, Response

from sibyl.alerts.contracts import StrategyAlertAction, StrategyAlertCreate, StrategyAlertUpdate
from sibyl.alerts.strategies import strategy_alert_example
from sibyl.api.routes import S

router = APIRouter(prefix="/api/v1/strategy-alerts", tags=["Alerts"])


@router.get("")
def rules(
    s: S,
    response: Response,
    include_archived: bool = False,
    offset: int = Query(0, ge=0, le=1_000_000),
    job_id: str | None = Query(None, pattern=r"^[a-f0-9]{32}$"),
):
    """Read paginated retained subscriptions without observing or controlling a run."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.alerts.rules(include_archived, offset, job_id)


@router.get("/example")
def example(response: Response):
    """Inspect illustrative rules/notifications without writing a subscription or job."""
    response.headers["Cache-Control"] = "no-store"
    return strategy_alert_example()


@router.post("", status_code=201)
def create(body: StrategyAlertCreate, s: S, response: Response):
    """Start watching future journal entries, without replaying existing events."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.alerts.create(body)


@router.post("/{rule_id}/edit")
def edit(rule_id: str, body: StrategyAlertUpdate, s: S, response: Response):
    """Save new settings paused and reject stale editors."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.alerts.edit(rule_id, body)


@router.post("/{rule_id}/action")
def action(rule_id: str, body: StrategyAlertAction, s: S, response: Response):
    """Pause/resume/archive/restore only the subscription, never the strategy itself."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.alerts.change(rule_id, body)
