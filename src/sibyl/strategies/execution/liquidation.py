"""Bounded sequential exits for one previously stopped exchange strategy."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sibyl.services.trading.lifecycle import TERMINAL
from sibyl.strategies.execution.cancellation import pending_evidence
from sibyl.strategies.execution.contracts import ClosePositionRequest, ExecutionGuard
from sibyl.strategies.execution.controls import require_submissions
from sibyl.strategies.execution.ownership import ledger


def active_plan(db, job_id):
    """Read the one plan that can authorize another sell for this run."""
    row = db.execute(
        "SELECT payload FROM strategy_liquidations WHERE job_id=? AND status='active'", (job_id,)
    ).fetchone()
    return json.loads(row[0]) if row else None


def order_cap(plan):
    """Keep all child sizes within the approved sell quantity, even after rebates."""
    remaining = max(0.0, plan["owned_quantity"] - plan["sold_quantity"])
    cap = plan["first_order_quantity"] if not plan["orders"] else plan["max_order_base"]
    return min(remaining, cap) if cap is not None else remaining


class LiquidationPlans:
    """Keep written intents attached to one explicit price, size and time envelope."""

    def __init__(self, runner):
        self.runner = runner
        self.store, self.journal = runner.store, runner.journal
        self.closing, self.trading = runner.closing, runner.trading
        with self.store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS strategy_liquidations (
                    id TEXT PRIMARY KEY, job_id TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS strategy_active_liquidation
                    ON strategy_liquidations(job_id) WHERE status='active';
                CREATE INDEX IF NOT EXISTS strategy_liquidation_by_job ON strategy_liquidations(job_id);
            """)
            db.execute("BEGIN IMMEDIATE")
            self.interrupt_all(db, "Backend restarted. New sells require a fresh plan approval.")

    @staticmethod
    def _public(plan):
        """Expose bounds and child order references without authority fingerprints."""
        private = {"pin", "ownership_events", "evidence", "control_revision", "credential_version", "sealed"}
        return {key: value for key, value in plan.items() if key not in private}

    @staticmethod
    def _read(db, identity, job_id):
        row = db.execute(
            "SELECT payload FROM strategy_liquidations WHERE id=? AND job_id=?", (identity, job_id)
        ).fetchone()
        if not row:
            raise LookupError("Liquidation plan not found.")
        return json.loads(row[0])

    @staticmethod
    def _save(db, plan):
        db.execute(
            "UPDATE strategy_liquidations SET status=?,payload=? WHERE id=?",
            (plan["status"], json.dumps(plan, allow_nan=False), plan["id"]),
        )

    def _state(self, db, plan, status, message):
        plan.update(status=status, message=message, updated_at=datetime.now(UTC).isoformat())
        self._save(db, plan)
        job = db.execute("SELECT payload FROM strategy_jobs WHERE id=?", (plan["job_id"],)).fetchone()
        event = self.runner.host._event(json.loads(job[0]), "LIQUIDATION", message, liquidation_id=plan["id"])
        db.execute(
            "INSERT INTO strategy_events(job_id,payload) VALUES (?,?)", (plan["job_id"], json.dumps(event))
        )

    def interrupt_all(self, db, message):
        """End pending authority atomically with restart or the global halt."""
        for row in db.execute("SELECT payload FROM strategy_liquidations WHERE status='active'").fetchall():
            self._state(db, json.loads(row[0]), "interrupted", message)

    def stop_active(self, db, job_id, message):
        plan = active_plan(db, job_id)
        if plan:
            self._state(db, plan, "stopped", message)

    def block(self, job_id, message):
        """Remove sell authority when execution evidence cannot be assessed."""
        with self.runner.lock, self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            plan = active_plan(db, job_id)
            if plan:
                self._state(db, plan, "blocked", message)

    def _authority(self, db, job, plan, *, child=False):
        require_submissions(db, plan["control_revision"])
        self.runner.enabled(submissions=False, db=db)
        if job["status"] not in {"stopped", "completed"}:
            raise ExecutionGuard("Liquidation requires a stopped or completed strategy.")
        if self.runner.ownership._credential_version(db, job["connection_id"]) != plan["credential_version"]:
            raise ExecutionGuard("The exchange account credentials changed. Review a new plan.")
        if [event["id"] for event in ledger.events(db, job["id"])] != plan[
            "ownership_events"
        ] or not ledger.current(db, plan["pin"]):
            raise ExecutionGuard("Earlier strategy order or ownership evidence changed. Review a new plan.")
        if child and (
            datetime.now(UTC) + timedelta(seconds=plan["policy"]["order_lifetime_seconds"])
            > datetime.fromisoformat(plan["ends_at"])
        ):
            raise ExecutionGuard("The remaining plan time is shorter than one order lifetime.")

    def view(self, job_id):
        """Return active or most recently authorized plan with local child status."""
        job = self.journal.job(job_id)
        if job.get("mode") != "exchange":
            raise ExecutionGuard("Liquidation applies to exchange strategies.")
        with self.store.db() as db:
            db.execute("BEGIN")
            row = db.execute(
                "SELECT payload FROM strategy_liquidations WHERE job_id=? AND status!='review' "
                "ORDER BY json_extract(payload,'$.authorized_at') DESC,rowid DESC LIMIT 1",
                (job_id,),
            ).fetchone()
            if not row:
                return None
            plan = json.loads(row[0])
            return {
                **self._public(plan),
                "orders": [
                    {key: order.get(key) for key in ("id", "status", "filled", "remaining", "price")}
                    for order in (self.trading.lifecycle.read(db, i) for i in plan["orders"])
                ],
            }

    def preview(self, job_id, request):
        """Review a capped first order; persist consent terms without placing any order."""
        with self.runner.lock:
            self.runner.enabled()
            job = self.journal.job(job_id)
            policy = ClosePositionRequest(
                **request.model_dump(include=set(ClosePositionRequest.model_fields))
            )
            with self.store.db() as db:
                db.execute("BEGIN")
                if active_plan(db, job_id):
                    raise ExecutionGuard("Stop the current liquidation plan first.")
                values, evidence = self.closing._snapshot(job, db)
                account = self.closing._check(values, db)
                seal = {
                    "pin": ledger.pin(db, job),
                    "ownership_events": [event["id"] for event in ledger.events(db, job_id)],
                    "credential_version": self.runner.ownership._credential_version(db, account.id),
                    "control_revision": require_submissions(db)["revision"],
                }
            quote = self.closing._quote(account, values, policy, max_base=request.max_order_base)
            now = datetime.now(UTC)
            plan = {
                "id": uuid4().hex,
                "job_id": job_id,
                "symbol": job["parameters"]["symbol"],
                "environment": job["environment"],
                "account": job["account"],
                "status": "review",
                "message": "Approve this review to authorize the bounded sequence.",
                "max_orders": request.max_orders,
                "max_order_base": request.max_order_base,
                "duration_minutes": request.duration_minutes,
                "policy": policy.model_dump(),
                "minimum_price": quote["limit_price"],
                "owned_quantity": quote["owned_quantity"],
                "first_order_quantity": quote["quantity"],
                "expires_at": (now + timedelta(seconds=90)).isoformat(),
                "confirmation": f"LIQUIDATE {'TEST' if job['sandbox'] else 'LIVE'} {job['parameters']['symbol']} {job_id[:8]}",
                "orders": [],
                "sealed": 0,
                "sold_quantity": 0.0,
                "evidence": evidence,
                **seal,
            }
            with self.store.db() as db:
                db.execute(
                    "INSERT INTO strategy_liquidations VALUES (?,?,?,?)",
                    (plan["id"], job_id, plan["status"], json.dumps(plan, allow_nan=False)),
                )
            return self._public(plan)

    def confirm(self, job_id, identity, confirmation):
        """Accept the exact plan locally. Only the worker can prepare its first native intent."""
        with self.runner.lock, self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            plan = self._read(db, identity, job_id)
            if confirmation != plan["confirmation"]:
                raise ExecutionGuard("Type " + plan["confirmation"] + " to authorize the plan.")
            if plan["status"] != "review":
                return self._public(plan)
            now = datetime.now(UTC)
            if now > datetime.fromisoformat(plan["expires_at"]):
                raise ExecutionGuard("Liquidation review expired. Review a fresh plan.")
            if active_plan(db, job_id):
                raise ExecutionGuard("A liquidation plan is already active on this strategy.")
            job = self.journal.job(job_id)
            values, evidence = self.closing._snapshot(job, db)
            self.closing._check(values, db)
            self._authority(db, job, plan)
            if evidence != plan["evidence"]:
                raise ExecutionGuard("Strategy ownership or order evidence changed. Review a fresh plan.")
            plan.update(
                authorized_at=now.isoformat(),
                ends_at=(now + timedelta(minutes=plan["duration_minutes"])).isoformat(),
            )
            self._state(db, plan, "active", "Liquidation authorized. Waiting for the strategy worker.")
            return self._public(plan)

    def stop(self, job_id, identity):
        """Withdraw future sell authority while retaining existing order expiry and tracking."""
        with self.runner.lock, self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            plan = self._read(db, identity, job_id)
            if plan["status"] == "active":
                self._state(
                    db,
                    plan,
                    "stopped",
                    "Future sells stopped. Any submitted order keeps its approved expiry.",
                )
            return self._public(plan)

    def require_child(self, db, job, plan_id, *, intent=None):
        """Revalidate the live plan in the same transaction as child submission."""
        plan = active_plan(db, job["id"])
        if not plan or plan["id"] != plan_id:
            raise ExecutionGuard("This liquidation plan no longer authorizes a sell.")
        self._authority(db, job, plan, child=True)
        if intent is not None:
            request = intent["request"]
            if (
                not plan["orders"]
                or plan["orders"][-1] != intent["id"]
                or plan["sealed"] != len(plan["orders"]) - 1
                or len(plan["orders"]) > plan["max_orders"]
                or request["side"] != "sell"
                or request["limit_price"] != plan["minimum_price"]
                or request["quantity"] > order_cap({**plan, "orders": plan["orders"][:-1]})
            ):
                raise ExecutionGuard("The native sell falls outside this liquidation approval.")
        return plan

    def link(self, db, job_id, plan_id, intent_id):
        """Record the child intent before it can cross the native write boundary."""
        plan = self._read(db, plan_id, job_id)
        if (
            plan["status"] != "active"
            or plan["sealed"] != len(plan["orders"])
            or len(plan["orders"]) >= plan["max_orders"]
        ):
            raise ExecutionGuard("This liquidation plan cannot prepare another sell.")
        plan["orders"].append(intent_id)
        plan["message"] = "Sell tracked. Waiting for terminal native order and fill evidence."
        self._save(db, plan)

    def _next(self, db, job, plan):
        """Decide whether a further sell may be prepared. No native I/O here."""
        if datetime.now(UTC) >= datetime.fromisoformat(plan["ends_at"]):
            self._state(db, plan, "expired", "Liquidation deadline passed. Remaining units stay owned.")
            return False
        self._authority(db, job, plan)
        if len(plan["orders"]) > plan["sealed"]:
            order = self.trading.lifecycle.read(db, plan["orders"][-1])
            if order.get("strategy_abandoned") or order["status"] in {
                "preview",
                "submitting",
                "unknown",
                "rejected",
            }:
                self._state(
                    db,
                    plan,
                    "interrupted",
                    "A sell was interrupted or uncertain. Review the linked order in Trade.",
                )
                return False
            if order["status"] not in TERMINAL or job["unresolved_orders"] or pending_evidence(db, job["id"]):
                return False
            if job["accounting_incomplete"] or job["unvalued_fees"]:
                self._state(
                    db,
                    plan,
                    "blocked",
                    "Resolve costs or approve new fee prices before reviewing another plan.",
                )
                return False
            if not order.get("filled"):
                self._state(
                    db, plan, "blocked", "The previous sell had no fills. Remaining units stay owned."
                )
                return False
            plan.update(
                pin=ledger.pin(db, job),
                sealed=len(plan["orders"]),
                sold_quantity=plan["sold_quantity"] + order["filled"],
            )
            self._save(db, plan)
        if job["quantity"] <= 1e-12:
            self._state(db, plan, "completed", "The strategy has no remaining owned units.")
            return False
        if order_cap(plan) <= 1e-12 or len(plan["orders"]) >= plan["max_orders"]:
            self._state(
                db, plan, "completed", "Approved order limit reached. Any remaining units stay owned."
            )
            return False
        self._authority(db, job, plan, child=True)
        return True

    def step(self, job):
        """Advance at most one child, through the existing at-most-once close pipeline."""
        with self.runner.lock:
            try:
                with self.store.db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    plan = active_plan(db, job["id"])
                    if not plan:
                        return
                    current = self.journal.job(job["id"])
                    values, _ = self.closing._snapshot(current, db)
                    if not self._next(db, values, plan):
                        return
                policy = ClosePositionRequest(**plan["policy"])
                review = self.closing.preview(job["id"], policy, liquidation_id=plan["id"])
                result = self.closing.confirm(review["id"], review["confirmation"], liquidation_id=plan["id"])
                if result["close_position"]["state"] not in {"interrupted", "unknown", "rejected"}:
                    return
                message = result["close_position"]["message"]
            except Exception as exc:
                message = (
                    str(exc)
                    if isinstance(exc, ExecutionGuard)
                    else "Liquidation could not continue. Review retained orders in the monitor."
                )
            self.block(job["id"], message)
