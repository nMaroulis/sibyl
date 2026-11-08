"""Single-worker durable local job admission, scheduling and terminal receipts.

Read-only handlers may restart from their frozen arguments. Other interrupted
work requires an explicit new request; arbitrary processes and provider writes
are never dispatched. Cancellation cannot kill a Python thread or undo domain
commits, and an admitted result cannot overwrite a later cancellation.
"""

import json
import threading
import time
from datetime import UTC, datetime
from uuid import uuid4

ACTIVE = {"queued", "running"}
MAX_JOBS = 100
MAX_RUNS = 20


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, UTC).isoformat()


class LocalJobs:
    """Persist due times and idempotency identities; claim/finish with short transactions."""

    def __init__(self, store, handlers, *, clock=time.time):
        self.store, self.clock = store, clock
        self.handlers = {handler.name: handler for handler in handlers}
        self.execution = threading.Lock()
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS local_jobs (id TEXT PRIMARY KEY, state TEXT NOT NULL, revision INTEGER NOT NULL, next_due REAL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS local_job_runs (id TEXT PRIMARY KEY, job_id TEXT NOT NULL, request_id TEXT NOT NULL UNIQUE, state TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS local_job_runs_queue ON local_job_runs(state,job_id);
                CREATE TABLE IF NOT EXISTS local_job_requests (request_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, run_id TEXT NOT NULL);
                INSERT OR IGNORE INTO local_job_requests SELECT request_id,job_id,id FROM local_job_runs;
            """)
            db.execute("BEGIN IMMEDIATE")
            for raw in db.execute("SELECT payload FROM local_job_runs WHERE state='running'").fetchall():
                run = json.loads(raw[0])
                handler = self.handlers.get(run["kind"])
                run.update(
                    state="queued" if handler and handler.restart_safe else "interrupted",
                    recovered=True,
                    finished_at=None if handler and handler.restart_safe else iso(clock()),
                    error=None
                    if handler and handler.restart_safe
                    else "Interrupted work was not replayed. Review domain results before submitting a new request.",
                )
                self._write_run(db, run)

    @staticmethod
    def _read(db, identity):
        row = db.execute("SELECT payload FROM local_jobs WHERE id=?", (identity,)).fetchone()
        if not row:
            raise LookupError("Job not found.")
        return json.loads(row[0])

    @staticmethod
    def _write(db, row):
        db.execute(
            "INSERT INTO local_jobs VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,revision=excluded.revision,next_due=excluded.next_due,payload=excluded.payload",
            (row["id"], row["state"], row["revision"], row["next_due"], json.dumps(row, allow_nan=False)),
        )

    @staticmethod
    def _write_run(db, run):
        db.execute(
            "INSERT INTO local_job_runs VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,payload=excluded.payload",
            (run["id"], run["job_id"], run["request_id"], run["state"], json.dumps(run, allow_nan=False)),
        )

    def create(self, body):
        """Validate a registered handler before persisting a paused/explicitly armed job."""
        handler = self.handlers.get(body.kind)
        if handler is None:
            raise ValueError("Choose an implemented job type.")
        if len(json.dumps(body.arguments)) > 16_384:
            raise ValueError("Job arguments exceed the 16 KiB budget.")
        arguments = handler.validate(body.arguments)
        if body.interval_seconds and not handler.repeatable:
            raise ValueError("This job type supports explicit one-off runs only.")
        if body.kind == "forecast.train" and arguments.get("input_kind") != "saved_dataset":
            raise ValueError("Use a pinned saved dataset for queued training.")
        now = self.clock()
        row = {
            "id": uuid4().hex,
            "label": body.label,
            "kind": body.kind,
            "arguments": arguments,
            "interval_seconds": body.interval_seconds,
            "missed": body.missed,
            "state": "active" if body.enabled else "paused",
            "revision": 1,
            "next_due": body.start_at.timestamp() if body.start_at else now,
            "created_at": iso(now),
            "skipped_occurrences": 0,
            "last_run_id": None,
        }
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if (
                db.execute("SELECT COUNT(*) FROM local_jobs WHERE state!='archived'").fetchone()[0]
                >= MAX_JOBS
            ):
                raise ValueError("The 100-job workspace limit has been reached.")
            self._write(db, row)
        return row

    def state(self):
        """Read schedules and actual outcomes; this does not execute a job or probe providers."""
        with self.store.db() as db:
            jobs = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT payload FROM local_jobs WHERE state!='archived' ORDER BY rowid DESC LIMIT 100"
                )
            ]
            for job in jobs:
                last = (
                    db.execute(
                        "SELECT payload FROM local_job_runs WHERE id=?", (job["last_run_id"],)
                    ).fetchone()
                    if job["last_run_id"]
                    else None
                )
                receipt = json.loads(last[0]) if last else None
                job["latest_run"] = (
                    {key: receipt[key] for key in ("id", "state", "created_at", "started_at", "finished_at")}
                    if receipt
                    else None
                )
            counts = {
                row[0]: row[1]
                for row in db.execute("SELECT state,COUNT(*) FROM local_job_runs GROUP BY state")
            }
        return {
            "items": jobs,
            "handlers": [handler.public() for handler in self.handlers.values()],
            "run_counts": counts,
            "limit": MAX_JOBS,
            "note": "Single local worker. Paused schedules can run once explicitly. Cancellation suppresses late job success but cannot kill a thread or undo domain work already committed. Read-only interrupted jobs resume; training requires review and a new request.",
        }

    def runs(self, identity):
        with self.store.db() as db:
            self._read(db, identity)
            rows = db.execute(
                "SELECT payload FROM local_job_runs WHERE job_id=? ORDER BY rowid DESC LIMIT 20", (identity,)
            ).fetchall()
        return {"items": [json.loads(row[0]) for row in rows], "limit": MAX_RUNS}

    def run(self, identity, run_id):
        """Read one retained receipt for inspection/export without executing it."""
        with self.store.db() as db:
            row = db.execute(
                "SELECT payload FROM local_job_runs WHERE job_id=? AND id=?", (identity, run_id)
            ).fetchone()
        if row is None:
            raise LookupError("Job run not retained.")
        return json.loads(row[0])

    def action(self, identity, body):
        """Change future scheduling with a revision guard; already queued work is separate."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._read(db, identity)
            if row["revision"] != body.revision:
                raise ValueError("Job settings changed. Reload before editing.")
            if row["state"] == "archived":
                raise ValueError("Archived jobs cannot be resumed.")
            row.update(
                state={"pause": "paused", "resume": "active", "archive": "archived"}[body.action],
                revision=row["revision"] + 1,
            )
            if body.action == "archive":
                for raw in db.execute(
                    "SELECT payload FROM local_job_runs WHERE job_id=? AND state IN ('queued','running')",
                    (identity,),
                ).fetchall():
                    run = json.loads(raw[0])
                    run.update(
                        state="cancelled",
                        finished_at=iso(self.clock()),
                        error="Job archived. Already admitted domain work cannot be undone.",
                    )
                    self._write_run(db, run)
            if body.action == "resume":
                row["next_due"] = self.clock()
            self._write(db, row)
        return row

    def _enqueue(self, db, row, request_id, scheduled_for=None):
        existing = db.execute(
            "SELECT payload FROM local_job_runs WHERE request_id=?", (request_id,)
        ).fetchone()
        if existing:
            run = json.loads(existing[0])
            if run["job_id"] != row["id"]:
                raise ValueError("This request identity belongs to another job.")
            return run
        if db.execute("SELECT 1 FROM local_job_requests WHERE request_id=?", (request_id,)).fetchone():
            raise ValueError(
                "This request was already accepted; its detailed receipt expired. It was not repeated."
            )
        if row["state"] == "archived":
            raise ValueError("Archived jobs cannot start new runs.")
        if db.execute(
            "SELECT 1 FROM local_job_runs WHERE job_id=? AND state IN ('queued','running')", (row["id"],)
        ).fetchone():
            raise ValueError("This job already has queued or running work.")
        run = {
            "id": uuid4().hex,
            "job_id": row["id"],
            "request_id": request_id,
            "label": row["label"],
            "kind": row["kind"],
            "arguments": row["arguments"],
            "job_revision": row["revision"],
            "state": "queued",
            "created_at": iso(self.clock()),
            "scheduled_for": iso(scheduled_for) if scheduled_for is not None else None,
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
            "recovered": False,
        }
        self._write_run(db, run)
        db.execute("INSERT INTO local_job_requests VALUES(?,?,?)", (request_id, row["id"], run["id"]))
        row["last_run_id"] = run["id"]
        self._write(db, row)
        # Keep active work and the newest 20 finished receipts per job.
        db.execute(
            "DELETE FROM local_job_runs WHERE job_id=? AND state NOT IN ('queued','running') AND id NOT IN (SELECT id FROM local_job_runs WHERE job_id=? ORDER BY rowid DESC LIMIT 20)",
            (row["id"], row["id"]),
        )
        return run

    def start(self, identity, request_id):
        """Accept one idempotent explicit run, including while its schedule is paused."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            return self._enqueue(db, self._read(db, identity), request_id)

    def cancel(self, identity, run_id):
        """Cancel local waiting/interest; a running domain operation may still finish."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            raw = db.execute(
                "SELECT payload FROM local_job_runs WHERE id=? AND job_id=?", (run_id, identity)
            ).fetchone()
            if not raw:
                raise LookupError("Job run not found.")
            run = json.loads(raw[0])
            if run["state"] not in ACTIVE:
                return run
            run.update(
                state="cancelled",
                finished_at=iso(self.clock()),
                error="Cancelled. Work already admitted to a domain service cannot be undone.",
            )
            self._write_run(db, run)
        return run

    def _due(self, db):
        now = self.clock()
        for raw in db.execute(
            "SELECT payload FROM local_jobs WHERE state='active' AND next_due<=? ORDER BY next_due LIMIT 100",
            (now,),
        ).fetchall():
            row = json.loads(raw[0])
            if db.execute(
                "SELECT 1 FROM local_job_runs WHERE job_id=? AND state IN ('queued','running')", (row["id"],)
            ).fetchone():
                continue
            due, interval = row["next_due"], row["interval_seconds"]
            missed = int((now - due) // interval) if interval else int(now - due > 60)
            if not interval:
                row["state"] = "exhausted"
            row["next_due"] = due + (missed + 1) * interval if interval else None
            row["skipped_occurrences"] += (
                (missed if interval else 0)
                if row["missed"] == "once"
                else (missed + 1 if interval else 1)
                if missed
                else 0
            )
            self._write(db, row)
            if missed and row["missed"] == "skip":
                continue
            self._enqueue(db, row, uuid4().hex, due)

    def tick(self):
        """Claim one FIFO run, execute outside SQLite and preserve concurrent cancellation."""
        if not self.execution.acquire(blocking=False):
            return
        try:
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                self._due(db)
                raw = db.execute(
                    "SELECT payload FROM local_job_runs WHERE state='queued' ORDER BY rowid LIMIT 1"
                ).fetchone()
                if raw is None:
                    return
                run = json.loads(raw[0])
                run.update(state="running", started_at=iso(self.clock()))
                self._write_run(db, run)
            started = time.monotonic()
            result, error = None, None
            try:
                handler = self.handlers[run["kind"]]
                result = handler.execute(handler.validate(run["arguments"]))
                encoded = json.dumps(result, allow_nan=False)
                if len(encoded.encode()) > 256_000:
                    raise ValueError("Job output exceeded the retained-result budget.")
            except Exception as exc:
                error = type(exc).__name__[:80]  # Native messages may contain private URLs/content.
                result = None
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute("SELECT state FROM local_job_runs WHERE id=?", (run["id"],)).fetchone()
                if current and current[0] == "running":
                    run.update(
                        state="failed" if error else "completed",
                        finished_at=iso(self.clock()),
                        result=result,
                        error=error,
                        duration_seconds=round(max(0, time.monotonic() - started), 3),
                    )
                    self._write_run(db, run)
        finally:
            self.execution.release()
