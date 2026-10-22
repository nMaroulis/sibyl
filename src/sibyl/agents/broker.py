"""Broker: its prompt, read-only tools and native ProtoLink Agent."""

from protolink import Agent

from sibyl.agents.common import COMMON_PROMPT, Services, background_tool, selected
from sibyl.exchanges.registry import provider_catalog
from sibyl.models import BacktestRequest
from sibyl.services.strategies import CATALOG

NAME = "Broker"
TAGLINE = "Build with discipline"
DESCRIPTION = "Explain strategy rules, simulation assumptions, and execution risk. Never execute trades."
SYSTEM_PROMPT = (
    "Explain strategy rules, recorded backtests, running paper strategy jobs and execution risk. Call "
    "strategy_context to inspect the selected job or simulation parameters. Use strategy_guide for "
    "supported rules and assumptions. Call exchange_support for manual spot order support, permissions "
    "and provider-specific history/recovery limits. Running strategies use virtual capital, not live automated "
    "execution. You cannot place, cancel, replace orders or start/stop jobs. "
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
            "execution": "Paper only; isolated virtual capital.",
            "backtests": "Next-open fills, configured fees and slippage; no look-ahead signal fills.",
            "url": "/strategies",
        }

    def exchange_support(exchange: str = "binance") -> dict:
        """Read manual spot trading support and gaps; never inspect keys or execute an order."""
        provider = next((item for item in provider_catalog()["items"] if item["id"] == exchange), None)
        return {
            "provider": provider,
            "manual_execution_enabled": services.settings.allow_live_trading,
            "permissions": "Balance/order-history reads; spot trading permission only for supported manual orders. Withdrawals and transfers stay disabled.",
            "url": "/settings?tab=exchanges",
            "note": "Trading remains manual with an explicit preview/confirmation. Strategies and agents cannot submit orders. Private account acceptance is pending.",
        }

    agent = Agent(
        name="sibyl-broker",
        description=DESCRIPTION,
        tools=[
            background_tool(strategy_context),
            background_tool(strategy_guide),
            background_tool(exchange_support),
        ],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent
