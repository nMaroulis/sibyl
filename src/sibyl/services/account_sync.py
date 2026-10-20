"""Resumable, read-only account imports with durable progress and bounded retries."""

import threading
import time
from datetime import UTC, datetime

import ccxt
from pydantic import Field, field_validator

from sibyl.exchanges.providers import CLIENTS
from sibyl.models import Connection, OrderRequest, Request
from sibyl.services.ledger import AccountLedger, now_iso
from sibyl.services.market import Market
from sibyl.storage import Store


def history_kind(exchange: str) -> str:
    """Inspect reviewed support without constructing or authenticating a transport."""
    return "demo-keyset" if exchange == "demo" else CLIENTS[exchange].history_kind


def environment(connection: Connection) -> str:
    """Keep demo, exchange test funds and production observations visibly separate."""
    return "demo" if connection.exchange == "demo" else "test" if connection.sandbox else "production"


class AccountSyncRequest(Request):
    """Queue only explicit canonical markets; never fan out over every listed pair."""

    symbols: list[str] = Field(min_length=1, max_length=12)

    @field_validator("symbols")
    @classmethod
    def valid_symbols(cls, values: list[str]) -> list[str]:
        """Apply the same exact-spot symbol contract as manual trading."""
        return list(dict.fromkeys(OrderRequest.valid_symbol(value) for value in values))


class AccountSync:
    """Consume one persisted page per tick; HTTP requests only enqueue work.

    A single application worker owns reads. Successful checkpoints survive process
    restarts. Transient transport errors retry at most five times with backoff;
    auth, unsupported and invalid-data errors wait for an explicit user retry.
    No import submits an order, changes balances, or calculates exchange P&L.
    """

    def __init__(self, market: Market, store: Store):
        self.market, self.store = market, store
        self.ledger = AccountLedger(store)
        self._work_lock = threading.Lock()
        self._closed = False

    def snapshot(self) -> dict:
        """Read public sync status without provider calls or decrypted credentials."""
        return {
            "accounts": [
                {
                    **connection.model_dump(mode="json"),
                    "environment": environment(connection),
                    "history_import": history_kind(connection.exchange) or None,
                }
                for connection in self.store.connections()
            ],
            "jobs": self.ledger.jobs(),
            "scope": "Selected spot markets only. Caught up describes the available provider range, not complete account history.",
        }

    def enqueue(self, connection: Connection, symbols: list[str]) -> dict:
        """Start or resume a bounded set of selected markets from saved checkpoints."""
        if not history_kind(connection.exchange):
            raise ValueError(
                "Durable history import is coming soon for this exchange. Bounded reads remain available."
            )
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            # Disconnect may have happened after the route resolved this account.
            if not db.execute("SELECT 1 FROM connections WHERE id=?", (connection.id,)).fetchone():
                raise LookupError("Connection not found.")
            for symbol in symbols:
                job = self.ledger.read_job(db, connection.id, symbol) or {
                    "account_id": connection.id,
                    "account": connection.label,
                    "exchange": connection.exchange,
                    "environment": environment(connection),
                    "symbol": symbol,
                    "cursor": {},
                    "pages": 0,
                    "inserted": 0,
                    "updated": 0,
                    "last_attempt": 0,
                    "next_attempt": 0,
                    "last_success_at": None,
                    "caught_up_at": None,
                    "retries": 0,
                    "error": None,
                    "status": "new",
                    "started_at": now_iso(),
                }
                if job["status"] not in {"queued", "running", "retrying"}:
                    job.update(status="queued", retries=0, error=None, next_attempt=0)
                self.ledger.write_job(db, job)
        return self.snapshot()

    def pause(self, account_id: str, symbol: str | None = None, *, disconnected: bool = False) -> dict:
        """Stop future pages; an in-flight successful page may still checkpoint."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT payload FROM account_sync WHERE account_id=?" + (" AND symbol=?" if symbol else ""),
                (account_id, symbol) if symbol else (account_id,),
            ).fetchall()
            if symbol and not rows:
                raise LookupError("Import job not found.")
            import json

            for row in rows:
                job = json.loads(row[0])
                job["status"] = "disconnected" if disconnected else "paused"
                self.ledger.write_job(db, job)
        return self.snapshot()

    def tick(self) -> None:
        """Read one due page fairly across jobs and keep provider failures contained."""
        if not self._work_lock.acquire(blocking=False):
            return
        try:
            if self._closed:
                return
            import json

            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT payload FROM account_sync WHERE status IN ('queued','retrying') "
                    "AND next_attempt<=? ORDER BY last_attempt,account_id,symbol LIMIT 1",
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
                client = self.market.client(connection)
                with client.lock:
                    page = client.fetch_trade_page(job["symbol"], job["cursor"], 100)
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
        else:
            message = "The history page could not be validated. The saved checkpoint is retained."
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.ledger.read_job(db, job["account_id"], job["symbol"])
            retries = current["retries"] + 1
            retry = transient and retries <= 5
            next_attempt = time.time() + min(300, 15 * 2 ** min(retries - 1, 5)) if retry else 0
            current.update(error=message, retries=retries, next_attempt=next_attempt)
            if current["status"] not in {"paused", "disconnected"}:
                current["status"] = "retrying" if retry else "error"
            current["retry_at"] = datetime.fromtimestamp(next_attempt, UTC).isoformat() if retry else None
            self.ledger.write_job(db, current)

    def close(self) -> None:
        """Wait for a finite in-flight read before the application closes transports."""
        with self._work_lock:
            self._closed = True
