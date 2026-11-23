"""Crypto.com cash executions with native parent proof and durable nanosecond ranges.

History starts with seven days. Exact-order reads inspect at most thirty days
since the parent was created. Every distinct parent must prove ordinary cash
scope and the same native account, market and direction as the execution.
"""

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.cryptocom_orders import DAY_NS, cash_order, following, result, stamp, window
from sibyl.exchanges.history import TradePage, normalize_trade
from sibyl.exchanges.venue_history import identity, rows_list


def parent_order(exchange, market, order_id):
    """Read and verify one regular cash parent before using its executions."""
    parent = result(exchange.v1PrivatePostPrivateGetOrderDetail({"order_id": order_id}))
    if (
        not cash_order(parent)
        or identity(parent.get("order_id")) != order_id
        or parent.get("instrument_name") != market["id"]
    ):
        raise ccxt.NotSupported("Crypto.com parent is unavailable or needs cash-scope review.")
    return parent


def normalize_fill(exchange, row, market, parent):
    """Keep native trade IDs and signed wallet fees; credit consumption stays unverified."""
    if (
        row.get("journal_type") != "TRADING"
        or row.get("instrument_name") != market["id"]
        or row.get("account_id") != parent["account_id"]
        or row.get("side") != parent["side"]
        or identity(row.get("order_id")) != identity(parent["order_id"])
        or row.get("isolation_id") not in (None, "", 0, "0")
        or row.get("isolation_type") not in (None, "")
    ):
        raise ccxt.ExchangeError("Unexpected Crypto.com execution account, market or direction.")
    fill = normalize_trade(exchange.parse_trade(row, market))
    native_fee = number(row.get("fees"))
    fee = {
        "currency": exchange.safe_currency_code(row["fee_instrument_name"])
        if row.get("fee_instrument_name")
        else None,
        "cost": -native_fee if native_fee is not None else None,
    }
    if row.get("fee_credits") not in (None, "") and number(row["fee_credits"]) != 0:
        fee = {"currency": None, "cost": None}
    fill.update(
        id=identity(row.get("trade_id")),
        order=identity(row["order_id"]),
        timestamp=stamp(row) // 1000000,
        fee=fee,
        fees=[fee],
    )
    return fill


def fetch_fill_page(exchange, symbol, cursor, limit, *, order_id=None):
    """Read one bounded native time range and share exact IDs with order reconciliation."""
    market = exchange.market(symbol)
    parent = parent_order(exchange, market, identity(order_id)) if order_id is not None else None
    end = cursor.get("end", (exchange.milliseconds() + 1) * 1000000)
    start = cursor.get("start", max(1, end - (30 if parent else 7) * DAY_NS))
    if parent:
        start = max(start, stamp(parent))
    lower, upper = window(cursor, start, end)
    size = min(limit, 20)
    raw = rows_list(
        result(
            exchange.v1PrivatePostPrivateGetTrades(
                {
                    "instrument_name": market["id"],
                    "start_time": str(lower),
                    "end_time": str(upper),
                    "limit": size,
                }
            )
        ).get("data"),
        size,
    )
    next_cursor = following(cursor, lower, upper, end, saturated=len(raw) == size)
    state = {"start": start, "end": end, **next_cursor}
    if len(raw) == size:
        return TradePage([], state, False)
    parents, selected, keys = {}, [], set()
    if parent:
        parents[identity(order_id)] = parent
    for row in raw:
        key = identity(row.get("trade_id"))
        if key in keys or row.get("instrument_name") != market["id"] or not lower <= stamp(row) < upper:
            raise ccxt.ExchangeError("Crypto.com execution differs from its frozen range or identity.")
        keys.add(key)
        native_order = identity(row.get("order_id"))
        if order_id is not None and native_order != str(order_id):
            continue
        if native_order not in parents:
            parents[native_order] = parent_order(exchange, market, native_order)
        selected.append(normalize_fill(exchange, row, market, parents[native_order]))
    complete = not next_cursor
    return TradePage(
        selected, {"start": max(1, end - DAY_NS)} if complete and order_id is None else state, complete
    )
