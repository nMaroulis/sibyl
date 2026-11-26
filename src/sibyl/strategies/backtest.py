"""Deterministic historical execution with costs and recorded trade evidence."""

import pandas as pd

from sibyl.exchanges.data import TIMEFRAMES
from sibyl.models import BacktestRequest
from sibyl.services.markets.analytics import performance_metrics
from sibyl.strategies.research.benchmarks import references
from sibyl.strategies.signals import exit_reason, signals, strategy_indicators
from sibyl.strategies.simulation_accounting import BacktestLedger, loss_floor


def _simulate(
    candles: list[dict], request: BacktestRequest, start: int, schedule=None, signal_override=None
) -> dict:
    """Run a long-only simulation with previous-close signals and next-open fills.

    Fee and slippage apply on both sides. Capped runs pause on closing marks and
    retain any open holdings through the final mark. Legacy runs liquidate at the
    final close. Sharpe uses candle equity returns and a zero risk-free rate.
    """
    frame = (
        pd.DataFrame(candles)
        if schedule or signal_override is not None
        else strategy_indicators(candles, request)
    )
    signal = (
        pd.Series(signal_override, index=frame.index)
        if signal_override is not None
        else None
        if schedule
        else signals(frame, request.strategy, request)
    )
    selected = []
    for left, right, parameters in schedule or []:
        context = strategy_indicators(candles[:right], parameters)
        selected.append((left, right, parameters, context, signals(context, parameters.strategy, parameters)))
    segment, transitions = 0, []
    fee, slip = request.fee_bps / 10_000, request.slippage_bps / 10_000
    limits = request.backtest_limits
    ledger = BacktestLedger(request.capital, fee, limits)
    threshold = loss_floor(request.capital, limits) if limits else None
    loss_pause = None
    curve, exposed = [], 0
    for i in range(start, len(frame)):
        row = frame.iloc[i]
        parameters, active_frame, active_signal = request, frame, signal
        if selected:
            if segment + 1 < len(selected) and i >= selected[segment + 1][0]:
                segment += 1
            left, _, parameters, active_frame, active_signal = selected[segment]
            if i == left:
                transitions.append(
                    {
                        "index": segment + 1,
                        "timestamp": row["timestamp"],
                        "cash": ledger.cash,
                        "quantity": ledger.quantity,
                        "entry_price": ledger.position.entry["price"] if ledger.position else None,
                        "equity_at_open": ledger.equity(float(row["open"])),
                        "parameters": parameters.model_dump(exclude={"dataset_id"}),
                    }
                )
        if loss_pause is None:
            position = ledger.position
            direction = int(active_signal.iloc[i - 1])
            reason = (
                exit_reason(float(active_frame.iloc[i - 1]["close"]), position.entry["price"], parameters)
                if position
                else None
            )
            if reason:
                direction = -1
            if (
                direction == 1
                and position is None
                and (parameters.max_trades is None or len(ledger.round_trips) < parameters.max_trades)
            ):
                ledger.buy(row["timestamp"], float(row["open"]) * (1 + slip))
            elif direction == -1 and position is not None:
                ledger.sell(row["timestamp"], float(row["open"]) * (1 - slip), reason or "Strategy signal")
        mark = ledger.equity(float(row["close"]))
        curve.append({"timestamp": row["timestamp"], "value": mark})
        exposed += ledger.position is not None
        if loss_pause is None and threshold is not None and mark <= threshold:
            close = pd.Timestamp(row["timestamp"]) + pd.Timedelta(seconds=TIMEFRAMES[request.timeframe])
            loss_pause = {"timestamp": close.isoformat(), "equity": mark, "threshold": threshold}
    last_close = float(frame.iloc[-1]["close"])
    if ledger.position and limits is None:
        ledger.sell(frame.iloc[-1]["timestamp"], last_close * (1 - slip), "End of backtest")
        curve[-1]["value"] = ledger.cash
    final_equity = ledger.equity(last_close)
    execution_limits = None
    if limits is not None:
        execution_limits = {
            **limits.model_dump(),
            "capped_orders": ledger.capped_orders,
            "partial_exits": ledger.partial_exits,
            "loss_pause": loss_pause,
            "ending_cash": ledger.cash,
            "realized_pnl": sum(trade["pnl"] for trade in ledger.round_trips)
            + (ledger.position.realized_pnl if ledger.position else 0.0),
            "open_position": ledger.position.marked(last_close) if ledger.position else None,
        }
    equity = [request.capital, *[point["value"] for point in curve]]
    metrics = performance_metrics(equity, ledger.trade_returns, 365 * 86400 / TIMEFRAMES[request.timeframe])
    benchmark = request.capital / (float(frame.iloc[start]["open"]) * (1 + slip) * (1 + fee))
    benchmark *= last_close * (1 - slip) * (1 - fee)
    return {
        **({"transitions": transitions} if schedule else {}),
        **({"execution_limits": execution_limits} if execution_limits is not None else {}),
        "strategy": request.strategy,
        "symbol": request.symbol,
        "initial_capital": request.capital,
        "final_equity": final_equity,
        "return_pct": (final_equity / request.capital - 1) * 100,
        "benchmark_pct": (benchmark / request.capital - 1) * 100,
        "sharpe": metrics["sharpe"],
        "max_drawdown": metrics["max_drawdown"],
        "metrics": metrics,
        "trade_returns": ledger.trade_returns,
        "timeframe": request.timeframe,
        "trades": len(ledger.round_trips),
        "win_rate": sum(r > 0 for r in ledger.trade_returns) / len(ledger.trade_returns) * 100
        if ledger.trade_returns
        else 0,
        "fees": sum(fill["fee"] for fill in ledger.fills),
        "curve": curve,
        "fills": ledger.fills,
        "round_trips": ledger.round_trips,
        "exposed_bars": exposed,
        "parameters": request.model_dump(exclude={"dataset_id"}),
        "execution": (
            "Previous-close signals fill at the next open with fees, slippage and a per-order cap. "
            "The loss pause uses candle-close marks. Any remaining holdings are valued at the final close."
            if limits
            else "Previous-close signals and close-based risk exits fill at next open; final liquidation at last close. No intrabar stop guarantee."
        ),
    }


class BacktestEngine:
    """Execute causal signals and derive inspectable results from actual simulated fills.

    There is no random performance generator. Source candles and parameter values
    fully determine fills. Indicators see only their candle prefix; entries use
    the following open. Limited runs mark any position remaining at the end.
    """

    version = "next-open-v2"
    limited_version = "next-open-v3-limits"

    @classmethod
    def revision_for(cls, request: BacktestRequest) -> str:
        """Use the recorded legacy revision for runs without order-level limits."""
        return cls.limited_version if request.backtest_limits is not None else cls.version

    def run(
        self,
        candles: list[dict],
        request: BacktestRequest,
        *,
        evaluation_start: int | None = None,
        parameter_schedule: list[tuple[int, int, BacktestRequest]] | None = None,
        signal_override: list[int] | None = None,
    ) -> dict:
        """Simulate a suffix, using its earlier prefix only for causal indicator context.

        Normal backtests start after indicator warm-up. Walk-forward tests pass
        their first test-bar index: no prefix trades, positions or performance
        enter the test, but the previous close can signal its first open.
        """
        import math

        start = request.warmup if evaluation_start is None else evaluation_start
        if type(start) is not int or not request.warmup <= start < len(candles):
            raise ValueError("Not enough closed candles after strategy warm-up.")
        times = pd.to_datetime([bar["timestamp"] for bar in candles], utc=True)
        if not times.is_monotonic_increasing or times.has_duplicates:
            raise ValueError("Backtest candles must have unique chronological timestamps.")
        step = TIMEFRAMES[request.timeframe]
        if any((times[i] - times[i - 1]).total_seconds() != step for i in range(1, len(times))):
            raise ValueError("Backtest input has gaps or the wrong timeframe.")
        if any(
            not math.isfinite(float(bar[key])) or float(bar[key]) <= 0
            for bar in candles
            for key in ("open", "high", "low", "close")
        ):
            raise ValueError("Backtest prices must be finite and positive.")
        if parameter_schedule:
            expected = start
            fixed_fields = (
                "strategy",
                "symbol",
                "timeframe",
                "capital",
                "fee_bps",
                "slippage_bps",
                "max_trades",
                "stop_loss_pct",
                "take_profit_pct",
                "backtest_limits",
            )
            for left, right, parameters in parameter_schedule:
                if (
                    type(left) is not int
                    or type(right) is not int
                    or left != expected
                    or not parameters.warmup <= left < right <= len(candles)
                ):
                    raise ValueError(
                        "A deployment schedule must cover the chronological test suffix without gaps."
                    )
                if any(getattr(parameters, field) != getattr(request, field) for field in fixed_fields):
                    raise ValueError(
                        "Continuous selection may change indicator settings, not the market, costs, capital or risk policy."
                    )
                expected = right
            if expected != len(candles):
                raise ValueError("A deployment schedule must cover the entire test suffix.")
        if signal_override is not None and (
            parameter_schedule
            or len(signal_override) != len(candles)
            or any(type(v) is not int or v not in {-1, 0, 1} for v in signal_override)
        ):
            raise ValueError("Use one valid direction per candle, without a parameter schedule.")
        result = _simulate(candles, request, start, parameter_schedule, signal_override)
        fills, trades = result["fills"], result["round_trips"]
        active = result.pop("exposed_bars")
        first = candles[start]
        fee, slip = request.fee_bps / 10000, request.slippage_bps / 10000
        units = request.capital / (first["open"] * (1 + slip) * (1 + fee))
        benchmark = [
            {"timestamp": bar["timestamp"], "value": units * bar["close"]} for bar in candles[start:]
        ]
        benchmark[-1]["value"] = request.capital * (1 + result["benchmark_pct"] / 100)
        gross_wins = sum(max(0, trade["pnl"]) for trade in trades)
        gross_losses = abs(sum(min(0, trade["pnl"]) for trade in trades))
        duration = len(result["curve"]) * step
        annual_exponent = math.log(result["final_equity"] / request.capital) * 365 * 86400 / duration
        result.update(
            engine_revision=self.revision_for(request),
            price_series=[
                {k: bar[k] for k in ("timestamp", "open", "high", "low", "close", "volume")}
                for bar in (candles if evaluation_start is None else candles[start:])
            ],
            benchmark_curve=benchmark,
            summary={
                "net_profit": result["final_equity"] - request.capital,
                "gross_profit": gross_wins,
                "gross_loss": gross_losses,
                "profit_factor": gross_wins / gross_losses if gross_losses else None,
                "expectancy": sum(t["pnl"] for t in trades) / len(trades) if trades else None,
                "exposure_pct": active / len(result["curve"]) * 100,
                "turnover": sum(fill["price"] * fill["quantity"] for fill in fills) / request.capital,
                "annualized_return_pct": math.expm1(annual_exponent) * 100
                if abs(annual_exponent) < 20
                else None,
                "average_holding_seconds": sum(t["holding_seconds"] for t in trades) / len(trades)
                if trades
                else None,
                "evaluated_bars": len(result["curve"]),
                "warmup_bars": start,
                "start": first["timestamp"],
                "end": candles[-1]["timestamp"],
            },
        )
        if evaluation_start is None:
            result["benchmarks"] = references(candles, request, start, benchmark)
        return result


def backtest(candles: list[dict], request: BacktestRequest) -> dict:
    """Run the deterministic engine; retained inputs permit exact offline reruns."""
    return BacktestEngine().run(candles, request)
