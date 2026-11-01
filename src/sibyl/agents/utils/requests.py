"""Durable Sibyl request state, visible progress, and interrupted-request recovery."""

import json
import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import Field

from sibyl.models import Request
from sibyl.storage import Store

ACTIVE = {"queued", "running", "cancelling"}
TERMINAL = {"completed", "cancelled", "failed", "interrupted"}


def now() -> str:
    """Return an aware UTC timestamp for request and consultation transitions."""
    return datetime.now(UTC).isoformat()


class CancelSibylRequest(Request):
    """Identify the exact request to stop; stale browser state cannot cancel a newer turn."""

    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class SibylRequests:
    """Record request outcomes without model secrets or private reasoning.

    This is an audit of request-driven work, not a scheduler. An interrupted
    request is never replayed automatically after a process restart.
    """

    def __init__(self, store: Store):
        self.store = store
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sibyl_requests (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                    status TEXT NOT NULL, payload TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sibyl_request_session
                    ON sibyl_requests(session_id, created_at);
                CREATE UNIQUE INDEX IF NOT EXISTS sibyl_one_active_request
                    ON sibyl_requests(session_id)
                    WHERE status IN ('queued','running','cancelling');
            """)

    def recover(self) -> None:
        """Mark unfinished work interrupted when the single application worker starts."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT payload FROM sibyl_requests WHERE status IN ('queued','running','cancelling')"
            ).fetchall()
            for row in rows:
                item = json.loads(row[0])
                self._finish(item, "interrupted", "The application restarted before this answer finished.")
                self._write(db, item)

    def start(
        self, session_id: str, question: str, provider: str, model: str, request_id: str | None
    ) -> dict:
        """Create one pending request; duplicate IDs never submit another model call."""
        timestamp = now()
        item = {
            "id": request_id or uuid4().hex,
            "session_id": session_id,
            "question": question,
            "provider": provider,
            "model": model,
            "status": "queued",
            "phase": "queued",
            "created_at": timestamp,
            "updated_at": timestamp,
            "started_at": None,
            "finished_at": None,
            "error": None,
            "delegations": [],
        }
        try:
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                if not db.execute("SELECT 1 FROM sibyl_conversations WHERE id=?", (session_id,)).fetchone():
                    raise LookupError("Conversation not found.")
                db.execute(
                    "INSERT INTO sibyl_requests VALUES (?,?,?,?,?,?)",
                    (item["id"], session_id, item["status"], json.dumps(item), timestamp, timestamp),
                )
                db.execute(
                    "UPDATE sibyl_conversations SET updated_at=?, title=CASE WHEN title='New conversation' "
                    "THEN ? ELSE title END WHERE id=?",
                    (timestamp, question[:80], session_id),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(
                "This request already exists or the conversation already has pending work."
            ) from exc
        return item

    def get(self, session_id: str, request_id: str) -> dict:
        """Read one request only within its owning conversation."""
        with self.store.db() as db:
            row = db.execute(
                "SELECT payload FROM sibyl_requests WHERE session_id=? AND id=?", (session_id, request_id)
            ).fetchone()
        if row is None:
            raise LookupError("Request not found.")
        return json.loads(row[0])

    def latest(self, session_id: str) -> dict | None:
        """Read the latest attempt independently of successful chat turns."""
        with self.store.db() as db:
            row = db.execute(
                "SELECT payload FROM sibyl_requests WHERE session_id=? ORDER BY created_at DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def history(self, session_id: str) -> list[dict]:
        """Return 20 bounded summaries; detailed evidence is available on demand."""
        with self.store.db() as db:
            rows = db.execute(
                "SELECT payload FROM sibyl_requests WHERE session_id=? ORDER BY created_at DESC LIMIT 20",
                (session_id,),
            ).fetchall()
        return [self.public(json.loads(row[0])) for row in rows]

    def update(self, request_id: str, **patch) -> None:
        """Advance active progress only; late tool completions cannot rewrite an outcome."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM sibyl_requests WHERE id=?", (request_id,)).fetchone()
            if row is None:
                return
            item = json.loads(row[0])
            if item["status"] not in ACTIVE:
                return
            item.update(patch, updated_at=now())
            self._write(db, item)

    def finish(self, request_id: str, status: str, error: str | None = None) -> None:
        """Finalize an active attempt once, retaining completed consultation evidence."""
        if status not in TERMINAL:
            raise ValueError("Invalid request outcome.")
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM sibyl_requests WHERE id=?", (request_id,)).fetchone()
            if row is None:
                return
            item = json.loads(row[0])
            if item["status"] in TERMINAL:
                return
            self._finish(item, status, error)
            self._write(db, item)

    @classmethod
    def complete(cls, db, result: dict) -> None:
        """Commit request success with its answer; Stop cannot erase a committed reply."""
        if not result.get("request_id"):
            return
        row = db.execute(
            "SELECT payload FROM sibyl_requests WHERE id=? AND session_id=?",
            (result["request_id"], result["session_id"]),
        ).fetchone()
        if row is None:
            raise LookupError("Request not found.")
        item = json.loads(row[0])
        if item["status"] not in {"queued", "running"}:
            raise ValueError("This request is no longer accepting an answer.")
        item.update(delegations=result["delegations"], reply_id=result["id"])
        cls._finish(item, "completed", None)
        cls._write(db, item)

    @staticmethod
    def _finish(item: dict, status: str, error: str | None) -> None:
        timestamp = now()
        item.update(status=status, phase=status, updated_at=timestamp, finished_at=timestamp, error=error)
        for consultation in item["delegations"]:
            if consultation["status"] == "running":
                consultation.update(
                    status="interrupted" if status == "interrupted" else "cancelled", finished_at=timestamp
                )

    @staticmethod
    def _write(db, item: dict) -> None:
        db.execute(
            "UPDATE sibyl_requests SET status=?,payload=?,updated_at=? WHERE id=?",
            (item["status"], json.dumps(item), item["updated_at"], item["id"]),
        )

    @staticmethod
    def public(item: dict | None) -> dict | None:
        """Keep frequent progress reads small; never include full evidence or model reasoning."""
        if item is None:
            return None
        return {
            **{key: value for key, value in item.items() if key != "delegations"},
            "delegations": [
                {key: value for key, value in entry.items() if key not in {"evidence", "answer"}}
                for entry in item["delegations"]
            ],
        }
