"""Explicit bounded SQLite checks and an allowlisted, content-free support report."""

import copy
import math
import platform
import sqlite3
import threading
import time
from collections import Counter
from contextlib import closing
from datetime import UTC, datetime

from sibyl import __version__

RESOURCE_FIELDS = (
    "cpu_percent",
    "sample_seconds",
    "rss_bytes",
    "threads",
    "database_bytes",
    "volume_free_bytes",
    "uptime_seconds",
)
STATES = {"starting", "running", "waiting", "retrying", "paused", "failed", "stalled", "overdue", "stopped"}


class WorkspaceDiagnostics:
    """Keep only the last explicit report in memory; agents never start a check.

    quick_check is not full integrity_check, logical accounting validation, vault
    authentication or a repair operation. Native SQLite messages can contain
    private names/content and are deliberately excluded from the report.
    """

    def __init__(self, store, workers, *, budget_seconds=2, clock=time.monotonic):
        self.store, self.workers = store, workers
        self.budget, self.clock = budget_seconds, clock
        self.lock, self._last = threading.Lock(), None

    def last(self):
        return copy.deepcopy(self._last)

    def check_database(self):
        started = self.clock()
        deadline = started + self.budget
        status, findings = "unavailable", None
        try:
            with closing(
                sqlite3.connect(self.store.path.resolve().as_uri() + "?mode=ro", uri=True, timeout=0.2)
            ) as db:
                try:
                    db.execute("PRAGMA query_only=ON")
                    db.set_progress_handler(lambda: int(self.clock() >= deadline), 1000)
                    if self.clock() >= deadline:
                        status = "incomplete"
                    else:
                        rows = db.execute("PRAGMA quick_check(10)").fetchall()
                        status = "passed" if rows == [("ok",)] else "issues_detected"
                        findings = 0 if status == "passed" else len(rows)
                finally:
                    db.set_progress_handler(None, 0)
        except (sqlite3.Error, OSError):
            status = "incomplete" if self.clock() >= deadline else "unavailable"
        return {
            "status": status,
            "findings": findings,
            "duration_ms": round((self.clock() - started) * 1000, 2),
            "method": "SQLite quick_check(10), read-only connection",
            "note": {
                "passed": "SQLite reported no issues in this quick check. This is not a full integrity check or proof that account data is correct.",
                "issues_detected": "SQLite reported structural issues. Native details are excluded to protect private data. Preserve a backup and investigate before attempting repairs.",
                "incomplete": "The quick check exceeded its execution budget. No integrity conclusion is available.",
                "unavailable": "The database could not be checked; it may be busy, inaccessible or invalid. No integrity conclusion is available.",
            }[status],
        }

    def run(self):
        if not self.lock.acquire(blocking=False):
            raise ValueError("A workspace health check is already running.")
        try:
            database = self.check_database()
            observation = "observed"
            try:
                health = self.workers.snapshot()
            except (sqlite3.Error, OSError):
                observation = "unavailable"
                health = {"resources": self.workers.resources.snapshot(), "workers": []}
            resources = {}
            for key in RESOURCE_FIELDS:
                value = health.get("resources", {}).get(key)
                resources[key] = (
                    value if type(value) in {int, float} and math.isfinite(value) and value >= 0 else None
                )
            counts = Counter(
                row["state"] if row.get("state") in STATES else "unknown" for row in health.get("workers", [])
            )
            report = {
                "schema": 1,
                "generated_at": datetime.now(UTC).isoformat(),
                "sibyl_version": __version__,
                "runtime": {
                    "python": platform.python_version(),
                    "sqlite": sqlite3.sqlite_version,
                    "os_family": platform.system(),
                },
                "database": database,
                "resources": resources,
                "worker_states": dict(counts),
                "worker_observation": observation,
                "scope": "One explicit local observation. No provider requests, repairs or account actions. Worker counts and process resources do not prove exchange readiness or external uptime.",
                "privacy": "Allowlisted versions, numeric process/storage counters, aggregate worker states and generic database outcomes only. Excludes credentials, tokens, paths, hostnames, account identifiers, balances, chats, articles, plugin code and raw error messages.",
            }
            self._last = report
            return self.last()
        finally:
            self.lock.release()
