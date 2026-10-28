"""Durable workspace-wide submission halt, independent of provider availability."""

import json
from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from sibyl.models import Request
from sibyl.strategies.execution.contracts import ExecutionGuard

RELEASE_CONFIRMATION = "RELEASE STRATEGY HALT"
HALT_MESSAGE = "Global strategy halt is active. Release it in Strategies, then review and Resume each run."


class ControlConflict(ExecutionGuard):
    """The displayed control revision no longer describes the current halt."""


class ControlAction(Request):
    """A revision-bound local control; releasing never resumes a strategy."""

    action: Literal["halt", "release"]
    revision: int = Field(ge=0, strict=True)
    reason: str = Field(default="", max_length=240)
    confirmation: str = Field(default="", max_length=120)


def read_control(db) -> dict:
    """Read the persisted latch in the caller's transaction; missing state fails closed."""
    row = db.execute("SELECT payload FROM strategy_execution_control WHERE id=1").fetchone()
    if row is None:
        raise ExecutionGuard("Strategy execution controls are unavailable; no submission is permitted.")
    return json.loads(row[0])


def require_submissions(db, revision: int | None = None) -> dict:
    """Check the latch and optional observation/review generation at the write boundary."""
    state = read_control(db)
    if state["halted"]:
        raise ExecutionGuard(HALT_MESSAGE)
    if revision is not None and revision != state["revision"]:
        raise ExecutionGuard("Global execution controls changed. Review the strategy again.")
    return state


class StrategyControls:
    """Serialize the latch with local strategy lifecycle/submission operations.

    A halt, all running exchange-job pauses and their journal events commit in
    one transaction. The lifecycle lock may wait for an already admitted native
    request. Paper runs, manual orders, separately approved exits and cancellation
    policies retain their existing authority. This is a local single-worker control.
    """

    def __init__(self, runner):
        self.runner, self.store = runner, runner.store
        with self.store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS strategy_execution_control (
                    id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS strategy_control_events (
                    revision INTEGER PRIMARY KEY, payload TEXT NOT NULL
                );
            """)
            db.execute(
                "INSERT OR IGNORE INTO strategy_execution_control VALUES(1,?)",
                (json.dumps({"halted": False, "revision": 0, "changed_at": None, "reason": ""}),),
            )

    def state(self) -> dict:
        """Read current control and its newest 20 audit entries without contacting providers."""
        with self.store.db() as db:
            db.execute("BEGIN")
            state = read_control(db)
            events = db.execute(
                "SELECT payload FROM strategy_control_events ORDER BY revision DESC LIMIT 20"
            ).fetchall()
            counts = db.execute(
                "SELECT json_extract(payload,'$.status'),COUNT(*) FROM strategy_jobs "
                "WHERE json_extract(payload,'$.mode')='exchange' GROUP BY 1"
            ).fetchall()
        return {
            **state,
            "server_enabled": self.runner.market.settings.allow_live_trading
            and self.runner.market.settings.allow_strategy_execution,
            "exchange_runs": dict(counts),
            "history": [json.loads(row[0]) for row in events],
            "history_limit": 20,
            "history_retention": 200,
            "release_confirmation": RELEASE_CONFIRMATION,
        }

    def require(self, revision: int | None = None) -> dict:
        """Check admission before provider reads as well as at submission."""
        with self.store.db() as db:
            return require_submissions(db, revision)

    def change(self, request: ControlAction) -> dict:
        """Halt without a provider call, or release with an exact typed confirmation."""
        with self.runner.lock, self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            state = read_control(db)
            if state["revision"] != request.revision:
                raise ControlConflict("Execution controls changed. Refresh before trying again.")
            halted = request.action == "halt"
            if not halted and request.confirmation != RELEASE_CONFIRMATION:
                raise ExecutionGuard("Type " + RELEASE_CONFIRMATION + " to release this halt.")
            if state["halted"] != halted:
                revision = state["revision"] + 1
                timestamp = datetime.now(UTC).isoformat()
                state = {
                    "halted": halted,
                    "revision": revision,
                    "changed_at": timestamp,
                    "reason": request.reason.strip(),
                }
                paused = []
                if halted:
                    for row in db.execute(
                        "SELECT id,payload FROM strategy_jobs WHERE json_extract(payload,'$.mode')='exchange' "
                        "AND json_extract(payload,'$.status')='running'"
                    ).fetchall():
                        job = json.loads(row["payload"])
                        job.update(
                            status="paused", error=HALT_MESSAGE, updated_at=timestamp, halt_revision=revision
                        )
                        event = self.runner.host._event(job, "PAUSE", HALT_MESSAGE, control_revision=revision)
                        db.execute(
                            "UPDATE strategy_jobs SET payload=? WHERE id=?", (json.dumps(job), row["id"])
                        )
                        db.execute(
                            "INSERT INTO strategy_events(job_id,payload) VALUES(?,?)",
                            (row["id"], json.dumps(event)),
                        )
                        paused.append(row["id"])
                    # Unsent signal intents acquire no authority from a later release.
                    for row in db.execute(
                        "SELECT id,payload FROM exchange_orders WHERE json_extract(payload,'$.origin')='strategy' "
                        "AND json_extract(payload,'$.status')='preview' "
                        "AND json_extract(payload,'$.strategy_close_review_id') IS NULL"
                    ).fetchall():
                        intent = json.loads(row["payload"])
                        intent.update(strategy_abandoned=True, tracking=False)
                        self.runner.trading.lifecycle.write(db, intent)
                audit = {
                    **state,
                    "action": request.action,
                    "paused_job_ids": paused,
                    "paused_count": len(paused),
                }
                db.execute("UPDATE strategy_execution_control SET payload=? WHERE id=1", (json.dumps(state),))
                db.execute("INSERT INTO strategy_control_events VALUES(?,?)", (revision, json.dumps(audit)))
                db.execute(
                    "DELETE FROM strategy_control_events WHERE revision NOT IN "
                    "(SELECT revision FROM strategy_control_events ORDER BY revision DESC LIMIT 200)"
                )
        return self.state()
