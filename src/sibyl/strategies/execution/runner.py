"""Approved exchange strategies using the shared at-most-once order pipeline."""

import hashlib
import json
import time
from datetime import UTC, datetime, timedelta

from sibyl.exchanges.catalog import CATALOG
from sibyl.models import ExchangeOrderRequest
from sibyl.services.analytics import performance_metrics
from sibyl.strategies.execution.accounting import project
from sibyl.strategies.execution.approvals import StrategyApprovals
from sibyl.strategies.execution.cancellation import StrategyCancellations
from sibyl.strategies.execution.closing import ClosePositions
from sibyl.strategies.execution.contracts import ExchangeStrategyRequest, ExecutionGuard, ExecutionParameters
from sibyl.strategies.execution.controls import StrategyControls
from sibyl.strategies.execution.stop_reviews import StopCancellationReviews
from sibyl.strategies.execution.venue import is_dust, observation, order_size, supported
from sibyl.strategies.signals import exit_reason, signals, strategy_indicators


def now():
    return datetime.now(UTC).isoformat()


class ExchangeStrategies:
    """One worker, one pending order per run, no retry of an uncertain native write.

    Startup pauses active exchange runs. Resume checks retained executions and
    primes the latest candle, so downtime never replays old signals. Pause/Stop
    serialize with submission; already submitted orders still belong to the venue.
    """

    def __init__(self, strategies, trading):
        self.host, self.trading = strategies, trading
        self.store, self.market = trading.store, trading.market
        self.journal, self.lock = strategies.journal, strategies._lock
        with self.store.db() as db:
            db.execute(
                "CREATE INDEX IF NOT EXISTS exchange_orders_strategy ON exchange_orders(json_extract(payload,'$.strategy_job_id'))"
            )
        self.controls = StrategyControls(self)
        self.approvals = StrategyApprovals(self)
        self.cancellations = StrategyCancellations(self)
        self.stop_reviews = StopCancellationReviews(self)
        self.closing = ClosePositions(self)
        for job in self.jobs():
            if job["status"] == "running":
                self._pause(
                    job,
                    "Backend restarted. Review order outcomes, then explicitly Resume; missed signals are not replayed.",
                )

    def jobs(self):
        return [job for job in self.host.jobs() if job.get("mode") == "exchange"]

    def enabled(self, *, submissions=True):
        """Check server permissions; only new signal orders consult the global halt."""
        if submissions:
            self.controls.require()
        if not self.market.settings.allow_live_trading:
            raise ExecutionGuard(
                "Exchange orders are disabled. Enable SIBYL_ALLOW_LIVE_TRADING on the backend first."
            )
        if not self.market.settings.allow_strategy_execution:
            raise ExecutionGuard(
                "Automated execution is disabled. Enable SIBYL_ALLOW_STRATEGY_EXECUTION on the backend as well as SIBYL_ALLOW_LIVE_TRADING."
            )

    def account(self, identity):
        connection = self.trading._connection(identity)
        if not connection.active:
            raise ExecutionGuard("Activate the execution account in Settings first.")
        if not supported(connection.exchange):
            raise ExecutionGuard(
                "This provider does not have the required limit-order and native execution import implementation."
            )
        return connection

    def options(self):
        """Advertise code-backed support and actual activation; never probe private accounts."""
        controls = self.controls.state()
        return {
            "enabled": self.market.settings.allow_live_trading
            and self.market.settings.allow_strategy_execution
            and not controls["halted"],
            "server_enabled": self.market.settings.allow_live_trading
            and self.market.settings.allow_strategy_execution,
            "controls": controls,
            "required_flags": ["SIBYL_ALLOW_LIVE_TRADING", "SIBYL_ALLOW_STRATEGY_EXECUTION"],
            "providers": [
                {"id": spec.id, "name": spec.name} for spec in CATALOG.values() if supported(spec.id)
            ],
            "accounts": [
                {**row.model_dump(mode="json"), "supported": supported(row.exchange)}
                for row in self.store.connections()
                if row.exchange != "demo"
            ],
            "execution": "Price-capped GTC limits with optional approved, best-effort local expiry. Pending orders block submissions. Pause/Stop request no immediate cancellation; approved expiry continues. Stop & cancel retains holdings. Selling a retained position requires a separate Close position approval.",
        }

    def markets(self, identity):
        """Return exact execution pairs/timeframes, without the public feed's quote aliases."""
        connection = self.account(identity)
        with self.market.adapter(connection) as client:
            return {"symbols": sorted(client.load_markets()), "timeframes": list(client.timeframes)}

    def preview(self, request: ExchangeStrategyRequest):
        """Create a read-only, expiring approval review."""
        return self.approvals.preview(request)

    def start(self, review_id, confirmation):
        """Start the immutable scope only after its explicit confirmation."""
        return self.approvals.start(review_id, confirmation)

    def _pause(self, job, reason):
        job.update(status="paused", error=reason, updated_at=now())
        return self.journal.save(job, self.host._event(job, "PAUSE", reason))

    def _project(self, job):
        result = project(job, self.trading)
        fills = result.pop("_native_fills")
        job.update(result)
        versions = job.setdefault("fill_versions", {})
        for fill in fills:
            digest = hashlib.sha256(json.dumps(fill, sort_keys=True).encode()).hexdigest()
            if versions.get(fill["id"]) != digest:
                correction = fill["id"] in versions
                versions[fill["id"]] = digest
                event = self.host._event(
                    job,
                    "FILL_CORRECTION" if correction else fill["side"].upper(),
                    "Native fill correction; strategy ownership was recomputed."
                    if correction
                    else "Confirmed native exchange execution.",
                    timestamp=fill["timestamp"],
                    fill_price=fill["price"],
                    quantity=fill["quantity"],
                    fee=fill["fee"],
                    fees=fill["fees"],
                    native_fill_id=fill["id"],
                )
                self.journal.save(job, event)
        price = job.get("reference_price", 0)
        job["equity"] = job["cash"] + job["quantity"] * price
        pending = self._intent(job)
        if (
            pending
            and (pending.get("strategy_abandoned") or pending["status"] in {"closed", "canceled", "expired"})
            and not job["unresolved_orders"]
        ):
            job["pending"] = None
        if job["status"] != "running" and not job["unresolved_orders"]:
            job["execution_state"] = job["status"]
        self.closing.progress(job)
        return job

    def status(self, job_id, state):
        """Pause/Stop block future writes; venue orders and real holdings remain live."""
        with self.lock:
            job = self._project(self.journal.job(job_id))
            if job["status"] == state:
                return job
            if job["status"] in {"stopped", "completed"}:
                raise ExecutionGuard(
                    "This strategy is terminal. Manage retained orders and holdings in Trade."
                )
            if state == "running":
                self.enabled()
                self.account(job["connection_id"])
                if job.get("risk_locked"):
                    raise ExecutionGuard(
                        "The loss guard is latched. Manage the position in Trade; this approval cannot resume."
                    )
                # An unsent preview/plan is abandoned, never replayed on Resume.
                pending = self._intent(job)
                if pending and pending["status"] == "preview":
                    pending.update(
                        tracking=False,
                        strategy_abandoned=True,
                    )
                    with self.store.db() as db:
                        self.trading.lifecycle.write(db, pending)
                    job["pending"] = None
                    job = self._project(job)
                if job["unresolved_orders"]:
                    raise ExecutionGuard(
                        "Resolve pending or uncertain orders and reconcile native fills in Trade before resuming."
                    )
                if job["accounting_incomplete"] or job["unvalued_fees"]:
                    raise ExecutionGuard(
                        "Native costs/fees are incomplete or use another currency. Review the strategy accounting before resuming."
                    )
                if sum(run["status"] == "running" for run in self.host.jobs()) >= 10:
                    raise ExecutionGuard("Pause another strategy before resuming more than ten runs.")
                with self.market.adapter(self.account(job["connection_id"])) as client:
                    observed = observation(client, ExecutionParameters(**job["parameters"]))
                job.update(
                    reference_price=observed["price"],
                    equity=job["cash"] + job["quantity"] * observed["price"],
                )
                self._risk(job, observed)
                if self._order_count(job) >= job["risk"]["max_orders_per_day"]:
                    raise ExecutionGuard(
                        "Rolling 24-hour order limit is still active. Wait for the window to clear before resuming."
                    )
                job.update(last_candle=observed["candles"][-1]["timestamp"], pending=None, error=None)
            job.update(status=state, updated_at=now())
            if state == "stopped":
                job["stopped_at"] = now()
            action = {"paused": "PAUSE", "running": "RESUME", "stopped": "STOP"}[state]
            return self.journal.save(
                job,
                self.host._event(
                    job,
                    action,
                    "Future submissions "
                    + (
                        "enabled from the next candle."
                        if state == "running"
                        else "disabled. Submitted orders are not canceled and holdings are not sold."
                    ),
                ),
            )

    def _intent(self, job):
        pending = job.get("pending")
        if not pending:
            return None
        with self.store.db() as db:
            row = db.execute(
                "SELECT payload FROM exchange_orders WHERE request_key=?", (pending["key"],)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def _risk(self, job, observed):
        if observed["spread_bps"] > job["risk"]["max_spread_bps"]:
            raise ExecutionGuard("Spread guard reached. Review the exchange before resuming.")
        if time.time() - observed["observed_at"] > 30:
            raise ExecutionGuard("Execution observation expired; no order was sent.")
        if job["equity"] <= job["parameters"]["capital"] * (1 - job["risk"]["max_loss_pct"] / 100):
            job["risk_locked"] = True
            self.journal.save(job)
            raise ExecutionGuard(
                "Allocated loss guard reached. New submissions are locked; manage retained orders and holdings in Trade."
            )
        if job["cash"] < -1e-8 or job["accounting_incomplete"] or job["unvalued_fees"]:
            raise ExecutionGuard(
                "Costs/fees exceed the allocation or cannot be fully valued in base/quote units. Review the native executions in Trade."
            )

    def _order_count(self, job):
        """Count durable prepared attempts, including rejected/abandoned intents, conservatively."""
        with self.store.db() as db:
            return db.execute(
                "SELECT COUNT(*) FROM exchange_orders WHERE json_extract(payload,'$.strategy_job_id')=? AND json_extract(payload,'$.created_at')>=?",
                (job["id"], (datetime.now(UTC) - timedelta(hours=24)).isoformat()),
            ).fetchone()[0]

    def tick(self):
        """Reconcile all retained runs locally; evaluate running jobs once per fresh close."""
        for snapshot in self.jobs():
            try:
                self._step(snapshot["id"])
            except Exception as error:
                with self.lock:
                    job = self.journal.job(snapshot["id"])
                    message = (
                        str(error)
                        if isinstance(error, ExecutionGuard)
                        else "Exchange evaluation failed. Review account access, market availability and order evidence before resuming."
                    )
                    if job["status"] == "running":
                        # Only our domain messages are public; provider/transport errors stay private.
                        message = (
                            str(error)
                            if isinstance(error, ExecutionGuard)
                            else "Exchange evaluation failed. Review account access, market availability and order evidence before resuming."
                        )
                        self._pause(job, message)
                    elif job.get("error") != message:
                        job.update(error=message, accounting_incomplete=True, statistics_complete=False)
                        self.journal.save(job, self.host._event(job, "ERROR", message))

    def _step(self, identity):
        # Cancellation is an independent, already approved lifecycle policy.
        # It may continue on paused/stopped runs, including after restart.
        self.cancellations.step(identity)
        with self.lock:
            job = self._project(self.journal.job(identity))
            self.journal.save(job)
            if job["status"] != "running":
                return
            self.enabled()
            control_revision = self.controls.require()["revision"]
            connection = self.account(job["connection_id"])
            if (connection.exchange, connection.sandbox) != (job["exchange"], job["sandbox"]):
                raise ExecutionGuard("Execution account environment changed.")
            pending = self._intent(job)
            if job.get("pending") and not pending:
                return self._pause(
                    job,
                    "An interrupted order plan was not submitted. Resume discards it and waits for a new candle.",
                )
            if pending and pending["status"] in {"preview", "submitting", "unknown", "rejected"}:
                return self._pause(
                    job,
                    "Order submission was interrupted, uncertain or rejected. Check the linked order in Trade; no submission will be retried.",
                )
        params = ExecutionParameters(**job["parameters"])
        with self.market.adapter(connection) as client:
            observed = observation(client, params)
        with self.lock:
            job = self._project(self.journal.job(identity))
            if job["status"] != "running":
                return
            self.enabled()
            self.controls.require(control_revision)
            self.account(job["connection_id"])
            job.update(
                reference_price=observed["price"],
                equity=job["cash"] + job["quantity"] * observed["price"],
                checked_at=now(),
                observed_at=now(),
            )
            self._risk(job, observed)
            if job["unresolved_orders"]:
                job.update(execution_state="waiting_order", error=None)
                return self._sample(job, observed)
            job["pending"] = None
            candle = observed["candles"][-1]
            if candle["timestamp"] == job["last_candle"]:
                return self._sample(job, observed)
            direction = int(
                signals(strategy_indicators(observed["candles"], params), params.strategy, params).iloc[-1]
            )
            risk_exit = (
                exit_reason(candle["close"], job.get("entry_price", 0), params) if job["quantity"] else None
            )
            if risk_exit:
                direction = -1
            job["last_candle"] = candle["timestamp"]
            with self.market.adapter(connection) as client:
                dust = is_dust(client, params.symbol, job["quantity"], observed["bid"])
                job["dust_position"] = dust
                side = (
                    "buy"
                    if direction == 1 and (job["quantity"] <= 1e-12 or dust)
                    else "sell"
                    if direction == -1 and job["quantity"] > 1e-12 and not dust
                    else None
                )
                if side and params.max_trades is not None and job["round_trips"] >= params.max_trades:
                    job["status"] = "completed"
                    side = None
                if side:
                    quantity, price = order_size(client, job, observed, side)
            if not side:
                self.journal.save(
                    job,
                    self.host._event(
                        job,
                        "HOLD",
                        "No new tradable entry/exit on this candle; residual dust remains owned.",
                        candle_timestamp=candle["timestamp"],
                    ),
                )
                return self._sample(job, observed)
            count = self._order_count(job)
            if count >= job["risk"]["max_orders_per_day"]:
                return self._pause(
                    job,
                    "Rolling 24-hour order limit reached. Review before resuming after the window clears.",
                )
            job["pending"] = {
                "key": f"strategy-{job['id']}-{hashlib.sha256(candle['timestamp'].encode()).hexdigest()[:20]}",
                "side": side,
                "quantity": quantity,
                "limit_price": price,
                "reference_price": observed["price"],
            }
            job["execution_state"] = "planning_order"
            self.journal.save(
                job,
                self.host._event(
                    job,
                    "ORDER_PLANNED",
                    risk_exit or "Strategy signal; one capped limit order planned.",
                    candle_timestamp=candle["timestamp"],
                ),
            )
        request = ExchangeOrderRequest(
            connection_id=job["connection_id"],
            symbol=params.symbol,
            side=side,
            quantity=quantity,
            order_type="limit",
            limit_price=price,
            idempotency_key=job["pending"]["key"],
        )
        intent = self.trading.preview(request)
        with self.lock:
            # Link the durable intent before the first possible write. All future
            # attempts, including API/manual callers, require the same strategy owner.
            with self.store.db() as db:
                intent = self.trading.lifecycle.read(db, intent["id"])
                intent.update(
                    origin="strategy", strategy_job_id=job["id"], strategy_control_revision=control_revision
                )
                intent["strategy_expiry_seconds"] = job["risk"].get("order_lifetime_seconds")
                self.trading.lifecycle.write(db, intent)
            current = self.journal.job(identity)
            if (
                current["status"] != "running"
                or not current.get("pending")
                or current["pending"]["key"] != job["pending"]["key"]
            ):
                intent.update(tracking=False, strategy_abandoned=True)
                with self.store.db() as db:
                    self.trading.lifecycle.write(db, intent)
                return
            self.enabled()
            self.account(current["connection_id"])
            self._risk(current, observed)
            result = self.trading.execute(intent["id"], intent["confirmation"], strategy_job_id=identity)
            current.update(execution_state="waiting_order", error=None)
            self.journal.save(
                current,
                self.host._event(
                    current,
                    "ORDER_SUBMITTED",
                    "Native order outcome: " + result["status"] + ". Fills are imported separately.",
                    order_id=intent["id"],
                ),
            )
            if result["status"] in {"unknown", "submitting", "rejected"}:
                self._pause(
                    current,
                    "Native submission is uncertain or rejected. Check Trade; this write will not be retried.",
                )
            else:
                self._sample(current, observed)

    def _sample(self, job, observed):
        job["execution_state"] = "waiting_order" if job.get("pending") else "waiting_candle"
        candle_timestamp = observed["candles"][-1]["timestamp"]
        if candle_timestamp != job.get("metric_candle"):
            job["metric_candle"] = candle_timestamp
            curve = [*job.get("curve", []), {"timestamp": candle_timestamp, "value": job["equity"]}]
            if len(curve) > 720:
                job["curve_baseline"] = curve[-721]["value"]
            job["curve"] = curve[-720:]
            from sibyl.exchanges.data import TIMEFRAMES

            job["metrics"] = performance_metrics(
                [
                    job.get("curve_baseline", job["parameters"]["capital"]),
                    *[point["value"] for point in job["curve"]],
                ],
                job["completed_returns"],
                365 * 86400 / TIMEFRAMES[job["parameters"]["timeframe"]],
            )
        return self.journal.save(
            job,
            sample={
                "timestamp": now(),
                "price": observed["price"],
                "equity": job["equity"],
                "cash": job["cash"],
                "position": job["quantity"],
            },
        )
