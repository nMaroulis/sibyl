"""Opt-in polling of retained pending funding; no new history or native writes."""

from uuid import uuid4

from sibyl.services.account_sync import environment
from sibyl.services.funding.contracts import FundingRefreshConflict, refresh_streams
from sibyl.services.funding.journal import RefreshJournal
from sibyl.services.funding.state import account_version
from sibyl.services.funding.worker import AutoFundingWorker


class FundingRefresh(AutoFundingWorker):
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
