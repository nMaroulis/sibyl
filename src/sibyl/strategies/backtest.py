"""Deterministic historical execution with costs and recorded trade evidence."""

import pandas as pd

from sibyl.exchanges.data import TIMEFRAMES
from sibyl.models import BacktestRequest
from sibyl.services.analytics import performance_metrics
from sibyl.strategies.signals import exit_reason, signals, strategy_indicators


def _simulate(candles: list[dict], request: BacktestRequest) -> dict:
    """Run a long-only simulation with previous-close signals and next-open fills.

    Fee and slippage apply on both sides. The last position is liquidated at the
    final close. Sharpe uses candle equity returns, timeframe annualization, and a zero risk-free
    rate. Drawdown is reported as a nonnegative percentage from the running peak.
    """
    frame = strategy_indicators(candles, request)
    signal = signals(frame, request.strategy, request)
    cash, quantity = request.capital, 0.0
    fee, slip = request.fee_bps / 10_000, request.slippage_bps / 10_000
    fills, curve, completed_returns = [], [], []
    entry_cost, entry_price = 0.0, 0.0
    warmup = request.warmup
    for i in range(warmup, len(frame)):
        row = frame.iloc[i]
        direction = int(signal.iloc[i - 1])
        reason = exit_reason(float(frame.iloc[i - 1]["close"]), entry_price, request) if quantity else None
        if reason:
            direction = -1
        if (
            direction == 1
            and quantity == 0
            and (request.max_trades is None or len(completed_returns) < request.max_trades)
        ):
            price = float(row["open"]) * (1 + slip)
            quantity = cash / (price * (1 + fee))
            entry_cost, entry_price = cash, price
            fills.append(
                {
                    "timestamp": row["timestamp"],
                    "side": "buy",
                    "price": price,
                    "quantity": quantity,
                    "fee": price * quantity * fee,
                }
            )
            cash = 0.0
        elif direction == -1 and quantity > 0:
            price = float(row["open"]) * (1 - slip)
            cash = quantity * price * (1 - fee)
            completed_returns.append((cash / entry_cost - 1) * 100)
            fills.append(
                {
                    "timestamp": row["timestamp"],
                    "side": "sell",
                    "price": price,
                    "quantity": quantity,
                    "fee": price * quantity * fee,
                    "reason": reason or "Strategy signal",
                }
            )
            quantity = 0.0
        curve.append({"timestamp": row["timestamp"], "value": cash + quantity * float(row["close"])})
    if not curve:
        raise ValueError("Not enough candles after strategy warm-up.")
    if quantity:
        price = float(frame.iloc[-1]["close"]) * (1 - slip)
        cash = quantity * price * (1 - fee)
        fills.append(
            {
                "timestamp": frame.iloc[-1]["timestamp"],
                "side": "sell",
                "price": price,
                "quantity": quantity,
                "fee": price * quantity * fee,
                "reason": "End of backtest",
            }
        )
        completed_returns.append((cash / entry_cost - 1) * 100)
        curve[-1]["value"] = cash
    equity = pd.Series([request.capital, *[point["value"] for point in curve]])
    metrics = performance_metrics(
        equity.tolist(), completed_returns, 365 * 86400 / TIMEFRAMES[request.timeframe]
    )
    benchmark = request.capital / (float(frame.iloc[warmup]["open"]) * (1 + slip) * (1 + fee))
    benchmark *= float(frame.iloc[-1]["close"]) * (1 - slip) * (1 - fee)
    return {
        "strategy": request.strategy,
        "symbol": request.symbol,
        "initial_capital": request.capital,
        "final_equity": cash,
        "return_pct": (cash / request.capital - 1) * 100,
        "benchmark_pct": (benchmark / request.capital - 1) * 100,
        "sharpe": metrics["sharpe"],
        "max_drawdown": metrics["max_drawdown"],
        "metrics": metrics,
        "trade_returns": completed_returns,
        "timeframe": request.timeframe,
        "trades": len(completed_returns),
        "win_rate": sum(r > 0 for r in completed_returns) / len(completed_returns) * 100
        if completed_returns
        else 0,
        "fees": sum(fill["fee"] for fill in fills),
        "curve": curve,
        "fills": fills,
        "parameters": request.model_dump(exclude={"dataset_id"}),
        "execution": "Previous-close signals and close-based risk exits fill at next open; final liquidation at last close. No intrabar stop guarantee.",
    }


class BacktestEngine:
    """Execute causal signals and derive inspectable results from actual simulated fills.

    There is no random performance generator. Source candles and parameter values
    fully determine fills. Indicators see only their candle prefix; entries use
    the following open and the final position closes at the final close.
    """

    version = "next-open-v2"

    def run(self, candles: list[dict], request: BacktestRequest) -> dict:
        """Validate chronological input and attach price, benchmark and trade evidence."""
        import math

        if len(candles) <= request.warmup:
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
        result = _simulate(candles, request)
        fills, trades = result["fills"], []
        for index in range(0, len(fills), 2):
            entry, exit = fills[index : index + 2]
            cost = entry["quantity"] * entry["price"] + entry["fee"]
            proceeds = exit["quantity"] * exit["price"] - exit["fee"]
            pnl = proceeds - cost
            trades.append(
                {
                    "id": index // 2 + 1,
                    "entry_time": entry["timestamp"],
                    "exit_time": exit["timestamp"],
                    "entry_price": entry["price"],
                    "exit_price": exit["price"],
                    "quantity": entry["quantity"],
                    "entry_fee": entry["fee"],
                    "exit_fee": exit["fee"],
                    "pnl": pnl,
                    "return_pct": pnl / cost * 100,
                    "reason": exit.get("reason", "Strategy signal"),
                    "holding_seconds": (
                        pd.Timestamp(exit["timestamp"]) - pd.Timestamp(entry["timestamp"])
                    ).total_seconds(),
                }
            )
        first = candles[request.warmup]
        fee, slip = request.fee_bps / 10000, request.slippage_bps / 10000
        units = request.capital / (first["open"] * (1 + slip) * (1 + fee))
        benchmark = [
            {"timestamp": bar["timestamp"], "value": units * bar["close"]}
            for bar in candles[request.warmup :]
        ]
        benchmark[-1]["value"] = request.capital * (1 + result["benchmark_pct"] / 100)
        gross_wins = sum(max(0, trade["pnl"]) for trade in trades)
        gross_losses = abs(sum(min(0, trade["pnl"]) for trade in trades))
        duration = len(result["curve"]) * step
        annual_exponent = math.log(result["final_equity"] / request.capital) * 365 * 86400 / duration
        active = 0
        held = False
        by_time = {}
        for fill in fills:
            by_time.setdefault(fill["timestamp"], []).append(fill)
        for point in result["curve"]:
            events = by_time.get(point["timestamp"], [])
            for fill in events:
                if fill["side"] == "buy":
                    held = True
                elif fill.get("reason") != "End of backtest":
                    held = False
            active += held
            if any(fill.get("reason") == "End of backtest" for fill in events):
                held = False
        result.update(
            engine_revision=self.version,
            price_series=[
                {k: bar[k] for k in ("timestamp", "open", "high", "low", "close", "volume")}
                for bar in candles
            ],
            benchmark_curve=benchmark,
            round_trips=trades,
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
                "warmup_bars": request.warmup,
                "start": first["timestamp"],
                "end": candles[-1]["timestamp"],
            },
        )
        return result


def backtest(candles: list[dict], request: BacktestRequest) -> dict:
    """Run the deterministic engine; retained inputs permit exact offline reruns."""
    return BacktestEngine().run(candles, request)
