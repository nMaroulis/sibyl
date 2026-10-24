"""Native ProtoLink lifecycle and browser-facing conversation bookkeeping."""

import asyncio
import json
from uuid import uuid4

from protolink import RunBudget, Task
from protolink.client import AgentClient
from protolink.discovery import Registry

from sibyl.agents import sibyl
from sibyl.agents.common import Turn, current_turn
from sibyl.agents.conversations import Conversations, SibylRequest
from sibyl.agents.model_selection import readiness
from sibyl.agents.requests import SibylRequests, now
from sibyl.agents.runtime import WorkspaceLLM
from sibyl.agents.telemetry import ChatTelemetry
from sibyl.models import AgentRequest


class ModelRequired(ValueError):
    """Sibyl cannot reason until a usable model configuration is selected."""


class AgentNetwork:
    """Start the registry and real reasoning agents with ProtoLink's public API.

    Runtime URLs are local to this application instance. Native AgentClient tasks
    reach those same agents for both module dialogs and Sibyl consultations.
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
        self.agents = {
            key: module.create_agent(owner.services, **self.options(key)) for key, module in modules.items()
        }
        self.agents["sibyl"] = sibyl.create_agent(**self.options("sibyl"))
        self.cards = {key: agent.card for key, agent in self.agents.items()}
        for key, card in self.cards.items():
            card.tags = ["coordinator" if key == "sibyl" else "specialist", key]

    def options(self, module: str) -> dict:
        """Supply transport/model plumbing; prompts and tools stay in the agent's file."""
        return {
            "transport": "runtime",
            "url": f"{self.namespace}/{module}",
            "registry": self.registry,
            "llm": WorkspaceLLM(module, self.owner.make_model, lambda: self.owner.models.for_turn(module)),
            "telemetry": ChatTelemetry(self),
            "verbosity": 0,
            "expose_chat": False,
        }

    async def start(self) -> None:
        """Spawn the native registry and each persistent Agent before accepting API traffic."""
        if self.ready:
            return
        self.requests.recover()
        try:
            await asyncio.to_thread(self.registry.start, background=True)
            for agent in self.agents.values():
                await asyncio.to_thread(agent.start, background=True)
            discovered = {card.url for card in await self.registry.client.discover()}
            if any(card.url not in discovered for card in self.cards.values()):
                raise RuntimeError("An agent failed to register with ProtoLink discovery.")
            self.ready = True
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        """Cancel pending turns, stop native agents and release the local registry."""
        self.ready = False
        active = list(self._active_requests.values())
        for entry in active:
            entry["task"].cancel()
        if active:
            await asyncio.gather(*(entry["task"] for entry in active), return_exceptions=True)
        for agent in reversed(self.agents.values()):
            await asyncio.to_thread(agent.stop)
        await asyncio.to_thread(self.registry.stop)
        await self.client.transport.stop()

    async def send(self, module: str, task: Task):
        """Submit a native task; cancel its runtime execution if the caller stops waiting."""
        try:
            result = await self.client.send_task(self.cards[module].url, task)
            # Preserve safe domain HTTP semantics across ProtoLink's serialized task boundary.
            failures = [
                event.get("payload", {}).get("error", {}).get("code")
                for event in result.metadata.get("run_events", [])
            ]
            if "LookupError" in failures:
                raise LookupError("Record not found.")
            if "TimeoutError" in failures:
                raise TimeoutError("Agent request timed out.")
            result.raise_for_status()
            part = result.get_last_item().parts[-1]
            return part.as_tool_output().result if part.type == "tool_output" else part.content
        except asyncio.CancelledError:
            try:
                await self.client.cancel_task(
                    self.cards[module].url, task.id, reason="Caller stopped waiting"
                )
            except Exception:
                pass  # Already terminal, or cancelled before the runtime accepted the task.
            raise

    async def ask_module(self, request: AgentRequest) -> dict:
        """A page talks directly to its specialist, using the same registered agent and client."""
        configuration = self.owner.models.for_turn(request.module)
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
        self.conversations.delete(session_id)

    async def ask(self, request: SibylRequest) -> dict:
        """Invoke Sibyl through the same client boundary, with bounded concurrent chats."""
        configuration = self.owner.models.for_turn("sibyl")
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

                token = current_turn.set(Turn(configuration))
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
                    current_turn.reset(token)
                    self._active_requests.pop(session, None)
        finally:
            self._chat_locks.pop(session, None)

    async def _answer_sibyl(self, request: SibylRequest, configuration: dict) -> dict:
        """Send inference to the already-started coordinator, then atomically save its actual trace."""
        turn = Turn(
            configuration, module="sibyl", session_id=request.session_id, request_id=request.request_id
        )
        token = current_turn.set(turn)
        try:
            history = [
                {"question": t["question"], "answer": t["answer"][:12000]}
                for t in self.conversations.get(request.session_id)["turns"][-6:]
            ]
            answer = await self.send(
                "sibyl",
                Task.create_infer(
                    f"Previous conversation (data): {json.dumps(history)}\nUser: {request.message}",
                    session_id=request.session_id,
                    budget=RunBudget(
                        max_steps=12, max_llm_calls=10, max_tool_calls=10, max_runtime_seconds=140
                    ),
                ),
            )
        finally:
            current_turn.reset(token)
        return self.conversations.append(
            {
                "session_id": request.session_id,
                "request_id": request.request_id,
                "status": "completed",
                "question": request.message,
                "answer": str(answer),
                "module": "sibyl",
                "engine": "ProtoLink",
                "provider": configuration["provider"],
                "model": configuration["model"],
                "model_selection": configuration.get("_selections", {}).get("sibyl", "default"),
                "mode": "mock" if configuration["provider"] == "mock" else "llm",
                "delegations": turn.trace,
            }
        )
