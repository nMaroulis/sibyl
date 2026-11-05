"""Persist report definitions and immutable attempts, separate from native run storage."""

import json
import sqlite3
from uuid import uuid4

from sibyl.agents.utils.requests import now
from sibyl.investigations.contracts import InvestigationCreate
from sibyl.storage import Store

ACTIVE = {"queued", "running", "cancelling"}


class InvestigationConflict(ValueError):
    """An investigation is busy or has reached its retained-report budget."""


class InvestigationRepository:
    """Store user research and report projections; ProtoLink owns execution evidence."""

    def __init__(self, store: Store):
        self.store = store
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS investigations (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS investigation_runs (
                    id TEXT PRIMARY KEY, investigation_id TEXT NOT NULL,
                    status TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS investigation_versions
                    ON investigation_runs(investigation_id,created_at);
                CREATE UNIQUE INDEX IF NOT EXISTS investigation_one_active
                    ON investigation_runs(investigation_id) WHERE status IN ('queued','running','cancelling');
            """)

    def recover(self):
        """Mark unfinished reports interrupted; never repeat paid inference after restart."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            for row in db.execute(
                "SELECT payload FROM investigation_runs WHERE status IN ('queued','running','cancelling')"
            ).fetchall():
                run = json.loads(row[0])
                self._write(
                    db,
                    {
                        **run,
                        "status": "interrupted",
                        "finished_at": now(),
                        "error": "The application stopped before this report finished. Rerun it explicitly.",
                    },
                )

    def create(self, request: InvestigationCreate):
        """Save a question without contacting any model or data provider."""
        item = {"id": uuid4().hex, **request.model_dump(), "created_at": now()}
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT COUNT(*) FROM investigations").fetchone()[0] >= 100:
                raise InvestigationConflict(
                    "Keep at most 100 investigations. Delete an old investigation first."
                )
            db.execute(
                "INSERT INTO investigations VALUES(?,?,?)", (item["id"], json.dumps(item), item["created_at"])
            )
        return item

    def list(self):
        """List bounded metadata without downloading report text or source snapshots."""
        with self.store.db() as db:
            rows = db.execute(
                "SELECT payload FROM investigations ORDER BY created_at DESC,id DESC LIMIT 100"
            ).fetchall()
            items = []
            for row in rows:
                item = json.loads(row[0])
                latest = db.execute(
                    "SELECT payload FROM investigation_runs WHERE investigation_id=? ORDER BY rowid DESC LIMIT 1",
                    (item["id"],),
                ).fetchone()
                items.append({**item, "runs": [self.summary(json.loads(latest[0]))] if latest else []})
            return items

    def get(self, identity):
        """Read a definition and at most fifty retained version summaries."""
        with self.store.db() as db:
            row = db.execute("SELECT payload FROM investigations WHERE id=?", (identity,)).fetchone()
            if row is None:
                raise LookupError("Investigation not found.")
            runs = db.execute(
                "SELECT payload FROM investigation_runs WHERE investigation_id=? ORDER BY rowid DESC",
                (identity,),
            ).fetchall()
        return {**json.loads(row[0]), "runs": [self.summary(json.loads(row[0])) for row in runs]}

    def run(self, identity, run_id):
        """Resolve a version only within the investigation that owns it."""
        with self.store.db() as db:
            row = db.execute(
                "SELECT payload FROM investigation_runs WHERE investigation_id=? AND id=?", (identity, run_id)
            ).fetchone()
        if row is None:
            raise LookupError("Investigation run not found.")
        return json.loads(row[0])

    def reserve(self, identity, run_id, context, models, origin="manual"):
        """Claim one version and workspace capacity atomically before accepting inference."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT investigation_id,payload FROM investigation_runs WHERE id=?", (run_id,)
            ).fetchone()
            if existing:
                if existing[0] != identity:
                    raise InvestigationConflict("This request identity belongs to another investigation.")
                return json.loads(existing[1]), False
            row = db.execute("SELECT payload FROM investigations WHERE id=?", (identity,)).fetchone()
            if row is None:
                raise LookupError("Investigation not found.")
            retained = db.execute(
                "SELECT COUNT(*) FROM investigation_runs WHERE investigation_id=?", (identity,)
            ).fetchone()[0]
            version = (
                db.execute(
                    "SELECT COALESCE(MAX(json_extract(payload,'$.version')),0) FROM investigation_runs WHERE investigation_id=?",
                    (identity,),
                ).fetchone()[0]
                + 1
            )
            if retained >= 50:
                raise InvestigationConflict(
                    "This investigation has 50 retained runs. Create a new investigation to continue."
                )
            if (
                db.execute(
                    "SELECT COUNT(*) FROM investigation_runs WHERE status IN ('queued','running','cancelling')"
                ).fetchone()[0]
                >= 4
            ):
                raise InvestigationConflict(
                    "Four investigations are already pending. Wait for one to finish."
                )
            run = {
                "id": run_id,
                "investigation_id": identity,
                "version": version,
                "origin": origin,
                "question": json.loads(row[0])["question"],
                "context": context,
                "models": models,
                "status": "queued",
                "created_at": now(),
                "finished_at": None,
                "session_id": None,
                "native_run_id": None,
                "report": None,
                "sources": [],
                "error": None,
            }
            try:
                db.execute(
                    "INSERT INTO investigation_runs VALUES(?,?,?,?,?)",
                    (run_id, identity, "queued", json.dumps(run), run["created_at"]),
                )
            except sqlite3.IntegrityError as exc:
                raise InvestigationConflict("This investigation already has a pending run.") from exc
        return run, True

    def prune_scheduled(self, identity, schedule_id, keep):
        """Apply explicit retention to old terminal runs from this schedule only.

        Manual reports, other schedules and active work are preserved. The caller
        decides whether an untouched generated conversation can also be removed.
        Keeping at least one version keeps future version numbers monotonic.
        """
        if keep < 1:
            raise ValueError("Retain at least one scheduled version.")
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT id,payload FROM investigation_runs WHERE investigation_id=? AND json_extract(payload,'$.origin')=? AND status NOT IN ('queued','running','cancelling') ORDER BY json_extract(payload,'$.version') DESC",
                (identity, f"schedule:{schedule_id}"),
            ).fetchall()
            removed = [json.loads(row["payload"]) for row in rows[keep:]]
            db.executemany("DELETE FROM investigation_runs WHERE id=?", [(run["id"],) for run in removed])
        return removed

    @staticmethod
    def _write(db, run):
        db.execute(
            "UPDATE investigation_runs SET status=?,payload=? WHERE id=?",
            (run["status"], json.dumps(run, allow_nan=False), run["id"]),
        )

    def update(self, identity, run_id, **patch):
        """Terminal results are immutable; a late completion cannot replace Stop."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT payload FROM investigation_runs WHERE investigation_id=? AND id=?", (identity, run_id)
            ).fetchone()
            if row is None:
                raise LookupError("Investigation run not found.")
            run = json.loads(row[0])
            if run["status"] in ACTIVE:
                run.update(patch)
                self._write(db, run)
        return run

    def delete(self, identity):
        """Delete saved reports only; their independently saved conversations remain available."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM investigation_runs WHERE investigation_id=? AND status IN ('queued','running','cancelling')",
                (identity,),
            ).fetchone():
                raise InvestigationConflict("Stop the investigation before deleting its reports.")
            if not db.execute("DELETE FROM investigations WHERE id=?", (identity,)).rowcount:
                raise LookupError("Investigation not found.")
            db.execute("DELETE FROM investigation_runs WHERE investigation_id=?", (identity,))

    @staticmethod
    def summary(run):
        """Keep polling/list responses free of large narrative and evidence payloads."""
        return {key: value for key, value in run.items() if key not in {"report", "sources"}}
