"""Persist observed worker stalls without depending on the API event loop or browser.

A local watchdog thread samples actual worker progress. It can observe a blocked
async event loop while Python threads still run. It cannot prove host uptime,
detect its own process death in real time or recover a side-effecting operation.
Observer gaps and process boundaries are uncertainty, never invented recovery.
"""

import json
import math
import re
import threading
import time
from datetime import UTC, datetime
from uuid import uuid4

from sibyl.alerts.history.schema import ensure_schema

ISSUES = {"failed", "stalled", "overdue", "retrying", "stopped"}


def stamp():
    return datetime.now(UTC).isoformat()


def evidence(row):
    """Allowlist bounded numeric/lifecycle observations; omit errors, paths and domain payloads."""
    result = {}
    for key in ("iterations", "failures", "deadline_seconds", "interval_seconds", "elapsed_seconds"):
        value = row.get(key)
        result[key] = value if type(value) in {int, float} and math.isfinite(value) and value >= 0 else None
    for key in ("last_started_at", "last_finished_at"):
        value = row.get(key)
        try:
            parsed = datetime.fromisoformat(value)
            result[key] = parsed.astimezone(UTC).isoformat() if parsed.tzinfo else None
        except (ValueError, TypeError):
            result[key] = None
    return result


class WorkerWatchdog:
    """Retain one incident per worker/observer, with local start/recovery inbox notices.

    Starting and ending observation are explicit owner lifecycle operations.
    Reads never manufacture samples. Notification acknowledgment does not close
    an incident, retry a worker or grant permission for an exchange operation.
    """

    def __init__(self, store, observations, *, clock=time.monotonic, interval=2):
        self.store, self.observations, self.clock = store, observations, clock
        self.interval = interval
        self.id = uuid4().hex
        self.stop = threading.Event()
        self.thread = None
        self.lock = threading.Lock()
        self.started_clock = clock()
        self.last_sample = None
        self.last_success = None
        self.errors = 0
        self.closed = False
        with store.db() as db:
            ensure_schema(db)
            db.executescript("""
                CREATE TABLE IF NOT EXISTS worker_watch_sessions (
                    id TEXT PRIMARY KEY,started_at TEXT NOT NULL,last_sample_at TEXT,ended_at TEXT
                );
                CREATE TABLE IF NOT EXISTS worker_incidents (
                    id TEXT PRIMARY KEY,observer_id TEXT NOT NULL,worker_id TEXT NOT NULL,
                    state TEXT NOT NULL,first_detected_at TEXT NOT NULL,last_observed_at TEXT NOT NULL,
                    ended_at TEXT,payload TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS worker_incident_open ON worker_incidents(observer_id,worker_id) WHERE state='active';
                CREATE TABLE IF NOT EXISTS worker_watch_gaps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,observer_id TEXT NOT NULL,detected_at TEXT NOT NULL,seconds REAL NOT NULL
                );
            """)
            # A later process cannot establish when/if the old worker recovered.
            db.execute(
                "UPDATE worker_incidents SET state='observation_ended',ended_at=NULL WHERE state='active'"
            )
            db.execute("INSERT INTO worker_watch_sessions VALUES(?,?,NULL,NULL)", (self.id, stamp()))
            db.execute(
                "DELETE FROM worker_watch_sessions WHERE id NOT IN (SELECT id FROM worker_watch_sessions ORDER BY rowid DESC LIMIT 20)"
            )

    def start(self):
        """Start one owned daemon thread after workers are registered; no provider is contacted."""
        if self.thread is not None or self.closed:
            return
        self.thread = threading.Thread(target=self._run, name="sibyl-worker-watchdog", daemon=True)
        self.thread.start()

    def _run(self):
        while not self.stop.wait(self.interval):
            try:
                self.sample()
            except Exception:
                # An observer fault must not alter any domain operation. The next
                # successful sample records the actual unobserved time interval.
                with self.lock:
                    self.errors += 1

    @staticmethod
    def _notify(db, identity, worker, action, phase, observed):
        payload = {
            "kind": "workspace",
            "label": "Background worker",
            "worker_id": worker,
            "incident_id": identity,
            "action": action,
            "phase": phase,
            "source": "local-workspace",
            "source_label": "Local Python backend",
            "environment": "local",
            "observed_at": observed,
            "note": "Observed progress only. No operation was cancelled, retried or verified at a provider.",
        }
        db.execute(
            "INSERT OR IGNORE INTO alert_notifications(id,rule_id,cycle,created_at,read_at,payload) VALUES(?,?,?,?,NULL,?)",
            (
                "worker-" + identity + "-" + action,
                "worker-" + identity,
                1 if action == "attention" else 2,
                observed,
                json.dumps(payload),
            ),
        )

    def sample(self):
        """Record actual observations even with a blocked event loop; deterministic for acceptance tests."""
        now, at = self.clock(), stamp()
        rows = self.observations()
        with self.lock:
            if self.closed:
                return
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                previous = self.last_success if self.last_success is not None else self.started_clock
                if now - previous > max(10, 3 * self.interval):
                    db.execute(
                        "INSERT INTO worker_watch_gaps(observer_id,detected_at,seconds) VALUES(?,?,?)",
                        (self.id, at, round(now - previous, 3)),
                    )
                for row in rows:
                    worker, phase = row.get("id", ""), row.get("state")
                    if not re.fullmatch(r"[a-z0-9-]{1,80}", worker):
                        continue
                    old = db.execute(
                        "SELECT * FROM worker_incidents WHERE observer_id=? AND worker_id=? AND state='active'",
                        (self.id, worker),
                    ).fetchone()
                    data = evidence(row)
                    if phase in ISSUES:
                        if old is None:
                            identity = uuid4().hex
                            payload = {
                                "first_phase": phase,
                                "last_phase": phase,
                                "first": data,
                                "last": data,
                                "observations": 1,
                            }
                            db.execute(
                                "INSERT INTO worker_incidents VALUES(?,?,?,'active',?,?,NULL,?)",
                                (identity, self.id, worker, at, at, json.dumps(payload)),
                            )
                            self._notify(db, identity, worker, "attention", phase, at)
                        else:
                            payload = json.loads(old["payload"])
                            payload.update(
                                last_phase=phase, last=data, observations=payload["observations"] + 1
                            )
                            db.execute(
                                "UPDATE worker_incidents SET last_observed_at=?,payload=? WHERE id=?",
                                (at, json.dumps(payload), old["id"]),
                            )
                    elif old is not None:
                        payload = json.loads(old["payload"])
                        # A successful real iteration must have advanced. Merely
                        # running/pausing or receiving a heartbeat is not recovery.
                        first_count = payload["first"].get("iterations")
                        if (
                            phase in {"running", "waiting"}
                            and first_count is not None
                            and data["iterations"] is not None
                            and data["iterations"] > first_count
                        ):
                            payload.update(last_phase=phase, last=data)
                            db.execute(
                                "UPDATE worker_incidents SET state='recovered',last_observed_at=?,ended_at=?,payload=? WHERE id=?",
                                (at, at, json.dumps(payload), old["id"]),
                            )
                            self._notify(db, old["id"], worker, "recovered", phase, at)
                db.execute("UPDATE worker_watch_sessions SET last_sample_at=? WHERE id=?", (at, self.id))
                db.execute(
                    "DELETE FROM worker_incidents WHERE state!='active' AND id NOT IN (SELECT id FROM worker_incidents ORDER BY rowid DESC LIMIT 200)"
                )
                db.execute(
                    "DELETE FROM worker_watch_gaps WHERE id NOT IN (SELECT id FROM worker_watch_gaps ORDER BY id DESC LIMIT 50)"
                )
            self.last_sample, self.last_success = at, now

    def status(self):
        """Read observer freshness; receiving this value is not itself a sample."""
        with self.lock:
            running = bool(self.thread and self.thread.is_alive() and not self.stop.is_set())
            lag = max(
                0, self.clock() - (self.last_success if self.last_success is not None else self.started_clock)
            )
            status = (
                "stopped"
                if self.closed
                else "not_started"
                if not self.thread
                else "overdue"
                if lag is not None and lag > max(10, 3 * self.interval)
                else "starting"
                if self.last_success is None and running
                else "observing"
                if running
                else "failed"
            )
            current = {
                "id": self.id,
                "status": status,
                "last_sample_at": self.last_sample,
                "sample_interval_seconds": self.interval,
                "sample_age_seconds": round(lag, 1) if lag is not None else None,
                "failed_samples": self.errors,
            }
        return current

    def snapshot(self, offset=0):
        """Read retained incidents and observer freshness without creating heartbeat evidence."""
        current = self.status()
        with self.store.db() as db:
            db.execute("BEGIN")
            rows = db.execute(
                "SELECT * FROM worker_incidents ORDER BY rowid DESC LIMIT 20 OFFSET ?", (offset,)
            ).fetchall()
            total = db.execute("SELECT COUNT(*) FROM worker_incidents").fetchone()[0]
            gaps = [
                dict(row)
                for row in db.execute(
                    "SELECT detected_at,seconds FROM worker_watch_gaps ORDER BY id DESC LIMIT 20"
                )
            ]
        return {
            "observer": current,
            "items": [
                {
                    **{key: row[key] for key in row.keys() if key != "payload"},
                    "evidence": json.loads(row["payload"]),
                }
                for row in rows
            ],
            "total": total,
            "offset": offset,
            "limit": 20,
            "gaps": gaps,
            "scope": "Observed local worker incidents, not exchange/host uptime. First detection is a sample, not an outage start. Recovered requires a later completed iteration; observation_ended is unresolved. Gaps, process death and suspend intervals are not reconstructed. Notices stay local and do not restart/cancel work.",
        }

    def close(self):
        """Stop and join the observer before workers are cancelled; never label shutdown recovery."""
        self.stop.set()
        if self.thread is not None:
            self.thread.join()
        with self.lock:
            if self.closed:
                return
            self.closed = True
            with self.store.db() as db:
                db.execute(
                    "UPDATE worker_incidents SET state='observation_ended' WHERE observer_id=? AND state='active'",
                    (self.id,),
                )
                db.execute("UPDATE worker_watch_sessions SET ended_at=? WHERE id=?", (stamp(), self.id))
