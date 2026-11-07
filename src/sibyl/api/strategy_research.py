"""Historical strategy research endpoints, separate from paper-run lifecycle."""

from fastapi import APIRouter

from sibyl.api.routes import S
from sibyl.market_data.research import current_backtest, rerun_backtest
from sibyl.models import BacktestRequest
from sibyl.strategies.plugins.contracts import PluginBacktest
from sibyl.strategies.validation import WalkForwardEngine, WalkForwardRequest

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
