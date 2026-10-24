"""Project native ProtoLink child-task events into Sibyl's existing chat/audit UI.

This observer never discovers agents, dispatches calls or changes task execution.
"""

import json

from protolink import RunContext
from protolink.core.part import ToolOutput
from protolink.telemetry import Telemetry

from sibyl.agents.common import current_turn
from sibyl.agents.requests import now


class ChatTelemetry(Telemetry):
    """Retain actual consultations and completed evidence using the SDK lifecycle hooks."""

    def __init__(self, network):
        self.network = network

    @staticmethod
    def model_evidence(turn, module):
        """Attribute an answer to that specialist's frozen configuration, never expose keys."""
        configs = turn.configuration.get("_agents", {})
        config = configs.get(module)
        if config is None and module in {"sibyl", *turn.models}:
            config = turn.configuration
        return {
            "provider": config["provider"] if config else "",
            "model": config["model"] if config else "",
            "model_selection": turn.configuration.get("_selections", {}).get(module, "external"),
        }

    def progress(self, turn) -> None:
        """Update the UI's lightweight request progress without storing reasoning."""
        if turn.request_id:
            phase = "consulting" if any(row["status"] == "running" for row in turn.trace) else "thinking"
            self.network.requests.update(turn.request_id, phase=phase, delegations=turn.trace)

    async def on_task_start(self, task, agent_name):
        """Observe a real delegated task after ProtoLink has validated and dispatched it."""
        turn = current_turn.get()
        context = RunContext.from_task(task)
        if not turn or turn.module != "sibyl" or not context.parent_run_id:
            return
        module = agent_name.removeprefix("sibyl-")
        role = self.network.roles.get(module)
        part = task.messages[-1].parts[-1]
        question = (
            part.content.get("prompt", "")
            if part.type == "infer"
            else f"{part.as_tool_call().tool_name}({json.dumps(part.as_tool_call().args)})"
        )
        entry = next(
            (
                row
                for row in reversed(turn.trace)
                if row["agent_id"] == module and row["status"] == "running" and not row.get("task_id")
            ),
            None,
        )
        if entry is not None:
            entry["task_id"] = task.id
        else:
            turn.trace.append(
                {
                    "agent_id": module,
                    "name": role[0] if role else agent_name,
                    "task_id": task.id,
                    "question": question[:4000],
                    "context": {},
                    "status": "running",
                    "started_at": now(),
                    "finished_at": None,
                }
            )
        self.progress(turn)

    async def on_task_end(self, task, result, agent_name):
        """Retain the native result; cancellation/failure stays explicit and cannot invent a reply."""
        turn = current_turn.get()
        if not turn or turn.module != "sibyl":
            return
        entry = next((row for row in turn.trace if row["task_id"] == task.id), None)
        if entry is None:
            return
        entry.update(
            status="cancelled" if result.state.value == "canceled" else "unavailable", finished_at=now()
        )
        if result.state.value == "completed":
            observations = [row for row in turn.observations if row["task_id"] == task.id]
            part = result.get_last_item().parts[-1]
            answer = part.as_tool_output().result if part.type == "tool_output" else part.content
            evidence = (
                observations[0]["evidence"]
                if observations
                else (answer if part.type == "tool_output" else {})
            )
            entry.update(
                status="completed",
                answer=answer if isinstance(answer, str) else json.dumps(answer),
                evidence=evidence,
                mode="llm" if task.messages[0].parts[0].type == "infer" else "tools",
                **self.model_evidence(turn, entry["agent_id"]),
            )
            record = {
                **entry,
                "module": entry["agent_id"],
                "session_id": f"sibyl:{turn.session_id}:{entry['agent_id']}",
                "engine": "ProtoLink",
                "tool": observations[0]["tool"] if observations else "",
                "observations": observations,
            }
            self.network.owner.store.record("agent", record)
        elif entry["status"] == "unavailable":
            entry["error"] = "The specialist could not complete this consultation."
        self.progress(turn)

    async def on_llm_event(self, event):
        """Observe native delegation even when a newly registered peer has no app telemetry."""
        turn = current_turn.get()
        kind = event.get("type")
        if (
            not turn
            or turn.module != "sibyl"
            or kind not in {"agent_call_start", "agent_call_result", "agent_call_error"}
        ):
            return
        module = event["agent"].removeprefix("sibyl-")
        if kind == "agent_call_start":
            payload = event["payload"]
            role = self.network.roles.get(module)
            turn.trace.append(
                {
                    "agent_id": module,
                    "name": role[0] if role else event["agent"],
                    "action_id": event["action_id"],
                    "task_id": "",
                    "question": (
                        payload.get("prompt")
                        or f"{payload.get('tool')}({json.dumps(payload.get('args', {}))})"
                    )[:4000],
                    "context": {},
                    "status": "running",
                    "started_at": now(),
                    "finished_at": None,
                }
            )
        else:
            entry = next(
                (
                    row
                    for row in reversed(turn.trace)
                    if row["agent_id"] == module
                    and (not event.get("action_id") or row.get("action_id") == event["action_id"])
                ),
                None,
            )
            if entry and entry["status"] == "running":
                if kind == "agent_call_result":
                    result = event.get("result")
                    if isinstance(result, ToolOutput):
                        result = result.result
                    if isinstance(result, dict) and "call_id" in result and "result" in result:
                        result = result["result"]
                    entry.update(
                        status="completed",
                        answer=result if isinstance(result, str) else json.dumps(result),
                        evidence=result if event["action"] == "tool_call" else {},
                        **self.model_evidence(turn, entry["agent_id"]),
                        mode="tools" if event["action"] == "tool_call" else "llm",
                        finished_at=now(),
                    )
                else:
                    entry.update(
                        status="unavailable",
                        error="The specialist could not complete this consultation.",
                        finished_at=now(),
                    )
        self.progress(turn)

    async def on_llm_start(self, prompt, model=None, metadata=None):
        """Do not retain prompts or private reasoning in the progress audit."""

    async def on_llm_end(self, response):
        """Answers are captured from completed native task results."""

    async def on_tool_start(self, tool_name, args):
        """Domain wrappers record only completed read observations."""

    async def on_tool_end(self, tool_name, result, error=None):
        """Tool failures stay in the native task lifecycle."""
