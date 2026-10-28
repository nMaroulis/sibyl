"""Explicit rolling funding history reads for new arrivals and completed corrections."""

from uuid import uuid4

from sibyl.services.account_sync import environment
from sibyl.services.funding.contracts import SCAN_PAGE_LIMIT, FundingRefreshConflict, scan_streams
from sibyl.services.funding.scan_journal import ScanJournal
from sibyl.services.funding.state import account_version
from sibyl.services.funding.worker import AutoFundingWorker


class FundingScans(AutoFundingWorker):
    """Discover/recheck a user-chosen recent window while preserving manual import checkpoints."""

    table = "funding_scans"
    key_field = "stream"
    page_limit = SCAN_PAGE_LIMIT
    limit_message = (
        "Recent-history page budget reached. Choose a shorter lookback or use a manual range import."
    )

    def __init__(self, market, store):
        super().__init__(market, store, ScanJournal(store))

    def configure(self, connection, stream, body):
        """Save opt-in window controls; new control revisions discard in-flight old passes."""
        if stream not in scan_streams(connection):
            raise ValueError("Recent funding sync is unavailable for this exchange/environment/stream.")
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            scope = account_version(db, connection.id)
            if not scope:
                raise LookupError("Connection not found.")
            if (
                body.enabled
                and not db.execute(
                    "SELECT 1 FROM active_accounts WHERE account_id=?", (connection.id,)
                ).fetchone()
            ):
                raise ValueError("Activate this account before enabling recent funding sync.")
            previous = self.ledger.read_job(db, connection.id, stream)
            if (previous["revision"] if previous else None) != body.replace_revision:
                raise FundingRefreshConflict("Recent-history controls changed. Reload before saving.")
            if body.check_now and not body.enabled:
                raise ValueError("Enable recent funding sync before requesting a scan.")
            old = previous or {}
            job = {
                "account_id": connection.id,
                "account": connection.label,
                "exchange": connection.exchange,
                "environment": environment(connection),
                "stream": stream,
                "revision": uuid4().hex,
                "enabled": body.enabled,
                "interval_minutes": body.interval_minutes,
                "lookback_days": body.lookback_days,
                "account_version": scope,
                "status": "idle" if body.enabled else "paused",
                "next_attempt": 0,
                "last_attempt": old.get("last_attempt", 0),
                "last_checked_at": old.get("last_checked_at"),
                "covered_start_ms": old.get("covered_start_ms"),
                "covered_end_ms": old.get("covered_end_ms"),
                "last_report": old.get("last_report"),
                "passes": old.get("passes", 0),
                "inserted": old.get("inserted", 0),
                "updated": old.get("updated", 0),
                "pages": 0,
                "retries": 0,
                "error": None,
                "retry_at": None,
            }
            self.ledger.clear_pass(db, connection.id, stream)
            self.ledger.write_job(db, job)
        return self.ledger.snapshot()
