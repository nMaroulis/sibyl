"""Authenticated NDJSON display streams over HTTP, using the normal API access controls."""

import asyncio
import json
import time
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from sibyl.api.routes import MarketSource, S, Symbol
from sibyl.models import Timeframe

router = APIRouter()


@router.get("/markets/live/status", tags=["Analyst"])
def status(s: S, source: MarketSource | None = None):
    """Read transient public-stream health without subscribing or refreshing providers."""
    return s.market.live.snapshot(source)


async def subscribe(s: S, symbol: Symbol, source: MarketSource | None = None, timeframe: Timeframe = "1d"):
    """Admit before response headers and hold the lease until the streamed response closes."""
    identity, native = await asyncio.to_thread(s.market.live.selection, source, symbol, timeframe)
    async with s.market.live.subscribe(identity, native, symbol, timeframe) as subscription:
        yield subscription


@router.get("/markets/live", tags=["Analyst"])
async def stream(s: S, subscription: Annotated[tuple, Depends(subscribe)]):
    """Subscribe to the selected exact public feed; disconnect releases its socket lease."""
    channel, queue = subscription

    def resolve():
        return s.market.live.selection(channel.identity["source"], channel.symbol, channel.timeframe)[0]

    return display_stream(channel, queue, resolve)


async def book_subscription(s: S, symbol: Symbol, source: MarketSource):
    """Require an explicit public book source before admitting the browser stream."""
    identity = await asyncio.to_thread(s.market.live.orderbook_selection, source, symbol)
    async with s.market.live.subscribe(identity, symbol, symbol, None) as lease:
        yield lease


@router.get("/markets/orderbook/live", tags=["Broker"])
async def orderbook_stream(s: S, subscription: Annotated[tuple, Depends(book_subscription)]):
    """Stream public spot depth through the authenticated workspace API."""
    channel, queue = subscription

    def resolve():
        return s.market.live.orderbook_selection(channel.identity["source"], channel.symbol)

    return display_stream(channel, queue, resolve)


def display_stream(channel, queue, resolve):
    """Keep streaming only while the selected provider and account scope remain available."""

    async def events():
        initial = channel.status()
        yield json.dumps(initial) + "\n"
        if channel.timeframe is not None or initial["state"] == "live":
            for event in tuple(channel.latest.values()):
                yield json.dumps(event) + "\n"
        checked = time.monotonic()
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), 10)
            except TimeoutError:
                event = channel.status()
            if time.monotonic() - checked >= 10:
                # Revalidate even when a busy feed never reaches the heartbeat timeout.
                checked = time.monotonic()
                try:
                    if await asyncio.to_thread(resolve) != channel.identity:
                        return
                except (ValueError, LookupError):
                    return
            yield json.dumps(event, allow_nan=False) + "\n"
            if channel.timeframe is None and event.get("state") == "unavailable":
                return

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
