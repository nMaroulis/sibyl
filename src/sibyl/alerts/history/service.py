"""Read-only exports and explicit, bounded pruning of old acknowledged inbox records.

Unread notices, unprocessed delivery cursors and unresolved outbound deliveries
are protected. Delivery receipts, rules, financial ledgers and conversations are
separate records and are never removed by this policy.
"""

import csv
import io
import json
import threading
from datetime import UTC, datetime, timedelta

MAX_EXPORT = 2000
BATCH = 500
TERMINAL_DELIVERIES = "('sent','skipped','failed','partial')"


def utc(value):
    """Require dated UTC-compatible export bounds; never compare caller-local date strings."""
    if value is None:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError
        return result.astimezone(UTC).isoformat()
    except (ValueError, TypeError):
        raise ValueError("Use an ISO date/time with a timezone for export bounds.") from None


class NotificationHistory:
    """Keep retention off by default and serialize policy changes with each deletion batch."""

    def __init__(self, store, *, clock=None):
        self.store, self.clock = store, clock or (lambda: datetime.now(UTC))
        self.worker, self.closed = threading.Lock(), False
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS notification_retention (id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS notification_retention_runs (id INTEGER PRIMARY KEY AUTOINCREMENT,payload TEXT NOT NULL);
            """)
            db.execute(
                "INSERT OR IGNORE INTO notification_retention VALUES(1,?)",
                (json.dumps({"enabled": False, "days": 90, "revision": 0, "next_check": 0}),),
            )

    @staticmethod
    def _policy(db):
        return json.loads(db.execute("SELECT payload FROM notification_retention WHERE id=1").fetchone()[0])

    @staticmethod
    def _write(db, policy):
        db.execute("UPDATE notification_retention SET payload=? WHERE id=1", (json.dumps(policy),))

    @staticmethod
    def _protections(db):
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        guards = []
        if "message_deliveries" in tables:
            guards.append(
                f"EXISTS(SELECT 1 FROM message_deliveries d WHERE json_extract(d.payload,'$.notification_id')=n.id AND d.state NOT IN {TERMINAL_DELIVERIES})"
            )
        if "alert_delivery_policies" in tables:
            guards.append(
                "EXISTS(SELECT 1 FROM alert_delivery_policies p WHERE p.rule_id=n.rule_id AND p.enabled=1 AND p.cursor<n.rowid)"
            )
        return "(" + " OR ".join(guards) + ")" if guards else "0"

    @staticmethod
    def _preview(db, policy, now):
        cutoff = (now - timedelta(days=policy["days"])).isoformat()
        protected = NotificationHistory._protections(db)
        row = db.execute(
            f"""SELECT COUNT(*),
            COALESCE(SUM(read_at IS NULL),0),
            COALESCE(SUM(read_at IS NOT NULL AND {protected}),0),
            COALESCE(SUM(read_at IS NOT NULL AND NOT {protected}),0)
            FROM alert_notifications n WHERE created_at<?""",
            (cutoff,),
        ).fetchone()
        return {
            "cutoff": cutoff,
            "older_records": row[0],
            "unread_protected": row[1],
            "delivery_protected": row[2],
            "eligible": row[3],
            "batch_limit": BATCH,
        }

    def status(self):
        """Inspect policy, eligible counts and actual recent passes without clearing anything."""
        return self.read_status(self.store, now=self.clock())

    @staticmethod
    def read_status(store, *, now=None):
        """Read existing retention evidence without initializing storage or changing the policy."""
        with store.db() as db:
            db.execute("BEGIN")
            policy = NotificationHistory._policy(db)
            preview = NotificationHistory._preview(db, policy, now or datetime.now(UTC))
            runs = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT payload FROM notification_retention_runs ORDER BY id DESC LIMIT 10"
                )
            ]
        return {
            "policy": policy,
            "preview": preview,
            "runs": runs,
            "scope": "Only old read inbox notices. Unread records and unfinished delivery evidence are protected; rules, financial records and delivery history are retained separately.",
        }

    def save(self, request):
        """Save an explicitly chosen policy; enabling schedules a later worker pass, not an inline deletion."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            policy = self._policy(db)
            if request.revision != policy["revision"]:
                raise ValueError("Retention settings changed. Refresh before saving again.")
            policy.update(
                enabled=request.enabled,
                days=request.days,
                revision=policy["revision"] + 1,
                updated_at=self.clock().isoformat(),
                next_check=0,
            )
            self._write(db, policy)
        return self.status()

    def clear(self, revision=None, *, manual=True):
        """Delete at most 500 eligible notices atomically, preserving every protected cursor/receipt."""
        with self.worker:
            if self.closed:
                raise ValueError("Notification history is shutting down.")
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                policy = self._policy(db)
                if revision is not None and revision != policy["revision"]:
                    raise ValueError("Retention settings changed. Review the latest preview before clearing.")
                if not manual and (not policy["enabled"] or policy["next_check"] > self.clock().timestamp()):
                    return None
                preview = self._preview(db, policy, self.clock())
                protected = NotificationHistory._protections(db)
                deleted = db.execute(
                    f"""DELETE FROM alert_notifications WHERE sequence IN
                    (SELECT n.rowid FROM alert_notifications n WHERE n.created_at<? AND n.read_at IS NOT NULL
                    AND NOT {protected} ORDER BY n.created_at,n.rowid LIMIT ?)""",
                    (preview["cutoff"], BATCH),
                ).rowcount
                receipt = {
                    "at": self.clock().isoformat(),
                    "cutoff": preview["cutoff"],
                    "deleted": deleted,
                    "remaining_eligible": max(0, preview["eligible"] - deleted),
                    "manual": manual,
                }
                db.execute(
                    "INSERT INTO notification_retention_runs(payload) VALUES(?)", (json.dumps(receipt),)
                )
                db.execute(
                    "DELETE FROM notification_retention_runs WHERE id NOT IN (SELECT id FROM notification_retention_runs ORDER BY id DESC LIMIT 100)"
                )
                policy["next_check"] = self.clock().timestamp() + (
                    60 if receipt["remaining_eligible"] else 3600
                )
                self._write(db, policy)
        return {"result": receipt, **self.status()}

    def tick(self):
        """Perform a due opt-in cleanup batch; disabled policies never remove records."""
        self.clear(manual=False)

    def close(self):
        """Drain an active local transaction before shutdown."""
        with self.worker:
            self.closed = True

    def export(self, kind="all", start=None, end=None):
        """Export an exact bounded history selection without acknowledging or deleting records."""
        if kind not in {"all", "price", "risk", "strategy", "connection", "order"}:
            raise ValueError("Unknown notification kind.")
        start, end = utc(start), utc(end)
        if start and end and start >= end:
            raise ValueError("Export end must follow start; the end is exclusive.")
        clauses, params = [], []
        if kind != "all":
            clauses.append("COALESCE(json_extract(payload,'$.kind'),'price')=?")
            params.append(kind)
        for operator, value in ((">=", start), ("<", end)):
            if value:
                clauses.append("created_at" + operator + "?")
                params.append(value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.store.db() as db:
            db.execute("BEGIN")
            total = db.execute("SELECT COUNT(*) FROM alert_notifications" + where, params).fetchone()[0]
            rows = db.execute(
                "SELECT id,created_at,read_at,payload FROM alert_notifications"
                + where
                + " ORDER BY created_at DESC,rowid DESC LIMIT ?",
                [*params, MAX_EXPORT],
            ).fetchall()
        return {
            "schema": 1,
            "exported_at": self.clock().isoformat(),
            "kind": kind,
            "start": start,
            "end": end,
            "total": total,
            "exported": len(rows),
            "limit": MAX_EXPORT,
            "truncated": total > len(rows),
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
        }


def csv_document(document):
    """Quote CSV fields and neutralize spreadsheet formulas in untrusted notification text."""
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["id", "kind", "created_at", "read_at", "rule_id", "symbol", "evidence_json"])
    for item in document["items"]:
        values = [item.get(key, "") for key in ("id", "kind", "created_at", "read_at", "rule_id", "symbol")]
        values.append(json.dumps(item, ensure_ascii=False, allow_nan=False))
        writer.writerow(
            [
                "'" + str(value) if str(value).lstrip().startswith(("=", "+", "-", "@")) else value
                for value in values
            ]
        )
    return output.getvalue()
