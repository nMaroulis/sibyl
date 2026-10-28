"""Persistent, isolated paper execution and lifecycle controls."""

import json
import threading
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from sibyl.alerts.strategies import StrategyAlerts
from sibyl.exchanges.data import TIMEFRAMES
from sibyl.models import BacktestRequest
from sibyl.services.analytics import performance_metrics
from sibyl.services.market import Market
from sibyl.storage import Store
from sibyl.strategies.journal import StrategyJournal
from sibyl.strategies.signals import exit_reason, signals, strategy_indicators
from sibyl.strategies.validation import StrategyValidation


class Strategies:
    """Own persistent paper jobs, terminal lifecycle controls, and their event journals.

    One worker observes reference quotes every 30 seconds and evaluates each newly
    closed candle once. Exchange jobs delegate to the attached execution domain. Job state, decision
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
        self.alerts = StrategyAlerts(store)
        self.validation = StrategyValidation(store, market.archive)
        self.execution = None

    def attach_execution(self, trading):
        """Attach account execution after the shared order pipeline is constructed."""
        from sibyl.strategies.execution import ExchangeStrategies

        self.execution = ExchangeStrategies(self, trading)

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
            "job_status": job["status"],
            "reason": reason,
            "cash": job["cash"],
            "position": job["quantity"],
            "equity": job["equity"],
            **details,
        }

    def start(self, request: BacktestRequest, *, source: str | None = None) -> dict:
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
                "source": source or self.market.source,
                "source_pinned": source is not None,
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
        if self.execution and self.journal.job(job_id).get("mode") == "exchange":
            return self.execution.status(job_id, state)
        with self._lock:
            job = self.journal.job(job_id)
            if job["status"] == state:
                return job
            if job["status"] in {"completed", "stopped"}:
                raise ValueError(
                    "A completed or stopped job cannot change state. Start a new paper strategy."
                )
            if state == "running":
                if not job.get("source_pinned") and job["source"] != self.market.source:
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
            if snapshot.get("mode") == "exchange" or snapshot["status"] != "running":
                continue
            try:
                with self._lock:
                    current = self.journal.job(snapshot["id"])
                    if current["status"] != "running" or self._pause_changed_source(current):
                        continue
                params = BacktestRequest(**snapshot["parameters"])
                # Network I/O intentionally stays outside the lifecycle lock.
                with self.market.snapshot(snapshot["source"] if snapshot.get("source_pinned") else None):
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
        if self.execution:
            self.execution.tick()

    def _pause_changed_source(self, job: dict) -> bool:
        """Pause incompatible runs while holding the lifecycle lock."""
        if job.get("source_pinned"):
            return False
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
