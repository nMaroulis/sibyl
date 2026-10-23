"""Read-only strategy reviews and explicit account-scoped execution approvals."""

from fastapi import APIRouter

from sibyl.api.routes import S
from sibyl.strategies.execution.contracts import ExchangeStrategyRequest, StrategyApproval

router = APIRouter(prefix="/api/v1/strategies/exchange", tags=["Broker"])


@router.get("/options")
def options(s: S):
    """Return implemented providers, saved accounts and server authorization state."""
    return s.strategies.execution.options()


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
