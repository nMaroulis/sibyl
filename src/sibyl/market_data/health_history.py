"""Bounded, local history of actual provider HTTP read outcomes.

Only fixed source IDs, counts, timings and classified errors are retained. History
is separate from current credential readiness, quote freshness and uptime claims.
"""

import math
import sqlite3
import threading
from contextlib import closing
from datetime import UTC, datetime, timedelta

from sibyl.market_data.control import MESSAGES
from sibyl.storage import Store

RETENTION_DAYS = 14
MAX_HOURS = 50_000
MAX_ERRORS = 2_000


class ProviderHistory:
    """Save read observations without making telemetry a dependency of provider calls.

    Each completed transport read commits one hourly counter update. Writes wait
    at most 50 ms for SQLite; storage failures are counted and disclosed rather
    than replacing a provider result, consuming its retries or affecting writes.
    There is no network probing, background sampler or buffered replay.
    """

    def __init__(self, store: Store, clock=None):
        self.store = store
        self.clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()
        self._dropped = 0
        self._last_failure_at = None
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS provider_read_hours (
                    source_id TEXT NOT NULL, kind TEXT NOT NULL, provider TEXT NOT NULL,
                    environment TEXT NOT NULL, generation TEXT NOT NULL, hour TEXT NOT NULL,
                    requests INTEGER NOT NULL DEFAULT 0, successes INTEGER NOT NULL DEFAULT 0,
                    failures INTEGER NOT NULL DEFAULT 0, latency_sum REAL NOT NULL DEFAULT 0,
                    latency_max REAL NOT NULL DEFAULT 0, first_at TEXT NOT NULL, last_at TEXT NOT NULL,
                    PRIMARY KEY(source_id, generation, hour)
                );
                CREATE INDEX IF NOT EXISTS provider_hours_time ON provider_read_hours(hour);
                CREATE INDEX IF NOT EXISTS provider_hours_source ON provider_read_hours(source_id, hour);
                CREATE TABLE IF NOT EXISTS provider_read_errors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT NOT NULL,
                    generation TEXT NOT NULL, at TEXT NOT NULL, kind TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS provider_errors_source ON provider_read_errors(source_id, at);
            """)
            self._prune(db)

    def _prune(self, db):
        """Bound age and row counts, independently of how many profiles have been used."""
        cutoff = (self.clock() - timedelta(days=RETENTION_DAYS)).isoformat()
        db.execute("DELETE FROM provider_read_hours WHERE hour < ?", (cutoff,))
        db.execute("DELETE FROM provider_read_errors WHERE at < ?", (cutoff,))
        db.execute(
            "DELETE FROM provider_read_hours WHERE rowid IN "
            "(SELECT rowid FROM provider_read_hours ORDER BY hour DESC, rowid DESC LIMIT -1 OFFSET ?)",
            (MAX_HOURS,),
        )
        db.execute(
            "DELETE FROM provider_read_errors WHERE id IN "
            "(SELECT id FROM provider_read_errors ORDER BY id DESC LIMIT -1 OFFSET ?)",
            (MAX_ERRORS,),
        )

    def recording(self) -> dict:
        """Expose missing observations instead of silently claiming complete telemetry."""
        with self._lock:
            return {
                "status": "partial" if self._dropped else "ready",
                "dropped_observations": self._dropped,
                "last_failure_at": self._last_failure_at,
            }

    def record(self, source: dict, generation: str, latency_ms: float, error_kind: str | None):
        """Commit one actual read; cache hits, deferrals, Demo and mutations never call this."""
        if source["provider"] == "demo":
            return
        if not math.isfinite(latency_ms) or latency_ms < 0:
            return
        at = self.clock()
        hour = at.replace(minute=0, second=0, microsecond=0).isoformat()
        failed = error_kind is not None
        kind = error_kind if error_kind in MESSAGES else "invalid_data"
        try:
            with closing(sqlite3.connect(self.store.path, timeout=0.05)) as db, db:
                db.execute("BEGIN IMMEDIATE")
                inserted = db.execute(
                    "INSERT OR IGNORE INTO provider_read_hours "
                    "(source_id,kind,provider,environment,generation,hour,first_at,last_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (
                        source["id"],
                        source["kind"],
                        source["provider"],
                        source["environment"],
                        generation,
                        hour,
                        at.isoformat(),
                        at.isoformat(),
                    ),
                ).rowcount
                db.execute(
                    "UPDATE provider_read_hours SET requests=requests+1, successes=successes+?, "
                    "failures=failures+?, latency_sum=latency_sum+?, latency_max=MAX(latency_max,?), "
                    "first_at=MIN(first_at,?), last_at=MAX(last_at,?) "
                    "WHERE source_id=? AND generation=? AND hour=?",
                    (
                        int(not failed),
                        int(failed),
                        latency_ms,
                        latency_ms,
                        at.isoformat(),
                        at.isoformat(),
                        source["id"],
                        generation,
                        hour,
                    ),
                )
                if failed:
                    db.execute(
                        "INSERT INTO provider_read_errors(source_id,generation,at,kind) VALUES (?,?,?,?)",
                        (source["id"], generation, at.isoformat(), kind),
                    )
                if inserted or failed:
                    self._prune(db)
        except sqlite3.Error:
            # Do not leak paths/SQL, mask a provider error, or cause a read/write retry.
            with self._lock:
                self._dropped += 1
                self._last_failure_at = at.isoformat()

    def identities(self) -> list[dict]:
        """Find at most 512 retained sources without retaining user labels or credentials."""
        cutoff = (self.clock() - timedelta(days=RETENTION_DAYS)).isoformat()
        with self.store.db() as db:
            rows = db.execute(
                "SELECT source_id AS id, kind, provider, environment, MAX(last_at) AS last_at "
                "FROM provider_read_hours WHERE hour>=? "
                "GROUP BY source_id,kind,provider,environment ORDER BY last_at DESC LIMIT 512",
                (cutoff,),
            ).fetchall()
        return [dict(row) for row in rows]

    def read(self, source_id: str, hours: int = 24) -> dict:
        """Read 24/168 hourly buckets; empty periods remain unobserved, never downtime."""
        if hours not in {24, 168}:
            raise ValueError("Choose a 24-hour or 7-day history window.")
        now = self.clock()
        start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=hours - 1)
        with self.store.db() as db:
            db.execute("BEGIN")
            rows = db.execute(
                "SELECT hour, SUM(requests) AS requests, SUM(successes) AS successes, "
                "SUM(failures) AS failures, SUM(latency_sum) AS latency_sum, "
                "MAX(latency_max) AS latency_max, MIN(first_at) AS first_at, MAX(last_at) AS last_at "
                "FROM provider_read_hours WHERE source_id=? AND hour>=? AND hour<=? "
                "GROUP BY hour ORDER BY hour",
                (source_id, start.isoformat(), now.isoformat()),
            ).fetchall()
            errors = db.execute(
                "SELECT at,kind FROM provider_read_errors WHERE source_id=? AND at>=? AND at<=? "
                "ORDER BY at DESC,id DESC LIMIT 20",
                (source_id, start.isoformat(), now.isoformat()),
            ).fetchall()
        by_hour = {row["hour"]: dict(row) for row in rows}
        count = sum(row["requests"] for row in rows)
        success = sum(row["successes"] for row in rows)
        latency = sum(row["latency_sum"] for row in rows)
        return {
            "source_id": source_id,
            "as_of": now.isoformat(),
            "start": start.isoformat(),
            "hours": hours,
            "retention_days": RETENTION_DAYS,
            "totals": {
                "requests": count,
                "successes": success,
                "failures": count - success,
                "success_rate": round(100 * success / count, 2) if count else None,
                "mean_latency_ms": round(latency / count, 1) if count else None,
                "max_latency_ms": max((row["latency_max"] for row in rows), default=None),
                "first_at": min((row["first_at"] for row in rows), default=None),
                "last_at": max((row["last_at"] for row in rows), default=None),
            },
            "series": [
                {
                    "at": (start + timedelta(hours=index)).isoformat(),
                    "requests": (item := by_hour.get((start + timedelta(hours=index)).isoformat(), {})).get(
                        "requests", 0
                    ),
                    "successes": item.get("successes", 0),
                    "failures": item.get("failures", 0),
                    "mean_latency_ms": round(item["latency_sum"] / item["requests"], 1) if item else None,
                }
                for index in range(hours)
            ],
            "recent_errors": [
                {
                    "at": row["at"],
                    "kind": row["kind"],
                    "message": MESSAGES.get(row["kind"], MESSAGES["invalid_data"]),
                }
                for row in errors
            ],
            "recording": self.recording(),
        }
