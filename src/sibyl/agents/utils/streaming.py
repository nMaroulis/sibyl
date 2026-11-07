"""HTTP presentation of native ProtoLink streams; no model/action protocol handling.

The SDK owns answer extraction, privacy, activity classification and execution.
Sibyl adds bounded NDJSON delivery and commits its application chat records.
"""

import asyncio
import json

import anyio
from fastapi import HTTPException
from protolink import StreamGapError, current_request_context, request_context


async def run_updates(handle, *, after: int = 0, answer_after: int = 0, answers: bool = True):
    """Multiplex native presentation/answer subscriptions without taking run ownership.

    Their cursors are independent. Closing this iterator only stops its readers;
    an initiating request decides whether to cancel the run on disconnect.
    """
    queue = asyncio.Queue(maxsize=32)

    async def publish(kind, events):
        try:
            async for event in events:
                await queue.put({"type": kind, "update": event.to_dict()})
            await queue.put(None)
        except Exception as exc:
            await queue.put(exc)

    streams = [("activity", handle.presentation_events(after=after))]
    if answers:
        streams.append(("answer", handle.answer_events(after=answer_after)))
    readers = [asyncio.create_task(publish(kind, events)) for kind, events in streams]
    try:
        remaining = len(readers)
        while remaining:
            item = await queue.get()
            if item is None:
                remaining -= 1
            elif isinstance(item, Exception):
                raise item
            else:
                yield item
    finally:
        with anyio.CancelScope(shield=True):
            for reader in readers:
                reader.cancel()
            await asyncio.gather(*readers, return_exceptions=True)


async def retained_run(handle, *, after: int = 0, answer_after: int = 0, answers: bool = True):
    """Observe retained work; never resubmit or cancel it when a viewer disconnects."""
    try:
        async for update in run_updates(handle, after=after, answer_after=answer_after, answers=answers):
            yield json.dumps(update, allow_nan=False) + "\n"
        result = await handle.result()
        yield json.dumps({"type": "result", "status": result.status}) + "\n"
    except StreamGapError as exc:
        yield (
            json.dumps(
                {
                    "type": "gap",
                    "after": exc.after,
                    "first_available": exc.first_available,
                    "latest": exc.latest,
                }
            )
            + "\n"
        )
    except ValueError:
        yield json.dumps({"type": "error", "status": 400, "message": "Invalid run stream cursor."}) + "\n"


async def stream_reply(invoke):
    """Stream one API operation; the initiating connection cancels/drains on disconnect."""
    queue = asyncio.Queue(maxsize=32)

    async def progress(frame):
        await queue.put(frame)

    async def produce():
        try:
            with request_context({**current_request_context(), "progress": progress}):
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
