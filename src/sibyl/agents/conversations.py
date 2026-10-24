"""Durable, local Sibyl conversations, separate from the rolling module-run list."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import Field, field_validator

from sibyl.agents.requests import SibylRequests
from sibyl.models import Request
from sibyl.storage import Store


class SibylRequest(Request):
    """One user turn; a missing session starts a new conversation."""

    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    request_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")

    @field_validator("message")
    @classmethod
    def nonblank(cls, value: str) -> str:
        """Reject empty turns before calling any model."""
        if not value.strip():
            raise ValueError("Write a message first.")
        return value.strip()


class Conversations:
    """Persist completed answers and delegation evidence without storing model secrets."""

    def __init__(self, store: Store):
        self.store = store
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sibyl_conversations (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sibyl_turns (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sibyl_turn_session
                ON sibyl_turns(session_id, created_at);
            """)

    def list(self) -> list[dict]:
        """Return the latest 100 conversation titles, including empty new chats."""
        with self.store.db() as db:
            return [
                dict(row)
                for row in db.execute("SELECT * FROM sibyl_conversations ORDER BY updated_at DESC LIMIT 100")
            ]

    def create(self, title: str = "New conversation") -> dict:
        """Allocate a conversation independently of any provider request."""
        now = datetime.now(UTC).isoformat()
        item = {"id": uuid4().hex, "title": title[:80], "created_at": now, "updated_at": now}
        with self.store.db() as db:
            db.execute("INSERT INTO sibyl_conversations VALUES (:id,:title,:created_at,:updated_at)", item)
        return item

    def get(self, session_id: str) -> dict:
        """Read a chat and its last 100 completed turns in chronological order."""
        with self.store.db() as db:
            row = db.execute("SELECT * FROM sibyl_conversations WHERE id=?", (session_id,)).fetchone()
            if row is None:
                raise LookupError("Conversation not found.")
            turns = db.execute(
                "SELECT payload FROM sibyl_turns WHERE session_id=? ORDER BY created_at DESC LIMIT 100",
                (session_id,),
            ).fetchall()
        return {**dict(row), "turns": [json.loads(t[0]) for t in reversed(turns)]}

    def require(self, session_id: str) -> None:
        """Validate chat existence without loading its messages and consultation evidence."""
        with self.store.db() as db:
            if not db.execute("SELECT 1 FROM sibyl_conversations WHERE id=?", (session_id,)).fetchone():
                raise LookupError("Conversation not found.")

    def append(self, result: dict) -> dict:
        """Commit the completed answer and update its chat title together."""
        now = datetime.now(UTC).isoformat()
        result = {**result, "id": uuid4().hex, "created_at": now}
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute(
                "SELECT 1 FROM sibyl_conversations WHERE id=?", (result["session_id"],)
            ).fetchone():
                raise LookupError("Conversation not found.")
            SibylRequests.complete(db, result)
            db.execute(
                "INSERT INTO sibyl_turns VALUES (?,?,?,?)",
                (
                    result["id"],
                    result["session_id"],
                    json.dumps(result),
                    now,
                ),
            )
            db.execute(
                "UPDATE sibyl_conversations SET updated_at=?, title=CASE WHEN title='New conversation' "
                "THEN ? ELSE title END WHERE id=?",
                (now, result["question"][:80], result["session_id"]),
            )
        return result

    def delete(self, session_id: str) -> None:
        """Remove this chat's local messages and delegation evidence."""
        with self.store.db() as db:
            db.execute("DELETE FROM sibyl_requests WHERE session_id=?", (session_id,))
            db.execute("DELETE FROM sibyl_turns WHERE session_id=?", (session_id,))
            db.execute("DELETE FROM sibyl_conversations WHERE id=?", (session_id,))
