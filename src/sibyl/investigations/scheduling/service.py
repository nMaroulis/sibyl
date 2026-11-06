"""Calendar admission, read-only investigation runs and explicit Telegram handoff.

ProtoLink continues to own the complete AI run. This service owns only calendar
policies, missed occurrences, the private accepted model snapshot and delivery
authorization. No model or Telegram provider is contacted by saving a schedule.
"""

import asyncio
from datetime import UTC, datetime

from sibyl.agents.utils.common import freeze
from sibyl.agents.utils.network import ModelRequired
from sibyl.investigations.contracts import InvestigationRun
from sibyl.investigations.repository import ACTIVE as ACTIVE_REPORTS
from sibyl.investigations.repository import InvestigationConflict
from sibyl.investigations.scheduling.delivery import briefing_text
from sibyl.investigations.scheduling.repository import BriefingConflict, BriefingRepository


class BriefingScheduler:
    """Operate one local bounded queue without replaying inference after a restart."""

    def __init__(self, investigations, messaging, clock=None):
        self.investigations, self.messaging = investigations, messaging
        self.store = investigations.repository.store
        self.repository = BriefingRepository(self.store)
        self.clock = clock or (lambda: datetime.now(UTC))
        self._models: dict[str, tuple[str, object]] = {}
        self._tick_lock = asyncio.Lock()
        self._closed = False
        self.last_tick = None
        self.messaging.notifications.authorizers["briefing"] = self.delivery_allowed
        self._recover()

    def _recover(self):
        """Reconnect accepted report identities; never reconstruct private queued model settings."""
        now = self.clock()
        for occurrence in [*self.repository.occurrences("waiting"), *self.repository.occurrences("running")]:
            try:
                self.investigations.repository.run(occurrence["investigation_id"], occurrence["id"])
            except LookupError:
                self.repository.update(
                    occurrence["id"],
                    status="interrupted",
                    finished_at=now.isoformat(),
                    error="The backend stopped before this briefing was accepted. No inference was replayed.",
                )
            else:
                self.repository.update(occurrence["id"], status="running", run_id=occurrence["id"])
        while self.repository.claim_due(now, startup=True) is not None:
            pass

    def _binding(self, body):
        if not body.telegram:
            return None
        profile = self.messaging.settings.profile()
        if not profile.get("verified") or not profile.get("bot_token") or not profile.get("bot_id"):
            raise BriefingConflict(
                "Save and check your Telegram bot in Settings → Messaging before selecting delivery."
            )
        if (
            profile["bot_id"] != body.telegram_target.bot_id
            or profile["allowed_user_id"] != body.telegram_target.user_id
        ):
            raise BriefingConflict(
                "Telegram changed while this form was open. Review the current bot and private user before saving delivery."
            )
        return {
            "bot_id": profile["bot_id"],
            "recipient_id": profile["allowed_user_id"],
            "bot_username": profile.get("bot_username", ""),
        }

    def create(self, investigation_id, body):
        """Save a future calendar, with optional delivery bound to the reviewed private recipient."""
        self.investigations.repository.get(investigation_id)
        return self.repository.create(investigation_id, body, self._binding(body), self.clock())

    def edit(self, identity, body):
        """Review changed calendars/recipients; cancel waiting work and unsent old deliveries."""
        schedule = self.repository.edit(identity, body, self._binding(body), self.clock())
        self._withdraw(identity)
        return schedule

    def change(self, identity, body):
        """Pause/resume/archive future work; an admitted report is stopped in Investigations."""
        original = self.repository.get(identity)
        if body.action == "resume":
            old = self.repository.get(identity)
            profile = self.messaging.settings.profile()
            binding = old.get("telegram_binding") or {}
            if old["telegram"] and (
                not profile.get("verified")
                or profile.get("bot_id") != binding.get("bot_id")
                or profile.get("allowed_user_id") != binding.get("recipient_id")
            ):
                raise BriefingConflict(
                    "Telegram changed. Edit and review delivery before resuming this schedule."
                )
        schedule = self.repository.change(identity, body, self.clock())
        if schedule["revision"] != original["revision"]:
            self._withdraw(identity)
        return schedule

    def _withdraw(self, identity):
        for occurrence_id, (schedule_id, _) in list(self._models.items()):
            if schedule_id == identity:
                self._models.pop(occurrence_id, None)
        self.messaging.notifications.invalidate(
            schedule_id=identity, reason="The briefing schedule changed before delivery."
        )

    def require_deletable(self, investigation_id):
        """Prevent an investigation from disappearing under an armed or paused calendar."""
        if self.repository.list(investigation_id):
            raise BriefingConflict("Archive this investigation's schedule before deleting its reports.")

    def _capture(self, occurrence):
        if occurrence["status"] == "waiting" and occurrence["id"] not in self._models:
            configuration = freeze(self.investigations.network.owner.models.for_turn("sibyl"))
            self._models[occurrence["id"]] = (occurrence["schedule_id"], configuration)

    async def run_now(self, identity, body):
        """Explicitly request one additional briefing; leave the calendar time unchanged."""
        if self._closed:
            raise BriefingConflict("The scheduler is shutting down.")
        occurrence = self.repository.run_now(identity, body, self.clock())
        self._capture(occurrence)
        return occurrence

    def _trim(self, schedule):
        removed = self.investigations.repository.prune_scheduled(
            schedule["investigation_id"], schedule["id"], schedule["keep_reports"] - 1
        )
        for run in removed:
            session = run.get("session_id")
            if not session:
                continue
            with self.store.db() as db:
                turns = db.execute(
                    "SELECT COUNT(*) FROM sibyl_turns WHERE session_id=?", (session,)
                ).fetchone()[0]
            if turns == 1:
                with self.store.db() as db:
                    requests = db.execute(
                        "SELECT COUNT(*) FROM sibyl_requests WHERE session_id=?", (session,)
                    ).fetchone()[0]
                if requests != 1:
                    continue
                try:
                    self.investigations.network.delete_conversation(session)
                except (LookupError, ValueError):
                    # A conversation continued by the user is never removed by retention.
                    pass

    async def _admit(self, occurrence, now):
        accepted = self._models.get(occurrence["id"])
        if accepted is None:
            self.repository.update(
                occurrence["id"],
                status="interrupted",
                finished_at=now.isoformat(),
                error="The accepted model snapshot is unavailable. Run the briefing again explicitly.",
            )
            return
        schedule = self.repository.admit(occurrence["id"], now)
        if schedule is None:
            return
        try:
            configuration = accepted[1]
            readiness = self.investigations.network.status(configuration)
            if not readiness["ready"]:
                raise ModelRequired(readiness["reason"])
            self._trim(schedule)
            run = await self.investigations.start(
                schedule["investigation_id"],
                InvestigationRun(request_id=occurrence["id"]),
                origin=f"schedule:{schedule['id']}",
                configuration=configuration,
            )
            self.repository.update(occurrence["id"], status="running", run_id=run["id"], error=None)
            self._models.pop(occurrence["id"], None)
        except InvestigationConflict as exc:
            self.repository.update(
                occurrence["id"],
                status="waiting",
                next_attempt=now.timestamp() + 5,
                error=str(exc),
            )
        except ModelRequired:
            self.repository.update(
                occurrence["id"],
                status="blocked",
                finished_at=now.isoformat(),
                error="The accepted AI model is not configured. Review Settings → AI models, then run explicitly or wait for the next scheduled time.",
            )
            self._models.pop(occurrence["id"], None)
        except LookupError:
            self.repository.update(
                occurrence["id"],
                status="interrupted",
                finished_at=now.isoformat(),
                error="The investigation was removed before report admission.",
            )
            self._models.pop(occurrence["id"], None)

    def _observe(self, occurrence, now):
        try:
            run = self.investigations.repository.run(
                occurrence["investigation_id"], occurrence["run_id"] or occurrence["id"]
            )
        except LookupError:
            self.repository.update(
                occurrence["id"],
                status="interrupted",
                finished_at=now.isoformat(),
                error="The report is no longer available.",
            )
            return
        if run["status"] in ACTIVE_REPORTS:
            return
        delivery_id, delivery_error = None, None
        schedule = self.repository.get(occurrence["schedule_id"])
        if run["status"] == "completed" and occurrence.get("telegram_requested"):
            if (
                not schedule["telegram"]
                or schedule["revision"] != occurrence["schedule_revision"]
                or schedule["status"] != "armed"
            ):
                delivery_error = "The schedule changed before this report finished. No delivery was queued."
            else:
                definition = self.investigations.repository.get(run["investigation_id"])
                delivery = self.messaging.notifications.enqueue(
                    occurrence["id"],
                    schedule,
                    run,
                    briefing_text(
                        definition["title"],
                        run,
                        schedule["delivery_format"],
                        document=schedule.get("telegram_format") == "document",
                    ),
                    now,
                )
                delivery_id = delivery["id"]
        self.repository.update(
            occurrence["id"],
            status=run["status"],
            finished_at=now.isoformat(),
            error=run.get("error"),
            delivery_id=delivery_id,
            delivery_error=delivery_error,
        )

    def delivery_allowed(self, delivery):
        """Fence each send against policy edits and deleted/pruned report versions."""
        try:
            schedule = self.repository.get(delivery["schedule_id"])
            run = self.investigations.repository.run(delivery["investigation_id"], delivery["run_id"])
        except LookupError:
            return False
        binding = schedule.get("telegram_binding") or {}
        return (
            schedule["status"] == "armed"
            and schedule["telegram"]
            and schedule["revision"] == delivery["schedule_revision"]
            and binding.get("bot_id") == delivery["bot_id"]
            and binding.get("recipient_id") == delivery["recipient_id"]
            and run["status"] == "completed"
        )

    def detail(self, identity):
        """Read a calendar and actual report/delivery outcomes without submitting work."""
        schedule = self.repository.get(identity)
        occurrences = self.repository.history(identity)
        with self.store.db() as db:
            available = {
                row[0]
                for row in db.execute(
                    "SELECT id FROM investigation_runs WHERE investigation_id=?",
                    (schedule["investigation_id"],),
                )
            }
        for occurrence in occurrences:
            occurrence["report_available"] = occurrence.get("run_id") in available
            try:
                occurrence["delivery"] = (
                    self.messaging.notifications.get(occurrence["delivery_id"])
                    if occurrence.get("delivery_id")
                    else None
                )
            except LookupError:
                occurrence["delivery"] = None
                occurrence["delivery_error"] = "This delivery receipt is outside its retained history window."
        return {**schedule, "occurrences": occurrences}

    async def tick(self):
        """Observe bounded local state, claim one due time and admit one queued report."""
        async with self._tick_lock:
            if self._closed:
                return
            now = self.clock()
            for occurrence in self.repository.occurrences("running"):
                self._observe(occurrence, now)
            occurrence = self.repository.claim_due(now)
            if occurrence is not None:
                self._capture(occurrence)
            for waiting in self.repository.occurrences("waiting"):
                if waiting["next_attempt"] <= now.timestamp():
                    await self._admit(waiting, now)
                    break
            active = {row["id"] for row in self.repository.occurrences("waiting")}
            self._models = {key: value for key, value in self._models.items() if key in active}
            self.last_tick = now.isoformat()

    async def close(self):
        """Stop future calendar admission; Investigations drains already accepted native work."""
        self._closed = True
        self._models.clear()
