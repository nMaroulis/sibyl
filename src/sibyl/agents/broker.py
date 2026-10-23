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
    "as predictive or confuse synthetic Demo input with observed exchange prices. "
    "Use validation_report for a selected walk-forward study: distinguish training selection from "
    "later independent test windows, fixed-parameter and buy-and-hold comparisons. Explain that "
    "test returns reset virtual capital rather than forming a continuous account, later training "
    "includes earlier test windows, and repeated searches can overfit. Never call the best training "
    "score an out-of-sample result or imply that this proves future performance. "
    "Call exchange_support for manual spot order support, permissions "
    "and provider-specific history/recovery limits. Inspect mode and environment: paper runs use virtual capital; "
    "approved exchange runs use actual/test exchange funds and native fills. Explain paused/uncertain orders, "
    "budget/loss controls, base/quote fees and unvalued fee limits accurately. "
    "Approved order lifetime is best-effort backend cancellation, not native time-in-force or guaranteed expiry. "
    "Its policy continues while paused/stopped and after restart, subject to account/server access. "
    "Stop alone requests no immediate cancellation; approved expiry still applies. Separately approved "
    "Stop & cancel requests cancellation without selling holdings. "
    "Inspect order cancellation state: requested/unknown is not a confirmed cancellation, and terminal status "
    "still needs native fill reconciliation. Uncertain cancellation writes are never automatically retried. "
    "Close position is a separate typed one-order sell approval for a stopped/completed exchange run. "
    "Use exit_readiness to explain local blockers. It requires reconciled fills/fees and completed "
    "cancellation follow-ups, then fresh book/funds checks. Fee reserves, precision/native caps and "
    "partial fills can leave owned units; never claim a position is flat from an acknowledgment. "
    "Entry caps/loss latches do not apply to this separate approval. It needs live-order permission "
    "but not strategy-submission permission. Its own expiry can cancel the exit, while an earlier "
    "Stop & cancel approval does not cancel the new sell. "
    "Residual ownership keeps the account/pair assigned to the stopped run; dust/position handoff "
    "to a new run is pending. Do not suggest a new run can simply adopt these units. "
    "You cannot place, cancel, replace orders, approve execution or start/stop jobs. "
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
                        "stop_cancellation",
                        "close_position",
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
            "validation": "Bounded two-axis grid search on expanding training prefixes, followed by disjoint test windows. Tests start in cash; fixed parameters and cost-aware buy-and-hold are compared. Settings are never applied to live or paper jobs automatically.",
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

    def validation_report(validation_id: str = "", window: int = 1) -> dict:
        """Read retained walk-forward evidence without running a search or accessing an exchange."""
        validation_id = selected("validation_id", validation_id or None, "")
        if not validation_id:
            return {"note": "Choose a saved walk-forward study first.", "url": "/strategies"}
        result = strategies.validation.get(validation_id)
        if not 1 <= window <= len(result["folds"]):
            return {"note": "Choose one of the study's recorded test windows."}
        fold = result["folds"][window - 1]
        return {
            **{
                key: result[key]
                for key in ("id", "dataset", "method", "engine_revision", "request", "summary", "assumptions")
            },
            "windows": [
                {
                    "index": item["index"],
                    "train": item["train"],
                    "test": item["test"],
                    "selected": item["selected"],
                    "test_return_pct": item["out_of_sample"]["return_pct"],
                    "fixed_return_pct": item["fixed_parameters"]["return_pct"],
                    "benchmark_pct": item["out_of_sample"]["benchmark_pct"],
                }
                for item in result["folds"]
            ],
            "selected_window": {
                "index": window,
                "training_ranking": fold["training_ranking"],
                "recent_test_round_trips": fold["out_of_sample"]["round_trips"][-10:],
            },
            "simulation": True,
            "url": "/strategies",
        }

    def exit_readiness(job_id: str | None = None) -> dict:
        """Read a selected exchange run's closing blockers; never prepare or submit an exit."""
        job_id = selected("job_id", job_id, "")
        if not job_id:
            return {"ready": False, "reason": "Open a specific exchange strategy monitor first."}
        return strategies.execution.closing.context(job_id)

    agent = Agent(
        name="sibyl-broker",
        description=DESCRIPTION,
        tools=[
            background_tool(strategy_context),
            background_tool(strategy_guide),
            background_tool(exchange_support),
            background_tool(backtest_report),
            background_tool(validation_report),
            background_tool(exit_readiness),
        ],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent
