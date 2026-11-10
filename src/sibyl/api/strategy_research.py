"""Historical strategy research endpoints, separate from paper-run lifecycle."""

from fastapi import APIRouter, Depends, Response

from sibyl.api.routes import S
from sibyl.market_data.research import current_backtest, rerun_backtest
from sibyl.models import BacktestRequest
from sibyl.strategies.plugins.contracts import PluginBacktest
from sibyl.strategies.portfolio.contracts import PortfolioStudy
from sibyl.strategies.research.adaptive.contracts import AdaptiveStudy
from sibyl.strategies.validation import WalkForwardEngine, WalkForwardRequest


def private(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/v1/strategies", tags=["Broker"], dependencies=[Depends(private)])


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


@router.get("/validation/options")
def validation_options():
    """List implemented algorithm search fields and CPU/sample limits."""
    return WalkForwardEngine.options()


@router.post("/validations", status_code=201)
def validate_strategy(body: WalkForwardRequest, s: S):
    """Select on earlier candles and retain independent later-window performance."""
    return s.strategies.validation.run(body)


@router.get("/validations")
def saved_validations(s: S, demo: bool | None = None):
    """Read recent validation summaries without rerunning or fetching a provider."""
    return s.strategies.validation.list(demo=demo)


@router.get("/validations/{identity}")
def validation_detail(identity: str, s: S):
    """Read the exact saved search, training rankings and test executions."""
    return s.strategies.validation.get(identity)


@router.post("/validations/{identity}/rerun", status_code=201)
def rerun_validation(identity: str, s: S):
    """Replay the original immutable input and verified candidate plan; retain the old study."""
    return s.strategies.validation.rerun(identity)


@router.get("/plugins")
def plugins(s: S):
    """List discovered extensions; only locally allowlisted packages were imported."""
    return s.strategies.plugins.registry.catalog()


@router.post("/plugins/backtests", status_code=201)
def plugin_backtest(body: PluginBacktest, s: S):
    """Run one trusted research-only extension on exact current or saved input."""
    return s.strategies.plugins.run(body)


@router.get("/plugins/backtests")
def plugin_runs(s: S):
    return s.strategies.plugins.list()


@router.get("/plugins/backtests/{identity}")
def plugin_result(identity: str, s: S):
    return s.strategies.plugins.get(identity)


@router.post("/plugins/backtests/{identity}/rerun", status_code=201)
def plugin_rerun(identity: str, s: S):
    return s.strategies.plugins.rerun(identity)


@router.delete("/plugins/backtests/{identity}", status_code=204)
def plugin_delete(identity: str, s: S):
    s.strategies.plugins.delete(identity)


@router.get("/adaptive/options")
def adaptive_options(s: S):
    """Read optional sampler presence and actual builtin/installed plugin distributions."""
    return s.strategies.adaptive.options()


@router.get("/adaptive")
def adaptive_studies(s: S, demo: bool | None = None):
    """Read saved train/test summaries without sampling or fetching providers."""
    return s.strategies.adaptive.list(demo)


@router.post("/adaptive", status_code=201)
def adaptive_run(body: AdaptiveStudy, s: S):
    """Run a bounded offline study; longer UI requests use the local job queue."""
    return s.strategies.adaptive.run(body)


@router.get("/adaptive/{identity}")
def adaptive_detail(identity: str, s: S):
    """Read retained trials, independent test executions, source pins and sampler evidence."""
    return s.strategies.adaptive.get(identity)


@router.post("/adaptive/{identity}/rerun", status_code=201)
def adaptive_replay(identity: str, s: S):
    """Require matching sampler/engine/plugin revisions and exact reproduced trial/test evidence."""
    return s.strategies.adaptive.rerun(identity)


@router.delete("/adaptive/{identity}", status_code=204)
def adaptive_delete(identity: str, s: S):
    """Remove one local research artifact; no exchange or job is changed."""
    s.strategies.adaptive.delete(identity)


@router.get("/portfolios")
def portfolio_studies(s: S, demo: bool | None = None):
    """Read saved multi-asset research summaries without provider calls."""
    return s.strategies.portfolios.list(demo)


@router.post("/portfolios", status_code=201)
def portfolio_study(body: PortfolioStudy, s: S):
    """Simulate cost-aware multi-asset targets from exact captured or saved candle inputs."""
    return s.strategies.portfolios.run(body)


@router.get("/portfolios/inputs")
def portfolio_inputs(s: S):
    """List all bounded immutable dataset metadata for multi-asset input selection."""
    return s.strategies.portfolios.inputs()


@router.get("/portfolios/{identity}")
def portfolio_report(identity: str, s: S):
    """Inspect actual simulated fills, costs, allocations and immutable source receipts."""
    return s.strategies.portfolios.get(identity)


@router.post("/portfolios/{identity}/rerun", status_code=201)
def portfolio_replay(identity: str, s: S):
    """Replay retained datasets offline and verify exact trade/equity reproduction."""
    return s.strategies.portfolios.rerun(identity)


@router.delete("/portfolios/{identity}", status_code=204)
def portfolio_delete(identity: str, s: S):
    """Remove a local research artifact, retaining input datasets and all trading state."""
    s.strategies.portfolios.delete(identity)
