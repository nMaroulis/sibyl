"""Persist opt-in Bitcoin outpoint checks and retain changes in the local inbox."""

import json
from datetime import UTC, datetime
from threading import Lock
from time import time
from uuid import uuid4

from sibyl.blockchain.bitcoin import BitcoinUnavailable
from sibyl.blockchain.identifiers import txid

WATCH_LIMIT = 25
CHECK_INTERVAL = 120


class WatchConflict(ValueError):
    """A watch control was submitted against an older revision."""


def iso(value):
    """Format an optional persisted scheduling timestamp for the API."""
    return datetime.fromtimestamp(value, UTC).isoformat() if value is not None else None


def evidence(report, index):
    """Keep exact output and inclusion evidence, independent of confirmation depth."""
    output = next((item for item in report["items"] if item["index"] == index), None)
    if output is None:
        raise LookupError("The indexer did not return this output.")
    if output["state"] == "unknown":
        raise BitcoinUnavailable("The indexer returned incomplete spending details.")
    parent, spender = report["parent_status"], output["status"] or {}
    if spender.get("confirmed") and (
        not parent["confirmed"] or spender["block_height"] < parent["block_height"]
    ):
        raise BitcoinUnavailable("The indexer returned inconsistent inclusion details.")
    return {
        "observed_at": report["observed_at"],
        "value_sats": output["value_sats"],
        "state": output["state"],
        "spending_txid": output["spending_txid"],
        "spending_input_index": output["spending_input_index"],
        "spending_block_hash": spender.get("block_hash"),
        "spending_block_height": spender.get("block_height"),
        "parent_block_hash": parent["block_hash"],
        "parent_block_height": parent["block_height"],
    }


def observed_changes(previous, current):
    """Compare reliable checkpoints without generating notices as chain depth grows."""
    changes = []
    if previous["parent_block_hash"] != current["parent_block_hash"]:
        changes.append("Parent inclusion changed")
    reference = ("spending_txid", "spending_input_index")
    if any(previous[key] != current[key] for key in reference):
        changes.append("Output spend changed")
    elif previous["spending_block_hash"] != current["spending_block_hash"]:
        changes.append("Spender inclusion changed")
    return changes


class BitcoinWatches:
    """Schedule bounded public reads and fence in-flight checks against local controls."""

    def __init__(self, store, explorer, *, clock=time, recovery_required=False):
        self.store = store
        self.explorer = explorer
        self.clock = clock
        self.recovery_required = recovery_required
        self.polling = Lock()
        self.live_retry_at = 0
        with store.db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS bitcoin_watches (
                id TEXT PRIMARY KEY, transaction_id TEXT NOT NULL, output_index INTEGER NOT NULL,
                demo INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1,
                revision INTEGER NOT NULL DEFAULT 1, cycle INTEGER NOT NULL DEFAULT 0,
                next_check REAL, checked_at REAL, created_at REAL NOT NULL,
                failures INTEGER NOT NULL DEFAULT 0, error TEXT, observation TEXT,
                UNIQUE(transaction_id,output_index,demo)
            )""")

    @staticmethod
    def _view(row):
        data = dict(row)
        data["demo"] = bool(data["demo"])
        data["active"] = bool(data["active"])
        data["observation"] = json.loads(data["observation"]) if data["observation"] else None
        for key in ("created_at", "checked_at", "next_check"):
            data[key] = iso(data[key])
        return data

    def list(self):
        """Read local watch status and the last reliable evidence for each output."""
        with self.store.db() as db:
            rows = db.execute("SELECT * FROM bitcoin_watches ORDER BY created_at DESC,id").fetchall()
        return {
            "items": [self._view(row) for row in rows],
            "limit": WATCH_LIMIT,
            "recovery_required": self.recovery_required,
        }

    def create(self, identity, index, demo):
        """Subscribe locally; the initial provider observation is taken by the worker."""
        if type(index) is not int or not 0 <= index <= 9999:
            raise ValueError("Choose an output index from 0 to 9,999.")
        if self.recovery_required:
            raise WatchConflict("Complete workspace recovery before starting Bitcoin watches.")
        identity = txid(identity)
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM bitcoin_watches WHERE transaction_id=? AND output_index=? AND demo=?",
                (identity, index, demo),
            ).fetchone()
            if row is not None:
                return self._view(row)
            if db.execute("SELECT COUNT(*) FROM bitcoin_watches").fetchone()[0] >= WATCH_LIMIT:
                raise ValueError(f"Remove an existing watch before adding more than {WATCH_LIMIT}.")
            now, watch_id = self.clock(), uuid4().hex
            db.execute(
                "INSERT INTO bitcoin_watches(id,transaction_id,output_index,demo,next_check,created_at) VALUES(?,?,?,?,?,?)",
                (watch_id, identity, index, demo, now, now),
            )
            return self._view(db.execute("SELECT * FROM bitcoin_watches WHERE id=?", (watch_id,)).fetchone())

    def control(self, watch_id, action, revision):
        """Pause, resume or remove a watch while retaining previously published notices."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM bitcoin_watches WHERE id=?", (watch_id,)).fetchone()
            if row is None:
                raise LookupError("Bitcoin watch not found.")
            if row["revision"] != revision:
                raise WatchConflict("The watch changed. Refresh it before trying again.")
            if action == "remove":
                db.execute("DELETE FROM bitcoin_watches WHERE id=?", (watch_id,))
                return {"removed": True}
            active = action == "resume"
            if active and self.recovery_required:
                raise WatchConflict("Complete workspace recovery before resuming Bitcoin watches.")
            if active != bool(row["active"]):
                next_check = max(self.clock(), (row["checked_at"] or 0) + CHECK_INTERVAL) if active else None
                db.execute(
                    """UPDATE bitcoin_watches SET active=?,next_check=?,revision=revision+1,
                        failures=0 WHERE id=?""",
                    (active, next_check, watch_id),
                )
            return self._view(db.execute("SELECT * FROM bitcoin_watches WHERE id=?", (watch_id,)).fetchone())

    def tick(self):
        """Check one due outpoint; a missing or indeterminate read preserves the last checkpoint."""
        if self.recovery_required or not self.polling.acquire(blocking=False):
            return
        try:
            now = self.clock()
            with self.store.db() as db:
                row = db.execute(
                    """SELECT * FROM bitcoin_watches WHERE active=1 AND next_check<=?
                        AND (demo=1 OR ?) ORDER BY next_check,created_at,id LIMIT 1""",
                    (now, now >= self.live_retry_at),
                ).fetchone()
            if row is not None:
                self._check(row)
        finally:
            self.polling.release()

    def _check(self, row):
        current = error = None
        try:
            report = self.explorer.output_spends(
                row["transaction_id"], simulated=bool(row["demo"]), output_offset=row["output_index"]
            )
            current = evidence(report, row["output_index"])
        except LookupError:
            error = "This transaction output was not found by the selected source."
        except BitcoinUnavailable as exc:
            error = str(exc)
            if exc.status == 429 and not row["demo"]:
                self.live_retry_at = self.clock() + CHECK_INTERVAL

        now = self.clock()
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            failures = min(row["failures"] + 1, 5) if error else 0
            updated = db.execute(
                """UPDATE bitcoin_watches SET checked_at=?,next_check=?,error=?,failures=?,
                    observation=COALESCE(?,observation)
                    WHERE id=? AND active=1 AND revision=? AND next_check=?""",
                (
                    now,
                    now + min(CHECK_INTERVAL * 2**failures, 1800),
                    error,
                    failures,
                    json.dumps(current) if current else None,
                    row["id"],
                    row["revision"],
                    row["next_check"],
                ),
            )
            if updated.rowcount and current and row["observation"]:
                previous = json.loads(row["observation"])
                changes = observed_changes(previous, current)
                if changes:
                    self._notify(db, row, previous, current, changes, now)

    @staticmethod
    def _notify(db, row, previous, current, changes, now):
        cycle = row["cycle"] + 1
        payload = {
            "kind": "bitcoin",
            "rule_id": row["id"],
            "rule_revision": row["revision"],
            "cycle": cycle,
            "label": f"Bitcoin output #{row['output_index']}",
            "transaction_id": row["transaction_id"],
            "output_index": row["output_index"],
            "source": "demo" if row["demo"] else "mempool.space",
            "source_label": "Demo" if row["demo"] else "mempool.space",
            "environment": "demo" if row["demo"] else "bitcoin-mainnet",
            "observed_at": current["observed_at"],
            "changes": changes,
            "previous": previous,
            "current": current,
        }
        db.execute("UPDATE bitcoin_watches SET cycle=? WHERE id=?", (cycle, row["id"]))
        db.execute(
            "INSERT INTO alert_notifications(id,rule_id,cycle,created_at,payload) VALUES(?,?,?,?,?)",
            (uuid4().hex, row["id"], cycle, iso(now), json.dumps(payload)),
        )
