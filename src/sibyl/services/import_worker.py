"""One-page import scheduling shared by fills and read-only funding history."""

import json
import threading
import time
from datetime import UTC, datetime

import ccxt

from sibyl.market_data.control import ProviderDeferred
from sibyl.services.ledger import now_iso


class ImportLimitError(ValueError):
    """A reviewed import budget was reached; request a narrower scope."""


class ImportWorker:
    """Serialize persisted page reads and contain provider failures without replaying writes.

    Subclasses supply a fixed database table/key, ledger and provider page reader.
    This workspace deliberately runs one API worker. Each page and checkpoint
    commit together in the ledger; concurrent pause/disconnect survives the commit.
    """

    table = "account_sync"
    key_field = "symbol"
    limit_message = "Import budget reached. Pause this stream and choose a smaller date range."

    def __init__(self, market, store, ledger):
        self.market, self.store, self.ledger = market, store, ledger
        self._work_lock = threading.Lock()
        self._closed = False

    def read_page(self, client, job):
        """Read one reviewed native page; subclasses must not submit exchange actions."""
        raise NotImplementedError

    def pause(self, account_id, key=None, *, disconnected=False):
        """Persist a pause through the domain service's own key contract."""
        raise NotImplementedError

    def tick(self) -> None:
        """Read one due page fairly across jobs and keep provider failures contained."""
        if not self._work_lock.acquire(blocking=False):
            return
        try:
            if self._closed:
                return
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    f"SELECT payload FROM {self.table} WHERE status IN ('queued','retrying') "
                    f"AND next_attempt<=? ORDER BY last_attempt,account_id,{self.key_field} LIMIT 1",
                    (time.time(),),
                ).fetchone()
                if row is None:
                    return
                job = json.loads(row[0])
                job.update(status="running", last_attempt=time.time(), last_attempt_at=now_iso())
                self.ledger.write_job(db, job)
            try:
                connection = next(
                    (item for item in self.store.connections() if item.id == job["account_id"]), None
                )
                if connection is None:
                    self.pause(job["account_id"], disconnected=True)
                    return
                if not connection.active:
                    self.pause(job["account_id"])
                    return
                with self.market.adapter(connection) as client:
                    page = self.read_page(client, job)
                self.ledger.commit_page(job, page)
            except Exception as error:
                self._failure(job, error)
        finally:
            self._work_lock.release()

    def _failure(self, job: dict, error: Exception) -> None:
        """Persist safe messages only; retain the last successfully committed cursor."""
        transient = isinstance(error, (ccxt.NetworkError, ccxt.RateLimitExceeded))
        if isinstance(error, (ccxt.AuthenticationError, ccxt.PermissionDenied)):
            message = "History access denied. Check this account's read permissions and credentials."
        elif isinstance(error, ccxt.NotSupported):
            message = "This provider does not support the reviewed history operation."
        elif isinstance(error, ccxt.BadSymbol):
            message = "This exact spot market is unavailable. Check the selected pair."
        elif transient:
            message = (
                "The provider is temporarily unavailable or rate limited. The saved checkpoint is retained."
            )
        elif isinstance(error, ImportLimitError):
            message = self.limit_message
        else:
            message = "The history page could not be validated. The saved checkpoint is retained."
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.ledger.read_job(db, job["account_id"], job[self.key_field])
            if current is None or current.get("revision") != job.get("revision"):
                return
            deferred = isinstance(error, ProviderDeferred)
            retries = current["retries"] + int(not deferred)
            retry = deferred or (transient and retries <= 5)
            delay = error.retry_after if deferred else min(300, 15 * 2 ** min(retries - 1, 5))
            next_attempt = time.time() + delay if retry else 0
            current.update(error=message, retries=retries, next_attempt=next_attempt)
            if current["status"] not in {"paused", "disconnected"}:
                current["status"] = "retrying" if retry else "error"
            current["retry_at"] = datetime.fromtimestamp(next_attempt, UTC).isoformat() if retry else None
            self.ledger.write_job(db, current)

    def close(self) -> None:
        """Wait for a finite in-flight read before the application closes transports."""
        with self._work_lock:
            self._closed = True
