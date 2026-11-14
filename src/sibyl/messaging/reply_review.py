"""Persistent grouped conversation receipts using the same review contract as notifications.

Only reply text is revealed on an explicit detail read. Older bot identities may
be unknown; a replacement connection must never inherit an old reply's target.
"""

import hashlib
import json
from datetime import UTC, datetime

from sibyl.messaging.review import DeliveryReview


def record_reply(db, revision, update_id, chat):
    identity = "reply-" + hashlib.sha256(json.dumps([revision, update_id]).encode()).hexdigest()[:32]
    row = db.execute(
        "SELECT payload FROM telegram_updates WHERE revision=? AND update_id=?", (revision, update_id)
    ).fetchone()
    source = json.loads(row[0]) if row else {}
    payload = {
        "id": identity,
        "kind": "reply",
        "recipient_id": chat,
        "bot_id": source.get("bot_id"),
        "bot_username": source.get("bot_username"),
        "request_id": source.get("request_id"),
        "created_at": datetime.fromtimestamp(source["received_at"], UTC).isoformat()
        if source.get("received_at")
        else None,
        "reviews": [],
        **({"attachment": source["attachment_receipt"]} if source.get("attachment_receipt") else {}),
    }
    db.execute(
        "INSERT OR IGNORE INTO telegram_reply_receipts VALUES(?,?,?,?)",
        (identity, revision, update_id, json.dumps(payload)),
    )


class ReplyReview(DeliveryReview):
    def __init__(self, store):
        self.store, self.outbox = store, self
        with store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS telegram_reply_receipts(id TEXT PRIMARY KEY,revision TEXT NOT NULL,update_id INTEGER NOT NULL,payload TEXT NOT NULL,UNIQUE(revision,update_id))"
            )
            for row in db.execute(
                "SELECT revision,update_id,MIN(chat_id) AS chat FROM telegram_outbox GROUP BY revision,update_id"
            ).fetchall():
                record_reply(db, row["revision"], row["update_id"], row["chat"])

    @staticmethod
    def _row(db, identity):
        row = db.execute("SELECT * FROM telegram_reply_receipts WHERE id=?", (identity,)).fetchone()
        if not row:
            raise LookupError("Conversation reply receipt not found.")
        return row

    def _public(self, db, identity):
        row = self._row(db, identity)
        parts = [
            dict(p)
            for p in db.execute(
                "SELECT part,state,attempts,next_attempt,error,native_id,format,filename FROM telegram_outbox WHERE revision=? AND update_id=? ORDER BY part",
                (row["revision"], row["update_id"]),
            )
        ]
        states = [p["state"] for p in parts]
        sent = states.count("sent")
        status = (
            "sent"
            if parts and sent == len(parts)
            else next(
                (s for s in ("sending", "uncertain", "failed", "pending", "blocked") if s in states),
                "partial" if sent else "skipped",
            )
        )
        if status == "pending" and any(p["attempts"] for p in parts if p["state"] == "pending"):
            status = "retrying"
        preview = "".join(p["text"] for p in self._parts(db, identity))[:240]
        return {
            **json.loads(row["payload"]),
            "parts": parts,
            "status": status,
            "preview": preview,
            "sent_parts": sent,
            "total_parts": len(parts),
            "error": next((p["error"] for p in parts if p["error"]), None),
        }

    def _parts(self, db, identity):
        row = self._row(db, identity)
        return [
            dict(p)
            for p in db.execute(
                "SELECT part,text,format,filename FROM telegram_outbox WHERE revision=? AND update_id=? ORDER BY part",
                (row["revision"], row["update_id"]),
            )
        ]

    def _load_payload(self, db, identity):
        return json.loads(self._row(db, identity)["payload"])

    def _save_payload(self, db, identity, payload):
        db.execute("UPDATE telegram_reply_receipts SET payload=? WHERE id=?", (json.dumps(payload), identity))

    def _skip(self, db, identity, reason):
        row = self._row(db, identity)
        db.execute(
            "UPDATE telegram_outbox SET state='skipped',error=? WHERE revision=? AND update_id=? AND state='pending'",
            (reason, row["revision"], row["update_id"]),
        )

    def _detail(self, db, identity):
        result = super()._detail(db, identity)
        result["note"] = (
            "This is a conversation reply, grouped across all message parts. A missing bot name means the older identity was not recorded. User acknowledgments remain separate from native outcomes; nothing here reruns inference, resends a message or recalls confirmed parts."
        )
        return result

    def history(self, limit=20, offset=0):
        with self.store.db() as db:
            db.execute("BEGIN")
            total = db.execute("SELECT COUNT(*) FROM telegram_reply_receipts").fetchone()[0]
            rows = db.execute(
                "SELECT id FROM telegram_reply_receipts ORDER BY rowid DESC LIMIT ? OFFSET ?", (limit, offset)
            ).fetchall()
            return {
                "items": [self._public(db, r[0]) for r in rows],
                "total": total,
                "limit": limit,
                "offset": offset,
            }


def reply_evidence(store):
    """Compact read-only conversation outcomes, excluding reply bodies and recipient identity."""
    with store.db() as db:
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='telegram_reply_receipts'"
        ).fetchone():
            return []
        items = []
        for row in db.execute("SELECT * FROM telegram_reply_receipts ORDER BY rowid DESC LIMIT 10"):
            payload = json.loads(row["payload"])
            counts = dict(
                db.execute(
                    "SELECT state,COUNT(*) FROM telegram_outbox WHERE revision=? AND update_id=? GROUP BY state",
                    (row["revision"], row["update_id"]),
                ).fetchall()
            )
            items.append(
                {
                    "id": row["id"],
                    "kind": "reply",
                    "states": counts,
                    "confirmed_parts": counts.get("sent", 0),
                    "total_parts": sum(counts.values()),
                    "user_review": [
                        {key: r[key] for key in ("decision", "at", "native_confirmation")}
                        for r in payload.get("reviews", [])
                    ],
                }
            )
        return items
