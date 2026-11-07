"""Bounded NDJSON bridge for public activity, provisional answer text and one reply.

ProtoLink remains the execution owner. The network projects native events before
this bridge; raw action chunks, arguments and provider errors never reach it.
"""

import asyncio
import json

import anyio
from fastapi import HTTPException
from protolink import RedactionPolicy, request_context


def public_activity(event) -> dict | None:
    """Project one native action lifecycle without exposing its input/output text."""
    payload = event.payload
    data = {**payload.get("metadata", {}), **payload}
    kind = payload.get("llm_event_type", "")
    action = data.get("action")
    action = action if isinstance(action, dict) else {}
    consultation = kind.startswith("agent_call_") or action.get("kind") == "agent.call"
    if event.type not in {
        "action.started",
        "action.completed",
        "action.failed",
        "action.rejected",
        "action.canceled",
        "action.denied",
    }:
        return None
    name = data.get("agent") if consultation else data.get("tool")
    name = name or action.get("name")
    if not name:
        return None
    return {
        "type": "activity",
        "id": event.action_id or event.event_id,
        "run_id": event.run_id,
        "task_id": event.task_id,
        "agent": event.agent_name,
        "kind": "consultation" if consultation else "tool",
        "label": str(name)[:120],
        "status": {
            "action.started": "running",
            "action.completed": "completed",
            "action.failed": "failed",
            "action.rejected": "rejected",
            "action.canceled": "cancelled",
            "action.denied": "rejected",
        }[event.type],
    }


class AnswerStream:
    """Display root native text events; JSON-mode actions wait for llm_final.

    This is a UI projection, not an action parser or LLM adapter. Native providers
    separate text from tool arguments. ProtoLink 0.8.3 has no safe answer-delta
    event for JSON-mode providers, so their raw chunks must stay private.
    """

    def __init__(self, task_id: str, policy: RedactionPolicy):
        self.task_id = task_id
        self.policy = policy
        self.native = False
        self.text = ""
        self.shown = ""

    def consume(self, event) -> dict | None:
        """Format public text, resetting provisional text between native model steps."""
        if event.task_id != self.task_id:
            return None
        payload = event.payload
        kind = payload.get("llm_event_type")
        terminal = kind == "llm_final"
        if kind in {"llm_call_started", "llm_parse_error", "llm_retry"} or (
            kind == "llm_action" and payload.get("action") != "final"
        ):
            self.text = ""
        elif terminal and isinstance(payload.get("content"), str):
            self.text = payload["content"]
        elif kind == "llm_chunk" and self.native and isinstance(payload.get("content"), str):
            if len(self.text) + len(payload["content"]) > 128_000:
                return None  # Stop growing the preview; the final API reply still follows.
            self.text += payload["content"]
            # Conservative fallback for action-like text and reasoning wrappers,
            # including providers using the SDK's native JSON-repair compatibility.
            if self.text.lstrip().startswith(("{", "[", "<", "`")):
                return None
        else:
            return None
        visible = self.policy.redact(self.text)
        if not terminal:
            # SDK redaction is per event. Withhold a possible secret prefix so
            # configured credentials split across chunks cannot reach the browser.
            hold = max(
                (
                    size
                    for secret in self.policy.sensitive_values
                    for size in range(1, min(len(secret), len(visible) + 1))
                    if visible.endswith(secret[:size])
                ),
                default=0,
            )
            if hold:
                visible = visible[:-hold]
        if visible == self.shown:
            return None
        append = visible.startswith(self.shown)
        frame = {
            "type": "answer",
            "operation": "append" if append else "replace",
            "text": visible[len(self.shown) :] if append else visible,
        }
        self.shown = visible
        return frame


async def stream_reply(invoke):
    """Stream an existing API operation exactly once; cancel/drain it on disconnect."""
    queue = asyncio.Queue(maxsize=32)

    async def progress(frame):
        await queue.put(frame)

    async def produce():
        try:
            await queue.put({"type": "status", "status": "queued"})
            with request_context({"progress": progress}):
                reply = await invoke()
            await queue.put({"type": "reply", "reply": reply})
        except asyncio.CancelledError:
            raise
        except HTTPException as exc:
            await queue.put({"type": "error", "status": exc.status_code, "message": str(exc.detail)})
        except LookupError:
            await queue.put({"type": "error", "status": 404, "message": "Record not found."})
        except Exception:
            await queue.put(
                {
                    "type": "error",
                    "status": 502,
                    "message": "The answer could not finish. Check request history before trying again.",
                }
            )

    work = asyncio.create_task(produce())
    try:
        while True:
            item = await queue.get()
            yield json.dumps(item, allow_nan=False) + "\n"
            if item["type"] in {"reply", "error"}:
                break
    finally:
        with anyio.CancelScope(shield=True):
            if not work.done():
                work.cancel()
            await asyncio.gather(work, return_exceptions=True)
