"""Run saved research with Sibyl's existing native coordinator and specialist team.

Only report admission and UI persistence live here. ProtoLink owns discovery,
delegation, model calls, budgets, cancellation, sessions and full run evidence.
Each rerun uses a fresh conversation and the team configuration frozen at acceptance.
"""

import asyncio
import json

from protolink import request_context
from pydantic import ValidationError

from sibyl.agents.utils.common import freeze
from sibyl.agents.utils.conversations import SibylRequest
from sibyl.agents.utils.network import ModelRequired
from sibyl.agents.utils.requests import now
from sibyl.investigations.contracts import InvestigationReport
from sibyl.investigations.evidence import report_sources, validate_references
from sibyl.investigations.repository import ACTIVE, InvestigationConflict, InvestigationRepository

REPORT_INSTRUCTIONS = (
    "Produce a saved research report for this question. Use the relevant discovered specialists and "
    "their read-only evidence tools. Distinguish observations from interpretation. Disclose missing, "
    "Demo, test, paper and stale data. Starting selections below are defaults, not evidence or permissions. "
    "Return ONLY a JSON object: summary (text), findings (list of {title, detail, sources}), "
    "uncertainties (list of text), next_questions (list of text). Each finding's sources must name "
    "actually completed evidence tools as agent_id.tool_name, for example analyst.market_analysis or "
    "reporter.news_briefing. Use [] for an interpretation with no supporting tool receipt; never invent "
    "citations. Keep lists short. Do not include credentials or claim unperformed actions."
)


class Investigations:
    """Own bounded report requests that survive closing the browser, never restart replay."""

    def __init__(self, store, network):
        self.network = network
        self.repository = InvestigationRepository(store)
        self.repository.recover()
        self._tasks: dict[str, asyncio.Task] = {}
        self._closing = False

    async def start(self, identity, request, *, origin="manual", configuration=None):
        """Accept one idempotent run and freeze all team models before it waits for a slot."""
        definition = self.repository.get(identity)
        try:
            return self.detail(identity, request.request_id)
        except LookupError:
            pass
        if self._closing:
            raise InvestigationConflict("The application is shutting down.")
        configuration = freeze(configuration or self.network.owner.models.for_turn("sibyl"))
        status = self.network.status(configuration)
        if not status["ready"]:
            raise ModelRequired(status["reason"])
        context = {**definition["context"]}
        context["market_source"] = context["market_source"] or self.network.owner.services.market.source
        context["news_mode"] = (
            context["news_mode"] or self.network.owner.services.research.news_service.default_mode
        )
        models = {
            agent: {
                "provider": config["provider"],
                "model": config["model"],
                "selection": configuration["_selections"].get(agent, "default"),
            }
            for agent, config in configuration["_agents"].items()
        }
        run, created = self.repository.reserve(identity, request.request_id, context, models, origin)
        if created:
            self._tasks[run["id"]] = asyncio.create_task(self._run(definition, run, configuration))
        return run

    async def _run(self, definition, run, configuration):
        """Project one native request into an immutable report or an explicit terminal outcome."""
        identity, run_id = run["investigation_id"], run["id"]
        try:
            session = self.network.conversations.create(f"Investigation: {definition['title']}")["id"]
            self.repository.update(identity, run_id, status="running", session_id=session)
            instructions = (
                f"{REPORT_INSTRUCTIONS}\nStarting selections: {json.dumps(run['context'])}\nQuestion: "
            )
            with request_context(
                {
                    "page": freeze(run["context"]),
                    "response_schema": InvestigationReport.model_json_schema(),
                    "response_instructions": instructions,
                    "investigation_id": identity,
                }
            ):
                answer = await self.network.ask(
                    SibylRequest(message=run["question"], session_id=session, request_id=run_id),
                    configuration=configuration,
                )
            if answer.get("status") == "cancelled":
                self._finish(identity, run_id, "cancelled")
                return
            self.repository.update(identity, run_id, native_run_id=answer["run_id"])
            report = InvestigationReport.model_validate_json(answer["answer"])
            native = self.network.run_store.get_report(answer["run_id"])
            sources = report_sources(native)
            validate_references(report, sources)
            self.repository.update(
                identity,
                run_id,
                status="completed",
                finished_at=now(),
                report=report.model_dump(),
                sources=sources,
            )
        except asyncio.CancelledError:
            self._finish(identity, run_id, "interrupted" if self._closing else "cancelled")
            raise
        except (ValidationError, ValueError):
            self._finish(
                identity,
                run_id,
                "failed",
                "Sibyl did not return a valid structured report with recorded source references. Review the conversation or rerun with another model.",
            )
        except Exception:
            self._finish(
                identity,
                run_id,
                "failed",
                "The investigation could not finish. Check the model and data sources before rerunning.",
            )
        finally:
            self._tasks.pop(run_id, None)

    def _finish(self, identity, run_id, status, error=None):
        """Retain completed observations even when the model fails or the user stops it."""
        run = self.repository.run(identity, run_id)
        patch = {"status": status, "finished_at": now(), "error": error}
        if run["session_id"]:
            try:
                attempt = self.network.requests.get(run["session_id"], run_id)
                if attempt.get("run_id"):
                    native = self.network.run_store.get_report(attempt["run_id"])
                    patch.update(native_run_id=attempt["run_id"], sources=report_sources(native))
            except LookupError:
                pass
        self.repository.update(identity, run_id, **patch)

    def detail(self, identity, run_id):
        """Read a report and lightweight native progress without another model call."""
        run = self.repository.run(identity, run_id)
        try:
            run["activity"] = self.network.activity(run["session_id"]) if run["session_id"] else None
        except LookupError:
            run["activity"] = None
        return run

    async def cancel(self, identity, run_id):
        """Stop this exact version; completed reports and previous versions stay unchanged."""
        run = self.repository.run(identity, run_id)
        if run["status"] == "cancelled":
            return self.detail(identity, run_id)
        if run["status"] not in ACTIVE or run_id not in self._tasks:
            raise InvestigationConflict("This report is no longer running.")
        task = self._tasks[run_id]
        self.repository.update(identity, run_id, status="cancelling")
        if run["session_id"]:
            try:
                await self.network.cancel(run["session_id"], run_id)
            except ValueError:
                task.cancel()
        else:
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        # A task cancelled before its coroutine starts does not execute its finally block.
        self.repository.update(identity, run_id, status="cancelled", finished_at=now())
        self._tasks.pop(run_id, None)
        return self.detail(identity, run_id)

    async def close(self):
        """Drain accepted requests before the application's native AgentGroup shuts down."""
        self._closing = True
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.repository.recover()
        self._tasks.clear()
