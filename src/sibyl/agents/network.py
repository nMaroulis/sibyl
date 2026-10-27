"""Native ProtoLink lifecycle and browser-facing conversation bookkeeping."""

import asyncio
import json
from hashlib import sha256
from uuid import uuid4

from protolink import (
    AgentGroup,
    ContextLimitError,
    ContextPolicy,
    RedactionPolicy,
    RunBudget,
    SQLiteRunStore,
    Task,
    current_request_context,
    request_context,
)
from protolink.client import AgentClient
from protolink.discovery import Registry
from protolink.state import State
from protolink.storage import SQLiteStorage

from sibyl.agents import sibyl
from sibyl.agents.common import freeze
from sibyl.agents.conversations import Conversations, SibylRequest
from sibyl.agents.model_selection import readiness
from sibyl.agents.presentation import RunPresentation
from sibyl.agents.requests import SibylRequests, now
from sibyl.models import AgentRequest


class ModelRequired(ValueError):
    """Sibyl cannot reason until a usable model configuration is selected."""


class AgentNetwork:
    """Start the registry and real reasoning agents with ProtoLink's public API.

    AgentGroup handles execute the registered objects. Owned local specialists
    inherit explicit private keys; AgentClient URLs also remain available for
    independent requests with transport-isolated dependencies.
    """

    def __init__(self, owner, modules: dict):
        self.owner = owner
        self.roles = {
            key: (module.NAME, module.TAGLINE, module.DESCRIPTION) for key, module in modules.items()
        }
        self.conversations = Conversations(owner.store)
        self.requests = SibylRequests(owner.store)
        self.namespace = f"runtime://sibyl-{uuid4().hex}"
        self.registry = Registry(transport="runtime", url=f"{self.namespace}/registry", verbosity=0)
        self.client = AgentClient("runtime", url=f"{self.namespace}/client")
        self.ready = False
        self._active_requests: dict[str, dict] = {}
        self._chat_locks: dict[str, asyncio.Lock] = {}
        self.database = owner.settings.data_dir / "agent-runtime.sqlite"
        self.database.touch(mode=0o600, exist_ok=True)
        self.database.chmod(0o600)
        self.run_store = SQLiteRunStore(self.database)
        self.states = {}
        self.agents = {
            key: module.create_agent(owner.services, **self.options(key)) for key, module in modules.items()
        }
        self.agents["sibyl"] = sibyl.create_agent(
            subagents=list(self.agents.values()), **self.options("sibyl")
        )
        self.group = AgentGroup(list(self.agents.values()), registry=self.registry, own_registry=True)
        self.cards = {key: agent.card for key, agent in self.agents.items()}
        for key, card in self.cards.items():
            card.tags = ["coordinator" if key == "sibyl" else "specialist", key]

    def options(self, module: str) -> dict:
        """Native factories, worker limits, evidence and session storage; no LLM adapter."""
        self.states[module] = State(SQLiteStorage(str(self.database), namespace=module), ["conversation"])
        return {
            "transport": "runtime",
            "url": f"{self.namespace}/{module}",
            "registry": self.registry,
            "llm_factory": lambda: self.owner.model_for(module),
            "sync_execution": "thread",
            "max_sync_workers": 4,
            "expose_tool_results": True,
            "state": self.states[module],
            "context_policy": ContextPolicy(preserve_recent=6),
            "verbosity": 0,
            "expose_chat": False,
        }

    async def start(self) -> None:
        """Let AgentGroup own native readiness, registration and partial-start cleanup."""
        if not self.ready:
            self.requests.recover()
            await self.group.start()
            self.ready = True

    async def close(self) -> None:
        """Cancel UI queue waiters; AgentGroup cancels/drains native runs and owned resources."""
        self.ready = False
        active = list(self._active_requests.values())
        for entry in active:
            entry["task"].cancel()
        if active:
            await asyncio.gather(*(entry["task"] for entry in active), return_exceptions=True)
        await self.group.close()
        await self.client.transport.stop()

    @staticmethod
    def session_key(module: str, session: str, page: dict) -> str:
        """Keep native conversation state separate for each module/page selection."""
        digest = sha256(json.dumps(page, sort_keys=True).encode()).hexdigest()[:20]
        return f"{module}:{session}:{digest}"

    @staticmethod
    def observations(evidence) -> list[dict]:
        """Project completed native evidence into the existing Inspect evidence UI."""
        return [
            {
                "agent_id": (item.agent_name or "").removeprefix("sibyl-"),
                "task_id": item.task_id,
                "tool": item.tool_name,
                "arguments": item.arguments,
                "evidence": item.result,
                "action_id": item.action_id,
                "delegation_id": item.delegation_id,
                "duration_seconds": item.duration_seconds,
            }
            for item in evidence
            if item.outcome == "completed" and not item.result_omitted
        ]

    async def send(self, module: str, task: Task, *, request=None):
        """Run a native handle, consume typed events and cancel it when the caller leaves.

        Local owned runs retain explicitly bound private dependencies. A plain
        AgentClient request crosses a transport boundary and resolves its model
        in the receiving application, without inheriting caller credentials.
        """
        configuration = current_request_context().get("models", {})
        progress = current_request_context().get("progress")
        secrets = frozenset(
            row["api_key"] for row in configuration.get("_agents", {}).values() if row.get("api_key")
        )
        policy = RedactionPolicy(sensitive_values=secrets)
        handle = self.group.run(
            self.agents[module],
            task,
            store=SQLiteRunStore(self.database, redaction_policy=policy),
            redaction_policy=policy,
        )
        view = RunPresentation(self, handle, configuration, request) if request else None
        if request:
            self.requests.update(request.request_id, run_id=handle.context.run_id)
        try:
            async for event in handle.events():
                if view:
                    view.consume(event)
                if progress:
                    await progress(event)
            result = await handle.result()
        except BaseException:
            await handle.cancel("Caller stopped waiting")
            result = await handle.result()
            if view:
                view.finish(result)
            raise
        if view:
            view.finish(result)
        if result.status == "canceled":
            raise asyncio.CancelledError()
        if result.status != "completed":
            failures = [result.error.get("code")] if isinstance(result.error, dict) else []
            for event in result.report.events:
                error = event.payload.get("error") or event.payload.get("metadata", {}).get("error")
                if isinstance(error, dict):
                    failures.append(error.get("code"))
            if "ContextLimitError" in failures:
                raise ContextLimitError(
                    "The configured model context window cannot fit this request. "
                    "Choose a model with more room in Settings → AI models; for Ollama, "
                    "increase its context window within the model and memory limits."
                )
            if "LookupError" in failures:
                raise LookupError("Record not found.")
            if "TimeoutError" in failures:
                raise TimeoutError("Agent request timed out.")
            raise RuntimeError("The agent could not complete this request.")
        return result

    async def ask_module(self, request: AgentRequest) -> dict:
        """A page runs its registered specialist through a native group handle."""
        configuration = freeze(self.owner.models.for_turn(request.module))
        async with self.owner._semaphore:
            async with asyncio.timeout(95):
                return await self.owner._answer(request, configuration)

    def status(self, configuration: dict | None = None) -> dict:
        """Return setup readiness without probing a provider or revealing credentials."""
        configuration = configuration or self.owner.models.resolve("sibyl")
        reason = readiness(configuration)
        return {
            "ready": self.ready and (not reason),
            "network_ready": self.ready,
            "reason": reason or ("The agent network is starting." if not self.ready else ""),
            "provider": configuration["provider"],
            "model": configuration["model"],
            "simulated": configuration["provider"] == "mock",
            "engine": "ProtoLink",
            "transport": "runtime",
            "specialists": len(self.roles),
            "settings_url": "/settings?tab=models",
        }

    def conversation(self, session_id: str) -> dict:
        """Expose saved turns and transient running state when a chat page is reopened."""
        lock = self._chat_locks.get(session_id)
        return {**self.conversations.get(session_id), "pending": bool(lock and lock.locked())}

    def activity(self, session_id: str) -> dict | None:
        """Read lightweight progress or the latest stopped/failed request without model calls."""
        self.conversations.require(session_id)
        return self.requests.public(self.requests.latest(session_id))

    async def cancel(self, session_id: str, request_id: str) -> dict:
        """Cancel only the selected active request, never another turn in the same chat."""
        self.conversations.require(session_id)
        current = self.requests.get(session_id, request_id)
        if current["status"] == "cancelled":
            return self.requests.public(current)
        entry = self._active_requests.get(session_id)
        if (
            current["status"] not in {"queued", "running", "cancelling"}
            or not entry
            or entry["id"] != request_id
            or entry["task"].done()
        ):
            raise ValueError("This request is no longer running. Refresh the conversation.")
        entry["cancel_requested"] = True
        self.requests.update(request_id, status="cancelling", phase="cancelling")
        entry["task"].cancel()
        return self.requests.public(self.requests.get(session_id, request_id))

    def delete_conversation(self, session_id: str) -> None:
        """Reject deleting a chat while its queued or active turn owns its lock."""
        lock = self._chat_locks.get(session_id)
        if lock and lock.locked():
            raise ValueError("Wait for Sibyl to finish before deleting this conversation.")
        native_session = self.session_key("sibyl", session_id, {})
        while records := self.run_store.list_report_records(session_id=native_session):
            for record in records:
                report = self.run_store.get_report(record.run_id)
                child_sessions = {
                    event.run_id for event in report.events if event.run_id and event.run_id != record.run_id
                }
                for state in self.states.values():
                    for child in child_sessions:
                        state.conversation.clear_session(child)
                self.run_store.delete_report(record.run_id)
        self.states["sibyl"].conversation.clear_session(native_session)
        self.conversations.delete(session_id)

    async def ask(self, request: SibylRequest) -> dict:
        """Run the native coordinator with bounded UI admission and a frozen team snapshot."""
        configuration = freeze(self.owner.models.for_turn("sibyl"))
        status = self.status(configuration)
        if not status["ready"]:
            raise ModelRequired(status["reason"])
        if request.session_id:
            self.conversations.get(request.session_id)
        else:
            request = request.model_copy(update={"session_id": self.conversations.create()["id"]})
        session = request.session_id
        lock = self._chat_locks.setdefault(session, asyncio.Lock())
        if lock.locked():
            raise ValueError("Sibyl is already answering in this conversation.")
        try:
            async with lock:
                record = self.requests.start(
                    session,
                    request.message,
                    configuration["provider"],
                    configuration["model"],
                    request.request_id,
                )
                request = request.model_copy(update={"request_id": record["id"]})
                entry = {"id": record["id"], "cancel_requested": False}

                async def execute():
                    async with self.owner._semaphore:
                        self.requests.update(
                            record["id"], status="running", phase="thinking", started_at=now()
                        )
                        return await self._answer_sibyl(request, configuration)

                work = asyncio.create_task(execute())
                entry["task"] = work
                self._active_requests[session] = entry
                try:
                    async with asyncio.timeout(150):
                        answer = await work
                    if entry["cancel_requested"]:
                        self.requests.finish(record["id"], "cancelled")
                        return {"status": "cancelled", "session_id": session, "request_id": record["id"]}
                    self.requests.finish(record["id"], "completed")
                    return answer
                except asyncio.CancelledError:
                    outcome = "cancelled" if entry["cancel_requested"] else "interrupted"
                    self.requests.finish(record["id"], outcome)
                    if entry["cancel_requested"]:
                        return {"status": "cancelled", "session_id": session, "request_id": record["id"]}
                    raise
                except Exception:
                    if entry["cancel_requested"]:
                        self.requests.finish(record["id"], "cancelled")
                        return {"status": "cancelled", "session_id": session, "request_id": record["id"]}
                    self.requests.finish(
                        record["id"],
                        "failed",
                        "The answer could not finish. Check your model provider and try again.",
                    )
                    raise
                finally:
                    if not work.done():
                        work.cancel()
                    self._active_requests.pop(session, None)
        finally:
            self._chat_locks.pop(session, None)

    async def _answer_sibyl(self, request: SibylRequest, configuration: dict) -> dict:
        """Use native session history, events and reports; retain only the UI chat projection."""
        with request_context(
            {**current_request_context(), "models": configuration, "page": freeze({})},
            inherit=("models", "page"),
        ):
            execution = await self.send(
                "sibyl",
                Task.create_infer(
                    request.message,
                    session_id=self.session_key("sibyl", request.session_id, {}),
                    budget=RunBudget(
                        max_steps=12, max_llm_calls=10, max_tool_calls=10, max_runtime_seconds=140
                    ),
                ),
                request=request,
            )
        return self.conversations.append(
            {
                "session_id": request.session_id,
                "request_id": request.request_id,
                "status": "completed",
                "question": request.message,
                "answer": str(execution.output),
                "module": "sibyl",
                "engine": "ProtoLink",
                "provider": configuration["provider"],
                "model": configuration["model"],
                "model_selection": configuration.get("_selections", {}).get("sibyl", "default"),
                "mode": "mock" if configuration["provider"] == "mock" else "llm",
                "run_id": execution.report.context.run_id,
                "delegations": self.requests.get(request.session_id, request.request_id)["delegations"],
            }
        )
