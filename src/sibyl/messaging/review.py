"""Explicit review of app-origin delivery evidence, with no resending or inference.

Provider acknowledgments remain authoritative for native outcomes. A user's
receipt acknowledgment is stored separately and cannot manufacture a Telegram
message ID. Optimistic tokens reject reviews based on stale in-flight evidence.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from sibyl.models import Request


class DeliveryDecision(Request):
    token: str = Field(pattern=r"^[a-f0-9]{64}$")
    decision: Literal["withdraw", "received", "dismissed"]
    note: str = Field(default="", max_length=500)


class DeliveryReview:
    def __init__(self, outbox):
        self.outbox = outbox

    def _detail(self, db, identity):
        delivery = self.outbox._public(db, identity)
        parts = self._parts(db, identity)
        token = hashlib.sha256(json.dumps([delivery, parts], sort_keys=True).encode()).hexdigest()
        busy = any(part["state"] == "sending" for part in delivery["parts"])
        return {
            **delivery,
            "text_parts": parts,
            "review_token": token,
            "can_withdraw": not busy and delivery["status"] in {"pending", "retrying"},
            "can_acknowledge": not busy
            and delivery["status"] in {"uncertain", "failed", "partial"}
            and len(delivery.get("reviews", [])) < 10,
            "note": "Review covers app-origin alerts and briefings, not conversation replies. User acknowledgments do not change Telegram-confirmed part outcomes. Nothing here resends a message.",
        }

    def _parts(self, db, identity):
        return [
            dict(row)
            for row in db.execute(
                "SELECT part,text FROM message_delivery_parts WHERE delivery_id=? ORDER BY part", (identity,)
            )
        ]

    def _load_payload(self, db, identity):
        return json.loads(
            db.execute("SELECT payload FROM message_deliveries WHERE id=?", (identity,)).fetchone()[0]
        )

    def _save_payload(self, db, identity, payload):
        db.execute("UPDATE message_deliveries SET payload=? WHERE id=?", (json.dumps(payload), identity))

    def get(self, identity):
        with self.outbox.store.db() as db:
            db.execute("BEGIN")
            return self._detail(db, identity)

    def decide(self, identity, body):
        with self.outbox.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self._detail(db, identity)
            if body.token != current["review_token"]:
                raise ValueError("Delivery changed. Refresh its details before reviewing.")
            if len(current.get("reviews", [])) >= 10:
                raise ValueError("This delivery already has ten review entries.")
            if body.decision == "withdraw":
                if not current["can_withdraw"]:
                    raise ValueError(
                        "Only queued or rate-limited parts can be withdrawn. Wait for an admitted send to finish."
                    )
                self.outbox._skip(
                    db, identity, "The user withdrew the unsent remainder. Confirmed parts remain delivered."
                )
            elif not current["can_acknowledge"]:
                raise ValueError(
                    "Only an unconfirmed, failed or partial delivery can be acknowledged. Wait for any admitted send to finish."
                )
            payload = self._load_payload(db, identity)
            payload.setdefault("reviews", []).append(
                {
                    "decision": body.decision,
                    "note": body.note.strip(),
                    "at": datetime.now(UTC).isoformat(),
                    "actor": "local_user",
                    "native_confirmation": False,
                }
            )
            self._save_payload(db, identity, payload)
            return self._detail(db, identity)


def delivery_evidence(store):
    """Read compact outcomes for agent explanation, excluding private message text and targets."""
    with store.db() as db:
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='message_deliveries'"
        ).fetchone():
            return {"items": [], "url": "/settings?tab=messaging"}
        items = []
        for row in db.execute("SELECT payload FROM message_deliveries ORDER BY rowid DESC LIMIT 10"):
            item = json.loads(row[0])
            parts = db.execute(
                "SELECT state FROM message_delivery_parts WHERE delivery_id=?", (item["id"],)
            ).fetchall()
            items.append(
                {
                    **{key: item.get(key) for key in ("id", "kind", "status", "created_at")},
                    "confirmed_parts": sum(p[0] == "sent" for p in parts),
                    "total_parts": len(parts),
                    "user_review": [
                        {"decision": review["decision"], "at": review["at"], "native_confirmation": False}
                        for review in item.get("reviews", [])
                    ],
                }
            )
    return {
        "items": items,
        "url": "/settings?tab=messaging",
        "note": "Only app-origin alerts/briefings. User review never changes native confirmation. Open Review delivery for exact text, target and controls; agents cannot send, withdraw or review messages.",
    }
