"""Thin NDJSON bridge from native run events to browser-safe activity.

ProtoLink remains the execution owner. This bridge forwards labels/outcomes,
never raw model chunks, prompts, tool arguments, results or provider errors.
"""

import asyncio
import json

import anyio
from fastapi import HTTPException
from protolink import request_context


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


async def stream_reply(invoke):
    """Stream an existing API operation exactly once; cancel/drain it on disconnect."""
    queue = asyncio.Queue(maxsize=32)

    async def progress(event):
        if activity := public_activity(event):
            await queue.put(activity)

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
