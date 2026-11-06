"""Per-account execution subscriptions over the local, atomic observation journal."""

import json
import threading
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import Field, field_validator

from sibyl.alerts.contracts import AlertAction, AlertConflict, StrategyAlertCreate
from sibyl.alerts.inbox import NotificationInbox
from sibyl.alerts.orders.events import schema
from sibyl.models import Request

GROUPS = [
    dict(id="fills", name="Fills & corrections"),
    dict(id="cancellations", name="Cancellations & expiry"),
    dict(id="attention", name="Execution problems"),
    dict(id="status", name="Other order status changes"),
]


class OrderAlertCreate(Request):
    """Subscribe to future retained observations for one selected account."""

    account_id: str = Field(min_length=1, max_length=100)
    label: str = Field(default="", max_length=80)
    events: list[Literal["fills", "cancellations", "attention", "status"]] = Field(
        default_factory=lambda: ["fills", "cancellations", "attention"], min_length=1, max_length=4
    )

    @field_validator("label")
    @classmethod
    def clean_label(cls, value):
        return StrategyAlertCreate.single_line(value)

    @field_validator("events")
    @classmethod
    def unique(cls, values):
        if len(set(values)) != len(values):
            raise ValueError("Choose each execution category once.")
        return sorted(values)


class OrderAlertUpdate(OrderAlertCreate):
    revision: int = Field(ge=1, strict=True)


def stamp():
    return datetime.now(UTC).isoformat()


class OrderAlerts:
    """Commit cursors and inbox evidence together; never query providers or change orders."""

    def __init__(self, store):
        self.store, self.inbox = store, NotificationInbox(store)
        self.lock, self.closed = threading.Lock(), False
        with store.db() as db:
            schema(db)
            db.execute(
                "CREATE TABLE IF NOT EXISTS order_alerts (id TEXT PRIMARY KEY, account_id TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS order_alerts_account ON order_alerts(account_id) WHERE status!='archived'"
            )

    @staticmethod
    def read(db, identity):
        row = db.execute("SELECT payload FROM order_alerts WHERE id=?", (identity,)).fetchone()
        if not row:
            raise LookupError("Execution alert not found.")
        return json.loads(row[0])

    @staticmethod
    def write(db, row):
        db.execute(
            "UPDATE order_alerts SET account_id=?,status=?,payload=? WHERE id=?",
            (row["account_id"], row["status"], json.dumps(row, allow_nan=False), row["id"]),
        )

    def account(self, identity):
        connection = next((item for item in self.store.connections() if item.id == identity), None)
        if connection is None:
            raise LookupError("Connection not found.")
        return dict(
            account_id=identity,
            account=connection.label,
            exchange=connection.exchange,
            environment="demo"
            if connection.exchange == "demo"
            else "test"
            if connection.sandbox
            else "production",
            source="connection:" + identity,
            source_label=connection.label,
        )

    @staticmethod
    def baseline(db):
        return db.execute("SELECT COALESCE(MAX(id),0) FROM execution_events").fetchone()[0]

    @staticmethod
    def capacity(db, account_id, identity="", creating=False):
        if (
            creating
            and db.execute("SELECT COUNT(*) FROM order_alerts WHERE status!='archived'").fetchone()[0] >= 50
        ):
            raise ValueError("Keep at most 50 non-archived execution alerts.")
        if db.execute(
            "SELECT 1 FROM order_alerts WHERE account_id=? AND status!='archived' AND id!=?",
            (account_id, identity),
        ).fetchone():
            raise AlertConflict("This account already has an execution alert. Edit its existing rule.")

    def create(self, body):
        account = self.account(body.account_id)
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self.capacity(db, body.account_id, creating=True)
            row = dict(
                **(body.model_dump() | account),
                id=uuid4().hex,
                status="armed",
                revision=1,
                cursor=self.baseline(db),
                created_at=stamp(),
                updated_at=stamp(),
                notifications=0,
                last_checked_at=None,
                error=None,
            )
            db.execute(
                "INSERT INTO order_alerts VALUES(?,?,?,?)",
                (row["id"], body.account_id, row["status"], json.dumps(row)),
            )
        return row

    def edit(self, identity, body):
        account = self.account(body.account_id)
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self.read(db, identity)
            if row["revision"] != body.revision:
                raise AlertConflict("Execution alert changed. Refresh its editor.")
            self.capacity(db, body.account_id, identity)
            row.update(body.model_dump() | account)
            row.update(
                revision=body.revision + 1,
                status="paused",
                cursor=self.baseline(db),
                updated_at=stamp(),
                error=None,
            )
            self.write(db, row)
        return row

    def change(self, identity, body: AlertAction):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self.read(db, identity)
            if row["revision"] != body.revision:
                raise AlertConflict("Execution alert changed. Refresh its controls.")
            if body.action in {"arm", "restore"}:
                self.capacity(db, row["account_id"], identity, creating=row["status"] == "archived")
                self.account(row["account_id"])
            row.update(
                status={"pause": "paused", "arm": "armed", "archive": "archived", "restore": "paused"}[
                    body.action
                ],
                revision=row["revision"] + 1,
                cursor=self.baseline(db),
                updated_at=stamp(),
                error=None,
            )
            self.write(db, row)
        return row

    def rules(self, include_archived=False, offset=0):
        with self.store.db() as db:
            rows = db.execute(
                "SELECT payload FROM order_alerts WHERE ? OR status!='archived' ORDER BY rowid DESC LIMIT 50 OFFSET ?",
                (include_archived, offset),
            ).fetchall()
            total = db.execute(
                "SELECT COUNT(*) FROM order_alerts WHERE ? OR status!='archived'", (include_archived,)
            ).fetchone()[0]
        return dict(
            items=[json.loads(row[0]) for row in rows], total=total, groups=GROUPS, offset=offset, limit=50
        )

    def tick(self):
        if self.closed or not self.lock.acquire(blocking=False):
            return
        try:
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                # Order by check time so quiet accounts cannot starve other subscriptions.
                selected = db.execute(
                    "SELECT id FROM order_alerts WHERE status='armed' ORDER BY COALESCE(json_extract(payload,'$.last_checked_at'),'') ASC,rowid LIMIT 1"
                ).fetchone()
                if not selected:
                    return
                rule = self.read(db, selected[0])
                oldest = db.execute("SELECT MIN(id) FROM execution_events").fetchone()[0]
                if oldest is not None and rule["cursor"] < oldest - 1:
                    rule.update(
                        status="paused",
                        revision=rule["revision"] + 1,
                        error="Execution journal retention passed this cursor. Review and resume from a new future-only baseline.",
                    )
                    self.write(db, rule)
                    return
                events = db.execute(
                    "SELECT id,payload FROM execution_events WHERE account_id=? AND id>? ORDER BY id LIMIT 100",
                    (rule["account_id"], rule["cursor"]),
                ).fetchall()
                for event in events:
                    observed = json.loads(event["payload"])
                    if set(observed["groups"]) & set(rule["events"]):
                        notice = dict(
                            **observed,
                            kind="order",
                            rule_id=rule["id"],
                            rule_revision=rule["revision"],
                            label=rule["label"],
                            source=rule["source"],
                            source_label=rule["source_label"],
                            account_id=rule["account_id"],
                            environment=rule["environment"],
                            event_id=event["id"],
                            cycle=event["id"],
                        )
                        db.execute(
                            "INSERT INTO alert_notifications(id,rule_id,cycle,created_at,read_at,payload) VALUES(?,?,?,?,NULL,?)",
                            (
                                uuid4().hex,
                                rule["id"],
                                event["id"],
                                stamp(),
                                json.dumps(notice, allow_nan=False),
                            ),
                        )
                        rule["notifications"] += 1
                    rule["cursor"] = event["id"]
                # Skip globally observed events belonging to other accounts only after draining this batch.
                if len(events) < 100:
                    rule["cursor"] = self.baseline(db)
                rule["last_checked_at"] = stamp()
                self.write(db, rule)
        finally:
            self.lock.release()

    def close(self):
        self.closed = True
        with self.lock:
            pass
