"""Local subscriptions to transport evidence, never active connection probes."""

import json
import threading
import time
from datetime import UTC, datetime
from uuid import uuid4

from sibyl.alerts.connection_conditions import assess_connection, reset_streaks
from sibyl.alerts.contracts import (
    AlertAction,
    AlertConflict,
    ConnectionAlertCreate,
    ConnectionAlertUpdate,
)
from sibyl.alerts.inbox import NotificationInbox
from sibyl.market_data.control import MESSAGES


class ConnectionAlerts:
    """Consume bounded read journals, committing notification and cursor atomically.

    Counters belong to an operation, source, session and profile. A quote cannot
    recover an account-read incident. Saving/resuming skips existing evidence;
    armed rules retain their cursor across restarts, subject to journal retention.
    """

    limit = 50

    def __init__(self, market, store, *, clock=time.time):
        self.market, self.store, self.clock = market, store, clock
        self.inbox = NotificationInbox(store)
        self._worker = threading.Lock()
        self._closed = False
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS connection_alerts (
                    id TEXT PRIMARY KEY, source TEXT NOT NULL, status TEXT NOT NULL,
                    next_check REAL NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS connection_alerts_due ON connection_alerts(status,next_check);
                CREATE UNIQUE INDEX IF NOT EXISTS connection_alerts_source
                    ON connection_alerts(source) WHERE status!='archived';
            """)

    def _stamp(self):
        return datetime.fromtimestamp(self.clock(), UTC).isoformat()

    def sources(self):
        """Read safe catalog identities, including previously observed sources, without HTTP."""
        return [
            {key: item[key] for key in ("id", "name", "kind", "provider", "environment", "available")}
            for item in self.market.provider_health()["items"]
            if item["provider"] != "demo"
        ]

    def _source(self, identity):
        source = next((item for item in self.sources() if item["id"] == identity), None)
        if source is None:
            raise ValueError(
                "Choose a configured or previously observed source. Demo has no connection to watch."
            )
        return source

    @staticmethod
    def _read(db, identity):
        row = db.execute("SELECT payload FROM connection_alerts WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise LookupError("Connection alert not found.")
        return json.loads(row[0])

    @staticmethod
    def _write(db, rule):
        db.execute(
            "UPDATE connection_alerts SET source=?,status=?,next_check=?,payload=? WHERE id=?",
            (
                rule["source"],
                rule["status"],
                rule["next_check"],
                json.dumps(rule, allow_nan=False),
                rule["id"],
            ),
        )

    @staticmethod
    def _revision(rule, revision):
        if rule["revision"] != revision:
            raise AlertConflict("This connection alert changed. Reopen it to review the latest settings.")

    def _available(self, db, source, identity="", *, capacity=True):
        if (
            capacity
            and db.execute("SELECT COUNT(*) FROM connection_alerts WHERE status!='archived'").fetchone()[0]
            >= self.limit
        ):
            raise ValueError("Keep at most 50 non-archived connection alerts. Archive an old rule first.")
        if db.execute(
            "SELECT 1 FROM connection_alerts WHERE source=? AND status!='archived' AND id!=?",
            (source, identity),
        ).fetchone():
            raise AlertConflict("This source already has an alert. Edit or resume its existing rule.")

    def _baseline(self, db, rule):
        rule.update(
            cursor=self.market.read_history.events.tail(db),
            operations={},
            tracking_note=None,
            last_event_at=None,
            last_checked_at=None,
        )

    def rules(self, include_archived=False, offset=0):
        """Page subscriptions and safe source choices; this never checks a provider."""
        if not 0 <= offset <= 1_000_000:
            raise ValueError("Choose a valid connection-alert page.")
        sources = self.sources()
        with self.store.db() as db:
            db.execute("BEGIN")
            rows = db.execute(
                "SELECT payload FROM connection_alerts WHERE (? OR status!='archived') ORDER BY rowid DESC LIMIT 50 OFFSET ?",
                (include_archived, offset),
            ).fetchall()
            total = db.execute(
                "SELECT COUNT(*) FROM connection_alerts WHERE (? OR status!='archived')", (include_archived,)
            ).fetchone()[0]
            count = db.execute("SELECT COUNT(*) FROM connection_alerts WHERE status!='archived'").fetchone()[
                0
            ]
        return dict(
            items=[json.loads(row[0]) for row in rows],
            count=count,
            total=total,
            offset=offset,
            page_size=50,
            limit=self.limit,
            sources=sources,
            recording=self.market.read_history.recording(),
            delivery="in_app",
            requires_running_server=True,
        )

    def create(self, request: ConnectionAlertCreate):
        """Watch only future recorded reads, without activating accounts or changing feeds."""
        source = self._source(request.source)
        now = self._stamp()
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._available(db, request.source)
            rule = dict(
                id=uuid4().hex,
                **request.model_dump(),
                source_info=source,
                status="armed",
                revision=1,
                notifications=0,
                next_check=0,
                created_at=now,
                updated_at=now,
                armed_at=now,
                last_notified_at=None,
            )
            self._baseline(db, rule)
            db.execute(
                "INSERT INTO connection_alerts VALUES(?,?,?,?,?)",
                (rule["id"], rule["source"], "armed", 0, json.dumps(rule)),
            )
        return rule

    def edit(self, identity: str, request: ConnectionAlertUpdate):
        """Save changed settings paused; immutable inbox evidence keeps its original revision."""
        source = self._source(request.source)
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rule = self._read(db, identity)
            self._revision(rule, request.revision)
            if rule["status"] == "archived":
                raise ValueError("Restore this rule before editing it.")
            self._available(db, request.source, identity, capacity=False)
            rule.update(request.model_dump(exclude={"revision"}))
            rule.update(
                source_info=source,
                status="paused",
                revision=rule["revision"] + 1,
                updated_at=self._stamp(),
                next_check=0,
            )
            self._baseline(db, rule)
            self._write(db, rule)
        return rule

    def change(self, identity: str, request: AlertAction):
        """Pause/resume/archive/restore only notifications. Resume starts a fresh observation window."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rule = self._read(db, identity)
            self._revision(rule, request.revision)
            target = {"pause": "paused", "arm": "armed", "archive": "archived", "restore": "paused"}[
                request.action
            ]
            if request.action == "restore":
                if rule["status"] != "archived":
                    return rule
                self._available(db, rule["source"], identity)
            elif request.action != "archive" and rule["status"] == "archived":
                raise ValueError("Restore this rule before resuming it.")
            if rule["status"] == target:
                return rule
            if request.action == "arm":
                self._baseline(db, rule)
                rule["armed_at"] = self._stamp()
            rule.update(status=target, revision=rule["revision"] + 1, updated_at=self._stamp(), next_check=0)
            self._write(db, rule)
        return rule

    def _notify(self, db, rule, event, action, checked):
        state = rule["operations"][event["operation"]]
        payload = dict(
            kind="connection",
            rule_id=rule["id"],
            rule_revision=rule["revision"],
            label=rule["label"],
            source=rule["source"],
            source_label=rule["source_info"]["name"],
            provider=event["provider"],
            environment=event["environment"],
            operation=event["operation"],
            action=action,
            error_kind=event["error_kind"],
            reason=MESSAGES.get(
                event["error_kind"], "Successful transport reads resumed for this operation."
            ),
            failures=state["failures"],
            successes=state["successes"],
            failures_required=rule["failures_required"],
            successes_required=rule["successes_required"],
            observed_at=event["at"],
            event_id=event["id"],
            cycle=event["id"],
        )
        db.execute(
            "INSERT INTO alert_notifications VALUES(?,?,?,?,NULL,?)",
            (uuid4().hex, rule["id"], event["id"], checked, json.dumps(payload, allow_nan=False)),
        )
        rule.update(notifications=rule["notifications"] + 1, last_notified_at=checked)

    def tick(self):
        """Inspect at most 100 local read events for one due rule; never call a provider."""
        with self._worker:
            if self._closed:
                return
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT id FROM connection_alerts WHERE status='armed' AND next_check<=? ORDER BY next_check,rowid LIMIT 1",
                    (self.clock(),),
                ).fetchone()
                if row is None:
                    return
                rule = self._read(db, row[0])
                pruned = db.execute(
                    "SELECT pruned_through FROM provider_event_retention WHERE id=1"
                ).fetchone()[0]
                if rule["cursor"] < pruned:
                    reset_streaks(
                        rule,
                        "Some read evidence expired before it was processed; consecutive counts restarted.",
                    )
                    rule["cursor"] = pruned
                events = db.execute(
                    "SELECT * FROM provider_read_events WHERE source_id=? AND id>? ORDER BY id LIMIT 100",
                    (rule["source"], rule["cursor"]),
                ).fetchall()
                checked = self._stamp()
                for row in events:
                    event = dict(row)
                    action = assess_connection(rule, event, self.clock())
                    if action:
                        self._notify(db, rule, event, action, checked)
                    rule.update(cursor=event["id"], last_event_at=event["at"])
                rule.update(
                    last_checked_at=checked, next_check=self.clock() + (0 if len(events) == 100 else 5)
                )
                self._write(db, rule)

    def close(self):
        """Finish a bounded local transaction before application shutdown."""
        with self._worker:
            self._closed = True
