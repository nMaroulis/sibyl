"""Broker: its prompt, read-only tools and native ProtoLink Agent."""

from protolink import Agent

from sibyl.agents.common import COMMON_PROMPT, Services, background_tool, selected
from sibyl.exchanges.registry import provider_catalog
from sibyl.models import BacktestRequest
from sibyl.strategies import CATALOG

NAME = "Broker"
TAGLINE = "Build with discipline"
DESCRIPTION = "Explain strategy rules, simulation assumptions, and execution risk. Never execute trades."
SYSTEM_PROMPT = (
    "Explain strategy rules, recorded backtests, running paper strategy jobs and execution risk. Call "
    "strategy_context to inspect the selected job or simulation parameters. Use strategy_guide for "
    "supported rules and assumptions. Call backtest_report for a saved or selected historical run: "
    "explain actual simulated fills, costs, input provenance and metrics. Never describe a backtest "
    "as predictive or confuse synthetic Demo input with observed exchange prices. Call exchange_support for manual spot order support, permissions "
    "and provider-specific history/recovery limits. Inspect mode and environment: paper runs use virtual capital; "
    "approved exchange runs use actual/test exchange funds and native fills. Explain paused/uncertain orders, "
    "budget/loss controls, base/quote fees and unvalued fee limits accurately. You cannot place, cancel, "
    "replace orders, approve execution or start/stop jobs. "
)


def create_agent(services: Services, **runtime) -> Agent:
    """Declare Broker's tools and expose them through ProtoLink's runtime transport."""
    strategies, store = (services.strategies, services.store)

    def strategy_context(
        symbol: str | None = None, parameters: dict | None = None, job_id: str | None = None
    ) -> dict:
        """Read validated simulation selections, paper jobs, recent fills, and backtests.

        This tool only describes parameters and recorded results. It never starts or executes a strategy.
        """
        job_id = selected("job_id", job_id, "")
        symbol = selected("symbol", symbol, "BTC/USDT")
        parameters = selected("parameters", parameters, None)
        if job_id:
            monitor = strategies.journal.monitor(job_id, 30)
            job = monitor["job"]
            return {
                "selected_parameters": job["parameters"],
                "selected_run": {
                    key: job.get(key)
                    for key in (
                        "id",
                        "status",
                        "source",
                        "cash",
                        "quantity",
                        "equity",
                        "realized_pnl",
                        "fees_paid",
                        "statistics_complete",
                        "checked_at",
                        "last_candle",
                        "error",
                        "mode",
                        "account",
                        "exchange",
                        "environment",
                        "risk",
                        "risk_locked",
                        "orders",
                        "fee_assets",
                        "unvalued_fees",
                        "execution_state",
                    )
                },
                "observations": monitor["observations"],
                "recent_events": strategies.journal.events(job_id, 20)["items"],
            }
        simulation = BacktestRequest(**({"symbol": symbol} | (parameters or {})))
        return {
            "selected_parameters": simulation.model_dump(),
            "catalog": CATALOG,
            "recent_paper_orders": store.orders()[:10],
            "paper_jobs": strategies.jobs(),
            "backtests": [
                {
                    "id": run["id"],
                    "strategy": run["payload"]["strategy"],
                    "return_pct": run["payload"]["return_pct"],
                }
                for run in store.runs("backtest")[:5]
            ],
        }

    def strategy_guide() -> dict:
        """List implemented strategies and the simulator's execution assumptions."""
        return {
            "catalog": CATALOG,
            "execution": "Paper runs use isolated virtual capital. Approved exchange runs use account-bound price-capped GTC limits and native fills; both backend execution flags are required. This agent cannot approve, start or submit orders.",
            "backtests": "Next-open fills, configured fees and slippage; no look-ahead signal fills.",
            "url": "/strategies",
        }

    def backtest_report(run_id: str = "") -> dict:
        """Read a retained experiment and ten round trips without rerunning or fetching prices."""
        import json

        run_id = selected("backtest_id", run_id or None, "")
        with store.db() as db:
            row = db.execute("SELECT payload FROM runs WHERE id=? AND kind='backtest'", (run_id,)).fetchone()
        if not row:
            return {"note": "Choose a saved backtest first.", "url": "/strategies"}
        result = json.loads(row[0])
        return {
            **{
                key: value
                for key, value in result.items()
                if key not in {"curve", "price_series", "benchmark_curve", "fills", "round_trips"}
            },
            "recent_round_trips": result.get("round_trips", [])[-10:],
            "evidence_trade_limit": 10,
            "simulation": True,
        }

    def exchange_support(exchange: str = "binance") -> dict:
        """Read manual spot trading support and gaps; never inspect keys or execute an order."""
        provider = next((item for item in provider_catalog()["items"] if item["id"] == exchange), None)
        return {
            "provider": provider,
            "manual_execution_enabled": services.settings.allow_live_trading,
            "permissions": "Balance/order-history reads; spot trading permission only for supported manual orders. Withdrawals and transfers stay disabled.",
            "url": "/settings?tab=exchanges",
            "note": "Manual orders require per-order review. Supported automated strategies require their own fixed-scope account/budget approval and execution flags. Agents cannot submit or approve orders. Private account acceptance is pending.",
        }

    agent = Agent(
        name="sibyl-broker",
        description=DESCRIPTION,
        tools=[
            background_tool(strategy_context),
            background_tool(strategy_guide),
            background_tool(exchange_support),
            background_tool(backtest_report),
        ],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent
