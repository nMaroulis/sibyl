"""Shared read scheduling and account guards for opt-in funding workers."""

import json
import time
from uuid import uuid4

from sibyl.services.funding.contracts import PAGE_LIMIT, READ_GAP
from sibyl.services.funding.state import account_version
from sibyl.services.import_worker import ImportLimitError, ImportWorker


class AutoFundingWorker(ImportWorker):
    """Share persisted read slots fairly; subclasses own their control and pass semantics."""

    page_limit = PAGE_LIMIT

    def __init__(self, market, store, ledger):
        super().__init__(market, store, ledger)
        with store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS funding_auto_read_slot(id INTEGER PRIMARY KEY CHECK(id=1), last_attempt REAL NOT NULL)"
            )
            db.execute("INSERT OR IGNORE INTO funding_auto_read_slot VALUES(1,0)")

    def tick(self):
        """Schedule domain work, then reserve a fair read slot across both automatic workers."""
        if self._closed:
            return
        self.ledger.schedule(time.time())
        if self._claim_read(time.time()):
            super().tick()

    def _claim_read(self, now):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            tables = [
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('funding_refresh','funding_scans')"
                )
            ]
            last = db.execute("SELECT last_attempt FROM funding_auto_read_slot WHERE id=1").fetchone()[0]
            candidates = []
            for table in tables:
                last = max(
                    last, db.execute(f"SELECT COALESCE(MAX(last_attempt),0) FROM {table}").fetchone()[0]
                )
                row = db.execute(
                    f"SELECT last_attempt,account_id,stream FROM {table} WHERE status IN ('queued','retrying') AND next_attempt<=? ORDER BY last_attempt,account_id,stream LIMIT 1",
                    (now,),
                ).fetchone()
                if row:
                    candidates.append((*row, table))
            if now < last + READ_GAP or not candidates or min(candidates)[-1] != self.table:
                return False
            db.execute("UPDATE funding_auto_read_slot SET last_attempt=? WHERE id=1", (now,))
            return True

    def read_page(self, client, job):
        """Read the same reviewed native funding endpoint as a manual import; never submit a movement."""
        if job["pages"] >= self.page_limit:
            raise ImportLimitError(self.limit_message)
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.ledger.read_job(db, job["account_id"], job["stream"])
            invalid = (
                not current
                or not current["enabled"]
                or current["revision"] != job["revision"]
                or current.get("run_id") != job.get("run_id")
            )
            if not invalid:
                scope = account_version(db, job["account_id"])
                active = db.execute(
                    "SELECT 1 FROM active_accounts WHERE account_id=?", (job["account_id"],)
                ).fetchone()
                if scope != current["account_version"] or not active:
                    current.update(
                        enabled=False,
                        status="paused" if scope else "disconnected",
                        revision=uuid4().hex,
                        error="Account configuration or activation changed; the queued read was discarded.",
                    )
                    self.ledger.write_job(db, current)
                    invalid = True
        if invalid:
            raise ValueError("The funding-update configuration changed before the native read.")
        return client.fetch_funding_page(job["stream"], job["cursor"], 50)

    def _failure(self, job, error):
        """Discard stale failures and stop a changed account before applying ordinary retry policy."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.ledger.read_job(db, job["account_id"], job["stream"])
            if (
                not current
                or current["revision"] != job["revision"]
                or current.get("run_id") != job.get("run_id")
            ):
                return
            scope = account_version(db, job["account_id"])
            active = db.execute(
                "SELECT 1 FROM active_accounts WHERE account_id=?", (job["account_id"],)
            ).fetchone()
            if scope != current["account_version"] or not active:
                current.update(
                    enabled=False,
                    status="paused" if scope else "disconnected",
                    revision=uuid4().hex,
                    error="Account configuration or activation changed; the failed read was discarded.",
                )
                self.ledger.write_job(db, current)
                return
        super()._failure(job, error)

    def pause(self, account_id, stream=None, *, disconnected=False):
        """Disable and invalidate in-flight checks without changing retained funding facts."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                f"SELECT payload FROM {self.table} WHERE account_id=?" + (" AND stream=?" if stream else ""),
                (account_id, stream) if stream else (account_id,),
            ).fetchall()
            for row in rows:
                job = json.loads(row[0])
                job.update(
                    enabled=False,
                    status="disconnected" if disconnected else "paused",
                    revision=uuid4().hex,
                    next_attempt=0,
                )
                self.ledger.write_job(db, job)
