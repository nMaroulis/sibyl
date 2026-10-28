"""Opt-in polling of retained pending funding; no new history or native writes."""

import json
import time
from uuid import uuid4

from sibyl.services.account_sync import environment
from sibyl.services.funding.contracts import PAGE_LIMIT, READ_GAP, FundingRefreshConflict, refresh_streams
from sibyl.services.funding.journal import RefreshJournal, account_version
from sibyl.services.import_worker import ImportLimitError, ImportWorker


class FundingRefresh(ImportWorker):
    """Revisit pending records fairly, one bounded page per read slot.

    Controls default off. Enabling explicitly authorizes status reads for retained
    records, not broad discovery. Manual imports keep their independent cursors.
    Deactivation, disconnect or account changes require another explicit enable.
    """

    table = "funding_refresh"
    key_field = "stream"
    limit_message = "Pending-update page budget reached. Review the record and use a manual range rescan."

    def __init__(self, market, store):
        super().__init__(market, store, RefreshJournal(store))

    def configure(self, connection, stream, body):
        """Save version-checked opt-in controls; a manual check retries unresolved records explicitly."""
        if stream not in refresh_streams(connection):
            raise ValueError("Pending funding updates are unavailable for this exchange/environment/stream.")
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            scope = account_version(db, connection.id)
            if not scope:
                raise LookupError("Connection not found.")
            active = db.execute(
                "SELECT 1 FROM active_accounts WHERE account_id=?", (connection.id,)
            ).fetchone()
            if body.enabled and not active:
                raise ValueError("Activate this account before enabling pending updates.")
            job = self.ledger.read_job(db, connection.id, stream)
            if (job["revision"] if job else None) != body.replace_revision:
                raise FundingRefreshConflict("Pending-update controls changed. Reload before saving.")
            if body.check_now and not body.enabled:
                raise ValueError("Enable pending updates before requesting a check.")
            previous = job or {}
            job = {
                "account_id": connection.id,
                "account": connection.label,
                "exchange": connection.exchange,
                "environment": environment(connection),
                "stream": stream,
                "revision": uuid4().hex,
                "enabled": body.enabled,
                "interval_minutes": body.interval_minutes,
                "account_version": scope,
                "status": "idle" if body.enabled else "paused",
                "next_attempt": 0,
                "last_attempt": previous.get("last_attempt", 0),
                "last_checked_at": previous.get("last_checked_at"),
                "last_success_at": previous.get("last_success_at"),
                "checked": previous.get("checked", 0),
                "updated": previous.get("updated", 0),
                "pages": 0,
                "retries": 0,
                "error": None,
                "retry_at": None,
            }
            if body.check_now:
                db.execute(
                    "UPDATE funding_rechecks SET next_attempt=0,missing_checks=0 WHERE event_id IN "
                    "(SELECT id FROM funding_events WHERE account_id=? AND stream=? AND status IN ('pending','restricted','unknown'))",
                    (connection.id, stream),
                )
            self.ledger.write_job(db, job)
        return self.ledger.snapshot()

    def tick(self):
        """Keep the global background read floor across restarts and reuse provider admission/backoff."""
        if self._closed:
            return
        with self.store.db() as db:
            latest = db.execute("SELECT MAX(last_attempt) FROM funding_refresh").fetchone()[0]
        if latest and time.time() < latest + READ_GAP:
            return
        self.ledger.schedule(time.time())
        super().tick()

    def read_page(self, client, job):
        """Read the same reviewed native funding endpoint as a manual import; never submit a movement."""
        if job["pages"] >= PAGE_LIMIT:
            raise ImportLimitError(self.limit_message)
        with self.store.db() as db:
            current = self.ledger.read_job(db, job["account_id"], job["stream"])
            changed = account_version(db, job["account_id"]) != job["account_version"]
        if changed or not current or not current["enabled"] or current["revision"] != job["revision"]:
            if changed:
                self.pause(job["account_id"])
            raise ValueError("The pending-update configuration changed before the native read.")
        return client.fetch_funding_page(job["stream"], job["cursor"], 50)

    def _failure(self, job, error):
        """Discard stale failures and stop a changed account before applying ordinary retry policy."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.ledger.read_job(db, job["account_id"], job["stream"])
            if not current or current["revision"] != job["revision"]:
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
                "SELECT payload FROM funding_refresh WHERE account_id=?"
                + (" AND stream=?" if stream else ""),
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
