"""Read-only reviews for the separate, typed Stop & cancel operation."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sibyl.services.order_lifecycle import TERMINAL
from sibyl.strategies.execution.contracts import ExecutionGuard


class StopCancellationReviews:
    """Stop future submissions atomically; the durable worker handles cancellation."""

    def __init__(self, runner):
        self.runner, self.store = runner, runner.store
        with self.store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS strategy_stop_reviews(id TEXT PRIMARY KEY,payload TEXT NOT NULL)"
            )

    def preview(self, identity):
        """Inspect one run locally, without canceling orders or changing its status."""
        with self.runner.lock:
            job = self.runner.journal.job(identity)
            if job.get("mode") != "exchange":
                raise ExecutionGuard("Stop & cancel applies only to exchange strategies.")
            review = {
                "id": uuid4().hex,
                "job_id": identity,
                "account": job["account"],
                "exchange": job["exchange"],
                "environment": job["environment"],
                "connection_id": job["connection_id"],
                "symbol": job["parameters"]["symbol"],
                "quantity": job["quantity"],
                "orders": [
                    {
                        key: order.get(key)
                        for key in (
                            "id",
                            "status",
                            "exchange_order_id",
                            "filled",
                            "remaining",
                            "cancel_state",
                        )
                    }
                    for order in self.runner.cancellations.orders(identity)
                    if order["status"] not in TERMINAL
                ],
                "confirmation": f"STOP AND CANCEL {'TEST' if job['sandbox'] else 'LIVE'} {job['parameters']['symbol']} {identity[:8]}",
                "expires_at": (datetime.now(UTC) + timedelta(minutes=2)).isoformat(),
            }
            with self.store.db() as db:
                db.execute(
                    "INSERT INTO strategy_stop_reviews VALUES(?,?)", (review["id"], json.dumps(review))
                )
            return review

    def confirm(self, review_id, confirmation):
        """Authorize this fixed run, including orders finishing submission before Stop commits."""
        with self.runner.lock:
            with self.store.db() as db:
                row = db.execute(
                    "SELECT payload FROM strategy_stop_reviews WHERE id=?", (review_id,)
                ).fetchone()
            if row is None:
                raise LookupError("Stop & cancel review not found.")
            review = json.loads(row[0])
            if confirmation != review["confirmation"]:
                raise ExecutionGuard("Type " + review["confirmation"] + " to approve.")
            job = self.runner.journal.job(review["job_id"])
            if job.get("stop_cancellation"):
                return self.runner._project(job)
            if datetime.now(UTC) > datetime.fromisoformat(review["expires_at"]):
                raise ExecutionGuard("Stop & cancel review expired. Review this run again.")
            if job.get("mode") != "exchange" or (
                job["connection_id"],
                job["exchange"],
                job["environment"],
                job["parameters"]["symbol"],
            ) != (review["connection_id"], review["exchange"], review["environment"], review["symbol"]):
                raise ExecutionGuard("The strategy scope changed. Review it again.")
            job.update(
                status="stopped",
                stopped_at=datetime.now(UTC).isoformat(),
                updated_at=datetime.now(UTC).isoformat(),
                stop_cancellation={"review_id": review_id, "requested_at": datetime.now(UTC).isoformat()},
            )
            return self.runner.journal.save(
                job,
                self.runner.host._event(
                    job,
                    "STOP_CANCEL",
                    "New submissions stopped permanently. This run's outstanding orders are queued for cancellation; fills and holdings remain owned. Cancellation is not yet confirmed.",
                ),
            )
