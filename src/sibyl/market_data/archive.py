"""Validated closed-candle storage, coverage evidence and immutable research datasets.

Every series is partitioned by source, environment, exact pair and timeframe.
Missing intervals stay missing. A dataset copies its input bars and content hash,
so later provider corrections or archive pruning cannot rewrite a saved test.
"""

import hashlib
import json
import math
import re
from datetime import UTC, datetime

from sibyl.exchanges.data import TIMEFRAMES

FIELDS = ("open", "high", "low", "close", "volume")
MAX_RANGE = 50_000


def now_ms():
    """Return current UTC milliseconds; all storage boundaries use integer times."""
    return int(datetime.now(UTC).timestamp() * 1000)


def iso(value: int) -> str:
    """Format a stored millisecond timestamp without local timezone ambiguity."""
    return datetime.fromtimestamp(value / 1000, UTC).isoformat()


def milliseconds(value: str | datetime) -> int:
    """Accept only timezone-aware timestamps, never a host-local date assumption."""
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Use timezone-aware candle dates.")
    return int(parsed.timestamp() * 1000)


def step_ms(timeframe):
    """Use the supported fixed UTC intervals; calendar months are not fabricated."""
    if timeframe not in TIMEFRAMES:
        raise ValueError("Unsupported candle timeframe.")
    return TIMEFRAMES[timeframe] * 1000


def floor_time(value: int, timeframe: str) -> int:
    """Use UTC boundaries, with Monday opening for weekly candles."""
    step = step_ms(timeframe)
    anchor = 345_600_000 if timeframe == "1w" else 0
    return (value - anchor) // step * step + anchor


def boundaries(start, end, timeframe) -> tuple[int, int]:
    """Choose whole closed intervals inside the inclusive-start/exclusive-end range."""
    raw_start, raw_end = milliseconds(start), milliseconds(end)
    step = step_ms(timeframe)
    left = floor_time(raw_start + step - 1, timeframe)
    right = floor_time(raw_end, timeframe)
    if raw_start < 1_262_304_000_000 or raw_end > now_ms() or left >= right:
        raise ValueError("Choose a past range after 2010 containing at least one whole closed candle.")
    if (right - left) // step > MAX_RANGE:
        raise ValueError(f"Choose at most {MAX_RANGE:,} candle intervals per range.")
    return left, right


def series_key(source, environment, symbol, timeframe):
    """Hash identities, never credentials or a mutable provider label."""
    if not re.fullmatch(r"[A-Z0-9]{1,12}/[A-Z0-9]{1,12}", symbol):
        raise ValueError("Choose an exact canonical spot pair.")
    step_ms(timeframe)
    return hashlib.sha256(json.dumps([source, environment, symbol, timeframe]).encode()).hexdigest()


def validated_rows(rows: list, timeframe: str, *, closed_at: int | None = None) -> list[list]:
    """Validate one bounded native page; reject conflicting duplicates and off-grid bars."""
    if not isinstance(rows, list) or len(rows) > 2001:
        raise ValueError("Candle response exceeds the bounded page contract.")
    clock = now_ms() if closed_at is None else closed_at
    step = step_ms(timeframe)
    result = {}
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            raise ValueError("Provider returned an incomplete candle.")
        if any(isinstance(value, bool) for value in row[:6]):
            raise ValueError("Provider returned invalid candle values.")
        try:
            values = [float(value) for value in row[:6]]
        except (ValueError, TypeError, OverflowError):
            raise ValueError("Provider returned invalid candle values.") from None
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Provider returned non-finite candle values.")
        timestamp, opening, high, low, close, volume = values
        if (
            timestamp <= 0
            or timestamp != int(timestamp)
            or floor_time(int(timestamp), timeframe) != timestamp
        ):
            raise ValueError("Provider candle times do not follow the supported UTC interval grid.")
        if (
            min(opening, high, low, close) <= 0
            or volume < 0
            or low > min(opening, close)
            or high < max(opening, close)
        ):
            raise ValueError("Provider returned invalid OHLCV bounds.")
        timestamp = int(timestamp)
        if timestamp + step > clock:
            continue  # unfinished intervals never enter retained research data
        normalized = [timestamp, opening, high, low, close, volume]
        if timestamp in result and result[timestamp] != normalized:
            raise ValueError("Provider returned conflicting candles for one timestamp.")
        result[timestamp] = normalized
    return [result[key] for key in sorted(result)]


class CandleArchive:
    """Keep bounded observations and coverage separate from immutable snapshot data."""

    per_series_limit = 100_000
    total_limit = 1_000_000

    def __init__(self, store):
        self.store = store
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS candle_series (
                    id TEXT PRIMARY KEY, metadata TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS candle_rows (
                    series_id TEXT NOT NULL, timestamp INTEGER NOT NULL,
                    open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL,
                    close REAL NOT NULL, volume REAL NOT NULL, observed_at TEXT NOT NULL,
                    PRIMARY KEY(series_id,timestamp)
                );
                CREATE TABLE IF NOT EXISTS candle_imports (
                    series_id TEXT PRIMARY KEY, status TEXT NOT NULL,
                    next_attempt REAL NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS candle_datasets (
                    id TEXT PRIMARY KEY, metadata TEXT NOT NULL, candles TEXT NOT NULL
                );
            """)

    def identify(self, metadata, symbol, timeframe):
        """Build safe provenance using only the source's public identity fields."""
        return {
            "id": series_key(metadata["source"], metadata["environment"], symbol, timeframe),
            **{key: metadata[key] for key in ("source", "source_label", "environment")},
            "symbol": symbol,
            "timeframe": timeframe,
            "provider": metadata.get("provider", metadata["source"]),
        }

    def commit_rows(self, db, metadata, symbol, timeframe, rows):
        """Upsert a validated page inside the same transaction as an import checkpoint."""
        identity = self.identify(metadata, symbol, timeframe)
        db.execute(
            "INSERT OR IGNORE INTO candle_series(id,metadata) VALUES(?,?)",
            (identity["id"], json.dumps(identity)),
        )
        changed = 0
        new = 0
        observed = iso(now_ms())
        for row in rows:
            old = db.execute(
                "SELECT open,high,low,close,volume FROM candle_rows WHERE series_id=? AND timestamp=?",
                (identity["id"], row[0]),
            ).fetchone()
            if old and list(old) == row[1:6]:
                continue
            changed += 1
            new += int(old is None)
            db.execute(
                "INSERT INTO candle_rows VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(series_id,timestamp) DO UPDATE SET open=excluded.open,high=excluded.high,low=excluded.low,close=excluded.close,volume=excluded.volume,observed_at=excluded.observed_at",
                (identity["id"], *row, observed),
            )
        if new:
            series_count = db.execute(
                "SELECT COUNT(*) FROM candle_rows WHERE series_id=?", (identity["id"],)
            ).fetchone()[0]
            total = db.execute("SELECT COUNT(*) FROM candle_rows").fetchone()[0]
            if series_count > self.per_series_limit or total > self.total_limit:
                raise ValueError(
                    "Candle storage budget reached. Pause imports and prune older archive rows; snapshots remain retained."
                )
        if changed:
            db.execute("UPDATE candle_series SET revision=revision+1 WHERE id=?", (identity["id"],))
        return changed

    def capture(self, metadata, symbol, timeframe, candles):
        """Persist successful closed chart pages; cache hits do not repeat these writes."""
        raw = [[milliseconds(c["timestamp"]), *[c[key] for key in FIELDS]] for c in candles]
        rows = validated_rows(raw, timeframe)
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self.commit_rows(db, metadata, symbol, timeframe, rows)

    @staticmethod
    def coverage(rows, start, end, timeframe):
        """Describe missing UTC slots without inventing zero-trade or price candles."""
        step = step_ms(timeframe)
        expected = (end - start) // step
        present = {r[0] for r in rows if start <= r[0] < end}
        gaps = []
        missing = 0
        gap = None
        for timestamp in range(start, end, step):
            if timestamp not in present:
                missing += 1
                if gap is None:
                    gap = timestamp
            elif gap is not None:
                gaps.append({"start": iso(gap), "end": iso(timestamp), "candles": (timestamp - gap) // step})
                gap = None
        if gap is not None:
            gaps.append({"start": iso(gap), "end": iso(end), "candles": (end - gap) // step})
        return {
            "expected": expected,
            "stored": len(present),
            "missing": missing,
            "complete": missing == 0 and expected > 0,
            "gaps": gaps[:100],
            "gap_ranges": len(gaps),
            "gaps_truncated": len(gaps) > 100,
        }

    def window(self, source, environment, symbol, timeframe, start=None, end=None, limit=2000):
        """Read retained rows only; preview is bounded, coverage covers the full chosen range."""
        if not 1 <= limit <= 2000:
            raise ValueError("Choose a candle preview of 1–2,000 observations.")
        key = series_key(source, environment, symbol, timeframe)
        with self.store.db() as db:
            db.execute("BEGIN")
            entry = db.execute("SELECT metadata,revision FROM candle_series WHERE id=?", (key,)).fetchone()
            extent = db.execute(
                "SELECT MIN(timestamp),MAX(timestamp),COUNT(*) FROM candle_rows WHERE series_id=?", (key,)
            ).fetchone()
            left, right = (
                boundaries(start, end, timeframe)
                if start is not None and end is not None
                else (extent[0], extent[1] + step_ms(timeframe))
                if extent[0] is not None
                else (None, None)
            )
            if (start is None) != (end is None):
                raise ValueError("Supply both archive range boundaries.")
            truncated = left is not None and (right - left) // step_ms(timeframe) > MAX_RANGE
            if truncated:
                # A series may be retained longer than one interactive query.
                left = right - MAX_RANGE * step_ms(timeframe)
            rows = (
                [
                    list(row)
                    for row in db.execute(
                        "SELECT timestamp,open,high,low,close,volume FROM candle_rows WHERE series_id=? AND timestamp>=? AND timestamp<? ORDER BY timestamp",
                        (key, left, right),
                    )
                ]
                if left is not None
                else []
            )
        preview = rows[-limit:]
        return {
            "series": json.loads(entry[0]) if entry else None,
            "revision": entry[1] if entry else 0,
            "retained": extent[2],
            "oldest": iso(extent[0]) if extent[0] is not None else None,
            "newest": iso(extent[1]) if extent[1] is not None else None,
            "start": iso(left) if left is not None else None,
            "end": iso(right) if right is not None else None,
            "coverage": self.coverage(rows, left, right, timeframe) if left is not None else None,
            "candles": [
                {"timestamp": iso(row[0]), **dict(zip(FIELDS, row[1:6], strict=True))} for row in preview
            ],
            "preview_truncated": len(rows) > limit,
            "range_truncated": truncated,
            "preview_limit": limit,
            "latest_closed_end": iso(floor_time(now_ms(), timeframe)),
            "limits": {
                "per_series": self.per_series_limit,
                "workspace": self.total_limit,
                "range": MAX_RANGE,
            },
        }

    def snapshot(self, metadata, symbol, timeframe, start, end, label=""):
        """Copy a contiguous retained interval; gaps never silently become a research dataset."""
        left, right = boundaries(start, end, timeframe)
        count = (right - left) // step_ms(timeframe)
        if not 60 <= count <= 20_000:
            raise ValueError("A research dataset needs 60–20,000 whole candle intervals.")
        key = series_key(metadata["source"], metadata["environment"], symbol, timeframe)
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = [
                list(row)
                for row in db.execute(
                    "SELECT timestamp,open,high,low,close,volume FROM candle_rows WHERE series_id=? AND timestamp>=? AND timestamp<? ORDER BY timestamp",
                    (key, left, right),
                )
            ]
            coverage = self.coverage(rows, left, right, timeframe)
            if not coverage["complete"]:
                raise ValueError(
                    "The selected range has missing candles. Import or narrow it before saving a dataset."
                )
            candles = [{"timestamp": iso(row[0]), **dict(zip(FIELDS, row[1:], strict=True))} for row in rows]
            identity = {
                "source": metadata["source"],
                "environment": metadata["environment"],
                "symbol": symbol,
                "timeframe": timeframe,
                "schema": 1,
            }
            digest = hashlib.sha256(
                json.dumps(
                    [identity, candles], sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode()
            ).hexdigest()
            old = db.execute("SELECT metadata FROM candle_datasets WHERE id=?", (digest,)).fetchone()
            if old:
                return json.loads(old[0])
            if db.execute("SELECT COUNT(*) FROM candle_datasets").fetchone()[0] >= 1000:
                raise ValueError("The workspace dataset budget (1,000) has been reached.")
            document = {
                **identity,
                "id": digest,
                "digest": digest,
                "label": label.strip() or f"{symbol} · {timeframe}",
                "source_label": metadata["source_label"],
                "count": count,
                "start": iso(left),
                "end": iso(right),
                "created_at": iso(now_ms()),
                "immutable": True,
            }
            db.execute(
                "INSERT INTO candle_datasets VALUES(?,?,?)",
                (digest, json.dumps(document), json.dumps(candles, allow_nan=False)),
            )
        return document

    def dataset(self, identity):
        """Read an immutable dataset without touching a provider or mutable archive rows."""
        with self.store.db() as db:
            row = db.execute(
                "SELECT metadata,candles FROM candle_datasets WHERE id=?", (identity,)
            ).fetchone()
        if row is None:
            raise LookupError("Candle dataset not found.")
        meta, candles = json.loads(row[0]), json.loads(row[1])
        provenance = {key: meta[key] for key in ("source", "environment", "symbol", "timeframe", "schema")}
        digest = hashlib.sha256(
            json.dumps([provenance, candles], sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()
        if digest != identity or len(candles) != meta["count"]:
            raise ValueError("Dataset integrity check failed. This saved input cannot be used.")
        return {"dataset": meta, "candles": candles}

    def catalog(self):
        """List retained series and their extents without contacting any provider."""
        with self.store.db() as db:
            rows = db.execute(
                "SELECT s.metadata,s.revision,MIN(c.timestamp),MAX(c.timestamp),COUNT(c.timestamp) FROM candle_series s LEFT JOIN candle_rows c ON c.series_id=s.id GROUP BY s.id ORDER BY s.rowid DESC LIMIT 1000"
            ).fetchall()
            total = db.execute("SELECT COUNT(*) FROM candle_series").fetchone()[0]
        return {
            "items": [
                {
                    **json.loads(r[0]),
                    "revision": r[1],
                    "oldest": iso(r[2]) if r[2] is not None else None,
                    "newest": iso(r[3]) if r[3] is not None else None,
                    "retained": r[4],
                }
                for r in rows
            ],
            "total": total,
            "truncated": total > 1000,
        }

    def datasets(self, offset=0):
        """Page small snapshot metadata only; chart/bar payloads are loaded on demand."""
        with self.store.db() as db:
            rows = db.execute(
                "SELECT metadata FROM candle_datasets ORDER BY rowid DESC LIMIT 50 OFFSET ?", (offset,)
            ).fetchall()
            count = db.execute("SELECT COUNT(*) FROM candle_datasets").fetchone()[0]
        return {"items": [json.loads(row[0]) for row in rows], "total": count, "offset": offset, "limit": 50}

    def prune(self, source, environment, symbol, timeframe, before, confirmation):
        """Remove only old mutable observations; referenced immutable datasets are untouched."""
        if confirmation != "PRUNE " + symbol:
            raise ValueError("Type PRUNE " + symbol + " to remove old archive observations.")
        cutoff = milliseconds(before)
        if cutoff > now_ms():
            raise ValueError("Use a past retention cutoff.")
        key = series_key(source, environment, symbol, timeframe)
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute(
                "SELECT 1 FROM candle_imports WHERE series_id=? AND status IN ('queued','running','retrying')",
                (key,),
            ).fetchone()
            if active:
                raise ValueError("Pause this series import before pruning older observations.")
            count = db.execute(
                "DELETE FROM candle_rows WHERE series_id=? AND timestamp<?", (key, cutoff)
            ).rowcount
            if count:
                db.execute("UPDATE candle_series SET revision=revision+1 WHERE id=?", (key,))
        return {"removed": count, "before": iso(cutoff), "snapshots_preserved": True}
