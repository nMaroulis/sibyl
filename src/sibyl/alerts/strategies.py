"""Durable per-run journal subscriptions, independent of provider and trading calls."""

import json
import threading
import time
from datetime import UTC, datetime
from sqlite3 import Connection
from uuid import uuid4

from sibyl.alerts.contracts import (
    AlertConflict,
    StrategyAlertAction,
    StrategyAlertCreate,
    StrategyAlertUpdate,
)
from sibyl.alerts.inbox import NotificationInbox
from sibyl.storage import Store
from sibyl.strategies.catalog import CATALOG

GROUPS = [
    {
        "id": "attention",
        "name": "Pauses, errors & recovery",
        "description": "Recorded PAUSE, ERROR and RECOVERED events, including manual pauses and startup safety pauses.",
    },
    {
        "id": "lifecycle",
        "name": "Run lifecycle",
        "description": "Recorded resumes, stops, Stop & cancel requests and transitions to completed.",
    },
]


def stamp() -> str:
    """Return a UTC receipt/check time, separate from the journal's event time."""
    return datetime.now(UTC).isoformat()


def event_kind(event: dict, last_status: str | None) -> tuple[str | None, str]:
    """Classify recorded evidence; a final SELL can also complete a paper run."""
    action = event.get("action", "")
    if action in {"ERROR", "PAUSE", "RECOVERED"}:
        return "attention", action
    if event.get("job_status") == "completed" and last_status != "completed":
        return "lifecycle", "COMPLETED"
    if action in {"RESUME", "STOP", "STOP_CANCEL"}:
        return "lifecycle", action
    return None, action


class StrategyAlerts:
    """Watch one run per active rule, committing its event cursor and inbox rows together.

    One local worker processes at most 100 journal rows for one due rule per tick.
    Creation/resume uses a new baseline; downtime preserves armed cursors. No
    market, account, strategy-control or external messaging operation is called.
    """

    limit = 50

    def __init__(self, store: Store):
        self.store = store
        self.inbox = NotificationInbox(store)
        self._worker = threading.Lock()
        self._closed = False
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS strategy_alerts (
                    id TEXT PRIMARY KEY, job_id TEXT NOT NULL, status TEXT NOT NULL,
                    next_check REAL NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS strategy_alerts_due ON strategy_alerts(status,next_check);
                CREATE UNIQUE INDEX IF NOT EXISTS strategy_alerts_run
                    ON strategy_alerts(job_id) WHERE status!='archived';
            """)

    @staticmethod
    def _read(db: Connection, identity: str) -> dict:
        row = db.execute("SELECT payload FROM strategy_alerts WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise LookupError("Strategy alert not found.")
        return json.loads(row[0])

    @staticmethod
    def _write(db: Connection, rule: dict) -> None:
        db.execute(
            "UPDATE strategy_alerts SET job_id=?,status=?,next_check=?,payload=? WHERE id=?",
            (
                rule["job_id"],
                rule["status"],
                rule["next_check"],
                json.dumps(rule, allow_nan=False),
                rule["id"],
            ),
        )

    @staticmethod
    def _baseline(db: Connection, job_id: str) -> tuple[dict, int, str]:
        """Capture a job's current identity/status and journal tail in one transaction."""
        row = db.execute("SELECT payload FROM strategy_jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise LookupError("Strategy not found.")
        job = json.loads(row[0])
        params = job["parameters"]
        names = {item["id"]: item["name"] for item in CATALOG}
        mode = job.get("mode", "paper")
        snapshot = {
            "strategy": params["strategy"],
            "name": names.get(params["strategy"], params["strategy"]),
            "symbol": params["symbol"],
            "timeframe": params["timeframe"],
            "mode": mode,
            "source": job["source"],
            "source_label": job.get("source_label")
            or ("Sibyl Demo" if job["source"] == "demo" else job["source"]),
            "environment": job.get("environment", "demo" if job["source"] == "demo" else "reference"),
            "account": job.get("account"),
        }
        cursor = db.execute(
            "SELECT COALESCE(MAX(id),0) FROM strategy_events WHERE job_id=?", (job_id,)
        ).fetchone()[0]
        return snapshot, cursor, job["status"]

    def _available(
        self, db: Connection, job_id: str, identity: str | None = None, *, capacity: bool = True
    ) -> None:
        if (
            capacity
            and db.execute("SELECT COUNT(*) FROM strategy_alerts WHERE status!='archived'").fetchone()[0]
            >= self.limit
        ):
            raise ValueError("Keep at most 50 non-archived strategy alerts. Archive an old rule first.")
        if db.execute(
            "SELECT 1 FROM strategy_alerts WHERE job_id=? AND status!='archived' AND id!=?",
            (job_id, identity or ""),
        ).fetchone():
            raise AlertConflict("This run already has a strategy alert. Edit or resume its existing rule.")

    @staticmethod
    def _revision(rule: dict, revision: int) -> None:
        if rule["revision"] != revision:
            raise AlertConflict("This strategy alert changed. Reopen it to review the latest settings.")

    def rules(self, include_archived: bool = False, offset: int = 0, job_id: str | None = None) -> dict:
        """Page saved rules and budgets using only local records."""
        if not 0 <= offset <= 1_000_000:
            raise ValueError("Choose a valid strategy-alert page.")
        clause = "(? OR status!='archived') AND (? IS NULL OR job_id=?)"
        args = (include_archived, job_id, job_id)
        with self.store.db() as db:
            db.execute("BEGIN")
            rows = db.execute(
                f"SELECT payload FROM strategy_alerts WHERE {clause} ORDER BY rowid DESC LIMIT 50 OFFSET ?",
                (*args, offset),
            ).fetchall()
            total = db.execute(f"SELECT COUNT(*) FROM strategy_alerts WHERE {clause}", args).fetchone()[0]
            count = db.execute("SELECT COUNT(*) FROM strategy_alerts WHERE status!='archived'").fetchone()[0]
        return {
            "items": [json.loads(row[0]) for row in rows],
            "count": count,
            "total": total,
            "offset": offset,
            "page_size": 50,
            "limit": self.limit,
            "groups": GROUPS,
            "delivery": "in_app",
            "requires_running_server": True,
        }

    def create(self, request: StrategyAlertCreate) -> dict:
        """Subscribe to future events without evaluating or changing the strategy."""
        now = stamp()
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            snapshot, cursor, state = self._baseline(db, request.job_id)
            self._available(db, request.job_id)
            rule = {
                "id": uuid4().hex,
                **request.model_dump(),
                "run": snapshot,
                "status": "armed",
                "revision": 1,
                "cursor": cursor,
                "last_status": state,
                "created_at": now,
                "updated_at": now,
                "armed_at": now,
                "next_check": 0,
                "last_checked_at": None,
                "last_event_at": None,
                "last_notified_at": None,
                "notifications": 0,
            }
            db.execute(
                "INSERT INTO strategy_alerts VALUES(?,?,?,?,?)",
                (rule["id"], rule["job_id"], rule["status"], 0, json.dumps(rule)),
            )
        return rule

    def edit(self, identity: str, request: StrategyAlertUpdate) -> dict:
        """Keep identity/history, skip prior journal entries and save new settings paused."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rule = self._read(db, identity)
            self._revision(rule, request.revision)
            if rule["status"] == "archived":
                raise ValueError("Restore this rule before editing it.")
            self._available(db, request.job_id, identity, capacity=False)
            snapshot, cursor, state = self._baseline(db, request.job_id)
            rule.update(request.model_dump(exclude={"revision"}))
            rule.update(
                run=snapshot,
                cursor=cursor,
                last_status=state,
                status="paused",
                revision=rule["revision"] + 1,
                updated_at=stamp(),
                next_check=0,
                last_checked_at=None,
                last_event_at=None,
            )
            self._write(db, rule)
        return rule

    def change(self, identity: str, request: StrategyAlertAction) -> dict:
        """Explicit resume starts at the current tail; paused-period events are skipped."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rule = self._read(db, identity)
            self._revision(rule, request.revision)
            action = request.action
            target = {"pause": "paused", "arm": "armed", "archive": "archived", "restore": "paused"}[action]
            if action == "restore":
                if rule["status"] != "archived":
                    return rule
                self._available(db, rule["job_id"], identity)
            elif action != "archive" and rule["status"] == "archived":
                raise ValueError("Restore this rule before resuming it.")
            if rule["status"] == target:
                return rule
            if action == "arm":
                snapshot, cursor, state = self._baseline(db, rule["job_id"])
                rule.update(
                    run=snapshot, cursor=cursor, last_status=state, armed_at=stamp(), last_event_at=None
                )
            rule.update(status=target, revision=rule["revision"] + 1, updated_at=stamp(), next_check=0)
            self._write(db, rule)
        return rule

    def tick(self) -> None:
        """Atomically inspect one bounded journal page and append each matching event once."""
        with self._worker:
            if self._closed:
                return
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT id FROM strategy_alerts WHERE status='armed' AND next_check<=? ORDER BY next_check,rowid LIMIT 1",
                    (time.time(),),
                ).fetchone()
                if row is None:
                    return
                rule = self._read(db, row[0])
                events = db.execute(
                    "SELECT id,payload FROM strategy_events WHERE job_id=? AND id>? ORDER BY id LIMIT 100",
                    (rule["job_id"], rule["cursor"]),
                ).fetchall()
                checked_at = stamp()
                for row in events:
                    event = json.loads(row["payload"])
                    group, action = event_kind(event, rule["last_status"])
                    if group in rule["events"]:
                        payload = {
                            "kind": "strategy",
                            "rule_id": rule["id"],
                            "rule_revision": rule["revision"],
                            "label": rule["label"],
                            "job_id": rule["job_id"],
                            **rule["run"],
                            "action": action,
                            "journal_action": event.get("action"),
                            "reason": event.get("reason", ""),
                            "job_status": event.get("job_status"),
                            "event_id": row["id"],
                            "observed_at": event["timestamp"],
                            "cycle": row["id"],
                            "group": group,
                        }
                        db.execute(
                            "INSERT INTO alert_notifications VALUES(?,?,?,?,NULL,?)",
                            (
                                uuid4().hex,
                                rule["id"],
                                row["id"],
                                checked_at,
                                json.dumps(payload, allow_nan=False),
                            ),
                        )
                        rule.update(notifications=rule["notifications"] + 1, last_notified_at=checked_at)
                    rule.update(
                        cursor=row["id"],
                        last_event_at=event["timestamp"],
                        last_status=event.get("job_status", rule["last_status"]),
                    )
                rule.update(
                    last_checked_at=checked_at, next_check=time.time() + (0 if len(events) == 100 else 5)
                )
                self._write(db, rule)

    def close(self) -> None:
        """Wait for the bounded local transaction before completing application shutdown."""
        with self._worker:
            self._closed = True


def strategy_alert_example() -> dict:
    """An isolated sample shows the complete rule/inbox contract without a fake run."""
    observed = "2026-10-23T08:00:00+00:00"
    run = {
        "strategy": "ema",
        "name": "EMA Crossover",
        "symbol": "BTC/USDT",
        "timeframe": "1h",
        "mode": "paper",
        "source": "demo",
        "source_label": "Sibyl Demo",
        "environment": "demo",
        "account": None,
    }
    rule = {
        "id": "example-strategy-alert",
        "job_id": "example-run",
        "run": run,
        "label": "My trend strategy",
        "events": ["attention", "lifecycle"],
        "status": "armed",
        "revision": 1,
        "cursor": 12,
        "last_status": "paused",
        "notifications": 1,
        "created_at": observed,
        "updated_at": observed,
        "armed_at": observed,
        "next_check": 0,
        "last_checked_at": observed,
        "last_event_at": observed,
        "last_notified_at": observed,
    }
    notification = {
        "kind": "strategy",
        "id": "example-strategy-notification",
        "rule_id": rule["id"],
        "rule_revision": 1,
        "label": rule["label"],
        "job_id": rule["job_id"],
        **run,
        "action": "PAUSE",
        "journal_action": "PAUSE",
        "job_status": "paused",
        "reason": "Price source changed. Start a new job for this source.",
        "event_id": 12,
        "cycle": 12,
        "group": "attention",
        "observed_at": observed,
        "created_at": observed,
        "read_at": None,
    }
    return {
        "rules": {
            "items": [rule],
            "count": 1,
            "total": 1,
            "limit": 50,
            "offset": 0,
            "page_size": 50,
            "groups": GROUPS,
            "delivery": "in_app",
            "requires_running_server": True,
        },
        "inbox": {
            "items": [notification],
            "total": 1,
            "unread": 1,
            "limit": 20,
            "offset": 0,
            "delivery": "in_app",
        },
    }
