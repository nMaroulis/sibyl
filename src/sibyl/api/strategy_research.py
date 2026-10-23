"""Historical strategy research endpoints, separate from paper-run lifecycle."""

from fastapi import APIRouter

from sibyl.api.routes import S
from sibyl.market_data.research import current_backtest, rerun_backtest
from sibyl.models import BacktestRequest

router = APIRouter(prefix="/api/v1/strategies", tags=["Broker"])


@router.post("/backtest/demo")
def demo_backtest(body: BacktestRequest, s: S):
    """Explicit synthetic input; never switch market settings or activate Demo accounts."""
    with s.market.snapshot("demo"):
        return current_backtest(s.market, s.store, body)


@router.post("/backtests/{identity}/rerun")
def rerun(identity: str, s: S):
    """Recompute an old run using its retained dataset and original parameters."""
    return rerun_backtest(s.market.archive, s.store, identity)


@router.post("/jobs/demo", status_code=201)
def demo_paper(body: BacktestRequest, s: S):
    """Run the real paper evaluator on explicit Demo prices without changing account/feed settings."""
    return s.strategies.start(body, source="demo")
