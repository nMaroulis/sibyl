"""Broker explains Trade and Strategies using native ProtoLink tools.

Recorded-order/strategy tools supply evidence; trade_help and strategy_help
retrieve focused UI instructions. No tool grants order or strategy control.
"""

from typing import Literal

from protolink import Agent, ToolRejectedError

from sibyl.agents.common import COMMON_PROMPT, Services, selected
from sibyl.agents.guides import read_guide
from sibyl.agents.guides.broker import STRATEGIES, TRADE, StrategyTopic, TradeTopic
from sibyl.exchanges.registry import provider_catalog
from sibyl.models import BacktestRequest
from sibyl.strategies import CATALOG

NAME = "Broker"
TAGLINE = "Build with discipline"
DESCRIPTION = "Explain Trade and Strategies: recorded orders/fills, backtests, monitored runs, execution support and practical page help."
SYSTEM_PROMPT = (
    "For how-to questions choose trade_help or strategy_help with the matching topic; "
    "instructions alone do not require reading account/order records. Use recorded_orders for "
    "the user's saved order status and reconciliation evidence. Its order_id is Sibyl's record ID, "
    "not a venue ID; ask or list records if unclear. This tool reads retained observations, not current "
    "exchange state. Never suggest an uncertain order is safe to resubmit. "
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
    "Use execution_controls for the actual global halt and retained control history. It blocks "
    "new automatic strategy orders across production/test accounts, survives restart and pauses "
    "exchange runs. Release never resumes runs; old start reviews and unsent plans stay invalid. "
    "It leaves manual Trade, separately approved exits and approved cancellation policies available. "
    "An admitted native request can complete before a halt returns. This is not liquidation or a "
    "confirmed venue cancellation; paper runs are unaffected. You cannot halt or release it. "
    "Use portfolio_limits for shared allocated-capital, gross-exposure and observed UTC daily-loss "
    "policies across exchange strategies. Production and test funds are separate. Exposure includes "
    "unfilled buys and retained stopped positions, without netting pending sells. P&L uses dated "
    "reference USDT prices and native fills, not whole-account returns. Missing fees, uncertain writes "
    "or stale prices block automatic orders. A daily-loss lock pauses its environment, survives restart "
    "and cannot be released on the breach UTC day. Release never resumes runs. Caps never liquidate, "
    "cancel existing orders or constrain manual Trade/separately approved closes. You can explain "
    "saved evidence but cannot set limits, refresh assessments or release locks. "
    "Use strategy_alerts to inspect saved per-run notification rules and retained notifications. "
    "They watch journal pauses/errors/recovery and lifecycle events; they never control trading. "
    "Creating/resuming a rule skips older events; armed rules catch up across restart. Pauses can be manual. "
    "Notification time differs from journal time; neither proves an order is canceled or a position closed. "
    "You cannot place, cancel, replace orders, approve execution or start/stop jobs. "
)


def create_agent(services: Services, **runtime) -> Agent:
    """Declare Broker's tools and expose them through ProtoLink's runtime transport."""
    strategies, store = (services.strategies, services.store)

    def strategy_context(
        symbol: str | None = None, parameters: dict | None = None, job_id: str | None = None
    ) -> dict:
        """Inspect a strategy run's parameters, status, observations, events and execution evidence.

        Use a known job_id or omit it to follow the selected monitor. Without a selected
        job, returns the configured simulation parameters, strategy catalog and recent
        saved experiments/jobs. symbol is an exact BASE/QUOTE pair; parameters contains
        the requested backtest settings. This is evidence, not an instruction to run a strategy.
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
                        "mode",
                        "sandbox",
                        "read_only",
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
                "alert_rules": strategies.alerts.rules(job_id=job_id),
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

    def strategy_alerts(job_id: str | None = None) -> dict:
        """Explain a strategy's saved notification rules and its latest journal-related notices.

        Use a known job_id or the selected run; omit both for all strategy rules/notices.
        Returns at most ten notices and the Strategy alerts link. Notifications do not
        prove an order was canceled or a position closed.
        """
        job_id = selected("job_id", job_id, "")
        if job_id:
            strategies.journal.job(job_id)
        rules = strategies.alerts.rules(job_id=job_id or None)
        # Filter in SQL before limiting, so unrelated price notices cannot hide this run's evidence.
        import json

        with store.db() as db:
            rows = db.execute(
                "SELECT payload,created_at FROM alert_notifications "
                "WHERE json_extract(payload,'$.kind')='strategy' "
                "AND (?='' OR json_extract(payload,'$.job_id')=?) ORDER BY created_at DESC,rowid DESC LIMIT 10",
                (job_id, job_id),
            ).fetchall()
        return {
            "rules": rules,
            "recent_notifications": [
                {**json.loads(row["payload"]), "created_at": row["created_at"]} for row in rows
            ],
            "url": "/alerts?tab=strategies",
            "delivery": "in_app",
        }

    def execution_controls() -> dict:
        """Check whether automatic strategy submissions are halted and inspect the control history.

        Use for the workspace's actual halt state; strategy_help(topic='halt') explains
        how the user can operate it. Halt does not liquidate holdings or cancel all orders.
        """
        return {**strategies.execution.controls.state(), "url": "/strategies?view=monitor"}

    def portfolio_limits() -> dict:
        """Inspect shared strategy budgets, position and pending-buy exposure, daily loss and lock history.

        Returns separate production/test policies, assessment dates, reference prices
        and per-run contributions. Check freshness before interpreting headroom. Manual
        trades and unrelated holdings are outside this strategy-only policy.
        """
        return {**strategies.execution.portfolio_limits.state(), "url": "/strategies?view=monitor"}

    def strategy_guide() -> dict:
        """List implemented strategy rules and explain backtest, paper and exchange execution methods.

        Use to compare supported algorithms or understand fill/cost assumptions and
        validation methodology. strategy_help provides practical workspace steps.
        """
        return {
            "catalog": CATALOG,
            "execution": "Paper runs use isolated virtual capital. Approved exchange runs use account-bound price-capped GTC limits and native fills; both backend execution flags are required. This agent cannot approve, start or submit orders.",
            "backtests": "Next-open fills, configured fees and slippage; no look-ahead signal fills.",
            "validation": "Bounded two-axis grid search on expanding training prefixes, followed by disjoint test windows. Tests start in cash; fixed parameters and cost-aware buy-and-hold are compared. Settings are never applied to live or paper jobs automatically.",
            "url": "/strategies",
        }

    def backtest_report(run_id: str = "") -> dict:
        """Inspect a saved backtest's metrics, costs, input provenance and ten recent round trips.

        Supply a known run_id or omit it for the selected experiment. Use to explain
        actual historical simulation results; strategy_help covers running or rerunning one.
        """
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
        """Check implemented spot-trading capabilities and gaps for an exchange catalog ID.

        Use exchange='binance', 'kraken' or another supported ID. Returns the provider's
        actual support matrix, permission guidance and whether manual execution is
        enabled on this server. Support does not verify the user's account credentials.
        """
        provider = next((item for item in provider_catalog()["items"] if item["id"] == exchange), None)
        return {
            "provider": provider,
            "manual_execution_enabled": services.settings.allow_live_trading,
            "permissions": "Balance/order-history reads; spot trading permission only for supported manual orders. Withdrawals and transfers stay disabled.",
            "url": "/settings?tab=exchanges",
            "note": "Manual orders require per-order review. Supported automated strategies require their own fixed-scope account/budget approval and execution flags. Agents cannot submit or approve orders. Private account acceptance is pending.",
        }

    def validation_report(validation_id: str = "", window: int = 1) -> dict:
        """Inspect a saved validation study's training rankings and independent test-window evidence.

        Supply a known validation_id or omit it for the selected study. window is the
        one-based test-window number. Returns retained settings, comparisons, metrics
        and up to ten round trips, rather than running a new parameter search.
        """
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
        """Explain why an exchange strategy position is or is not ready for a reviewed close.

        Use a known job_id or the selected monitor. Returns retained position ownership,
        reconciliation requirements and closing blockers; it does not approve a sell.
        """
        job_id = selected("job_id", job_id, "")
        if not job_id:
            return {"ready": False, "reason": "Open a specific exchange strategy monitor first."}
        return strategies.execution.closing.context(job_id)

    def recorded_orders(
        account_id: str = "",
        status: Literal["", "active", "terminal"] = "",
        order_id: str = "",
    ) -> dict:
        """Inspect retained exchange/Demo order status, partial fills, fees and reconciliation gaps.

        List up to ten submitted records, optionally filtered by account_id and active
        or terminal status. To inspect one order and ten retained fills, pass its Sibyl
        record order_id from this list (not the exchange's native order ID).
        Returns observation dates, account/environment labels and evidence limitations.
        These are saved observations; use Trade's Check exchange/Check executions for new checks.
        """
        execution = strategies.execution
        if execution is None:
            return {"items": [], "note": "Order monitoring is unavailable.", "url": "/trade?tab=executions"}
        trading = execution.trading

        def summary(order):
            return {
                **{
                    key: order.get(key)
                    for key in (
                        "id",
                        "exchange_order_id",
                        "account",
                        "exchange",
                        "environment",
                        "origin",
                        "status",
                        "filled",
                        "remaining",
                        "average",
                        "cost",
                        "created_at",
                        "submitted_at",
                        "refreshed_at",
                        "tracking",
                        "recovery",
                        "cancel_state",
                        "cancel_message",
                        "cancel_requested_at",
                        "message",
                    )
                },
                "request": {
                    key: order["request"].get(key)
                    for key in (
                        "connection_id",
                        "symbol",
                        "side",
                        "quantity",
                        "order_type",
                        "limit_price",
                    )
                },
            }

        result = {
            "url": "/trade?tab=executions",
            "scope": "Retained order observations, not a fresh exchange check.",
        }
        if order_id:
            try:
                detail = trading.reconciliation.detail(order_id)
            except LookupError as exc:
                raise ToolRejectedError(
                    "Unknown Sibyl order record ID. List recorded_orders first or ask the user to select a record."
                ) from exc
            if account_id and detail["order"]["request"]["connection_id"] != account_id:
                raise ToolRejectedError(
                    "The order does not belong to the selected account. Use that account's recorded order ID."
                )
            return {
                **result,
                "order": summary(detail["order"]),
                "reconciliation": detail["reconciliation"],
                "fills": detail["fills"][:10],
                "has_more_fills": detail["has_more"] or len(detail["fills"]) > 10,
                "evidence_fill_limit": 10,
            }
        monitor = trading.monitor(account_id=account_id, status=status, limit=10)
        return {
            **result,
            "items": [{**summary(row), "reconciliation": row["reconciliation"]} for row in monitor["items"]],
            "total": monitor["total"],
            "has_more": monitor["has_more"],
            "evidence_order_limit": 10,
        }

    def trade_help(topic: TradeTopic = "overview") -> dict:
        """Explain Trade workflows: accounts, spot orders, account history, executions, tracking, cancellation or recovery.

        Choose history for 'How can I see my account history?' or another topic for
        concrete UI steps and a destination link. overview lists the available topics.
        This tool provides instructions, not the user's order or balance evidence.
        """
        return read_guide(TRADE, topic)

    def strategy_help(topic: StrategyTopic = "overview") -> dict:
        """Explain Strategies workflows: backtesting, results/trade markers, validation, paper/exchange runs, monitoring, stopping or halt.

        Choose a topic for concrete steps and relevant limitations, or overview for
        orientation. Use the report/run tools when asked about a saved result's actual numbers.
        """
        return read_guide(STRATEGIES, topic)

    agent = Agent(
        name="sibyl-broker",
        description=DESCRIPTION,
        tools=[
            strategy_context,
            strategy_guide,
            execution_controls,
            portfolio_limits,
            strategy_alerts,
            exchange_support,
            backtest_report,
            validation_report,
            exit_readiness,
            recorded_orders,
            trade_help,
            strategy_help,
        ],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent
