"""Observe real worker iterations without manufacturing heartbeat activity."""

import asyncio
import inspect
import threading
import time
from datetime import UTC, datetime

from sibyl.operations.resources import ProcessResources


def timestamp():
    return datetime.now(UTC).isoformat()


class WorkerHealth:
    """Supervise local tasks and expose bounded, credential-free operational evidence.

    Unexpected failures stop that worker rather than blindly retrying potentially
    side-effecting work. Explicit retry classes preserve existing storage-retry
    behavior. Stale state is derived from actual start/finish times, not a separate
    heartbeat timer. This is process-local observation, not an uptime guarantee.
    """

    def __init__(self, store, *, clock=time.monotonic):
        self.store, self.clock = store, clock
        from sibyl.operations.diagnostics import WorkspaceDiagnostics

        self.diagnostics = WorkspaceDiagnostics(store, self)
        self.workers, self.tasks = {}, []
        self.inflight = set()
        self.recovery_required = False
        self.lock = threading.RLock()
        self.started_at = timestamp()
        self.resources = ProcessResources(store)
        with store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS worker_events (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,kind TEXT NOT NULL,at TEXT NOT NULL,error TEXT)"
            )

    def _event(self, name, kind, error=None):
        try:
            with self.store.db() as db:
                db.execute(
                    "INSERT INTO worker_events(name,kind,at,error) VALUES(?,?,?,?)",
                    (name, kind, timestamp(), error),
                )
                db.execute(
                    "DELETE FROM worker_events WHERE id NOT IN (SELECT id FROM worker_events ORDER BY id DESC LIMIT 200)"
                )
        except Exception:
            pass  # A failed diagnostics write must not change a domain operation's outcome.

    def start(self, name, label, action, *, interval=1, deadline=60, retryable=(), paused=False):
        """Start a periodic action; elapsed deadlines describe stalls and never cancel a native write."""
        row = {
            "id": name,
            "label": label,
            "state": "paused" if paused else "starting",
            "interval_seconds": interval,
            "deadline_seconds": deadline,
            "last_started_at": None,
            "last_finished_at": None,
            "last_duration_seconds": None,
            "iterations": 0,
            "failures": 0,
            "last_error": None,
            "since": self.clock(),
            "next_due": self.clock(),
        }
        self.workers[name] = row
        if not paused:
            self.tasks.append(
                asyncio.create_task(self._periodic(name, action, retryable), name=f"sibyl-{name}")
            )

    async def _offload(self, action, *args):
        """Track threads through caller cancellation so shutdown can drain them."""
        work = asyncio.create_task(asyncio.to_thread(action, *args))
        self.inflight.add(work)

        def settled(task):
            self.inflight.discard(task)
            if not task.cancelled():
                task.exception()

        work.add_done_callback(settled)
        return await asyncio.shield(work)

    async def _periodic(self, name, action, retryable):
        row = self.workers[name]
        try:
            while True:
                with self.lock:
                    row.update(state="running", since=self.clock(), last_started_at=timestamp())
                try:
                    if inspect.iscoroutinefunction(action):
                        await action()
                    else:
                        await self._offload(action)
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    code = type(error).__name__[:80]
                    with self.lock:
                        row.update(
                            state="retrying" if isinstance(error, retryable) else "failed",
                            failures=row["failures"] + 1,
                            last_error=code,
                            last_finished_at=timestamp(),
                            last_duration_seconds=round(self.clock() - row["since"], 3),
                        )
                    await self._offload(self._event, name, row["state"], code)
                    if not isinstance(error, retryable):
                        return
                else:
                    if row["last_error"]:
                        await self._offload(self._event, name, "recovered")
                    with self.lock:
                        row.update(
                            state="waiting",
                            iterations=row["iterations"] + 1,
                            last_error=None,
                            last_finished_at=timestamp(),
                            last_duration_seconds=round(self.clock() - row["since"], 3),
                        )
                with self.lock:
                    row["next_due"] = self.clock() + row["interval_seconds"]
                await asyncio.sleep(row["interval_seconds"])
        finally:
            if row["state"] != "failed":
                row["state"] = "stopped"

    def snapshot(self):
        """Report current progress plus retained fault transitions; never expose exception messages."""
        now = self.clock()
        with self.lock:
            rows = []
            for row in self.workers.values():
                item = {k: v for k, v in row.items() if k not in {"since", "next_due"}}
                if row["state"] == "running" and now - row["since"] > row["deadline_seconds"]:
                    item["state"] = "stalled"
                elif row["state"] in {"waiting", "retrying", "starting"} and now - row["next_due"] > max(
                    10, row["interval_seconds"] * 2
                ):
                    item["state"] = "overdue"
                item["elapsed_seconds"] = (
                    round(max(0, now - row["since"]), 1) if row["state"] == "running" else None
                )
                rows.append(item)
        issues = sum(row["state"] in {"failed", "stalled", "overdue", "retrying", "stopped"} for row in rows)
        with self.store.db() as db:
            events = [
                dict(row) for row in db.execute("SELECT * FROM worker_events ORDER BY id DESC LIMIT 30")
            ]
        return {
            "status": "attention"
            if issues
            else "paused"
            if rows and all(r["state"] == "paused" for r in rows)
            else "observed",
            "issue_count": issues,
            "resources": self.resources.snapshot(),
            "started_at": self.started_at,
            "observed_at": timestamp(),
            "workers": rows,
            "events": events,
            "scope": "Current-process progress. Counters reset on restart; bounded fault history is retained. Healthy ticks do not prove provider access or completed trades. Restart to recover a failed worker after reviewing its domain state.",
        }

    async def close(self):
        """Cancel and drain supervised tasks; domain services retain ownership of their outstanding threads."""
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await asyncio.gather(*tuple(self.inflight), return_exceptions=True)
