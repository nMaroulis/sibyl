"""User-controlled, resumable funding imports in explicit date ranges."""

import json
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import AwareDatetime, Field, model_validator

from sibyl.exchanges.funding import DAY, funding_streams
from sibyl.models import Connection, Request
from sibyl.services.account_sync import environment
from sibyl.services.funding_ledger import MAX_PAGES, NOTE, FundingLedger, funding_event
from sibyl.services.import_worker import ImportLimitError, ImportWorker
from sibyl.services.ledger import now_iso


class FundingSyncRequest(Request):
    """An explicit closed UTC range; restarting a completed range rescans status corrections."""

    streams: list[Literal["deposit", "withdrawal", "transfer"]] = Field(min_length=1, max_length=3)
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def date_window(self):
        """Keep all provider jobs below the reviewed ninety-day window and in the past."""
        if self.start.timestamp() <= 0 or not self.start < self.end <= datetime.now(UTC):
            raise ValueError("Choose a past start/end range with explicit timezones.")
        if (self.end - self.start).total_seconds() >= 90 * 86400:
            raise ValueError("Import ranges must be shorter than 90 days; import older ranges separately.")
        self.streams = list(dict.fromkeys(self.streams))
        return self


def supported(connection: Connection) -> list[str]:
    """Production funding endpoints must never leak into dedicated or legacy sandbox clients."""
    return [] if connection.sandbox else funding_streams(connection.exchange)


class FundingSync(ImportWorker):
    """Own one range checkpoint per account/stream, independently of fill imports."""

    table = "funding_sync"
    key_field = "stream"

    def __init__(self, market, store):
        super().__init__(market, store, FundingLedger(store))

    def snapshot(self) -> dict:
        """Read saved support, retained account labels and progress without provider calls."""
        return {
            "accounts": [
                {
                    **row.model_dump(mode="json"),
                    "environment": environment(row),
                    "funding_streams": supported(row),
                    "funding_note": (
                        "Binance Spot Test Network does not expose the production capital-history endpoints."
                        if row.exchange == "binance-testnet" or (row.exchange == "binance" and row.sandbox)
                        else "Kraken imports posted ledger entries for the default wallet. Pending funding requests are outside this source."
                        if row.exchange == "kraken"
                        else "Funding import is coming soon for this exchange/environment."
                        if not supported(row)
                        else ""
                    ),
                }
                for row in self.store.connections()
            ],
            "jobs": self.ledger.jobs(),
            "scope": NOTE,
            "demo_note": "Demo has no funding transactions. Its virtual seed balances are opening inventory, not fabricated deposits. View the isolated example to explore funding history.",
        }

    def enqueue(self, connection: Connection, request: FundingSyncRequest) -> dict:
        """Queue/resume a range; a different range requires pausing the active stream first."""
        if any(stream not in supported(connection) for stream in request.streams):
            raise ValueError("Funding import is coming soon for this exchange or selected stream.")
        start, end = int(request.start.timestamp() * 1000), int(request.end.timestamp() * 1000)
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM connections WHERE id=?", (connection.id,)).fetchone():
                raise LookupError("Connection not found.")
            if not db.execute(
                "SELECT 1 FROM active_accounts WHERE account_id=?", (connection.id,)
            ).fetchone():
                raise ValueError("Activate this account before importing funding history.")
            for stream in request.streams:
                job = self.ledger.read_job(db, connection.id, stream)
                same_range = job and (job["start_ms"], job["end_ms"]) == (start, end)
                if job and job["status"] in {"queued", "running", "retrying"}:
                    if not same_range:
                        raise ValueError("Pause the active funding stream before changing its date range.")
                    continue
                resume = same_range and job["status"] in {"paused", "error"} and not job.get("caught_up_at")
                if not resume:
                    job = {
                        "account_id": connection.id,
                        "account": connection.label,
                        "exchange": connection.exchange,
                        "environment": environment(connection),
                        "stream": stream,
                        "start_ms": start,
                        "end_ms": end,
                        "cursor": {"start": start, "end": end},
                        "revision": uuid4().hex,
                        "pages": 0,
                        "inserted": 0,
                        "updated": 0,
                        "last_attempt": 0,
                        "last_success_at": None,
                        "caught_up_at": None,
                        "started_at": now_iso(),
                    }
                job.update(status="queued", retries=0, error=None, next_attempt=0)
                self.ledger.write_job(db, job)
        return self.snapshot()

    def pause(self, account_id: str, stream: str | None = None, *, disconnected: bool = False) -> dict:
        """Stop future pages while allowing an in-flight same-range page to checkpoint."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT payload FROM funding_sync WHERE account_id=?" + (" AND stream=?" if stream else ""),
                (account_id, stream) if stream else (account_id,),
            ).fetchall()
            if stream and not rows:
                raise LookupError("Import job not found.")
            for row in rows:
                job = json.loads(row[0])
                if job["status"] == "caught_up" and not disconnected:
                    continue
                job["status"] = "disconnected" if disconnected else "paused"
                self.ledger.write_job(db, job)
        return self.snapshot()

    def read_page(self, client, job):
        """Read one native funding page; this service has no money-movement methods."""
        if job["pages"] >= MAX_PAGES:
            raise ImportLimitError("Choose a smaller date range.")
        return client.fetch_funding_page(job["stream"], job["cursor"], 50)

    @staticmethod
    def example() -> dict:
        """Build a standalone example; it is never persisted or mixed with account observations."""
        scope = {
            "account_id": "example",
            "account": "Example account",
            "exchange": "demo",
            "environment": "demo",
            "start_ms": 1,
            "end_ms": 1_800_000_000_000,
        }
        events = []
        for index, (stream, asset, quantity, status, fee) in enumerate(
            [
                ("deposit", "USDT", 2500, "completed", None),
                ("withdrawal", "ETH", 0.2, "completed", 0.001),
                ("transfer", "USDT", 300, "completed", 0),
                ("deposit", "BTC", 0.01, "pending", None),
            ]
        ):
            events.append(
                funding_event(
                    {
                        "native_id": f"example-{index}",
                        "reference": None,
                        "asset": asset,
                        "timestamp_ms": 1_704_153_600_000 + index * DAY,
                        "kind": stream,
                        "direction": "in" if stream == "deposit" else "out",
                        "quantity": quantity,
                        "status": status,
                        "internal": stream == "transfer",
                        "amount_basis": "provider_reported",
                        "fee": {"currency": asset if fee is not None else None, "cost": fee},
                    },
                    {**scope, "stream": stream},
                )
            )
        return {
            "example": True,
            "items": list(reversed(events)),
            "total": len(events),
            "offset": 0,
            "limit": 50,
            "has_more": False,
            "summaries": [
                {
                    key: row[key]
                    for key in (
                        "account_id",
                        "account",
                        "environment",
                        "asset",
                        "kind",
                        "direction",
                        "quantity",
                    )
                }
                | {"count": 1}
                for row in events
                if row["status"] == "completed"
            ],
            "fees": [{"account_id": "example", "environment": "demo", "currency": "ETH", "quantity": 0.001}],
            "complete_history": False,
            "note": NOTE,
        }
