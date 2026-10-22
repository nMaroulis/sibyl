"""Resumable, read-only account imports with durable progress and bounded retries."""

from typing import Literal
from uuid import uuid4

from pydantic import Field, field_validator

from sibyl.exchanges.providers import CLIENTS
from sibyl.exchanges.spot_history import history_note
from sibyl.models import Connection, OrderRequest, Request
from sibyl.services.import_worker import ImportLimitError, ImportWorker
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
    mode: Literal["incremental", "rescan"] = "incremental"

    @field_validator("symbols")
    @classmethod
    def valid_symbols(cls, values: list[str]) -> list[str]:
        """Apply the same exact-spot symbol contract as manual trading."""
        return list(dict.fromkeys(OrderRequest.valid_symbol(value) for value in values))


class AccountSync(ImportWorker):
    """Consume one persisted page per tick; HTTP requests only enqueue work.

    A single application worker owns reads. Successful checkpoints survive process
    restarts. Transient transport errors retry at most five times with backoff;
    auth, unsupported and invalid-data errors wait for an explicit user retry.
    No import submits an order, changes balances, or calculates exchange P&L.
    """

    limit_message = "Fill import page budget reached. Retained records and the last checkpoint are saved. Review this market before restarting."

    def __init__(self, market: Market, store: Store):
        super().__init__(market, store, AccountLedger(store))

    def snapshot(self) -> dict:
        """Read public sync status without provider calls or decrypted credentials."""
        return {
            "accounts": [
                {
                    **connection.model_dump(mode="json"),
                    "environment": environment(connection),
                    "history_import": history_kind(connection.exchange) or None,
                    "history_note": history_note(connection.exchange),
                }
                for connection in self.store.connections()
            ],
            "jobs": self.ledger.jobs(),
            "scope": "Selected spot markets only. Caught up describes the available provider range, not complete account history.",
        }

    def enqueue(self, connection: Connection, symbols: list[str], mode: str = "incremental") -> dict:
        """Resume checkpoints or rescan retained provider history without deleting evidence.

        Rescans require pausing active work first. A revision makes any old
        in-flight result harmless, including an old failure after a new scan.
        """
        if mode not in {"incremental", "rescan"}:
            raise ValueError("Choose incremental sync or rescan.")
        if not history_kind(connection.exchange):
            raise ValueError(
                "Durable history import is coming soon for this exchange. Bounded reads remain available."
            )
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            # Disconnect may have happened after the route resolved this account.
            if not db.execute("SELECT 1 FROM connections WHERE id=?", (connection.id,)).fetchone():
                raise LookupError("Connection not found.")
            if not db.execute(
                "SELECT 1 FROM active_accounts WHERE account_id=?", (connection.id,)
            ).fetchone():
                raise ValueError("Activate this account before importing history.")
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
                if mode == "rescan" and job["status"] in {"queued", "running", "retrying"}:
                    raise ValueError("Pause this market import before starting a rescan.")
                if job["status"] not in {"queued", "running", "retrying"}:
                    if mode == "rescan":
                        job.update(cursor={}, seen_cursors=[], seen_pages=[], caught_up_at=None)
                    if mode == "rescan" or job["status"] in {"new", "caught_up"} or job.get("pass_complete"):
                        job.update(
                            revision=uuid4().hex,
                            mode=mode,
                            pass_pages=0,
                            pass_started_at=now_iso(),
                            pass_inserted=0,
                            pass_updated=0,
                            pass_complete=False,
                            seen_cursors=[],
                            seen_pages=[],
                        )
                    # Older persisted jobs acquire a revision without losing their cursor.
                    job.setdefault("revision", uuid4().hex)
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

    def read_page(self, client, job):
        """Read one exact market with the provider's reviewed fill cursor."""
        if job.get("pass_pages", job["pages"]) >= 10_000:
            raise ImportLimitError("Fill import page budget reached; start a new rescan.")
        return client.fetch_trade_page(job["symbol"], job["cursor"], 100)
