"""Read-only strategy reviews and explicit account-scoped execution approvals."""

from fastapi import APIRouter, Response

from sibyl.api.routes import S
from sibyl.strategies.execution.contracts import (
    ClosePositionRequest,
    ExchangeStrategyRequest,
    StrategyApproval,
)
from sibyl.strategies.execution.controls import ControlAction
from sibyl.strategies.execution.risk.contracts import Environment, ReleaseLossLock, SaveLimits

router = APIRouter(prefix="/api/v1/strategies/exchange", tags=["Broker"])


@router.get("/options")
def options(s: S):
    """Return implemented providers, saved accounts and server authorization state."""
    return s.strategies.execution.options()


@router.get("/controls")
def controls(s: S, response: Response):
    """Read the durable global halt and retained audit; never contact an exchange."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.controls.state()


@router.post("/controls")
def change_controls(body: ControlAction, s: S, response: Response):
    """Pause exchange runs or explicitly release admission without resuming any run."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.controls.change(body)


@router.get("/limits")
def portfolio_limits(s: S, response: Response):
    """Read shared policy, dated assessment and audit without contacting an exchange."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.portfolio_limits.state()


@router.post("/limits/{environment}")
def save_limits(environment: Environment, body: SaveLimits, s: S, response: Response):
    """Save explicitly confirmed shared limits and pause affected exchange runs."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.portfolio_limits.save(environment, body)


@router.post("/limits/{environment}/check")
def check_limits(environment: Environment, s: S, response: Response):
    """Refresh bounded public reference prices; never place or cancel an order."""
    response.headers["Cache-Control"] = "no-store"
    limits = s.strategies.execution.portfolio_limits
    limits.check(environment)
    return limits.state()


@router.post("/limits/{environment}/release")
def release_loss(environment: Environment, body: ReleaseLossLock, s: S, response: Response):
    """Release a prior UTC day's loss lock after assessment, leaving all runs paused."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.portfolio_limits.release(environment, body)


@router.get("/markets/{connection_id}")
def markets(connection_id: str, s: S):
    """Read exact spot pairs/timeframes for one active supported account."""
    return s.strategies.execution.markets(connection_id)


@router.post("/preview")
def preview(body: ExchangeStrategyRequest, s: S):
    """Read account funds and market evidence; save a two-minute approval review."""
    return s.strategies.execution.preview(body)


@router.post("/reviews/{review_id}/start", status_code=201)
def start(review_id: str, body: StrategyApproval, s: S):
    """Approve the reviewed budget and policy; wait for the next closed candle."""
    return s.strategies.execution.start(review_id, body.confirmation)


@router.post("/jobs/{job_id}/stop-cancel-review")
def stop_cancel_review(job_id: str, s: S):
    """Read a run's cancellation scope without changing it or contacting its exchange."""
    return s.strategies.execution.stop_reviews.preview(job_id)


@router.post("/stop-reviews/{review_id}/confirm")
def stop_cancel(review_id: str, body: StrategyApproval, s: S):
    """Permanently stop submissions and authorize owned-order cancellation, never liquidation."""
    return s.strategies.execution.stop_reviews.confirm(review_id, body.confirmation)


@router.get("/jobs/{job_id}/close-position")
def close_position_context(job_id: str, s: S):
    """Read local eligibility and retained position without contacting the exchange."""
    return s.strategies.execution.closing.context(job_id)


@router.post("/jobs/{job_id}/close-preview")
def close_position_preview(job_id: str, body: ClosePositionRequest, s: S):
    """Read the exact exchange book/funds and save a short-lived fixed exit review."""
    return s.strategies.execution.closing.preview(job_id, body)


@router.post("/close-reviews/{review_id}/confirm")
def close_position_confirm(review_id: str, body: StrategyApproval, s: S):
    """Approve one strategy-owned sell; duplicate requests never repeat a native write."""
    return s.strategies.execution.closing.confirm(review_id, body.confirmation)
