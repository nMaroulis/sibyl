"""Atomic read-schedule nudges; stream messages never become financial observations."""

import json
import time


class OrderWakeups:
    """Expedite enabled healthy REST readers while preserving pauses and failure backoff."""

    def __init__(self, trading):
        self.trading = trading

    def apply(self, db, account_id, targets):
        """Wake exact known orders or a bounded account sweep inside the signal acknowledgment.

        Empty targets means all locally retained tracked orders. Unknown native
        orders need the separately enabled discovery reader. Reconciliation
        continues to validate exact native fill IDs and fees in its own ledger.
        A scheduling receipt does not establish REST completion or coverage.
        """
        counts = {"status": 0, "fills": 0, "discovery": 0}
        rows = db.execute(
            "SELECT id,payload FROM exchange_orders WHERE json_extract(payload,'$.request.connection_id')=? AND json_extract(payload,'$.exchange_order_id') IS NOT NULL ORDER BY rowid DESC LIMIT 5000",
            (account_id,),
        ).fetchall()
        selected = {tuple(item) for item in targets}
        for row in rows:
            intent = json.loads(row["payload"])
            if (
                selected
                and (intent["request"]["symbol"], str(intent.get("exchange_order_id"))) not in selected
            ):
                continue
            if (
                intent.get("tracking")
                and not intent.get("sync_failures")
                and intent["status"] not in {"preview", "closed", "canceled", "expired", "rejected"}
            ):
                intent["next_check"] = 0
                db.execute("UPDATE exchange_orders SET payload=? WHERE id=?", (json.dumps(intent), row["id"]))
                counts["status"] += 1
            job = self.trading.reconciliation._read(db, row["id"])
            if (
                job
                and job.get("enabled")
                and not job.get("failures")
                and job.get("state") not in {"paused", "error"}
            ):
                job["next_attempt"] = 0
                self.trading.reconciliation._write(db, row["id"], job)
                counts["fills"] += 1
        discovery = self.trading.discovery.read(db, account_id)
        if (
            discovery
            and discovery.get("enabled")
            and not discovery.get("failures")
            and discovery.get("state") not in {"paused", "running", "error", "disconnected"}
        ):
            discovery["next_attempt"] = min(discovery.get("next_attempt", time.time()), time.time())
            self.trading.discovery.write(db, discovery)
            counts["discovery"] = 1
        return counts
