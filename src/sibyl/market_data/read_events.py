"""Bounded, credential-free transport evidence for local connection alerts."""

import threading
from collections import OrderedDict
from uuid import uuid4

from sibyl.market_data.control import MESSAGES, READS

MAX_EVENTS = 50_000
MAX_STREAMS = 1024


class ProviderReadEvents:
    """Journal actual read completions in the same transaction as hourly telemetry.

    Session/generation/operation sequence numbers disclose dropped or reordered
    observations. The writer never saves a URL, request argument, body, key or
    raw exception. Pruning records a watermark so consumers can reset safely.
    """

    def __init__(self, store):
        self.session = uuid4().hex
        self._lock = threading.Lock()
        self._streams = OrderedDict()
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS provider_read_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, source_id TEXT NOT NULL,
                    provider TEXT NOT NULL, environment TEXT NOT NULL, source_kind TEXT NOT NULL,
                    session TEXT NOT NULL, generation TEXT NOT NULL, sequence INTEGER NOT NULL,
                    operation TEXT NOT NULL, at TEXT NOT NULL, error_kind TEXT, retired INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS provider_events_source ON provider_read_events(source_id,id);
                CREATE INDEX IF NOT EXISTS provider_events_time ON provider_read_events(at);
                CREATE TABLE IF NOT EXISTS provider_event_retention (
                    id INTEGER PRIMARY KEY CHECK(id=1), pruned_through INTEGER NOT NULL
                );
                INSERT OR IGNORE INTO provider_event_retention VALUES(1,0);
            """)

    def prepare(self, source, generation, at, error_kind, operation="read", retired=False):
        """Assign sequence before storage; a failed write leaves a detectable gap."""
        operation = operation if operation in READS else "read"
        key = (source["id"], generation, operation)
        with self._lock:
            sequence, stream = self._streams.pop(key, (0, None))
            sequence += 1
            # A new stream token also distinguishes LRU eviction from reordering.
            stream = stream or uuid4().hex
            self._streams[key] = (sequence, stream)
            if len(self._streams) > MAX_STREAMS:
                self._streams.popitem(last=False)
        return (
            source["id"],
            source["provider"],
            source["environment"],
            source["kind"],
            f"{self.session}:{stream}",
            generation,
            sequence,
            operation,
            at,
            error_kind if error_kind in MESSAGES else None if error_kind is None else "invalid_data",
            int(retired),
        )

    @staticmethod
    def _watermark(db, identity):
        if identity is not None:
            db.execute(
                "UPDATE provider_event_retention SET pruned_through=MAX(pruned_through,?) WHERE id=1",
                (identity,),
            )

    def append(self, db, observation):
        """Append under the caller's bounded telemetry transaction; cap by journal ID."""
        identity = db.execute(
            "INSERT INTO provider_read_events(source_id,provider,environment,source_kind,session,generation,sequence,operation,at,error_kind,retired) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            observation,
        ).lastrowid
        cutoff = identity - MAX_EVENTS
        if cutoff > 0:
            db.execute("DELETE FROM provider_read_events WHERE id<=?", (cutoff,))
            self._watermark(db, cutoff)

    def prune_age(self, db, cutoff):
        """Retain a contiguous suffix when old evidence expires, including clock anomalies."""
        last_old = db.execute("SELECT MAX(id) FROM provider_read_events WHERE at<?", (cutoff,)).fetchone()[0]
        if last_old is not None:
            db.execute("DELETE FROM provider_read_events WHERE id<=?", (last_old,))
            self._watermark(db, last_old)

    @staticmethod
    def tail(db):
        """Keep a monotonic boundary even when retention emptied the journal."""
        return max(
            db.execute("SELECT COALESCE(MAX(id),0) FROM provider_read_events").fetchone()[0],
            db.execute("SELECT pruned_through FROM provider_event_retention WHERE id=1").fetchone()[0],
        )
