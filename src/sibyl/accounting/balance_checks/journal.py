"""Bounded local checkpoint inputs and retained comparison reports; no provider calls."""

import hashlib
import json
from importlib.metadata import version

from sibyl.accounting.balance_checks.contracts import HISTORY_LIMIT, MAX_RECORDS
from sibyl.accounting.funding import FundingReviews
from sibyl.exchanges.providers import CLIENTS


class CheckJournal:
    """Save one checkpoint and the newest twenty reports per account."""

    summary_fields = (
        "id",
        "checkpoint_id",
        "account",
        "environment",
        "observed_at",
        "starting_at",
        "status",
        "differences",
        "incomplete",
    )

    def __init__(self, store):
        self.store = store
        FundingReviews(store)
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS balance_checkpoints(account_id TEXT PRIMARY KEY,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS balance_check_reports(id TEXT PRIMARY KEY,account_id TEXT NOT NULL,payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS balance_check_account ON balance_check_reports(account_id);
            """)

    @staticmethod
    def scope(db, account_id):
        """Fingerprint encrypted credentials and wallet semantics privately; never return the hash."""
        row = db.execute(
            "SELECT exchange,sandbox,credentials FROM connections WHERE id=?", (account_id,)
        ).fetchone()
        if row is None:
            raise LookupError("Saved account no longer exists.")
        provider = CLIENTS.get(row[0])
        values = [row[0], row[1], row[2].hex(), getattr(provider, "balance_params", {}), version("ccxt"), 1]
        return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()

    @staticmethod
    def checkpoint(db, account_id):
        row = db.execute(
            "SELECT payload FROM balance_checkpoints WHERE account_id=?", (account_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def inputs(db, account_id):
        """Read native facts in one bounded SQLite snapshot, preserving all asset/market identities."""
        result = {}
        for table, kind in (("account_fills", "fills"), ("funding_events", "funding")):
            rows = db.execute(
                f"SELECT payload FROM {table} WHERE account_id=? ORDER BY id LIMIT ?",
                (account_id, MAX_RECORDS + 1),
            ).fetchall()
            if len(rows) > MAX_RECORDS:
                raise ValueError("This account exceeds the balance check's 10,000-record per-ledger limit.")
            result[kind] = [json.loads(row[0]) for row in rows]
        result["funding"] = FundingReviews.enrich(db, result["funding"])
        result["imports"] = []
        for table, kind in (("account_sync", "fills"), ("funding_sync", "funding")):
            for row in db.execute(f"SELECT payload FROM {table} WHERE account_id=?", (account_id,)):
                job = json.loads(row[0])
                result["imports"].append(
                    {
                        "kind": kind,
                        "status": job["status"],
                        "caught_up": job["status"] == "caught_up",
                        "selection": job.get("symbol", job.get("stream")),
                    }
                )
        return result

    def state(self, account_id):
        """Expose saved evidence only; keep checkpoint inputs, credential hashes and native metadata private."""
        with self.store.db() as db:
            db.execute("BEGIN")
            checkpoint = self.checkpoint(db, account_id)
            fields = ",".join(f"json_extract(payload,'$.{key}') AS {key}" for key in self.summary_fields)
            history = [
                dict(row)
                for row in db.execute(
                    f"SELECT {fields} FROM balance_check_reports WHERE account_id=? ORDER BY rowid DESC LIMIT ?",
                    (account_id, HISTORY_LIMIT),
                )
            ]
            latest = db.execute(
                "SELECT payload FROM balance_check_reports WHERE account_id=? AND json_extract(payload,'$.checkpoint_id')=? ORDER BY rowid DESC LIMIT 1",
                (account_id, checkpoint["id"] if checkpoint else ""),
            ).fetchone()
            try:
                current_scope = self.scope(db, account_id)
            except LookupError:
                current_scope = None
        public = (
            {
                key: checkpoint[key]
                for key in (
                    "id",
                    "account_id",
                    "account",
                    "exchange",
                    "environment",
                    "observed_at",
                    "wallet_scope",
                )
            }
            if checkpoint
            else None
        )
        return {
            "checkpoint": public,
            "configuration_changed": bool(checkpoint and checkpoint["scope"] != current_scope),
            "latest": json.loads(latest[0]) if latest else None,
            "history": history,
        }

    def report(self, account_id, report_id):
        """Read one historical report, enforcing its account before deserialization."""
        with self.store.db() as db:
            row = db.execute(
                "SELECT payload FROM balance_check_reports WHERE id=? AND account_id=?",
                (report_id, account_id),
            ).fetchone()
        if row is None:
            raise LookupError("Saved balance check not found.")
        return json.loads(row[0])

    def save_report(self, db, report):
        db.execute(
            "INSERT INTO balance_check_reports VALUES(?,?,?)",
            (report["id"], report["account_id"], json.dumps(report, allow_nan=False)),
        )
        db.execute(
            "DELETE FROM balance_check_reports WHERE account_id=? AND id NOT IN "
            "(SELECT id FROM balance_check_reports WHERE account_id=? ORDER BY rowid DESC LIMIT ?)",
            (report["account_id"], report["account_id"], HISTORY_LIMIT),
        )
