"""Shared retained notifications; acknowledging never removes trigger evidence."""

import json
from datetime import UTC, datetime


class NotificationInbox:
    """Store local notification evidence and idempotent unread acknowledgments."""

    def __init__(self, store):
        self.store = store
        with store.db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS alert_notifications (
                id TEXT PRIMARY KEY, rule_id TEXT NOT NULL, cycle INTEGER NOT NULL,
                created_at TEXT NOT NULL, read_at TEXT, payload TEXT NOT NULL,
                UNIQUE(rule_id,cycle)
            )""")

    def page(self, limit: int = 20, offset: int = 0) -> dict:
        """Read a mixed price/strategy/connection page without evaluating any alert."""
        if not 1 <= limit <= 100 or not 0 <= offset <= 1_000_000:
            raise ValueError("Choose a valid notification page.")
        with self.store.db() as db:
            db.execute("BEGIN")
            rows = db.execute(
                "SELECT * FROM alert_notifications ORDER BY created_at DESC,rowid DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            total, unread = db.execute(
                "SELECT COUNT(*),COALESCE(SUM(read_at IS NULL),0) FROM alert_notifications"
            ).fetchone()
        return {
            "items": [
                {
                    "kind": "price",
                    **json.loads(row["payload"]),
                    "id": row["id"],
                    "created_at": row["created_at"],
                    "read_at": row["read_at"],
                }
                for row in rows
            ],
            "total": total,
            "unread": unread,
            "limit": limit,
            "offset": offset,
            "delivery": "in_app",
        }

    def mark_read(self, identity: str | None = None) -> dict:
        """Preserve the first acknowledgment time and all immutable event details."""
        now = datetime.now(UTC).isoformat()
        with self.store.db() as db:
            if identity is not None:
                if not db.execute("SELECT 1 FROM alert_notifications WHERE id=?", (identity,)).fetchone():
                    raise LookupError("Notification not found.")
                db.execute(
                    "UPDATE alert_notifications SET read_at=COALESCE(read_at,?) WHERE id=?", (now, identity)
                )
            else:
                db.execute("UPDATE alert_notifications SET read_at=? WHERE read_at IS NULL", (now,))
        return self.page()
