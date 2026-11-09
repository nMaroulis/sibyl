"""Durable calendar policies and bounded occurrence history, without model execution."""

import json
import sqlite3
from datetime import datetime
from uuid import uuid4

from sibyl.investigations.scheduling.calendar import next_occurrence
from sibyl.investigations.scheduling.contracts import delivery_channel, message_format

ACTIVE = {"waiting", "running"}
GRACE_SECONDS = 15 * 60


class BriefingConflict(ValueError):
    """A schedule changed, is busy or exceeds the local admission budget."""


class BriefingRepository:
    """Serialize calendar edits and occurrence claims with short SQLite transactions."""

    def __init__(self, store):
        self.store = store
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS briefing_schedules (
                    id TEXT PRIMARY KEY, investigation_id TEXT NOT NULL,
                    status TEXT NOT NULL, next_at REAL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS briefing_due ON briefing_schedules(status,next_at);
                CREATE UNIQUE INDEX IF NOT EXISTS briefing_one_schedule
                    ON briefing_schedules(investigation_id) WHERE status!='archived';
                CREATE TABLE IF NOT EXISTS briefing_occurrences (
                    id TEXT PRIMARY KEY, schedule_id TEXT NOT NULL,
                    scheduled_for TEXT, status TEXT NOT NULL, next_attempt REAL NOT NULL,
                    payload TEXT NOT NULL, UNIQUE(schedule_id,scheduled_for)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS briefing_one_pending
                    ON briefing_occurrences(schedule_id) WHERE status IN ('waiting','running');
            """)

    @staticmethod
    def _read(db, identity):
        row = db.execute("SELECT payload FROM briefing_schedules WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise LookupError("Briefing schedule not found.")
        return BriefingRepository._public_defaults(json.loads(row[0]))

    @staticmethod
    def _public_defaults(schedule):
        """Project canonical fields without rewriting an older saved calendar."""
        return {
            **schedule,
            "channel": delivery_channel(schedule),
            "message_format": message_format(schedule),
            "delivery_binding": schedule.get("delivery_binding") or schedule.get("telegram_binding"),
        }

    @staticmethod
    def _write(db, schedule):
        next_at = (
            datetime.fromisoformat(schedule["next_run_at"]).timestamp() if schedule["next_run_at"] else None
        )
        db.execute(
            "UPDATE briefing_schedules SET status=?,next_at=?,payload=? WHERE id=?",
            (schedule["status"], next_at, json.dumps(schedule), schedule["id"]),
        )

    @staticmethod
    def _revision(schedule, revision):
        if schedule["revision"] != revision:
            raise BriefingConflict("This schedule changed. Refresh it before applying your changes.")

    def create(self, investigation_id, body, binding, now):
        """Save an explicit future calendar; creation never generates a report."""
        values = body.model_dump(exclude={"enabled", "telegram_target", "private_target"})
        schedule = {
            "id": uuid4().hex,
            "investigation_id": investigation_id,
            **values,
            "delivery_binding": binding,
            "telegram_binding": binding if body.channel == "telegram" else None,
            "status": "armed" if body.enabled else "paused",
            "revision": 1,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "next_run_at": next_occurrence(values, now).isoformat() if body.enabled else None,
        }
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("SELECT 1 FROM investigations WHERE id=?", (investigation_id,)).fetchone():
                raise LookupError("Investigation not found.")
            if (
                db.execute("SELECT COUNT(*) FROM briefing_schedules WHERE status!='archived'").fetchone()[0]
                >= 50
            ):
                raise BriefingConflict("Keep at most 50 non-archived briefing schedules.")
            try:
                db.execute(
                    "INSERT INTO briefing_schedules VALUES(?,?,?,?,?)",
                    (
                        schedule["id"],
                        investigation_id,
                        schedule["status"],
                        datetime.fromisoformat(schedule["next_run_at"]).timestamp()
                        if schedule["next_run_at"]
                        else None,
                        json.dumps(schedule),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise BriefingConflict(
                    "This investigation already has a schedule. Edit or resume it instead."
                ) from exc
        return schedule

    def get(self, identity):
        """Read a policy without contacting a provider or evaluating the calendar."""
        with self.store.db() as db:
            return self._read(db, identity)

    def list(self, investigation_id=None, archived=False):
        """List saved calendars, optionally including their archived audit records."""
        with self.store.db() as db:
            rows = db.execute(
                "SELECT payload FROM briefing_schedules WHERE (? IS NULL OR investigation_id=?) AND (? OR status!='archived') ORDER BY rowid DESC LIMIT 100",
                (investigation_id, investigation_id, archived),
            ).fetchall()
        return [self._public_defaults(json.loads(row[0])) for row in rows]

    def _cancel_waiters(self, db, identity, now):
        rows = db.execute(
            "SELECT payload FROM briefing_occurrences WHERE schedule_id=? AND status='waiting'", (identity,)
        ).fetchall()
        for row in rows:
            occurrence = json.loads(row[0])
            occurrence.update(
                status="cancelled",
                finished_at=now.isoformat(),
                error="The schedule changed before this report started.",
            )
            self._write_occurrence(db, occurrence)

    def edit(self, identity, body, binding, now):
        """Reset the next calendar time and invalidate waiting work from the old revision."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            schedule = self._read(db, identity)
            self._revision(schedule, body.revision)
            if schedule["status"] == "archived":
                raise BriefingConflict("Create a new schedule instead of editing an archived calendar.")
            schedule.update(body.model_dump(exclude={"revision", "telegram_target", "private_target"}))
            schedule.update(
                delivery_binding=binding,
                telegram_binding=binding if body.channel == "telegram" else None,
                revision=schedule["revision"] + 1,
                updated_at=now.isoformat(),
                next_run_at=next_occurrence(schedule, now).isoformat()
                if schedule["status"] == "armed"
                else None,
            )
            self._cancel_waiters(db, identity, now)
            self._write(db, schedule)
        return schedule

    def change(self, identity, body, now):
        """Pause/resume future automation or archive its calendar, preserving history."""
        target = {"pause": "paused", "resume": "armed", "archive": "archived"}[body.action]
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            schedule = self._read(db, identity)
            self._revision(schedule, body.revision)
            if schedule["status"] == "archived":
                raise BriefingConflict("This schedule is archived. Create a new calendar to continue.")
            if schedule["status"] == target:
                return schedule
            schedule.update(
                status=target,
                revision=schedule["revision"] + 1,
                updated_at=now.isoformat(),
                next_run_at=next_occurrence(schedule, now).isoformat() if target == "armed" else None,
            )
            self._cancel_waiters(db, identity, now)
            self._write(db, schedule)
        return schedule

    @staticmethod
    def _occurrence(schedule, now, scheduled_for=None, identity=None, trigger="calendar"):
        due = datetime.fromisoformat(scheduled_for) if scheduled_for else now
        return {
            "id": identity or uuid4().hex,
            "schedule_id": schedule["id"],
            "investigation_id": schedule["investigation_id"],
            "schedule_revision": schedule["revision"],
            "delivery_requested": delivery_channel(schedule) is not None,
            "delivery_channel": delivery_channel(schedule),
            "telegram_requested": delivery_channel(schedule) == "telegram",
            "trigger": trigger,
            "scheduled_for": scheduled_for,
            "requested_at": now.isoformat(),
            "deadline": due.timestamp() + GRACE_SECONDS,
            "next_attempt": 0,
            "status": "waiting",
            "run_id": None,
            "delivery_id": None,
            "delivery_error": None,
            "finished_at": None,
            "error": None,
            "calendar": {key: schedule[key] for key in ("frequency", "local_time", "timezone", "weekday")},
        }

    @staticmethod
    def _insert(db, occurrence):
        db.execute(
            "INSERT INTO briefing_occurrences VALUES(?,?,?,?,?,?)",
            (
                occurrence["id"],
                occurrence["schedule_id"],
                occurrence["scheduled_for"],
                occurrence["status"],
                occurrence["next_attempt"],
                json.dumps(occurrence),
            ),
        )
        db.execute(
            "DELETE FROM briefing_occurrences WHERE schedule_id=? AND status NOT IN ('waiting','running') AND id NOT IN (SELECT id FROM briefing_occurrences WHERE schedule_id=? ORDER BY rowid DESC LIMIT 200)",
            (occurrence["schedule_id"], occurrence["schedule_id"]),
        )

    @staticmethod
    def _write_occurrence(db, occurrence):
        db.execute(
            "UPDATE briefing_occurrences SET status=?,next_attempt=?,payload=? WHERE id=?",
            (occurrence["status"], occurrence["next_attempt"], json.dumps(occurrence), occurrence["id"]),
        )

    def claim_due(self, now, *, startup=False):
        """Claim one due occurrence and advance its calendar atomically; downtime never replays."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT payload FROM briefing_schedules s WHERE status='armed' AND next_at<=? AND (? OR NOT EXISTS(SELECT 1 FROM briefing_occurrences o WHERE o.schedule_id=s.id AND o.status IN ('waiting','running'))) ORDER BY next_at LIMIT 1",
                (now.timestamp(), startup),
            ).fetchone()
            if row is None:
                return None
            schedule = json.loads(row[0])
            existing = db.execute(
                "SELECT payload FROM briefing_occurrences WHERE schedule_id=? AND scheduled_for=?",
                (schedule["id"], schedule["next_run_at"]),
            ).fetchone()
            if existing:
                schedule["next_run_at"] = next_occurrence(
                    schedule, max(now, datetime.fromisoformat(schedule["next_run_at"]))
                ).isoformat()
                self._write(db, schedule)
                return json.loads(existing[0])
            occurrence = self._occurrence(schedule, now, schedule["next_run_at"])
            if startup or now.timestamp() > occurrence["deadline"]:
                occurrence.update(
                    status="missed",
                    finished_at=now.isoformat(),
                    missed_until=now.isoformat(),
                    error="The scheduled time passed while the backend was unavailable. No catch-up report was generated.",
                )
            self._insert(db, occurrence)
            schedule["next_run_at"] = next_occurrence(schedule, now).isoformat()
            self._write(db, schedule)
        return occurrence

    def run_now(self, identity, body, now):
        """Claim one explicitly requested briefing without moving its next calendar time."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            schedule = self._read(db, identity)
            existing = db.execute(
                "SELECT payload FROM briefing_occurrences WHERE id=?", (body.request_id,)
            ).fetchone()
            if existing:
                occurrence = json.loads(existing[0])
                if occurrence["schedule_id"] != identity:
                    raise BriefingConflict("This request identity belongs to a different schedule.")
                return occurrence
            self._revision(schedule, body.revision)
            if schedule["status"] != "armed":
                raise BriefingConflict("Resume the schedule before running and delivering a briefing.")
            occurrence = self._occurrence(schedule, now, identity=body.request_id, trigger="manual")
            try:
                self._insert(db, occurrence)
            except sqlite3.IntegrityError as exc:
                raise BriefingConflict("This schedule already has a pending briefing.") from exc
        return occurrence

    def occurrences(self, status):
        """Read a bounded local queue without admitting model execution."""
        with self.store.db() as db:
            rows = db.execute(
                "SELECT payload FROM briefing_occurrences WHERE status=? ORDER BY rowid LIMIT 50", (status,)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def admit(self, identity, now):
        """Fence report admission against a concurrent pause or schedule edit."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM briefing_occurrences WHERE id=?", (identity,)).fetchone()
            if row is None:
                raise LookupError("Briefing occurrence not found.")
            occurrence = json.loads(row[0])
            if occurrence["status"] != "waiting" or occurrence["next_attempt"] > now.timestamp():
                return None
            schedule = self._read(db, occurrence["schedule_id"])
            if schedule["revision"] != occurrence["schedule_revision"] or schedule["status"] != "armed":
                occurrence.update(
                    status="cancelled",
                    finished_at=now.isoformat(),
                    error="The schedule changed before report admission.",
                )
            elif occurrence["deadline"] < now.timestamp():
                occurrence.update(
                    status="missed",
                    finished_at=now.isoformat(),
                    error="No report slot became available within fifteen minutes. No delayed report was generated.",
                )
            else:
                occurrence["status"] = "running"
            self._write_occurrence(db, occurrence)
            return schedule if occurrence["status"] == "running" else None

    def update(self, identity, **patch):
        """Advance an active occurrence once; terminal occurrence outcomes are immutable."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM briefing_occurrences WHERE id=?", (identity,)).fetchone()
            if row is None:
                raise LookupError("Briefing occurrence not found.")
            occurrence = json.loads(row[0])
            if occurrence["status"] in ACTIVE:
                occurrence.update(patch)
                self._write_occurrence(db, occurrence)
        return occurrence

    def history(self, identity):
        """Return the latest thirty retained occurrences, including missed and blocked runs."""
        self.get(identity)
        with self.store.db() as db:
            rows = db.execute(
                "SELECT payload FROM briefing_occurrences WHERE schedule_id=? ORDER BY rowid DESC LIMIT 30",
                (identity,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]
