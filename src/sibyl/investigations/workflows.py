"""Thin application controls over native ProtoLink durable research execution.

ProtoLink owns checkpoints, leases, action receipts, questions, approvals, context
and cumulative budgets. Sibyl persists only its existing report projection and
an encrypted private model snapshot, so a continuation keeps the accepted team.
No private dependency is copied into a Task or serialized RunContext metadata.
"""

import asyncio
from collections.abc import Mapping

from protolink import (
    ActionDeniedError,
    AgentGroup,
    ContextPolicy,
    GroupLimits,
    RedactionPolicy,
    RunBudget,
    RunManager,
    RunReport,
    SQLiteDurableStore,
    Task,
    request_context,
)
from protolink.storage.durable import DurableExecutionError

from sibyl.agents.sibyl import create_workflow_agent
from sibyl.agents.utils.common import freeze
from sibyl.agents.utils.network import ModelRequired
from sibyl.agents.utils.requests import now
from sibyl.investigations.contracts import InvestigationReport
from sibyl.investigations.evidence import report_sources, validate_references
from sibyl.investigations.repository import ACTIVE, InvestigationConflict

EXECUTION_VERSION = "research-workflow-1"


def thaw(value):
    """Copy immutable application selections into the encrypted local profile only."""
    if isinstance(value, Mapping):
        return {key: thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [thaw(item) for item in value]
    return value


def redaction(configuration):
    """Native report/management redaction; model credentials remain private dependencies."""
    return RedactionPolicy(
        sensitive_values=frozenset(
            row["api_key"] for row in configuration.get("_agents", {}).values() if row.get("api_key")
        ),
        max_string_length=12000,
    )


class ResearchWorkflows:
    """Own the durable Sibyl variant while the existing network owns its specialists."""

    def __init__(self, owner):
        self.owner, self.network, self.repository = owner, owner.network, owner.repository
        self.store = self.repository.store
        self.path = self.store.path.parent / "investigation-checkpoints.sqlite"
        self.checkpoints = SQLiteDurableStore(self.path)
        self.path.chmod(0o600)
        network = self.network
        self.agent = create_workflow_agent(
            network.owner.services.library,
            transport="runtime",
            url=network.namespace + "/research-workflow",
            subagents=list(network.owner.agents.values()),
            llm_factory=lambda: network.owner.model_for("sibyl"),
            sync_execution="thread",
            max_sync_workers=4,
            expose_tool_results=True,
            durability=self.checkpoints,
            execution_version=EXECUTION_VERSION,
            yield_after_steps=3,
            run_store=network.run_store,
            context_policy=ContextPolicy(preserve_recent=6),
            verbosity=0,
            expose_chat=False,
        )
        self.group = AgentGroup(
            [self.agent],
            external_agents=list(network.owner.agents.values()),
            limits=GroupLimits(max_concurrent_runs=2, max_queued_runs=4, queue_timeout=30),
            event_buffer_size=4096,
            max_retained_runs=20,
        )
        self.tasks = {}
        self.closing = False

    async def start(self):
        """Start the native coordinator without creating or contacting any model."""
        await self.group.start()
        self.recover()

    def _snapshot(self, run):
        profile = self.store.data_profile("workflow-models:" + run["id"])
        if not profile.get("models"):
            raise InvestigationConflict(
                "The private model snapshot is no longer available. Start a new investigation version."
            )
        return freeze(profile["models"])

    def _clear_snapshot(self, run_id):
        self.store.save_data_profile("workflow-models:" + run_id, {})

    def recover(self):
        """Expose native continuation boundaries after restart, never replay inference."""
        with self.store.db() as db:
            rows = db.execute(
                "SELECT payload FROM investigation_runs WHERE COALESCE(json_extract(payload,'$.durable'),0)=1 AND status IN ('queued','running','cancelling','input_required')"
            ).fetchall()
        import json

        for record in rows:
            run = json.loads(record[0])
            checkpoint = (
                self.checkpoints.get(run.get("native_run_id", "")) if run.get("native_run_id") else None
            )
            if checkpoint is None:
                self.repository.update(
                    run["investigation_id"],
                    run["id"],
                    status="interrupted",
                    finished_at=now(),
                    error="No committed native checkpoint was retained. Start a new version explicitly.",
                )
                self._clear_snapshot(run["id"])
            elif checkpoint.status == "completed":
                self._finish_task(run, Task.from_dict(checkpoint.data["task"]))
                self._clear_snapshot(run["id"])
            elif checkpoint.status in {"failed", "canceled"}:
                self.repository.update(
                    run["investigation_id"],
                    run["id"],
                    status="cancelled" if checkpoint.status == "canceled" else "failed",
                    finished_at=now(),
                    error="The retained native execution is terminal and is not replayed.",
                )
                self._clear_snapshot(run["id"])
            else:
                self.repository.update(
                    run["investigation_id"],
                    run["id"],
                    status="input_required",
                    error="Native progress was retained. Inspect and continue explicitly; uncertain actions cannot be replayed.",
                )

    def launch(self, definition, run, configuration, instructions):
        """Freeze credentials privately, then submit one ordinary native group run."""
        if self.closing:
            raise InvestigationConflict("The application is shutting down.")
        self.store.save_data_profile("workflow-models:" + run["id"], {"models": thaw(configuration)})
        run = self.repository.update(run["investigation_id"], run["id"], durable=True)
        self.tasks[run["id"]] = asyncio.create_task(self._execute(run, instructions=instructions))
        return run

    def inspect(self, run):
        """Return the native bounded management view, never raw checkpoint task/history."""
        identity = run.get("native_run_id")
        if not identity:
            return None
        configuration = self._snapshot(run) if run["status"] in ACTIVE else {}
        try:
            return RunManager(self.agent, redaction_policy=redaction(configuration)).inspect(identity)
        except DurableExecutionError:
            return {
                "status": "incompatible",
                "run_id": identity,
                "interruption": None,
                "uncertain_actions": [],
                "message": "The native checkpoint does not match this application contract. Start a new version; it will not be silently replayed.",
            }

    async def resume(self, identity, run_id, body):
        """Resume the exact pending native question/approval/handoff, preserving frozen models."""
        run = self.repository.run(identity, run_id)
        if not run.get("durable"):
            raise InvestigationConflict("This version was not started with native checkpoints.")
        if run["status"] == "completed":
            return self.owner.detail(identity, run_id)
        if self.closing or run["status"] != "input_required" or run_id in self.tasks:
            raise InvestigationConflict("This workflow is not waiting for continuation.")
        configuration = self._snapshot(run)
        status = self.network.status(configuration)
        if not status["ready"]:
            raise ModelRequired(status["reason"])
        try:
            pending = RunManager(self.agent, redaction_policy=redaction(configuration)).inspect(
                run["native_run_id"]
            )
        except DurableExecutionError:
            raise InvestigationConflict(
                "The native checkpoint no longer matches this application contract. Start a new version; no action was replayed."
            ) from None
        interruption = pending.get("interruption")
        if interruption:
            if (
                body.request_id != interruption["request_id"]
                or body.fingerprint != interruption["fingerprint"]
            ):
                raise InvestigationConflict(
                    "The native request changed. Refresh its current question or approval."
                )
            expected = {"input": {"answer"}, "approval": {"approve", "reject"}, "yield": {"continue"}}
            if body.kind not in expected.get(interruption["kind"], set()):
                raise InvestigationConflict("Choose the response matching the pending native request.")
        elif body.kind != "continue":
            raise InvestigationConflict("This checkpoint has no pending question or approval.")
        if body.kind == "answer" and (not body.answer or not body.answer.strip()):
            raise InvestigationConflict("Write an answer to the native question.")
        response = {}
        if body.kind in {"approve", "reject", "answer"}:
            response = {"request_id": body.request_id, "fingerprint": body.fingerprint}
            if body.kind == "answer":
                response["answer"] = body.answer
            else:
                response["approved"] = body.kind == "approve"
        self.repository.update(identity, run_id, status="running", error=None)
        self.tasks[run_id] = asyncio.create_task(self._execute(run, response=response))
        return self.owner.detail(identity, run_id)

    async def _execute(self, run, *, instructions=None, response=None):
        """Delegate all execution/resumption to native Group/RunManager APIs."""
        handle = None
        identity, run_id = run["investigation_id"], run["id"]
        try:
            configuration = self._snapshot(run)
            with request_context(
                {"models": configuration, "page": freeze(run["context"])}, inherit=("models", "page")
            ):
                if instructions is not None:
                    self.repository.update(identity, run_id, status="running", error=None)
                    task = Task.create_infer(
                        instructions + run["question"],
                        session_id="investigation:" + run_id,
                        output_schema=InvestigationReport.model_json_schema(),
                        budget=RunBudget(
                            max_steps=24, max_llm_calls=20, max_tool_calls=20, max_runtime_seconds=1200
                        ),
                    )
                    handle = self.group.run(
                        self.agent,
                        task,
                        request_id="investigation:" + run_id,
                        redaction_policy=redaction(configuration),
                    )
                    run = self.repository.update(identity, run_id, native_run_id=handle.context.run_id)
                    result = await handle.result()
                    if result.task is None:
                        raise ValueError("Native execution did not retain a final task.")
                    task = result.task
                else:
                    result = await RunManager(self.agent, redaction_policy=redaction(configuration)).resume(
                        run["native_run_id"], **(response or {})
                    )
                    checkpoint = self.checkpoints.get(run["native_run_id"])
                    if checkpoint is None:
                        raise ValueError("The native continuation checkpoint is missing.")
                    # RunManager returns a bounded management projection; the
                    # trusted native checkpoint retains the complete final Task.
                    task = Task.from_dict(checkpoint.data["task"])
            if task.state.value == "input-required":
                self.repository.update(identity, run_id, status="input_required", error=None)
            elif response and response.get("approved") is False and task.state.value == "failed":
                self.repository.update(
                    identity,
                    run_id,
                    status="cancelled",
                    finished_at=now(),
                    error="The local note approval was declined. Native policy stopped this execution.",
                )
            else:
                self._finish_task(run, task)
        except asyncio.CancelledError:
            if handle:
                await handle.cancel("Research workflow caller stopped")
                await handle.result()
            checkpoint = (
                self.checkpoints.get(run.get("native_run_id", "")) if run.get("native_run_id") else None
            )
            # A native ready/uncertain boundary may survive shutdown. Explicit Stop
            # stays terminal in the app; shutdown never automatically continues it.
            self.repository.update(
                identity,
                run_id,
                status="input_required"
                if self.closing and checkpoint and checkpoint.status not in {"canceled", "failed"}
                else "interrupted"
                if self.closing
                else "cancelled",
                error="The application stopped. Inspect the native checkpoint before continuing."
                if self.closing
                else None,
                finished_at=None if self.closing else now(),
            )
            raise
        except ActionDeniedError:
            self.repository.update(
                identity,
                run_id,
                status="cancelled" if response and response.get("approved") is False else "failed",
                finished_at=now(),
                error="Native policy declined the requested action. No further research was executed.",
            )
        except Exception:
            current = self.repository.run(identity, run_id)
            try:
                view = self.inspect(current)
            except (ValueError, LookupError):
                view = None
            waiting = view and view.get("status") not in {"completed", "failed", "canceled", "incompatible"}
            self.repository.update(
                identity,
                run_id,
                status="input_required" if waiting else "failed",
                error="The native workflow could not complete. Inspect its checkpoint, model readiness and any uncertain action before continuing.",
                finished_at=None if waiting else now(),
            )
        finally:
            self.tasks.pop(run_id, None)
            current = self.repository.run(identity, run_id)
            if current["status"] not in ACTIVE:
                self._clear_snapshot(run_id)

    def _finish_task(self, run, task):
        identity, run_id = run["investigation_id"], run["id"]
        if task.state.value != "completed":
            self.repository.update(
                identity,
                run_id,
                status="cancelled" if task.state.value == "canceled" else "failed",
                finished_at=now(),
                error="The native research execution did not complete. Its observed evidence remains retained.",
            )
            return
        output = task.get_output()
        report = (
            InvestigationReport.model_validate(output)
            if isinstance(output, dict)
            else InvestigationReport.model_validate_json(output)
        )
        # save_task and the first live handle's report are separate SDK stores.
        # Derive the authoritative cumulative report from the final native Task.
        native = RunReport.from_task(task)
        native = RunReport.from_dict(native.to_dict(redaction_policy=redaction(self._snapshot(run))))
        self.network.run_store.save_report(native)
        sources = report_sources(native)
        validate_references(report, sources)
        self.repository.update(
            identity,
            run_id,
            status="completed",
            finished_at=now(),
            report=report.model_dump(),
            sources=sources,
            error=None,
        )

    def verify_note(self, identity, run_id, action_id):
        """Reconcile only an actually retained exact-content note through native receipts."""
        from sibyl.research_library.notes import ResearchNotes

        run = self.repository.run(identity, run_id)
        if not run.get("durable") or run["status"] != "input_required" or run_id in self.tasks:
            raise InvestigationConflict("Inspect a stopped native workflow before verifying a note.")
        manager = RunManager(self.agent, redaction_policy=redaction(self._snapshot(run)))
        view = manager.inspect(run["native_run_id"])
        if not any(
            item["action_id"] == action_id and item["name"] == "save_research_note"
            for item in view["uncertain_actions"]
        ):
            raise InvestigationConflict("This is not an uncertain local research-note action.")
        checkpoint = self.checkpoints.get(run["native_run_id"])
        entry = next(
            (
                item
                for item in checkpoint.data["actions"].values()
                if item["action"]["action_id"] == action_id
            ),
            None,
        )
        if not entry:
            raise InvestigationConflict("The native action changed. Refresh its current state.")
        arguments = entry["action"]["payload"]["arguments"]
        result = ResearchNotes(self.network.owner.services.library).observed(
            arguments["title"], arguments["text"]
        )
        if result is None:
            raise InvestigationConflict(
                "No exact matching local note is retained. The original write outcome remains unknown; it will not be replayed."
            )
        try:
            manager.reconcile(run["native_run_id"], action_id, result=result)
        except DurableExecutionError:
            raise InvestigationConflict(
                "The native action is still owned or no longer matches this observation. Refresh before continuing."
            ) from None
        self.repository.update(identity, run_id, error=None)
        return self.owner.detail(identity, run_id)

    async def cancel(self, identity, run_id):
        run = self.repository.run(identity, run_id)
        if run["status"] not in ACTIVE:
            return self.owner.detail(identity, run_id)
        task = self.tasks.get(run_id)
        if task:
            self.repository.update(identity, run_id, status="cancelling")
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self.tasks.pop(run_id, None)
        elif run.get("native_run_id"):
            try:
                RunManager(self.agent, redaction_policy=redaction(self._snapshot(run))).cancel(
                    run["native_run_id"]
                )
            except DurableExecutionError as error:
                raise InvestigationConflict(
                    "Native cancellation requires an unambiguous matching checkpoint. Inspect/reconcile any uncertain action first."
                ) from error
        self.repository.update(identity, run_id, status="cancelled", finished_at=now(), error=None)
        self._clear_snapshot(run_id)
        return self.owner.detail(identity, run_id)

    async def close(self):
        """Drain application continuations, then let Group shut down its owned coordinator."""
        self.closing = True
        for task in list(self.tasks.values()):
            task.cancel()
        await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)
        await self.group.close()
