"""Kraken v2 public ticker/OHLC observations; no credentials or execution data.

OHLC snapshots contain older candles and have no close flag or reliable event
clock. Only the current aligned interval is displayed, explicitly timed by
local receipt. Untimestamped tickers retain that same attribution.
"""

import math
import time
from datetime import UTC, datetime

ENDPOINT = "wss://ws.kraken.com/v2"
INTERVALS = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080}


class SubscriptionRejected(ConnectionError):
    """A native subscription was rejected; REST remains available without reconnect churn."""


def number(value, *, positive=False):
    if isinstance(value, bool):
        raise ValueError("Invalid public stream number.")
    value = float(value)
    if not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError("Invalid public stream number.")
    return value


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Missing stream timezone.")
    return parsed.timestamp()


async def subscribe(socket, native, timeframe):
    """Request separate public channels on one owned connection."""
    for channel in ("ticker", "ohlc"):
        params = {"channel": channel, "symbol": [native], "snapshot": True}
        if channel == "ohlc":
            params["interval"] = INTERVALS[timeframe]
        await socket.send_json({"method": "subscribe", "params": params})


def observations(payload, native, symbol, timeframe, *, wall=None):
    """Validate exact symbols/intervals and expose sanitized, explicitly dated display events."""
    wall = time.time() if wall is None else wall
    if payload.get("method") == "subscribe" and payload.get("success") is False:
        raise SubscriptionRejected("Kraken rejected the public subscription. Use the REST snapshot.")
    channel = payload.get("channel")
    if channel not in {"ticker", "ohlc"} or payload.get("type") not in {"snapshot", "update"}:
        return []
    rows = payload.get("data")
    if not isinstance(rows, list) or len(rows) > 50:
        raise ValueError("Invalid public stream batch.")
    received = datetime.fromtimestamp(wall, UTC).isoformat()
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid public stream observation.")
        if row.get("symbol") != native:
            continue
        base = {
            "symbol": symbol,
            "observed_at": received,
            "received_at": received,
            "time_basis": "receipt",
            "snapshot": payload["type"] == "snapshot",
        }
        if channel == "ticker":
            if row.get("timestamp"):
                stamp = timestamp(row["timestamp"])
                if not wall - 60 <= stamp <= wall + 2:
                    continue
                base.update(observed_at=datetime.fromtimestamp(stamp, UTC).isoformat(), time_basis="provider")
            change = float(row["change_pct"])
            if isinstance(row["change_pct"], bool) or not math.isfinite(change):
                raise ValueError("Invalid public stream change.")
            result.append(
                {**base, "type": "ticker", "price": number(row["last"], positive=True), "change": change}
            )
            continue
        interval = INTERVALS[timeframe]
        if type(row.get("interval")) is not int or row["interval"] != interval:
            continue
        start = timestamp(row["interval_begin"])
        step = interval * 60
        if not start <= wall < start + step or start % 60 or (interval < 10080 and start % step):
            continue  # Native weekly anchors vary; never synthesize or relabel older intervals.
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
            raise ValueError("Invalid public stream candle.")
        candle["timestamp"] = datetime.fromtimestamp(start, UTC).isoformat()
        result.append({**base, "type": "candle", "candle": candle, "closed": False})
    return result
