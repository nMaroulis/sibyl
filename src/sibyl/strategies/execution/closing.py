"""One reviewed strategy exit, using the shared native order and fill pipeline.

No closing order is queued for replay. Scope and ledger evidence are checked
again inside the transaction that commits submission. Every later exit needs a
fresh review, including residual units after a partial fill or venue size cap.
"""

import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sibyl.models import ExchangeOrderRequest
from sibyl.services.order_lifecycle import TERMINAL
from sibyl.strategies.execution.accounting import project
from sibyl.strategies.execution.cancellation import pending_evidence
from sibyl.strategies.execution.contracts import ClosePositionRequest, ExecutionGuard
from sibyl.strategies.execution.venue import is_dust, order_book, order_size


def now():
    return datetime.now(UTC).isoformat()


class ClosePositions:
    """Review, submit once, and report a stopped run's explicitly approved exit."""

    def __init__(self, runner):
        self.runner, self.trading = runner, runner.trading
        self.store, self.journal = runner.store, runner.journal
        with self.store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS strategy_close_reviews(id TEXT PRIMARY KEY,payload TEXT NOT NULL)"
            )
            # A prepared exit never passed the shared submitting boundary. Do
            # not replay it after restart, even if its review had been approved.
            for row in db.execute(
                "SELECT payload FROM exchange_orders WHERE json_extract(payload,'$.strategy_action')='close' "
                "AND json_extract(payload,'$.status')='preview'"
            ).fetchall():
                intent = json.loads(row[0])
                intent.update(strategy_abandoned=True, tracking=False)
                self.trading.lifecycle.write(db, intent)

    @staticmethod
    def _scope(job):
        return [job.get(key) for key in ("connection_id", "exchange", "sandbox")] + [
            job["parameters"]["symbol"]
        ]

    def _snapshot(self, job, db, ignore=None):
        """Read ownership and its approval digest from one coherent ledger snapshot."""
        values = {**job, **project(job, self.trading, db=db)}
        values["unresolved_orders"] = [row for row in values["unresolved_orders"] if row["id"] != ignore]
        evidence = {
            key: values[key]
            for key in (
                "quantity",
                "cash",
                "entry_cost",
                "realized_pnl",
                "fee_assets",
                "accounting_incomplete",
                "unvalued_fees",
                "unresolved_orders",
                "_native_fills",
            )
        }
        digest = hashlib.sha256(json.dumps([self._scope(job), evidence], sort_keys=True).encode()).hexdigest()
        return values, digest

    def _account(self, job):
        """One-off reviewed exits need live-order permission, not strategy-submission permission."""
        if not self.runner.market.settings.allow_live_trading:
            raise ExecutionGuard("Enable SIBYL_ALLOW_LIVE_TRADING on the backend before reviewing an exit.")
        connection = self.runner.account(job["connection_id"])
        if (connection.exchange, connection.sandbox) != (job["exchange"], job["sandbox"]):
            raise ExecutionGuard("The account environment changed. No exit is allowed.")
        return connection

    def _check(self, job, db, ignore=None):
        """Require stopped submissions and reconciled ownership before any exit approval."""
        if job.get("mode") != "exchange":
            raise ExecutionGuard("Position closing applies only to exchange strategies.")
        if job["status"] not in {"stopped", "completed"}:
            raise ExecutionGuard(
                "Use Stop & cancel orders first, then wait for native order and fill reconciliation."
            )
        if job["unresolved_orders"]:
            raise ExecutionGuard(
                "Resolve outstanding or uncertain orders and reconcile their native fills in Trade first."
            )
        if job["accounting_incomplete"] or job["unvalued_fees"]:
            raise ExecutionGuard(
                "Native costs and fees must be complete and valued in the pair's base/quote assets before closing."
            )
        if job["quantity"] <= 1e-12:
            raise ExecutionGuard("This strategy has no retained position to close.")
        if pending_evidence(db, job["id"], ignore=ignore):
            raise ExecutionGuard(
                "Wait for cancellation reconciliation and all three late native status checks in the monitor."
            )
        return self._account(job)

    def context(self, identity):
        """Explain readiness using local evidence only; no exchange or order mutation."""
        job = self.journal.job(identity)
        if job.get("mode") != "exchange":
            raise ExecutionGuard("Position closing applies only to exchange strategies.")
        with self.store.db() as db:
            db.execute("BEGIN")
            values, _ = self._snapshot(job, db)
            reason = None
            try:
                self._check(values, db)
            except ExecutionGuard as error:
                reason = str(error)
        return {
            "ready": reason is None,
            "reason": reason,
            "quantity": values["quantity"],
            "account": job["account"],
            "exchange": job["exchange"],
            "environment": job["environment"],
            "symbol": job["parameters"]["symbol"],
            "status": job["status"],
            "close_position": job.get("close_position"),
        }

    def _quote(self, connection, values, policy, *, fixed=None):
        """Size within owned units, native maxima and a conservative base-fee reserve."""
        symbol = values["parameters"]["symbol"]
        base = symbol.split("/")[0]
        try:
            with self.runner.market.adapter(connection) as client:
                client.load_markets()
                observed = order_book(client, symbol)
                if observed["spread_bps"] > policy.max_spread_bps:
                    raise ExecutionGuard("The current spread exceeds this exit's reviewed limit.")
                full_value = values["quantity"] * observed["ask"]
                if not math.isfinite(full_value):
                    raise ExecutionGuard("The strategy position cannot be valued for a finite exit.")
                if fixed is None:
                    quantity, price = order_size(
                        client,
                        {
                            **values,
                            "risk": {**policy.model_dump(), "max_order_quote": full_value},
                        },
                        observed,
                        "sell",
                    )
                else:
                    quantity, price = fixed["quantity"], fixed["limit_price"]
                for field, amount in (("amount", quantity), ("price", price), ("cost", quantity * price)):
                    limits = (client.market(symbol).get("limits") or {}).get(field) or {}
                    if (limits.get("min") is not None and amount < limits["min"]) or (
                        limits.get("max") is not None and amount > limits["max"]
                    ):
                        raise ExecutionGuard(
                            "The exit is outside current native size/price limits. Fee-reserved dust may be too small to trade."
                        )
                reserve = quantity * policy.fee_reserve_bps / 10000
                available = float(client.fetch_balance().get("free", {}).get(base) or 0)
                if not math.isfinite(available) or available + 1e-12 < quantity + reserve:
                    raise ExecutionGuard(
                        f"Not enough free {base} for the reviewed exit and base-fee reserve. Resolve account balances in Trade."
                    )
                residual = max(0, values["quantity"] - quantity)
                dust = is_dust(client, symbol, residual, observed["bid"])
            return {
                "quantity": quantity,
                "limit_price": price,
                "reference_bid": observed["bid"],
                "spread_bps": observed["spread_bps"],
                "owned_quantity": values["quantity"],
                "base_fee_reserve": reserve,
                "proceeds_before_fees": quantity * price,
                "quote_fee_allowance": quantity * price * policy.fee_reserve_bps / 10000,
                "residual_before_fees": residual,
                "residual_is_dust": dust,
            }
        except ExecutionGuard:
            raise
        except Exception as error:
            raise ExecutionGuard(
                "Could not verify the native exit book, precision and free funds. Check account access and tradable minimums."
            ) from error

    def preview(self, identity, policy: ClosePositionRequest):
        """Save a 60-second fixed sell review without stopping, canceling or placing an order."""
        with self.runner.lock:
            job = self.journal.job(identity)
            with self.store.db() as db:
                db.execute("BEGIN")
                values, digest = self._snapshot(job, db)
                connection = self._check(values, db)
            quote = self._quote(connection, values, policy)
            review = {
                "id": uuid4().hex,
                "job_id": identity,
                "scope": self._scope(job),
                "account": job["account"],
                "exchange": job["exchange"],
                "environment": job["environment"],
                "symbol": job["parameters"]["symbol"],
                "policy": policy.model_dump(),
                "evidence": digest,
                **quote,
                "created_at": now(),
                "expires_at": (datetime.now(UTC) + timedelta(seconds=60)).isoformat(),
                "confirmation": f"CLOSE {'TEST' if job['sandbox'] else 'LIVE'} {job['parameters']['symbol']} {identity[:8]}",
            }
            with self.store.db() as db:
                db.execute(
                    "INSERT INTO strategy_close_reviews VALUES(?,?)", (review["id"], json.dumps(review))
                )
            return review

    def confirm(self, identity, confirmation):
        """Submit this exact approved sell once; repeated calls only return retained state."""
        with self.runner.lock:
            with self.store.db() as db:
                row = db.execute(
                    "SELECT payload FROM strategy_close_reviews WHERE id=?", (identity,)
                ).fetchone()
            if row is None:
                raise LookupError("Close position review not found.")
            review = json.loads(row[0])
            if confirmation != review["confirmation"]:
                raise ExecutionGuard("Type " + review["confirmation"] + " to approve this exit.")
            job = self.journal.job(review["job_id"])
            if review.get("intent_id"):
                self._abandon_prepared(review["intent_id"])
                return self.journal.save(self.runner._project(job))
            if datetime.now(UTC) > datetime.fromisoformat(review["expires_at"]):
                raise ExecutionGuard("Exit review expired. Review a fresh exit.")
            policy = ClosePositionRequest(**review["policy"])

            def validate(db, intent=None):
                if datetime.now(UTC) > datetime.fromisoformat(review["expires_at"]):
                    raise ExecutionGuard("Exit review expired. Review a fresh exit.")
                current = self.journal.job(job["id"])
                values, digest = self._snapshot(current, db, intent["id"] if intent else None)
                connection = self._check(values, db, intent["id"] if intent else None)
                if self._scope(current) != review["scope"] or digest != review["evidence"]:
                    raise ExecutionGuard(
                        "Strategy ownership or order evidence changed. Review the exit again."
                    )
                if review["quantity"] * (1 + policy.fee_reserve_bps / 10000) > values["quantity"] + 1e-12:
                    raise ExecutionGuard(
                        "The reviewed quantity and fee reserve exceed current strategy ownership."
                    )
                return connection, values

            with self.store.db() as db:
                db.execute("BEGIN")
                connection, values = validate(db)
            self._quote(connection, values, policy, fixed=review)
            try:
                intent = self.trading.preview(
                    ExchangeOrderRequest(
                        connection_id=job["connection_id"],
                        symbol=review["symbol"],
                        side="sell",
                        quantity=review["quantity"],
                        order_type="limit",
                        limit_price=review["limit_price"],
                        idempotency_key="strategy-close-" + identity,
                    ),
                    strategy_job_id=job["id"],
                    strategy_close_review_id=identity,
                    strategy_expiry_seconds=policy.order_lifetime_seconds,
                )
            except Exception as error:
                raise ExecutionGuard(
                    "The exchange order preview could not be verified. Review account funds, native limits and this exit again."
                ) from error
            with self.trading.lifecycle.lock(intent["id"]):
                if intent.get("strategy_abandoned"):
                    raise ExecutionGuard("This prepared exit was interrupted. Create a fresh review.")
                review["intent_id"] = intent["id"]
                job["close_position"] = {
                    "review_id": identity,
                    "intent_id": intent["id"],
                    "state": "approved",
                    "message": "Exit approved; native submission is not yet confirmed.",
                    "checked_at": now(),
                }
                event = self.runner.host._event(
                    job,
                    "CLOSE_APPROVED",
                    job["close_position"]["message"],
                    order_id=intent["id"],
                    close_review_id=identity,
                )
                with self.store.db() as db:
                    db.execute(
                        "UPDATE strategy_close_reviews SET payload=? WHERE id=?",
                        (json.dumps(review), identity),
                    )
                    db.execute("UPDATE strategy_jobs SET payload=? WHERE id=?", (json.dumps(job), job["id"]))
                    db.execute(
                        "INSERT INTO strategy_events(job_id,payload) VALUES(?,?)",
                        (job["id"], json.dumps(event)),
                    )
                try:
                    self.trading.execute(
                        intent["id"],
                        intent["confirmation"],
                        strategy_job_id=job["id"],
                        before_submit=validate,
                    )
                except Exception as error:
                    self._abandon_prepared(intent["id"])
                    self.journal.save(self.runner._project(self.journal.job(job["id"])))
                    if isinstance(error, ExecutionGuard):
                        raise
                    raise ExecutionGuard(
                        "Exit submission was interrupted. Inspect the retained order; no write will be replayed."
                    ) from error
                return self.journal.save(self.runner._project(self.journal.job(job["id"])))

    def _abandon_prepared(self, identity):
        """Only a still-unsent preview can be discarded; native attempts remain observable."""
        with self.trading.lifecycle.lock(identity), self.store.db() as db:
            intent = self.trading.lifecycle.read(db, identity)
            if intent["status"] == "preview":
                intent.update(strategy_abandoned=True, tracking=False)
                self.trading.lifecycle.write(db, intent)

    def progress(self, job):
        """Project the latest exit locally; fills, not acknowledgments, change ownership."""
        previous = job.get("close_position")
        if not previous:
            return
        with self.store.db() as db:
            intent = self.trading.lifecycle.read(db, previous["intent_id"])
        if intent.get("strategy_abandoned") or intent["status"] == "preview":
            state, message = "interrupted", "Prepared exit was not submitted. A fresh review is required."
        elif intent["status"] == "rejected" and not intent.get("exchange_order_id"):
            state, message = "rejected", "Native exit was rejected. Resolve the cause before a fresh review."
        elif intent["status"] in {"unknown", "submitting"}:
            state, message = (
                "unknown",
                "Exit outcome is uncertain. Inspect its client/native ID in Trade; this write is never automatically repeated.",
            )
        elif intent["status"] not in TERMINAL:
            state, message = (
                "submitted",
                "Native exit remains open; partial executions are retained. No replacement or additional sell is automatic.",
            )
        elif any(row["id"] == intent["id"] for row in job["unresolved_orders"]):
            state, message = (
                "reconciling",
                "Native exit is terminal; waiting for matching fill and fee evidence.",
            )
        else:
            state, message = (
                "reconciled",
                "Exit fills currently reconcile. Remaining units stay owned; any further sell needs a fresh review.",
            )
        job["close_position"] = {
            **previous,
            "state": state,
            "message": message,
            "checked_at": now(),
            "native_status": intent["status"],
            "filled": intent.get("filled"),
            "requested": intent["request"]["quantity"],
            "remaining_position": job["quantity"],
        }
        if (state, message) != (previous.get("state"), previous.get("message")):
            self.journal.save(
                job,
                self.runner.host._event(
                    job,
                    "CLOSE_" + state.upper(),
                    message,
                    order_id=intent["id"],
                    close_review_id=previous["review_id"],
                ),
            )
