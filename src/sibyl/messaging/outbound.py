"""Durable app-origin Telegram deliveries with conservative, inspectable outcomes.

Conversation replies keep their existing outbox. This queue accepts explicitly
authorized briefing and alert messages and never exposes credentials or retries uncertain writes.
"""

import json
import time
from datetime import UTC, datetime
from uuid import uuid4

from sibyl.messaging.review import DeliveryReview
from sibyl.messaging.telegram import TelegramError


def chunks(text, units=4000):
    """Split plain text below Telegram's UTF-16 limit without splitting a code point."""
    parts, current, length = [], [], 0
    for character in text:
        size = 2 if ord(character) > 0xFFFF else 1
        if length + size > units:
            parts.append("".join(current))
            current, length = [], 0
        current.append(character)
        length += size
    if current:
        parts.append("".join(current))
    return parts


class NotificationOutbox:
    """Bind each delivery to its approved policy, private user and connection controls."""

    def __init__(self, store, settings, client, on_error):
        self.store, self.settings = store, settings
        self.client, self.on_error = client, on_error
        self.authorizers = {}
        self.review = DeliveryReview(self)
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS message_deliveries (
                    id TEXT PRIMARY KEY, origin_id TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS message_delivery_parts (
                    id INTEGER PRIMARY KEY, delivery_id TEXT NOT NULL, part INTEGER NOT NULL,
                    text TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt REAL NOT NULL DEFAULT 0, error TEXT, native_id INTEGER,
                    UNIQUE(delivery_id,part)
                );
            """)
            sending = db.execute(
                "SELECT DISTINCT delivery_id FROM message_delivery_parts WHERE state='sending'"
            ).fetchall()
            for row in sending:
                db.execute(
                    "UPDATE message_delivery_parts SET state='uncertain',error='Delivery was interrupted. Check Telegram; this part will not be resent automatically.' WHERE delivery_id=? AND state='sending'",
                    (row[0],),
                )
                db.execute(
                    "UPDATE message_delivery_parts SET state='blocked',error='An earlier part was not confirmed.' WHERE delivery_id=? AND state='pending'",
                    (row[0],),
                )
                self._state(db, row[0], "uncertain", "Delivery was interrupted before confirmation.")

    @staticmethod
    def _state(db, identity, state, error=None):
        row = db.execute("SELECT payload FROM message_deliveries WHERE id=?", (identity,)).fetchone()
        item = json.loads(row[0])
        item.update(status=state, error=error, updated_at=datetime.now(UTC).isoformat())
        db.execute(
            "UPDATE message_deliveries SET state=?,payload=? WHERE id=?", (state, json.dumps(item), identity)
        )

    def authorize(self, delivery):
        """Dispatch each message to its domain's current authorization check; deny unknown kinds."""
        guard = self.authorizers.get(delivery.get("kind", "briefing"))
        return bool(guard and guard(delivery))

    def enqueue(self, origin_id, schedule, run, text, now):
        """Queue one completed report once, without making any HTTP request."""
        return self.enqueue_message(
            origin_id,
            schedule.get("telegram_binding") or {},
            text,
            now,
            datetime.fromisoformat(run["finished_at"]).timestamp() + 3600,
            {
                "kind": "briefing",
                "schedule_id": schedule["id"],
                "schedule_revision": schedule["revision"],
                "investigation_id": run["investigation_id"],
                "run_id": run["id"],
                "report_version": run.get("version"),
            },
        )

    def enqueue_message(self, origin_id, binding, text, now, expiry, metadata, *, error=None, db=None):
        """Persist explicitly authorized text, optionally in the caller's cursor transaction.

        Metadata identifies its domain policy. It must contain no credentials.
        The shared sender rechecks that policy and connection before every send.
        """
        profile = self.settings.profile()
        if not error:
            if (profile.get("bot_id"), profile.get("allowed_user_id")) != (
                binding.get("bot_id"),
                binding.get("recipient_id"),
            ):
                error = "Telegram's recipient changed. Review the delivery setting again."
            elif not profile.get("enabled") or not profile.get("verified"):
                error = "Telegram is paused or unverified. This notification stays local."
            elif expiry <= now.timestamp():
                error = "This notification's delivery window expired. Briefings expire after one hour."
        item = {
            **metadata,
            "id": uuid4().hex,
            "origin_id": origin_id,
            "preview": text[:240],
            "connection_revision": profile.get("revision"),
            "bot_id": binding.get("bot_id"),
            "control_id": profile.get("control_id"),
            "recipient_id": binding.get("recipient_id"),
            "bot_username": profile.get("bot_username"),
            "expires_at": expiry,
            "status": "skipped" if error else "pending",
            "error": error,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        if db is not None:
            return self._persist(db, item, text)
        with self.store.db() as connection:
            connection.execute("BEGIN IMMEDIATE")
            return self._persist(connection, item, text)

    def _persist(self, db, item, text):
        existing = db.execute(
            "SELECT id FROM message_deliveries WHERE origin_id=?", (item["origin_id"],)
        ).fetchone()
        if existing:
            return self._public(db, existing[0])
        if (
            item["status"] == "pending"
            and db.execute(
                "SELECT COUNT(*) FROM message_deliveries WHERE state IN ('pending','sending','retrying')"
            ).fetchone()[0]
            >= 20
        ):
            item.update(
                status="skipped", error="The notification delivery queue is full. Evidence remains in Sibyl."
            )
        db.execute(
            "INSERT INTO message_deliveries VALUES(?,?,?,?,?)",
            (
                item["id"],
                item["origin_id"],
                item["status"],
                json.dumps(item),
                item["created_at"],
            ),
        )
        scope = item.get("schedule_id") or item.get("rule_id")
        older = db.execute(
            "SELECT id FROM message_deliveries WHERE COALESCE(json_extract(payload,'$.schedule_id'),json_extract(payload,'$.rule_id'))=? AND state IN ('sent','skipped','failed','partial') ORDER BY rowid DESC LIMIT -1 OFFSET 200",
            (scope,),
        ).fetchall()
        for old in older:
            db.execute("DELETE FROM message_delivery_parts WHERE delivery_id=?", (old[0],))
            db.execute("DELETE FROM message_deliveries WHERE id=?", (old[0],))
        if item["status"] == "pending":
            db.executemany(
                "INSERT INTO message_delivery_parts(delivery_id,part,text,state) VALUES(?,?,?,'pending')",
                [(item["id"], index, part) for index, part in enumerate(chunks(text))],
            )
        return self._public(db, item["id"])

    def history(self, *, kind, rule_id=None, limit=20, offset=0):
        """Page safe delivery receipts; never expose queued message bodies or bot tokens."""
        with self.store.db() as db:
            db.execute("BEGIN")
            clause = "COALESCE(json_extract(payload,'$.kind'),'briefing')=? AND (? IS NULL OR json_extract(payload,'$.rule_id')=?)"
            args = (kind, rule_id, rule_id)
            total = db.execute(f"SELECT COUNT(*) FROM message_deliveries WHERE {clause}", args).fetchone()[0]
            rows = db.execute(
                f"SELECT id FROM message_deliveries WHERE {clause} ORDER BY rowid DESC LIMIT ? OFFSET ?",
                (*args, limit, offset),
            ).fetchall()
            return {
                "items": [self._public(db, row[0]) for row in rows],
                "total": total,
                "offset": offset,
                "limit": limit,
            }

    @staticmethod
    def _public(db, identity):
        row = db.execute("SELECT payload FROM message_deliveries WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise LookupError("Notification delivery not found.")
        parts = db.execute(
            "SELECT part,state,attempts,next_attempt,error,native_id FROM message_delivery_parts WHERE delivery_id=? ORDER BY part",
            (identity,),
        ).fetchall()
        return {
            **json.loads(row[0]),
            "parts": [dict(part) for part in parts],
            "sent_parts": sum(part["state"] == "sent" for part in parts),
            "total_parts": len(parts),
        }

    def get(self, identity):
        """Read message-level and chunk-level outcomes without message bodies or credentials."""
        with self.store.db() as db:
            return self._public(db, identity)

    def summary(self, revision=None, *, kind="briefing"):
        """Count actual app-origin delivery outcomes separately from conversation replies."""
        with self.store.db() as db:
            return dict(
                db.execute(
                    "SELECT state,COUNT(*) FROM message_deliveries WHERE (? IS NULL OR json_extract(payload,'$.connection_revision')=?) AND COALESCE(json_extract(payload,'$.kind'),'briefing')=? GROUP BY state",
                    (revision, revision, kind),
                ).fetchall()
            )

    def invalidate(
        self, *, schedule_id=None, rule_id=None, policy_revision=None, connection_revision=None, reason
    ):
        """Withdraw queued parts after a policy or connection-control change."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT id,payload FROM message_deliveries WHERE state IN ('pending','retrying')"
            ).fetchall()
            for row in rows:
                item = json.loads(row["payload"])
                if (
                    (schedule_id and item.get("schedule_id") != schedule_id)
                    or (connection_revision and item["connection_revision"] != connection_revision)
                    or (rule_id and item.get("rule_id") != rule_id)
                    or (policy_revision is not None and item.get("policy_revision") != policy_revision)
                ):
                    continue
                self._skip(db, row["id"], reason)

    def _skip(self, db, identity, reason):
        db.execute(
            "UPDATE message_delivery_parts SET state='skipped',error=? WHERE delivery_id=? AND state='pending'",
            (reason, identity),
        )
        sent = db.execute(
            "SELECT COUNT(*) FROM message_delivery_parts WHERE delivery_id=? AND state='sent'", (identity,)
        ).fetchone()[0]
        self._state(db, identity, "partial" if sent else "skipped", reason)

    async def deliver(self, profile):
        """Admit one chunk and retry only explicit Telegram rate-limit rejections."""
        current = self.settings.profile()
        if (
            not current.get("enabled")
            or current.get("revision") != profile.get("revision")
            or current.get("control_id") != profile.get("control_id")
        ):
            return False
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT p.* FROM message_delivery_parts p JOIN message_deliveries d ON d.id=p.delivery_id WHERE p.state='pending' AND d.state IN ('pending','retrying') AND NOT EXISTS(SELECT 1 FROM message_delivery_parts earlier WHERE earlier.delivery_id=p.delivery_id AND earlier.part<p.part AND earlier.state!='sent') ORDER BY d.rowid,p.part LIMIT 1"
            ).fetchone()
            if row is None:
                return False
            delivery = self._public(db, row["delivery_id"])
            valid = self._approved_profile(delivery, current)
            if not valid or delivery["expires_at"] <= time.time() or not self.authorize(delivery):
                self._skip(
                    db,
                    delivery["id"],
                    "Delivery authorization changed or the notification expired. Evidence remains in Sibyl.",
                )
                return True
            if row["next_attempt"] > time.time():
                return True
            db.execute(
                "UPDATE message_delivery_parts SET state='sending',attempts=attempts+1 WHERE id=?",
                (row["id"],),
            )
            self._state(db, delivery["id"], "sending")
        try:
            native_id = await self.client(current).send(delivery["recipient_id"], row["text"])
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "UPDATE message_delivery_parts SET state='sent',native_id=? WHERE id=?",
                    (native_id, row["id"]),
                )
                waiting = db.execute(
                    "SELECT COUNT(*) FROM message_delivery_parts WHERE delivery_id=? AND state!='sent'",
                    (delivery["id"],),
                ).fetchone()[0]
                if waiting and (
                    not self._approved_profile(delivery, self.settings.profile())
                    or not self.authorize(delivery)
                ):
                    self._skip(
                        db, delivery["id"], "Authorization changed while an admitted part was being sent."
                    )
                else:
                    self._state(db, delivery["id"], "pending" if waiting else "sent")
        except TelegramError as error:
            retry = bool(error.retry_after and row["attempts"] + 1 < 5)
            state = "pending" if retry else "uncertain" if error.ambiguous else "failed"
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "UPDATE message_delivery_parts SET state=?,next_attempt=?,error=? WHERE id=?",
                    (state, time.time() + error.retry_after, str(error), row["id"]),
                )
                if not retry:
                    db.execute(
                        "UPDATE message_delivery_parts SET state='blocked',error='An earlier part was not confirmed.' WHERE delivery_id=? AND state='pending'",
                        (delivery["id"],),
                    )
                self._state(db, delivery["id"], "retrying" if retry else state, str(error))
                if retry and (
                    not self._approved_profile(delivery, self.settings.profile())
                    or not self.authorize(delivery)
                ):
                    self._skip(
                        db, delivery["id"], "Authorization changed before the rejected part could be retried."
                    )
            self.on_error(profile["revision"], error)
        return True

    @staticmethod
    def _approved_profile(delivery, profile):
        return bool(
            profile.get("enabled")
            and profile.get("verified")
            and delivery["connection_revision"] == profile.get("revision")
            and delivery["control_id"] == profile.get("control_id")
            and delivery["bot_id"] == profile.get("bot_id")
            and delivery["recipient_id"] == profile.get("allowed_user_id")
        )
