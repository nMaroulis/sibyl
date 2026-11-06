"""On-demand, shared public market streams; execution and closed-candle history stay REST-based.

Each exact source/pair/interval owns one upstream socket while viewed. Bounded
subscriber queues coalesce updates rather than building a backlog. No account
credentials, arbitrary URLs or provider payloads cross the browser boundary.
"""

import asyncio
import json
import math
import random
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime

import aiohttp

ENDPOINTS = {
    "production": "wss://data-stream.binance.vision/stream",
    "test": "wss://stream.testnet.binance.vision/stream",
}
PROVIDERS = {"binance", "binance-testnet", "kraken"}


def numeric(value, *, positive=False):
    """Accept finite native numbers and reject booleans and negative volume/prices."""
    if isinstance(value, bool):
        raise ValueError("Invalid stream number.")
    result = float(value)
    if not math.isfinite(result) or result < 0 or (positive and result == 0):
        raise ValueError("Invalid stream number.")
    return result


def observation(message, native_symbol, symbol, timeframe, wall=None):
    """Validate a Binance ticker or candle and return only typed display evidence."""
    data = message.get("data", message)
    if data.get("s") != native_symbol:
        return None
    stamp = numeric(data.get("E"), positive=True)
    wall = time.time() if wall is None else wall
    if stamp > wall * 1000 + 2000 or stamp < wall * 1000 - 60_000:
        return None
    base = {"symbol": symbol, "observed_at": datetime.fromtimestamp(stamp / 1000, UTC).isoformat()}
    if data.get("e") == "24hrTicker":
        change = float(data["P"])
        if not math.isfinite(change):
            raise ValueError("Invalid change.")
        return {**base, "type": "ticker", "price": numeric(data["c"], positive=True), "change": change}
    if data.get("e") != "kline":
        return None
    row = data["k"]
    if row.get("s") != native_symbol or row.get("i") != timeframe or not isinstance(row.get("x"), bool):
        return None
    candle = {
        key: numeric(row[native], positive=key != "volume")
        for key, native in (("open", "o"), ("high", "h"), ("low", "l"), ("close", "c"), ("volume", "v"))
    }
    start = numeric(row["t"], positive=True)
    if (
        start > stamp
        or not candle["low"]
        <= min(candle["open"], candle["close"])
        <= max(candle["open"], candle["close"])
        <= candle["high"]
    ):
        raise ValueError("Invalid stream candle.")
    candle["timestamp"] = datetime.fromtimestamp(start / 1000, UTC).isoformat()
    return {**base, "type": "candle", "closed": row["x"], "candle": candle}


@dataclass
class Channel:
    """Transient display state; it is never a historical data or execution ledger."""

    identity: dict
    native_symbol: str
    symbol: str
    timeframe: str
    queues: set = field(default_factory=set)
    task: asyncio.Task | None = None
    state: str = "connecting"
    reconnects: int = 0
    received: int = 0
    invalid: int = 0
    last_received: float = 0
    latest: dict = field(default_factory=dict)

    def status(self):
        stale = self.state == "live" and time.time() - self.last_received > 15
        return {
            "type": "status",
            **self.identity,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "state": "stale" if stale else self.state,
            "reconnects": self.reconnects,
            "received": self.received,
            "invalid": self.invalid,
            "last_received_at": datetime.fromtimestamp(self.last_received, UTC).isoformat()
            if self.last_received
            else None,
            "fallback": "REST snapshots remain available; indicators use closed candles.",
        }

    def publish(self, event):
        for queue in self.queues:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)


class LiveMarkets:
    """Share bounded public sockets and cancel/drain them when the last viewer leaves."""

    def __init__(self, market):
        self.market, self.channels, self.closed = market, {}, False
        self.connect = self._connect

    def selection(self, source, symbol, timeframe):
        """Resolve the actual feed/environment and native symbol without disclosing keys."""
        with self.market.snapshot(source):
            identity = self.market.metadata()
            supported = identity["provider"] in PROVIDERS and identity["environment"] in ENDPOINTS
            if identity["provider"] == "kraken":
                from sibyl.market_data.streaming.kraken import INTERVALS

                supported = identity["environment"] == "production" and timeframe in INTERVALS
            if not supported:
                raise ValueError(
                    "Live streaming is available for Binance/Testnet and supported Kraken production intervals. This feed uses REST snapshots."
                )
            client = self.market.client()
            if timeframe not in client.timeframes:
                raise ValueError("This interval is unavailable on the selected feed.")
            native = client.stream_symbol(symbol)
            if not isinstance(native, str) or not re.fullmatch(
                r"[A-Z0-9]{1,12}/[A-Z0-9]{1,12}" if identity["provider"] == "kraken" else r"[A-Z0-9]{2,48}",
                native,
            ):
                raise ValueError("Invalid native spot stream identifier.")
            return {
                key: identity[key] for key in ("source", "source_label", "provider", "environment")
            }, native

    @asynccontextmanager
    async def subscribe(self, selection, native, symbol, timeframe):
        if self.closed:
            raise ValueError("Market streaming is shutting down.")
        key = (selection["source"], selection["environment"], native, timeframe)
        channel = self.channels.get(key)
        if channel is None:
            if len(self.channels) >= 16:
                raise ValueError("Live market capacity reached; REST snapshots remain available.")
            channel = self.channels[key] = Channel(selection, native, symbol, timeframe)
        if len(channel.queues) >= 32:
            raise ValueError("This stream has reached its viewer limit.")
        queue = asyncio.Queue(maxsize=8)
        channel.queues.add(queue)
        if channel.task is None:
            channel.task = asyncio.create_task(self._run(channel), name="sibyl-market-stream")
        try:
            yield channel, queue
        finally:
            channel.queues.discard(queue)
            if not channel.queues:
                self.channels.pop(key, None)
                channel.task.cancel()
                await asyncio.gather(channel.task, return_exceptions=True)

    @asynccontextmanager
    async def _connect(self, url):
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=10)
        ) as session:
            async with session.ws_connect(url, autoping=True, heartbeat=20, max_msg_size=65536) as socket:
                yield socket

    async def _run(self, channel):
        attempt = 0
        streams = f"{channel.native_symbol.lower()}@ticker/{channel.native_symbol.lower()}@kline_{channel.timeframe}"
        from sibyl.market_data.streaming import kraken

        is_kraken = channel.identity["provider"] == "kraken"
        url = (
            kraken.ENDPOINT
            if is_kraken
            else f"{ENDPOINTS[channel.identity['environment']]}?streams={streams}"
        )
        while True:
            try:
                channel.state = "connecting" if not channel.reconnects else "reconnecting"
                channel.publish(channel.status())
                async with self.connect(url) as socket:
                    if is_kraken:
                        await kraken.subscribe(socket, channel.native_symbol, channel.timeframe)
                    while True:
                        message = await asyncio.wait_for(socket.receive(), 30)
                        if message.type != aiohttp.WSMsgType.TEXT:
                            raise ConnectionError("Stream closed.")
                        try:
                            payload = json.loads(message.data)
                            if not is_kraken and payload.get("data", payload).get("e") == "serverShutdown":
                                raise ConnectionError("Provider rotating connection.")
                            events = (
                                kraken.observations(
                                    payload, channel.native_symbol, channel.symbol, channel.timeframe
                                )
                                if is_kraken
                                else [
                                    observation(
                                        payload, channel.native_symbol, channel.symbol, channel.timeframe
                                    )
                                ]
                            )
                        except (ValueError, KeyError, TypeError, OverflowError, AttributeError):
                            channel.invalid += 1
                            continue
                        for event in events:
                            if event is None:
                                continue
                            previous = channel.latest.get(event["type"])
                            if previous and event["observed_at"] < previous["observed_at"]:
                                continue
                            channel.latest[event["type"]] = {**event, **channel.identity}
                            channel.received += 1
                            channel.last_received, attempt = time.time(), 0
                            if channel.state != "live":
                                channel.state = "live"
                                channel.publish(channel.status())
                            channel.publish(channel.latest[event["type"]])
            except asyncio.CancelledError:
                raise
            except kraken.SubscriptionRejected:
                channel.state = "unavailable"
                channel.publish(channel.status())
                return
            except Exception:
                channel.reconnects += 1
                channel.state = "reconnecting"
                channel.publish(channel.status())
                attempt += 1
                await asyncio.sleep(min(30, 2 ** min(attempt, 5)) + random.random())

    def snapshot(self, source=None):
        """Inspect observed stream health; never open a socket or refresh provider data."""
        return {
            "items": [
                {
                    **channel.status(),
                    "ticker": channel.latest.get("ticker"),
                    "forming_candle": channel.latest.get("candle"),
                }
                for channel in tuple(self.channels.values())
                if not source or channel.identity["source"] == source
            ],
            "scope": "Only viewed Binance/Testnet and Kraken public market streams. Kraken receipt-timed data does not prove last-trade freshness. Account/order tracking and analysis remain REST-based.",
        }

    async def close(self):
        """Drain all sockets on application shutdown without affecting exchange orders."""
        self.closed = True
        tasks = [channel.task for channel in self.channels.values() if channel.task]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.channels.clear()
