"""Coinbase Advanced Trade public display feed, with exact product and sequence checks.

Candles are native five-minute buckets only. Other intervals receive tickers,
with their existing REST candle snapshot. Public USDC aliases are rejected rather
than relabeling a USD observation. Heartbeats keep the socket open but never
establish price freshness or update historical/execution evidence.
"""

import math
import time
from datetime import UTC, datetime

from sibyl.market_data.streaming.common import SubscriptionRejected, number, timestamp

ENDPOINT = "wss://advanced-trade-ws.coinbase.com"


class SequenceGap(ConnectionError):
    """Reconnect after a missing native message; no inference or historical repair is implied."""


def exact_product(native):
    if native.endswith("-USDC") and native not in {"USDT-USDC", "EURC-USDC"}:
        raise ValueError(
            "Coinbase's public stream aliases this USDC product to USD. Use exact-source REST data or select the USD market explicitly."
        )


async def subscribe(socket, native, timeframe):
    exact_product(native)
    for channel in ("heartbeats", "ticker", *(("candles",) if timeframe == "5m" else ())):
        payload = {"type": "subscribe", "channel": channel}
        if channel != "heartbeats":
            payload["product_ids"] = [native]
        await socket.send_json(payload)


class PublicFeed:
    """Sequence state belongs to one socket and is discarded on reconnect."""

    def __init__(self):
        self.sequence = None

    def observations(self, payload, native, symbol, timeframe, *, wall=None):
        if payload.get("type") == "error":
            raise SubscriptionRejected("Coinbase rejected the public subscription. Use REST snapshots.")
        channel = payload.get("channel")
        sequence = payload.get("sequence_num")
        if channel not in {"ticker", "candles", "heartbeats", "subscriptions"} and sequence is None:
            return []
        if type(sequence) is not int or sequence < 0:
            raise ValueError("Missing native stream sequence.")
        previous = self.sequence
        if previous is not None and sequence <= previous:
            return []
        if previous is not None and sequence != previous + 1:
            raise SequenceGap("A Coinbase stream message was missed. Reconnect and retain REST fallback.")
        self.sequence = sequence
        if channel not in {"ticker", "candles", "heartbeats"}:
            return []
        wall = time.time() if wall is None else wall
        stamp = timestamp(payload["timestamp"])
        if not wall - 60 <= stamp <= wall + 2:
            return []
        events = payload.get("events")
        if not isinstance(events, list) or len(events) > 30:
            raise ValueError("Invalid public stream events.")
        result = []
        for event in events:
            if channel == "heartbeats" or event.get("type") not in {"snapshot", "update"}:
                continue
            rows = event.get("tickers" if channel == "ticker" else "candles")
            if not isinstance(rows, list) or len(rows) > 100:
                raise ValueError("Invalid public stream rows.")
            for row in rows:
                if row.get("product_id") != native:
                    continue
                base = {
                    "symbol": symbol,
                    "observed_at": datetime.fromtimestamp(stamp, UTC).isoformat(),
                    "received_at": datetime.fromtimestamp(wall, UTC).isoformat(),
                    "time_basis": "provider_envelope",
                    "snapshot": event["type"] == "snapshot",
                    "sequence": sequence,
                }
                if channel == "ticker":
                    change = float(row["price_percent_chg_24_h"])
                    if isinstance(row["price_percent_chg_24_h"], bool) or not math.isfinite(change):
                        raise ValueError("Invalid daily change.")
                    result.append(
                        {
                            **base,
                            "type": "ticker",
                            "price": number(row["price"], positive=True),
                            "change": change,
                        }
                    )
                elif timeframe == "5m":
                    start = number(row["start"], positive=True)
                    if start % 300 or not start <= wall < start + 300:
                        continue
                    candle = {
                        key: number(row[key], positive=key != "volume")
                        for key in ("open", "high", "low", "close", "volume")
                    }
                    if (
                        not candle["low"]
                        <= min(candle["open"], candle["close"])
                        <= max(candle["open"], candle["close"])
                        <= candle["high"]
                    ):
                        raise ValueError("Invalid candle bounds.")
                    candle["timestamp"] = datetime.fromtimestamp(start, UTC).isoformat()
                    result.append({**base, "type": "candle", "candle": candle, "closed": False})
        return result
