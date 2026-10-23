"""Exact exchange market reads and conservative order sizing; no quote substitution."""

import math
import time
from datetime import UTC, datetime
from decimal import Decimal

import ccxt

from sibyl.exchanges.catalog import exchange_spec
from sibyl.exchanges.data import TIMEFRAMES
from sibyl.exchanges.order_fills import ORDER_FILL_KINDS
from sibyl.exchanges.providers import CLIENTS
from sibyl.strategies.execution.contracts import ExecutionGuard


def supported(exchange: str) -> bool:
    """Require implemented limit submission and exact-order native fill imports."""
    return (
        exchange in CLIENTS
        and exchange_spec(exchange).supports_order("limit")
        and CLIENTS[exchange].history_kind in ORDER_FILL_KINDS
    )


def observation(client, parameters) -> dict:
    """Validate contiguous closed candles and a fresh two-sided book on the exact pair."""
    started = time.time()
    symbol, timeframe = parameters.symbol, parameters.timeframe
    market = client.market(symbol)
    if not market.get("spot") or market.get("active") is False:
        raise ExecutionGuard("Choose an active spot market on this account's exchange.")
    if timeframe not in client.timeframes:
        raise ExecutionGuard("This timeframe is unavailable on the execution exchange.")
    step = TIMEFRAMES[timeframe] * 1000
    rows = client.fetch_ohlcv(symbol, timeframe, limit=parameters.candles + 1)
    now_ms = time.time() * 1000
    rows = [row for row in rows if row[0] + step <= now_ms][-parameters.candles :]
    if len(rows) <= parameters.warmup:
        raise ExecutionGuard("Not enough closed candles to evaluate this strategy.")
    if any(rows[i][0] - rows[i - 1][0] != step for i in range(1, len(rows))):
        raise ExecutionGuard("Execution candles have gaps or duplicate timestamps.")
    if now_ms - (rows[-1][0] + step) > step or rows[-1][0] > now_ms:
        raise ExecutionGuard("The latest closed execution candle is stale.")
    if any(not math.isfinite(float(value)) or float(value) <= 0 for row in rows for value in row[1:5]):
        raise ExecutionGuard("The exchange returned invalid execution candles.")
    observed = order_book(client, symbol, started=started)
    return {
        **observed,
        "candles": [
            dict(
                zip(
                    ("timestamp", "open", "high", "low", "close", "volume"),
                    [datetime.fromtimestamp(row[0] / 1000, UTC).isoformat(), *row[1:6]],
                    strict=True,
                )
            )
            for row in rows
        ],
    }


def order_book(client, symbol, *, started=None):
    """Read a fresh, two-sided spot book; position exits do not depend on candle history."""
    started = time.time() if started is None else started
    market = client.market(symbol)
    if not market.get("spot") or market.get("active") is False:
        raise ExecutionGuard("Choose an active spot market on this account's exchange.")
    book = client.fetch_order_book(symbol, limit=10)
    bid, ask = float(book["bids"][0][0]), float(book["asks"][0][0])
    stamp = book.get("timestamp")
    if (
        not all(math.isfinite(value) and value > 0 for value in (bid, ask))
        or ask < bid
        or (stamp is not None and not -5000 <= time.time() * 1000 - stamp <= 30_000)
        or time.time() - started > 30
    ):
        raise ExecutionGuard("A fresh two-sided exchange order book is required.")
    return {
        "bid": bid,
        "ask": ask,
        "price": (bid + ask) / 2,
        "spread_bps": (ask / bid - 1) * 10000,
        "observed_at": time.time(),
        "native_book_timestamp": stamp,
    }


def order_size(client, job, observed, side):
    """Round down base size, retain a fee reserve, and cap the GTC limit notional."""
    symbol, risk = job["parameters"]["symbol"], job["risk"]
    factor = risk["price_limit_bps"] / 10000
    target = observed["ask"] * (1 + factor) if side == "buy" else observed["bid"] * (1 - factor)
    formatted_price = client.price_to_precision(symbol, target)
    price = float(formatted_price)
    # Some venues round price to the nearest tick. Move to the safe adjacent
    # tick when necessary, then verify the cap rather than silently widening it.
    if (side == "buy" and price > target) or (side == "sell" and price < target):
        tick = float(Decimal(1).scaleb(Decimal(formatted_price).as_tuple().exponent))
        distance = max(tick, 2 * abs(target - price))
        price = float(
            client.price_to_precision(symbol, target - distance if side == "buy" else target + distance)
        )
    if (
        price <= 0
        or (side == "buy" and price > target + 1e-10)
        or (side == "sell" and price < target - 1e-10)
    ):
        raise ExecutionGuard("The venue price precision produced an invalid limit.")
    reserve = 1 + risk["fee_reserve_bps"] / 10000
    quantity = (
        min(job["cash"], risk["max_order_quote"]) / (price * reserve)
        if side == "buy"
        else min(job["quantity"] / reserve, risk["max_order_quote"] / price)
    )
    limits = client.market(symbol).get("limits") or {}
    quantity = min(
        quantity,
        1_000_000,  # The shared order contract's base-unit bound.
        (limits.get("amount") or {}).get("max") or math.inf,
        ((limits.get("cost") or {}).get("max") or math.inf) / price,
    )
    precise = float(client.amount_to_precision(symbol, quantity))
    if precise > quantity + 1e-12 or precise <= 0 or precise * price > risk["max_order_quote"] + 1e-8:
        raise ExecutionGuard("Order cannot be sized within the approved precision and budget.")
    return precise, price


def is_dust(client, symbol, quantity, price):
    """Keep residual ownership visible while allowing a later entry when it cannot be traded."""
    if quantity <= 1e-12:
        return False
    limits = client.market(symbol).get("limits") or {}
    try:
        precise = float(client.amount_to_precision(symbol, quantity))
    except ccxt.InvalidOrder:
        # CCXT raises rather than returning zero when amount precision underflows.
        return True
    return (
        precise <= 0
        or precise < ((limits.get("amount") or {}).get("min") or 0)
        or precise * price < ((limits.get("cost") or {}).get("min") or 0)
    )
