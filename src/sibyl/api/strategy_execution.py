"""Read-only strategy reviews and explicit account-scoped execution approvals."""

from fastapi import APIRouter, Response
from pydantic import Field

from sibyl.api.routes import S
from sibyl.models import Request
from sibyl.strategies.execution.contracts import (
    ClosePositionRequest,
    ExchangeStrategyRequest,
    LiquidationRequest,
    StrategyApproval,
)
from sibyl.strategies.execution.controls import ControlAction
from sibyl.strategies.execution.ownership.contracts import OwnershipReview
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


@router.get("/jobs/{job_id}/ownership")
def ownership(job_id: str, s: S, response: Response):
    """Read local attribution receipts and the last explicit account position check."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.ownership.state(job_id)


@router.post("/jobs/{job_id}/ownership/check")
def ownership_check(job_id: str, s: S, response: Response):
    """Read native balances/book and compare all strategy owners of this base asset."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.ownership.inspect(job_id)


@router.post("/jobs/{job_id}/ownership/preview")
def ownership_preview(job_id: str, body: OwnershipReview, s: S, response: Response):
    """Save a short-lived local adoption/release review without creating an order."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.ownership.preview(job_id, body)


@router.post("/ownership-reviews/{review_id}/confirm")
def ownership_confirm(review_id: str, body: StrategyApproval, s: S, response: Response):
    """Confirm one audited local attribution; duplicate confirmation creates no second receipt."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.ownership.confirm(review_id, body.confirmation)


class ArchiveStrategyRun(Request):
    """Change whether a settled flat run appears in the default list."""

    archived: bool


@router.get("/jobs/{job_id}/performance")
def strategy_performance(job_id: str, s: S, response: Response):
    """Read retained strategy lifetime performance without contacting the venue."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.performance.report(job_id)


@router.post("/jobs/{job_id}/performance/mark")
def strategy_mark(job_id: str, s: S, response: Response):
    """Record the current exact venue book midpoint without order or balance changes."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.performance.refresh(job_id)


@router.post("/jobs/{job_id}/archive")
def archive_strategy(job_id: str, body: ArchiveStrategyRun, s: S, response: Response):
    """Archive or restore an exchange run without changing its lifecycle."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.performance.archive(job_id, body.archived)


class FeeReviewApproval(Request):
    """Apply the exact locally reviewed batch of historical fee prices."""

    review_id: str = Field(pattern=r"^[0-9a-f]{64}$")


@router.get("/jobs/{job_id}/fee-review")
def fee_review(job_id: str, s: S, response: Response):
    """Read fee pricing candidates from local candles for this exact run."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.fee_reviews.preview(job_id)


@router.post("/jobs/{job_id}/fee-review")
def apply_fee_review(job_id: str, body: FeeReviewApproval, s: S, response: Response):
    """Approve the reviewed fee prices without placing an order or resuming the run."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.fee_reviews.approve(job_id, body.review_id)


@router.get("/jobs/{job_id}/fee-review/{review_id}")
def fee_review_receipt(job_id: str, review_id: str, s: S, response: Response):
    """Read the approved fee evidence as recorded at review time."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.fee_reviews.receipt(job_id, review_id)


@router.get("/jobs/{job_id}/liquidation")
def liquidation_status(job_id: str, s: S, response: Response):
    """Read the last authorized plan and native child status."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.liquidation.view(job_id)


@router.post("/jobs/{job_id}/liquidation/preview")
def liquidation_preview(job_id: str, body: LiquidationRequest, s: S, response: Response):
    """Review a bounded sell sequence without placing an order."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.liquidation.preview(job_id, body)


@router.post("/jobs/{job_id}/liquidation/{plan_id}/confirm")
def liquidation_confirm(job_id: str, plan_id: str, body: StrategyApproval, s: S, response: Response):
    """Authorize the reviewed sequence for the worker."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.liquidation.confirm(job_id, plan_id, body.confirmation)


@router.post("/jobs/{job_id}/liquidation/{plan_id}/stop")
def liquidation_stop(job_id: str, plan_id: str, s: S, response: Response):
    """Withdraw future sells. Submitted orders retain their existing expiry."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.liquidation.stop(job_id, plan_id)


class OwnershipRepairApproval(StrategyApproval):
    """Approve the exact replay shown in the ownership repair review."""

    review_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    allow_quantity_changes: bool = Field(default=False, strict=True)
    repair_releases: bool = Field(default=False, strict=True)


@router.get("/jobs/{job_id}/ownership/repair")
def preview_ownership_repair(
    job_id: str,
    s: S,
    response: Response,
    allow_quantity_changes: bool = False,
    repair_releases: bool = False,
):
    """Preview balanced cost-basis corrections across the affected family."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.ownership_repairs.preview(
        job_id,
        allow_quantity_changes=allow_quantity_changes,
        repair_releases=repair_releases,
    )


@router.post("/jobs/{job_id}/ownership/repair")
def approve_ownership_repair(job_id: str, body: OwnershipRepairApproval, s: S, response: Response):
    """Approve repaired historical cost basis without placing orders or resuming runs."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.ownership_repairs.approve(
        job_id,
        body.review_id,
        body.confirmation,
        allow_quantity_changes=body.allow_quantity_changes,
        repair_releases=body.repair_releases,
    )


@router.get("/jobs/{job_id}/ownership/repairs/{repair_id}")
def ownership_repair_receipt(job_id: str, repair_id: str, s: S, response: Response):
    """Read the original review and its approved basis changes."""
    response.headers["Cache-Control"] = "no-store"
    return s.strategies.execution.ownership_repairs.receipt(job_id, repair_id)
