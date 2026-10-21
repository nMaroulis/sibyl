"""Source-pinned, one-page candle imports with atomic checkpoints and bounded retries."""

import json
import threading
import time
from datetime import datetime
from typing import Literal

import ccxt
from pydantic import Field, field_validator

from sibyl.market_data.archive import boundaries, iso, now_ms, series_key, step_ms, validated_rows
from sibyl.market_data.clients import CryptoCompareClient
from sibyl.market_data.control import ProviderDeferred
from sibyl.models import BacktestRequest, OrderRequest, Request, Timeframe

REVIEWED = {
    "demo",
    "binance",
    "binanceus",
    "binance-testnet",
    "coinbase",
    "coinbase-sandbox",
    "kraken",
    "cryptocompare",
}


class CandleRange(Request):
    """An exact source/pair and a bounded interval of whole closed candles."""

    source: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9:-]+$")
    symbol: str
    timeframe: Timeframe = "1d"
    start: datetime
    end: datetime
    _symbol = field_validator("symbol")(OrderRequest.valid_symbol.__func__)


class DatasetCreate(CandleRange):
    """Copy a complete retained interval, without making provider requests."""

    label: str = Field(default="", max_length=100)


class ImportAction(Request):
    """Keep range state explicit; rescanning is distinct from resuming a checkpoint."""

    action: Literal["pause", "resume", "rescan"]


class RetentionRequest(Request):
    """Prune old mutable bars after a typed local confirmation."""

    source: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9:-]+$")
    symbol: str
    timeframe: Timeframe = "1d"
    before: datetime
    confirmation: str = Field(max_length=100)
    _symbol = field_validator("symbol")(OrderRequest.valid_symbol.__func__)


class DatasetBacktest(BacktestRequest):
    """Use every bar of one immutable dataset; running strategies remain separate."""

    dataset_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    candles: int = Field(default=180, ge=60, le=20_000)


class CandleHistory:
    """Schedule one reviewed 200-slot read per tick in a single local API worker."""

    def __init__(self, market, store):
        self.market, self.store, self.archive = market, store, market.archive
        self._worker = threading.Lock()
        self._closed = False
        with store.db() as db:
            # No write needs replaying: interrupted jobs resume their last committed window.
            for row in db.execute("SELECT payload FROM candle_imports WHERE status='running'").fetchall():
                job = json.loads(row[0])
                job.update(status="queued", next_attempt=0)
                self._write(db, job)

    @staticmethod
    def _write(db, job):
        db.execute(
            "INSERT INTO candle_imports VALUES(?,?,?,?) ON CONFLICT(series_id) DO UPDATE SET status=excluded.status,next_attempt=excluded.next_attempt,payload=excluded.payload",
            (job["id"], job["status"], job["next_attempt"], json.dumps(job, allow_nan=False)),
        )

    @staticmethod
    def _read(db, identity):
        row = db.execute("SELECT payload FROM candle_imports WHERE series_id=?", (identity,)).fetchone()
        if row is None:
            raise LookupError("Candle import not found.")
        return json.loads(row[0])

    def metadata(self, source):
        """Resolve safe identities for offline reads too, including disconnected archives."""
        if self.market.data_settings:
            public = self.market.data_settings.public_market()
            row = next((r for r in public["catalog"] if r["id"] == source), None)
            if row:
                return {
                    "source": source,
                    "source_label": row["name"],
                    "environment": row["environment"],
                    "provider": row["provider"],
                    "available": row["available"],
                    "candles": row["candles"],
                }
        else:
            with self.market.snapshot(source):
                return {**self.market.metadata(), "available": True, "candles": True}
        with self.store.db() as db:
            row = db.execute(
                "SELECT metadata FROM candle_series WHERE json_extract(metadata,'$.source')=? LIMIT 1",
                (source,),
            ).fetchone()
        if row:
            return {**json.loads(row[0]), "available": False, "candles": True}
        raise ValueError("Unknown market source. Choose a configured source or retained archive.")

    def status(self, source, symbol, timeframe, start=None, end=None):
        """Read coverage, preview and checkpoints without any provider request."""
        meta = self.metadata(source)
        key = series_key(source, meta["environment"], symbol, timeframe)
        with self.store.db() as db:
            row = db.execute("SELECT payload FROM candle_imports WHERE series_id=?", (key,)).fetchone()
        supported = meta.get("provider", source) in REVIEWED and meta["candles"]
        provider = meta.get("provider", source)
        page_intervals = 200
        if provider == "cryptocompare":
            supported = supported and timeframe in CryptoCompareClient.intervals
            if supported:
                page_intervals = min(200, 2000 // CryptoCompareClient.intervals[timeframe][1] - 1)
        note = (
            "Kraken exposes only its most recent 720 intervals; older data cannot be backfilled."
            if meta.get("provider") == "kraken"
            else "Demo offers 730 synthetic intervals per timeframe, without a market-liquidity claim."
            if source == "demo"
            else "Historical pagination for this provider/timeframe is not reviewed yet. Successful current chart pages can still be retained."
            if not supported
            else "Import uses bounded provider windows; missing/no-trade periods stay visible as gaps."
        )
        return {
            **meta,
            **self.archive.window(source, meta["environment"], symbol, timeframe, start, end),
            "job": json.loads(row[0]) if row else None,
            "backfill": {"supported": supported, "page_intervals": page_intervals, "note": note},
        }

    def queue(self, request: CandleRange):
        """Validate capabilities before saving a frozen range; do not read candle pages here."""
        left, right = boundaries(request.start, request.end, request.timeframe)
        with self.market.snapshot(request.source):
            meta = self.market.metadata()
            client = self.market.client()
            client.market(request.symbol)
            if not client.candle_history or request.timeframe not in client.timeframes:
                raise ValueError("Historical candle pagination is unavailable for this provider/timeframe.")
            page_intervals = client.candle_page_size(request.timeframe)
        key = series_key(request.source, meta["environment"], request.symbol, request.timeframe)
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT payload FROM candle_imports WHERE series_id=?", (key,)).fetchone()
            previous = json.loads(old[0]) if old else None
            if previous and (previous["start_ms"], previous["end_ms"]) == (left, right):
                return previous
            if previous and previous["status"] in {"queued", "running", "retrying"}:
                raise ValueError("Pause this import before changing its range.")
            active = db.execute(
                "SELECT COUNT(*) FROM candle_imports WHERE status IN ('queued','running','retrying')"
            ).fetchone()[0]
            if active >= 12:
                raise ValueError("Keep at most 12 active candle imports; pause one first.")
            job = {
                "id": key,
                **meta,
                "symbol": request.symbol,
                "timeframe": request.timeframe,
                "start_ms": left,
                "end_ms": right,
                "start": iso(left),
                "end": iso(right),
                "cursor": left,
                "status": "queued",
                "pages": 0,
                "page_intervals": page_intervals,
                "observations": 0,
                "revision": (previous["revision"] + 1) if previous else 1,
                "next_attempt": 0,
                "failures": 0,
                "error": None,
                "created_at": iso(now_ms()),
                "checked_at": None,
                "coverage": None,
            }
            self._write(db, job)
        return job

    def action(self, identity, action):
        """Pause or resume saved progress; a rescan starts a fresh pass over the same range."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            job = self._read(db, identity)
            if action == "pause":
                if job["status"] not in {"queued", "running", "retrying"}:
                    return job
                job["status"] = "paused"
            elif action in {"resume", "rescan"}:
                if action == "resume" and job["status"] in {"complete", "gaps"}:
                    return job
                if job["status"] in {"queued", "running", "retrying"}:
                    return job
                active = db.execute(
                    "SELECT COUNT(*) FROM candle_imports WHERE status IN ('queued','running','retrying')"
                ).fetchone()[0]
                if active >= 12:
                    raise ValueError("Keep at most 12 active candle imports; pause one first.")
                job.update(status="queued", error=None, failures=0, next_attempt=0)
                if action == "rescan":
                    job.update(cursor=job["start_ms"], pages=0, observations=0, coverage=None)
            else:
                raise ValueError("Unknown candle import action.")
            job["revision"] += 1
            self._write(db, job)
        return job

    def tick(self):
        """Fetch one page outside SQLite; commit observations and progress together."""
        with self._worker:
            if self._closed:
                return
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT payload FROM candle_imports WHERE status IN ('queued','retrying') AND next_attempt<=? ORDER BY next_attempt,rowid LIMIT 1",
                    (time.time(),),
                ).fetchone()
                if not row:
                    return
                job = json.loads(row[0])
                job["status"] = "running"
                self._write(db, job)
            try:
                step = step_ms(job["timeframe"])
                end = min(job["end_ms"], job["cursor"] + job.get("page_intervals", 200) * step)
                with self.market.snapshot(job["source"]):
                    if self.market.metadata()["environment"] != job["environment"]:
                        raise ValueError("Source environment changed; choose a new import.")
                    rows = self.market.client().fetch_candle_page(
                        job["symbol"], job["timeframe"], job["cursor"], end
                    )
                rows = validated_rows(rows, job["timeframe"])
                if any(not job["cursor"] <= r[0] < end for r in rows):
                    raise ValueError("Provider returned candles outside the requested historical window.")
                with self.store.db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    current = self._read(db, job["id"])
                    if current["revision"] != job["revision"] or current["status"] != "running":
                        return
                    self.archive.commit_rows(db, job, job["symbol"], job["timeframe"], rows)
                    current.update(
                        cursor=end,
                        pages=current["pages"] + 1,
                        observations=current["observations"] + len(rows),
                        checked_at=iso(now_ms()),
                        failures=0,
                        error=None,
                        next_attempt=time.time() + 1,
                        status="queued",
                    )
                    if end == job["end_ms"]:
                        # Read the complete requested interval inside the same checkpoint transaction.
                        all_rows = [
                            list(r)
                            for r in db.execute(
                                "SELECT timestamp FROM candle_rows WHERE series_id=? AND timestamp>=? AND timestamp<? ORDER BY timestamp",
                                (job["id"], job["start_ms"], job["end_ms"]),
                            )
                        ]
                        coverage = self.archive.coverage(
                            all_rows, job["start_ms"], job["end_ms"], job["timeframe"]
                        )
                        current.update(
                            coverage=coverage, status="complete" if coverage["complete"] else "gaps"
                        )
                    self._write(db, current)
            except Exception as error:
                with self.store.db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    current = self._read(db, job["id"])
                    if current["revision"] != job["revision"] or current["status"] != "running":
                        return
                    deferred = isinstance(error, ProviderDeferred)
                    failures = min(10, current["failures"] + int(not deferred))
                    retry = deferred or (isinstance(error, ccxt.NetworkError) and failures <= 5)
                    message = (
                        "Provider unavailable or rate limited; the last committed checkpoint is retained."
                        if retry
                        else "Candle page unavailable or invalid. Check feed access, supported dates and provider history limits; no data was substituted."
                    )
                    current.update(
                        status="retrying" if retry else "error",
                        failures=failures,
                        error=message,
                        next_attempt=time.time()
                        + (error.retry_after if deferred else min(900, 15 * 2**failures)),
                        checked_at=iso(now_ms()),
                    )
                    self._write(db, current)

    def close(self):
        """Wait for a finite in-flight read before shared provider sessions close."""
        with self._worker:
            self._closed = True
