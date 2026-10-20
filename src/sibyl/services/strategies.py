"""Six transparent strategies, honest backtesting, and durable paper strategy jobs."""

import json
import threading
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import numpy as np
import pandas as pd

from sibyl.models import BacktestRequest
from sibyl.services.analytics import indicators, performance_metrics
from sibyl.services.market import TIMEFRAMES, Market
from sibyl.services.strategy_monitor import StrategyJournal
from sibyl.storage import Store

CATALOG = [
    {
        "id": "ema",
        "name": "EMA Crossover",
        "tag": "Trend following",
        "description": "Follow the direction of configurable fast and slow exponential moving averages.",
        "risk": "Moderate",
    },
    {
        "id": "rsi",
        "name": "RSI Reversion",
        "tag": "Mean reversion",
        "description": "Buy lower RSI readings and exit higher readings, with configurable Wilder RSI thresholds.",
        "risk": "Moderate",
    },
    {
        "id": "bollinger",
        "name": "Bollinger Bands",
        "tag": "Volatility",
        "description": "Enter below the lower band and exit above the upper band.",
        "risk": "Moderate",
    },
    {
        "id": "bollinger-surge",
        "name": "Bollinger Surge",
        "tag": "Multi factor",
        "description": "Combine band extremes, RSI, an EMA trend filter, and a configurable volume surge.",
        "risk": "Elevated",
    },
    {
        "id": "impulse-breakout",
        "name": "Impulse Breakout",
        "tag": "Momentum",
        "description": "Confirm band and RSI reversals with EMA, MACD, ADX above 25, and volume.",
        "risk": "Elevated",
    },
    {
        "id": "quantum-momentum",
        "name": "Quantum Momentum",
        "tag": "Multi factor",
        "description": "Confirm MACD direction with money flow, TSI momentum, and expanding ATR.",
        "risk": "Elevated",
    },
]


def signals(frame: pd.DataFrame, strategy: str, request: BacktestRequest | None = None) -> pd.Series:
    """Return BUY=1, SELL=-1, HOLD=0 using only data at or before each row."""
    lower = (
        request.rsi_lower
        if request and request.rsi_lower is not None
        else (35 if strategy == "impulse-breakout" else 30)
    )
    upper = (
        request.rsi_upper
        if request and request.rsi_upper is not None
        else (65 if strategy == "impulse-breakout" else 70)
    )
    buy, sell = frame["close"] < frame["lower"], frame["close"] > frame["upper"]
    if strategy == "rsi":
        buy, sell = frame["rsi"] < lower, frame["rsi"] > upper
    elif strategy == "ema":
        buy, sell = frame["ema_fast"] > frame["ema_slow"], frame["ema_fast"] < frame["ema_slow"]
    elif strategy in {"bollinger-surge", "impulse-breakout"}:
        buy &= frame["rsi"] < lower
        sell &= frame["rsi"] > upper
        buy &= (frame["ema_fast"] > frame["ema_slow"]) & frame["volume_surge"]
        sell &= (frame["ema_fast"] < frame["ema_slow"]) & frame["volume_surge"]
        if strategy == "impulse-breakout":
            buy &= (frame["macd"] > frame["macd_signal"]) & (frame["adx"] > 25)
            sell &= (frame["macd"] < frame["macd_signal"]) & (frame["adx"] > 25)
    elif strategy == "quantum-momentum":
        buy = (
            (frame["macd"] > frame["macd_signal"])
            & (frame["tsi"] > 20)
            & (frame["cmf"] > 0)
            & (frame["atr"] > frame["atr"].rolling(10).mean())
        )
        sell = (frame["macd"] < frame["macd_signal"]) & (frame["tsi"] < -20) & (frame["cmf"] < 0)
    elif strategy != "bollinger":
        raise ValueError("Unknown strategy.")
    return pd.Series(np.select([buy, sell], [1, -1], default=0), index=frame.index)


def strategy_indicators(candles: list[dict], request: BacktestRequest) -> pd.DataFrame:
    """Apply the same configurable indicator parameters in backtests and paper jobs."""
    return indicators(
        candles,
        request.window,
        fast_period=request.fast_period,
        slow_period=request.slow_period,
        rsi_period=request.rsi_period,
        band_std=request.band_std,
        volume_multiplier=request.volume_multiplier,
        macd_fast_period=request.macd_fast_period,
        macd_slow_period=request.macd_slow_period,
        macd_signal_period=request.macd_signal_period,
        adx_period=request.adx_period,
        atr_period=request.atr_period,
        cmf_period=request.cmf_period,
        tsi_short_period=request.tsi_short_period,
        tsi_long_period=request.tsi_long_period,
    )


def exit_reason(price: float, entry: float, request: BacktestRequest) -> str | None:
    """Check close-based risk exits, never claiming intrabar stop execution."""
    change = (price / entry - 1) * 100 if entry else 0
    if request.stop_loss_pct is not None and change <= -request.stop_loss_pct:
        return "Stop loss at observed close"
    if request.take_profit_pct is not None and change >= request.take_profit_pct:
        return "Take profit at observed close"
    return None


def backtest(candles: list[dict], request: BacktestRequest) -> dict:
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
        "parameters": request.model_dump(),
        "execution": "Previous-close signals and close-based risk exits fill at next open; final liquidation at last close. No intrabar stop guarantee.",
    }


class Strategies:
    """Own persistent paper jobs, terminal lifecycle controls, and their event journals.

    One worker observes reference quotes every 30 seconds and evaluates each newly
    closed candle once. No strategy submits exchange orders. Job state, decision
    events, and quote observations commit atomically; downtime is not replayed.
    """

    def __init__(self, market: Market, store: Store):
        self.market, self.store = market, store
        self._lock = threading.RLock()
        with store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS strategy_jobs (id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )
        self.journal = StrategyJournal(store)

    def jobs(self) -> list[dict]:
        """List runs newest first, including stopped and completed runs."""
        with self.store.db() as db:
            rows = db.execute("SELECT payload FROM strategy_jobs ORDER BY rowid DESC").fetchall()
        return [json.loads(row[0]) for row in rows]

    def _save(self, job: dict) -> dict:
        """Save a job snapshot; worker transitions use the atomic journal writer."""
        return self.journal.save(job)

    @staticmethod
    def _event(job: dict, action: str, reason: str, **details) -> dict:
        """Describe a decision or lifecycle event using actual persisted balances."""
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "kind": "decision" if action in {"BUY", "SELL", "HOLD", "SKIP_BUY", "SKIP_SELL"} else "system",
            "action": action,
            "reason": reason,
            "cash": job["cash"],
            "position": job["quantity"],
            "equity": job["equity"],
            **details,
        }

    def start(self, request: BacktestRequest) -> dict:
        """Allocate isolated paper capital and persist the start event without trading."""
        with self._lock:
            if sum(job["status"] == "running" for job in self.jobs()) >= 10:
                raise ValueError("Pause a strategy before starting more than ten paper jobs.")
            now = datetime.now(UTC).isoformat()
            job = {
                "id": uuid4().hex,
                "parameters": request.model_dump(),
                "status": "running",
                "cash": request.capital,
                "quantity": 0.0,
                "equity": request.capital,
                "last_candle": None,
                "fills": [],
                "source": self.market.source,
                "created_at": now,
                "monitoring_since": now,
                "error": None,
                "statistics_complete": True,
                "journal_started": True,
                "realized_pnl": 0.0,
                "fees_paid": 0.0,
                "completed_returns": [],
                "round_trips": 0,
            }
            return self.journal.save(
                job, self._event(job, "START", "Paper strategy started with isolated virtual capital.")
            )

    def status(self, job_id: str, state: str) -> dict:
        """Pause/resume or permanently stop evaluation, retaining the virtual position.

        Stop does not liquidate. Stopped and completed runs are terminal, even if
        another lifecycle action is requested later. Repeated requests are idempotent.
        """
        if state not in {"paused", "running", "stopped"}:
            raise ValueError("Choose pause, resume, or stop.")
        with self._lock:
            job = self.journal.job(job_id)
            if job["status"] == state:
                return job
            if job["status"] in {"completed", "stopped"}:
                raise ValueError(
                    "A completed or stopped job cannot change state. Start a new paper strategy."
                )
            if state == "running":
                if job["source"] != self.market.source:
                    raise ValueError("Price source changed. Start a new strategy for the current source.")
                if sum(run["status"] == "running" for run in self.jobs()) >= 10:
                    raise ValueError("Pause another strategy before resuming more than ten paper jobs.")
            job["status"] = state
            job["updated_at"] = datetime.now(UTC).isoformat()
            if state == "stopped":
                job["stopped_at"] = job["updated_at"]
            action = {"paused": "PAUSE", "running": "RESUME", "stopped": "STOP"}[state]
            reason = {
                "paused": "Evaluation paused. The paper position is retained.",
                "running": "Evaluation resumed. Missed candles are not replayed.",
                "stopped": "Evaluation stopped permanently. The paper position is retained and its valuation is frozen.",
            }[state]
            return self.journal.save(job, self._event(job, action, reason))

    def tick(self) -> None:
        """Read providers without blocking controls, then commit once per closed candle.

        State is re-read under the lifecycle lock after every provider read. A
        pause or stop accepted during a slow request therefore prevents any fill
        from that pending observation. Duplicate signals/candles never double-fill.
        """
        for snapshot in self.jobs():
            if snapshot["status"] != "running":
                continue
            try:
                with self._lock:
                    current = self.journal.job(snapshot["id"])
                    if current["status"] != "running" or self._pause_changed_source(current):
                        continue
                params = BacktestRequest(**snapshot["parameters"])
                # Network I/O intentionally stays outside the lifecycle lock.
                with self.market.snapshot():
                    candles = self.market.candles(params.symbol, params.candles, params.timeframe)
                    price = self.market.price(params.symbol)
                self._observe(snapshot["id"], params, candles, price)
            except Exception:
                with self._lock:
                    job = self.journal.job(snapshot["id"])
                    if job["status"] != "running":
                        continue
                    message = "Evaluation failed. Check the exchange, symbol, and market availability."
                    event = self._event(job, "ERROR", message) if job.get("error") != message else None
                    job.update(error=message, checked_at=datetime.now(UTC).isoformat())
                    self.journal.save(job, event)

    def _pause_changed_source(self, job: dict) -> bool:
        """Pause incompatible runs while holding the lifecycle lock."""
        if job["source"] == self.market.source:
            return False
        job.update(status="paused", error="Price source changed. Start a new job for this source.")
        self.journal.save(job, self._event(job, "PAUSE", job["error"]))
        return True

    def _observe(self, job_id: str, params: BacktestRequest, candles: list[dict], price: float) -> None:
        """Atomically apply an observation only if the run still permits evaluation."""
        with self._lock:
            original = self.journal.job(job_id)
            if original["status"] != "running" or self._pause_changed_source(original):
                return
            job = deepcopy(original)
            now = datetime.now(UTC).isoformat()
            job.setdefault("monitoring_since", now)
            job.update(equity=job["cash"] + job["quantity"] * price, reference_price=price, observed_at=now)
            event = None
            if job["last_candle"] != candles[-1]["timestamp"]:
                event = self._decision(job, params, candles, price)
            if not job.get("journal_started"):
                event = event or self._event(
                    job,
                    "MONITORING_STARTED",
                    "Detailed monitoring started. Earlier retained fills remain available separately.",
                )
                job["journal_started"] = True
            if original.get("error") and event is None:
                event = self._event(
                    job, "RECOVERED", "Market observations resumed after an evaluation error."
                )
            job.update(checked_at=now, error=None)
            job["fills"] = job["fills"][-100:]
            sample = {
                "timestamp": now,
                "price": price,
                "equity": job["equity"],
                "cash": job["cash"],
                "position": job["quantity"],
            }
            self.journal.save(job, event, sample)

    def _decision(self, job: dict, params: BacktestRequest, candles: list[dict], price: float) -> dict:
        """Apply one closed-candle signal and return its auditable paper decision."""
        direction = int(signals(strategy_indicators(candles, params), params.strategy, params).iloc[-1])
        signal = {1: "BUY", -1: "SELL", 0: "HOLD"}[direction]
        risk = (
            exit_reason(candles[-1]["close"], job.get("entry_price", 0), params) if job["quantity"] else None
        )
        if risk:
            direction = -1
        action, reason = "HOLD", "No entry or exit signal on this closed candle."
        fill = None
        fee_rate, slip = params.fee_bps / 10000, params.slippage_bps / 10000
        completed = job.get("completed_returns", [])
        round_trips = job.get("round_trips", len(completed))
        if direction == 1:
            if job["quantity"] > 0:
                action, reason = "SKIP_BUY", "Already holding a position; no additional entry."
            elif params.max_trades is not None and round_trips >= params.max_trades:
                action, reason = "SKIP_BUY", "Maximum completed round trips reached."
                job["status"] = "completed"
            elif job["cash"] <= 0:
                action, reason = "SKIP_BUY", "No virtual cash available."
            else:
                fill_price = price * (1 + slip)
                job["entry_cost"], job["entry_price"] = job["cash"], fill_price
                job["quantity"] = job["cash"] / (fill_price * (1 + fee_rate))
                job["cash"] = 0.0
                action, reason = "BUY", "Strategy entry signal."
                fill = self._fill(job, action, price, fill_price, job["quantity"], fee_rate, reason)
        elif direction == -1:
            if job["quantity"] <= 0:
                action, reason = "SKIP_SELL", "No open paper position to sell."
            else:
                fill_price, quantity = price * (1 - slip), job["quantity"]
                job["cash"] = quantity * fill_price * (1 - fee_rate)
                if job.get("entry_cost"):
                    pnl = job["cash"] - job["entry_cost"]
                    completed.append(pnl / job["entry_cost"] * 100)
                    job["realized_pnl"] = job.get("realized_pnl", 0) + pnl
                job["completed_returns"], job["round_trips"] = completed, round_trips + 1
                job["quantity"] = 0.0
                action, reason = "SELL", risk or "Strategy exit signal."
                fill = self._fill(job, action, price, fill_price, quantity, fee_rate, reason)
                if params.max_trades is not None and job["round_trips"] >= params.max_trades:
                    job["status"] = "completed"
                    reason += " Round-trip limit reached; run completed."
        job["equity"] = job["cash"] + job["quantity"] * price
        job["last_candle"] = candles[-1]["timestamp"]
        curve = [*job.get("curve", []), {"timestamp": job["last_candle"], "value": job["equity"]}]
        if len(curve) > 720:
            job["curve_baseline"] = curve[-721]["value"]
        job["curve"] = curve[-720:]
        job["metrics"] = performance_metrics(
            [job.get("curve_baseline", params.capital), *[point["value"] for point in job["curve"]]],
            completed,
            365 * 86400 / TIMEFRAMES[params.timeframe],
        )
        return self._event(
            job,
            action,
            reason,
            signal=signal,
            candle_timestamp=job["last_candle"],
            candle_close=candles[-1]["close"],
            reference_price=price,
            fill_price=fill["price"] if fill else None,
            slippage=fill["slippage"] if fill else None,
            slippage_bps=fill["slippage_bps"] if fill else None,
            quantity=fill["quantity"] if fill else 0,
            fee=fill["fee"] if fill else 0,
        )

    @staticmethod
    def _fill(
        job: dict, action: str, reference: float, price: float, quantity: float, fee_rate: float, reason: str
    ) -> dict:
        """Record a simulated fill with signed price slippage and actual charged paper fees."""
        fill = {
            "timestamp": datetime.now(UTC).isoformat(),
            "side": action.lower(),
            "price": price,
            "reference_price": reference,
            "quantity": quantity,
            "fee": price * quantity * fee_rate,
            "slippage": price - reference,
            "slippage_bps": (price / reference - 1) * 10000,
            "reason": reason,
            "event_recorded": True,
        }
        job["fills"].append(fill)
        job["fees_paid"] = job.get("fees_paid", 0) + fill["fee"]
        return fill
