"""Approve immutable historical fee marks without an exchange write or run restart."""

import json
import math
from datetime import UTC, datetime

from sibyl.strategies.execution.accounting import project
from sibyl.strategies.execution.cancellation import pending_evidence
from sibyl.strategies.execution.contracts import ExecutionGuard
from sibyl.strategies.execution.fees import price_unreviewed
from sibyl.strategies.execution.ownership.ledger import digest
from sibyl.strategies.execution.performance import read_job

REVIEW_SIZE = 25


class StrategyFeeReviews:
    """Accept one bounded set of date-, source- and fill-bound estimates atomically."""

    def __init__(self, runner):
        self.runner = runner
        self.store = runner.store
        with self.store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS strategy_fee_values (
                    job_id TEXT NOT NULL, fill_id TEXT NOT NULL, fee_version TEXT NOT NULL,
                    review_id TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(job_id,fill_id,fee_version)
                );
                CREATE INDEX IF NOT EXISTS strategy_fee_review ON strategy_fee_values(job_id,review_id);
            """)

    def _preview(self, db, job):
        state = project(job, self.runner.trading, db=db)
        entries = state["_foreign_fees"]
        pending = [entry for entry in entries if not entry["receipt"]]
        result = {
            "run_id": job["id"],
            "source": job["source"],
            "environment": job["environment"],
            "quote": job["parameters"]["symbol"].split("/")[1],
            "pending_count": len(pending),
            "approved_count": len(entries) - len(pending),
            "approved_quote": state["foreign_fees_quote"],
            "review_id": None,
            "rows": [],
            "reason": None,
        }
        if not pending:
            return result
        if job["status"] == "running":
            return {**result, "reason": "Pause the run before reviewing fee prices."}
        if state["unresolved_orders"] or pending_evidence(db, job["id"]):
            return {**result, "reason": "Reconcile native orders and finish cancellation follow-ups first."}
        if state["_native_costs_incomplete"]:
            return {**result, "reason": "Resolve missing native costs or fees before reviewing prices."}
        try:
            prices = price_unreviewed(db, job, pending[:REVIEW_SIZE])
        except ValueError as error:
            return {**result, "reason": str(error)}
        values = [row["quote_fee"] for fill in prices for row in fill["rows"]]
        approved = [
            row["quote_fee"] for entry in entries if entry["receipt"] for row in entry["receipt"]["rows"]
        ]
        if any(value is None for value in values):
            result["reason"] = (
                "Import eligible closed candles on this account’s exact market feed for the missing fee pairs."
            )
        else:
            combined = approved + values
            try:
                batch = math.fsum(values)
                total = math.fsum(combined)
                reserve = math.fsum(max(value, 0) for value in combined)
            except OverflowError:
                total = reserve = math.inf
            if math.isfinite(total) and math.isfinite(reserve):
                result["review_id"] = digest([job["id"], job["source"], job["environment"], prices])
                result["batch_quote"] = batch
            else:
                result["reason"] = "Fee values exceed the supported range."
        result["rows"] = prices
        return result

    def preview(self, identity):
        """Read reviewable estimates from the native ledger and local candles."""
        with self.store.db() as db:
            db.execute("BEGIN")
            return self._preview(db, read_job(db, identity))

    def receipt(self, identity, review_id):
        """Return the original evidence, including after native fee corrections."""
        with self.store.db() as db:
            db.execute("BEGIN")
            job = read_job(db, identity)
            rows = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT payload FROM strategy_fee_values WHERE job_id=? AND review_id=? ORDER BY rowid",
                    (identity, review_id),
                )
            ]
            if not rows:
                raise LookupError("Fee pricing receipt not found.")
            return {
                "review_id": review_id,
                "source": job["source"],
                "environment": job["environment"],
                "quote": job["parameters"]["symbol"].split("/")[1],
                "approved_at": rows[0]["approved_at"],
                "rows": rows,
            }

    def approve(self, identity, review_id):
        """Recheck exact evidence, then save the reviewed batch and journal event together."""
        with self.runner.lock, self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            job = read_job(db, identity)
            previous = db.execute(
                "SELECT 1 FROM strategy_fee_values WHERE job_id=? AND review_id=?", (identity, review_id)
            ).fetchone()
            if previous:
                return {"review_id": review_id, "saved": True}
            review = self._preview(db, job)
            if not review["review_id"] or review["review_id"] != review_id:
                raise ExecutionGuard(
                    review["reason"] or "Fee review changed. Read the current evidence again."
                )
            stamp = datetime.now(UTC).isoformat()
            for fill in review["rows"]:
                receipt = {**fill, "review_id": review_id, "approved_at": stamp}
                db.execute(
                    "INSERT INTO strategy_fee_values VALUES (?,?,?,?,?)",
                    (
                        identity,
                        fill["fill_id"],
                        fill["fee_version"],
                        review_id,
                        json.dumps(receipt, allow_nan=False),
                    ),
                )
            event = self.runner.host._event(
                job,
                "FEE_VALUATION",
                f"Approved historical fee values for {len(review['rows'])} native fills.",
                fee_review_id=review_id,
            )
            db.execute(
                "INSERT INTO strategy_events(job_id,payload) VALUES(?,?)",
                (identity, json.dumps(event, allow_nan=False)),
            )
        return {"review_id": review_id, "saved": True}
