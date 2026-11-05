"""Transfer explicitly selected future inbox events into the existing Telegram outbox.

The local inbox remains the authoritative trigger record. Cursor advancement and
outbox insertion share one transaction, so restarts cannot replay processed events.
Every send is fenced by the current delivery policy, rule revision and recipient.
"""

import json
import threading
from datetime import UTC, datetime

from sibyl.alerts.contracts import AlertConflict
from sibyl.alerts.delivery.formatting import alert_text

TABLES = {
    "price": "price_alerts",
    "risk": "risk_alerts",
    "strategy": "strategy_alerts",
    "connection": "connection_alerts",
    "order": "order_alerts",
}


class AlertDelivery:
    """Own per-rule opt-in, bounded inbox admission and safe delivery receipts."""

    def __init__(self, store, messaging, clock=None):
        self.store, self.messaging = store, messaging
        self.clock = clock or (lambda: datetime.now(UTC))
        self.outbox = messaging.notifications
        self._worker = threading.Lock()
        self._closed = False
        self.outbox.authorizers["alert"] = self.allowed
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS alert_delivery_policies (
                    rule_id TEXT PRIMARY KEY, kind TEXT NOT NULL, enabled INTEGER NOT NULL,
                    cursor INTEGER NOT NULL, payload TEXT NOT NULL
                );
            """)

    @staticmethod
    def _rule(db, kind, identity):
        # The table is selected from a fixed map, never supplied as SQL by a caller.
        row = db.execute(f"SELECT payload FROM {TABLES[kind]} WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise LookupError("Alert rule not found.")
        return json.loads(row[0])

    @staticmethod
    def _read(db, kind, identity):
        row = db.execute(
            "SELECT kind,payload FROM alert_delivery_policies WHERE rule_id=?", (identity,)
        ).fetchone()
        if row and row["kind"] != kind:
            raise LookupError("Alert delivery policy not found.")
        return (
            json.loads(row["payload"])
            if row
            else {
                "rule_id": identity,
                "kind": kind,
                "enabled": False,
                "revision": 0,
                "cooldown_seconds": 300,
                "expiry_seconds": 600,
                "telegram_binding": None,
                "cursor": 0,
                "last_queued_at": None,
                "updated_at": None,
            }
        )

    @staticmethod
    def _write(db, policy):
        db.execute(
            "INSERT INTO alert_delivery_policies VALUES(?,?,?,?,?) ON CONFLICT(rule_id) DO UPDATE SET enabled=excluded.enabled,cursor=excluded.cursor,payload=excluded.payload",
            (
                policy["rule_id"],
                policy["kind"],
                int(policy["enabled"]),
                policy["cursor"],
                json.dumps(policy),
            ),
        )

    def policies(self):
        """Read active opt-in indicators for cards without returning private recipient IDs."""
        with self.store.db() as db:
            rows = []
            for kind, table in TABLES.items():
                rows.extend(
                    db.execute(
                        f"SELECT p.payload FROM alert_delivery_policies p JOIN {table} r ON r.id=p.rule_id WHERE p.enabled=1 AND p.kind=? AND r.status!='archived' LIMIT 50",
                        (kind,),
                    ).fetchall()
                )
        return [
            {"rule_id": item["rule_id"], "kind": item["kind"], "enabled": True}
            for item in (json.loads(row[0]) for row in rows)
        ]

    def detail(self, kind, identity):
        """Read the reviewed recipient, live rule state and recent safe receipts; no HTTP."""
        with self.store.db() as db:
            rule = self._rule(db, kind, identity)
            policy = self._read(db, kind, identity)
        return {
            "policy": policy,
            "rule": {
                "id": identity,
                "revision": rule["revision"],
                "status": rule["status"],
                "label": rule.get("label", ""),
            },
            "history": self.outbox.history(kind="alert", rule_id=identity),
        }

    def save(self, kind, identity, body):
        """Save explicit opt-in for future notices only, without sending any messages."""
        now = self.clock()
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rule = self._rule(db, kind, identity)
            policy = self._read(db, kind, identity)
            if body.revision != policy["revision"] or body.rule_revision != rule["revision"]:
                raise AlertConflict(
                    "This rule or delivery setting changed. Refresh and review it before saving."
                )
            if body.enabled and rule["status"] == "archived":
                raise AlertConflict("Restore the alert rule before enabling Telegram delivery.")
            binding = policy["telegram_binding"]
            if body.enabled:
                profile = self.messaging.settings.profile()
                if not profile.get("verified") or not profile.get("bot_id") or not profile.get("bot_token"):
                    raise AlertConflict("Save and check a Telegram bot in Settings → Messaging first.")
                target = body.telegram_target
                if (profile["bot_id"], profile["allowed_user_id"]) != (target.bot_id, target.user_id):
                    raise AlertConflict(
                        "Telegram changed while this form was open. Review its current private recipient."
                    )
                binding = {
                    "bot_id": target.bot_id,
                    "recipient_id": target.user_id,
                    "bot_username": profile.get("bot_username", ""),
                }
            tail = db.execute("SELECT COALESCE(MAX(rowid),0) FROM alert_notifications").fetchone()[0]
            policy.update(
                enabled=body.enabled,
                telegram_binding=binding,
                cooldown_seconds=body.cooldown_seconds,
                expiry_seconds=body.expiry_seconds,
                cursor=tail,
                revision=policy["revision"] + 1,
                updated_at=now.isoformat(),
                last_queued_at=None,
            )
            self._write(db, policy)
        self.outbox.invalidate(
            rule_id=identity,
            policy_revision=policy["revision"] - 1,
            reason="This alert's delivery settings changed before sending.",
        )
        return self.detail(kind, identity)

    @staticmethod
    def _event_time(notice, now):
        try:
            stamps = [datetime.fromisoformat(notice[key]) for key in ("created_at", "observed_at")]
            if any(stamp.tzinfo is None or stamp.timestamp() > now.timestamp() + 60 for stamp in stamps):
                return None
            return min(stamp.timestamp() for stamp in stamps)
        except (ValueError, TypeError, KeyError, OverflowError):
            return None

    def allowed(self, delivery):
        """Authorize this exact notice against current rule/policy revisions before each send."""
        kind, identity = delivery.get("alert_kind"), delivery.get("rule_id")
        if kind not in TABLES or not identity:
            return False
        with self.store.db() as db:
            try:
                rule, policy = self._rule(db, kind, identity), self._read(db, kind, identity)
            except LookupError:
                return False
            notice = db.execute(
                "SELECT rule_id FROM alert_notifications WHERE id=?", (delivery.get("notification_id"),)
            ).fetchone()
        binding = policy["telegram_binding"] or {}
        return bool(
            notice
            and notice[0] == identity
            and policy["enabled"]
            and policy["revision"] == delivery["policy_revision"]
            and rule["status"] in {"armed", "triggered"}
            and rule["revision"] == delivery["rule_revision"]
            and binding.get("bot_id") == delivery["bot_id"]
            and binding.get("recipient_id") == delivery["recipient_id"]
        )

    def tick(self):
        """Atomically process at most twenty future notices from one policy; never call a provider."""
        with self._worker:
            if not self._closed:
                self._tick()

    def close(self):
        """Drain a local admission transaction before the shared messaging service shuts down."""
        with self._worker:
            self._closed = True

    def _tick(self):
        now = self.clock()
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT p.payload FROM alert_delivery_policies p WHERE p.enabled=1 AND EXISTS(SELECT 1 FROM alert_notifications n WHERE n.rule_id=p.rule_id AND n.rowid>p.cursor) ORDER BY p.cursor,p.rowid LIMIT 1"
            ).fetchone()
            if row is None:
                return
            policy = json.loads(row[0])
            rule = self._rule(db, policy["kind"], policy["rule_id"])
            notices = db.execute(
                "SELECT rowid,id,created_at,payload FROM alert_notifications WHERE rule_id=? AND rowid>? ORDER BY rowid LIMIT 20",
                (policy["rule_id"], policy["cursor"]),
            ).fetchall()
            for row in notices:
                notice = {**json.loads(row["payload"]), "id": row["id"], "created_at": row["created_at"]}
                observed = self._event_time(notice, now)
                expiry = (observed if observed is not None else now.timestamp()) + policy["expiry_seconds"]
                error = None
                if (
                    notice.get("kind", "price") != policy["kind"]
                    or notice.get("rule_revision") != rule["revision"]
                    or rule["status"] not in {"armed", "triggered"}
                ):
                    error = "The alert rule changed or was paused before delivery admission."
                elif observed is None or expiry <= now.timestamp():
                    error = "This alert's observation is stale or invalid. No backlog message was queued."
                elif (
                    policy["last_queued_at"]
                    and now.timestamp() < policy["last_queued_at"] + policy["cooldown_seconds"]
                ):
                    error = (
                        "Telegram cooldown suppressed this alert. Its evidence remains in the local inbox."
                    )
                receipt = self.outbox.enqueue_message(
                    "alert:" + notice["id"],
                    policy["telegram_binding"] or {},
                    alert_text(notice),
                    now,
                    expiry,
                    {
                        "kind": "alert",
                        "alert_kind": policy["kind"],
                        "rule_id": policy["rule_id"],
                        "rule_revision": notice.get("rule_revision"),
                        "policy_revision": policy["revision"],
                        "notification_id": notice["id"],
                    },
                    error=error,
                    db=db,
                )
                if receipt["status"] == "pending":
                    policy["last_queued_at"] = now.timestamp()
                policy["cursor"] = row["rowid"]
            self._write(db, policy)
