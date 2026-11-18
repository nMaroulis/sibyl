"""Crypto.com Exchange cash orders through the native v1 account APIs.

Explicit execution-instruction arrays distinguish regular cash spot orders from
margin, liquidation and advanced instructions. Missing scope evidence is never
inferred from the instrument name alone. Private responses stay in the backend.
"""

import re

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.venue_history import identity, rows_list

DAY_NS = 86400 * 1000000000
OPEN = {"PENDING", "NEW", "ACTIVE"}
TERMINAL = {"FILLED", "CANCELED", "REJECTED", "EXPIRED"}


def result(response):
    """Require a successful native envelope before interpreting its account evidence."""
    if (
        not isinstance(response, dict)
        or type(response.get("code")) is not int
        or response["code"] != 0
        or not isinstance(response.get("result"), dict)
    ):
        raise ccxt.ExchangeError("Invalid Crypto.com account response.")
    return response["result"]


def stamp(row):
    """Retain native nanoseconds as integers; millisecond-only records keep that precision."""
    milliseconds = int(identity(row.get("create_time")))
    nanoseconds = (
        int(identity(row["create_time_ns"]))
        if row.get("create_time_ns") is not None
        else milliseconds * 1000000
    )
    if nanoseconds <= 0 or nanoseconds // 1000000 != milliseconds:
        raise ccxt.ExchangeError("Inconsistent Crypto.com creation time.")
    return nanoseconds


def cash_order(row):
    """Select ordinary spot instructions, excluding borrowed, linked and trigger orders."""
    instructions = row.get("exec_inst")
    return (
        isinstance(instructions, list)
        and all(
            isinstance(value, str) and value in {"POST_ONLY", "SMART_POST_ONLY"} for value in instructions
        )
        and row.get("order_type") in {"LIMIT", "MARKET"}
        and row.get("side") in {"BUY", "SELL"}
        and isinstance(row.get("account_id"), str)
        and bool(row["account_id"])
        and row.get("spot_margin") in (None, "SPOT")
        and all(
            row.get(name) in (None, "") or number(row.get(name)) == 0
            for name in (
                "isolation_id",
                "isolation_type",
                "isolated_margin_amount",
                "leverage",
                "list_id",
                "contingency_type",
                "leg_id",
                "trigger_price",
                "ref_price",
                "attach_order_id",
                "attach_isolation_id",
            )
        )
    )


def parse_order(exchange, row, market):
    """Keep actual cumulative cash facts separate from quote budgets and average-price defaults."""
    parsed = exchange.parse_order(row, market)
    parsed.update(
        id=identity(row.get("order_id")),
        status="open" if row.get("status") in OPEN else parsed["status"],
        timestamp=stamp(row) // 1000000,
        cost=number(row.get("cumulative_value")),
        filled=number(row.get("cumulative_quantity")),
    )
    if row.get("order_type") == "MARKET" and row.get("side") == "BUY":
        # Native market buys can use notional instead of base quantity.
        if (number(row.get("quantity")) or 0) <= 0:
            parsed.update(amount=None, remaining=None)
    return parsed


def window(cursor, start, end):
    """Resume at most one native day; split full responses instead of skipping timestamp ties."""
    bounds = (cursor.get("windows") or [[start, min(start + DAY_NS, end)]])[0]
    if len(bounds) != 2 or any(type(value) is not int for value in bounds):
        raise ValueError("Invalid Crypto.com time range.")
    lower, upper = bounds
    if not 0 < start <= lower < upper <= end or upper - lower > DAY_NS:
        raise ValueError("Crypto.com time range differs from the frozen query.")
    return lower, upper


def following(cursor, lower, upper, end, *, saturated):
    """Save remaining ranges without treating a capped native snapshot as complete."""
    pending = (cursor.get("windows") or [[lower, upper]])[1:]
    if saturated:
        if upper - lower <= 1:
            raise ccxt.NotSupported("Crypto.com timestamp boundary exceeds the reviewed capacity.")
        middle = (lower + upper) // 2
        return {"windows": [[lower, middle], [middle, upper], *pending]}
    if not pending and upper < end:
        pending = [[upper, min(upper + DAY_NS, end)]]
    return {"windows": pending} if pending else {}


def discover_page(exchange, stream, cursor, start, end, symbols):
    """Read an account-wide cash open snapshot or selected-pair native history window."""
    recent = stream == "recent"
    if recent:
        index = cursor.get("market", 0)
        if index >= len(symbols):
            return [], {}, True, 0
        market = exchange.market(symbols[index])
        lower, upper = window(cursor, start * 1000000, end * 1000000)
        raw = rows_list(
            result(
                exchange.v1PrivatePostPrivateGetOrderHistory(
                    {
                        "instrument_name": market["id"],
                        "start_time": str(lower),
                        "end_time": str(upper),
                        "limit": 100,
                    }
                )
            ).get("data"),
            100,
        )
        next_cursor = following(cursor, lower, upper, end * 1000000, saturated=len(raw) == 100)
        if len(raw) == 100:
            return [], {"market": index, **next_cursor}, False, 0
    else:
        raw = rows_list(result(exchange.v1PrivatePostPrivateGetOpenOrders({})).get("data"), 1000)
    keys, selected = set(), []
    for row in raw:
        key = identity(row.get("order_id"))
        if key in keys:
            raise ccxt.ExchangeError("Duplicate Crypto.com order identity.")
        keys.add(key)
        instrument = row.get("instrument_name")
        if not isinstance(instrument, str) or not instrument:
            raise ccxt.ExchangeError("Missing Crypto.com order instrument.")
        if recent and instrument != market["id"]:
            raise ccxt.ExchangeError("Crypto.com returned a different history instrument.")
        candidate = exchange.safe_market(instrument, marketType="spot")
        if not candidate.get("spot") or not cash_order(row):
            continue
        if row.get("status") not in (TERMINAL if recent else OPEN):
            raise ccxt.ExchangeError("Unexpected Crypto.com order state.")
        if recent and not lower <= stamp(row) < upper:
            raise ccxt.ExchangeError("Crypto.com order differs from its frozen creation range.")
        selected.append(parse_order(exchange, row, candidate))
    if recent:
        index += int(not next_cursor)
        complete = index >= len(symbols)
        return (
            selected,
            {"market": index, **next_cursor} if not complete else {},
            complete,
            len(raw) - len(selected),
        )
    return selected, {}, True, len(raw) - len(selected)


def lookup_order(exchange, client_id, symbol):
    """Read the saved client_oid and require unchanged ordinary cash GTC limit terms."""
    if not isinstance(client_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,36}", client_id):
        raise ValueError("Invalid persisted Crypto.com client order ID.")
    try:
        row = result(exchange.v1PrivatePostPrivateGetOrderDetail({"client_oid": client_id}))
    except ccxt.OrderNotFound:
        return []
    market = exchange.market(symbol)
    if (
        not cash_order(row)
        or row.get("client_oid") != client_id
        or row.get("instrument_name") != market["id"]
        or row.get("order_type") != "LIMIT"
        or row.get("time_in_force") != "GOOD_TILL_CANCEL"
        or row.get("exec_inst") != []
        or row.get("status") not in OPEN | TERMINAL
    ):
        raise ValueError("Crypto.com order evidence differs from the reviewed cash GTC limit.")
    return [parse_order(exchange, row, market)]
