"""Upbit Korea regular spot order discovery and exact identifier recovery.

Open orders use native numbered pages. Closed-order queries have no page token,
so saturated creation-time windows split and checkpoint rather than dropping
orders with tied timestamps. Reserved orders and other regional endpoints stay
outside this adapter.
"""

import hashlib
import json
import re
from uuid import UUID

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.venue_history import rows_list

LIMIT = 100
OPEN = {"wait"}
TERMINAL = {"done", "cancel"}


def native_id(value):
    """Keep a canonical native order UUID and reject malformed venue identities."""
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("Invalid Upbit native order UUID.")
    return value


def regular_order(row):
    """Select regular limit/market spot orders and exclude reserved/triggered orders."""
    return (
        (row.get("ord_type"), row.get("side"))
        in {("limit", "bid"), ("limit", "ask"), ("price", "bid"), ("market", "ask")}
        and row.get("state") != "watch"
        and not row.get("trigger_price")
        and not row.get("stop_price")
    )


def parse_order(exchange, row, *, recent):
    """Validate native identity and spot scope before delegating field parsing to CCXT."""
    native_id(row.get("uuid"))
    if row.get("side") not in {"bid", "ask"} or row.get("state") not in (TERMINAL if recent else OPEN):
        raise ccxt.ExchangeError("Unexpected Upbit order state or direction.")
    instrument = row.get("market")
    if not isinstance(instrument, str) or not instrument:
        raise ccxt.ExchangeError("Missing Upbit spot instrument.")
    market = exchange.safe_market(instrument, marketType="spot")
    if not market.get("spot"):
        return None
    return exchange.parse_order(row, market)


def discover_page(exchange, stream, cursor, start, end):
    """Read one open page or split a capped recent creation-time window."""
    recent = stream == "recent"
    if recent:
        (lower, upper), *pending = cursor.get("windows") or [[start, end]]
        if not 0 < lower < upper or upper - lower > 7 * 86400000:
            raise ValueError("Upbit recent orders require a window of at most seven days.")
        rows = rows_list(
            exchange.privateGetOrdersClosed(
                {
                    "start_time": str(lower),
                    "end_time": str(upper - 1),
                    "limit": LIMIT,
                    "order_by": "asc",
                }
            ),
            LIMIT,
        )
        stamps = [exchange.parse8601(row.get("created_at")) for row in rows]
        if any(stamp is None or not lower <= stamp < upper for stamp in stamps):
            raise ccxt.ExchangeError("Upbit order differs from the selected creation window.")
        if len(rows) == LIMIT:
            if upper - lower <= 1:
                raise ccxt.NotSupported("Upbit timestamp boundary exceeds the reviewed order capacity.")
            middle = (lower + upper) // 2
            return [], {"windows": [[lower, middle], [middle, upper], *pending]}, False, 0
        following = {"windows": pending} if pending else {}
    else:
        page = cursor.get("page", 1)
        if type(page) is not int or not 1 <= page <= 100:
            raise ValueError("Invalid Upbit open-order page.")
        rows = rows_list(
            exchange.privateGetOrdersOpen({"state": "wait", "page": page, "limit": LIMIT, "order_by": "asc"}),
            LIMIT,
        )
        keys = [native_id(row.get("uuid")) for row in rows]
        digest = hashlib.sha256(json.dumps(sorted(keys)).encode()).hexdigest()
        if rows and digest == cursor.get("digest"):
            raise ccxt.ExchangeError("Upbit returned a repeated open-order page.")
        following = {"page": page + 1, "digest": digest} if len(rows) == LIMIT else {}
    keys = [native_id(row.get("uuid")) for row in rows]
    if len(set(keys)) != len(keys):
        raise ccxt.ExchangeError("Duplicate Upbit order identities.")
    orders = []
    for row in rows:
        if regular_order(row):
            parsed = parse_order(exchange, row, recent=recent)
            if parsed is not None:
                orders.append(parsed)
    return orders, following, not following, len(rows) - len(orders)


def lookup_order(exchange, client_id, symbol):
    """Read the saved identifier and require unchanged regular GTC limit instructions."""
    if not isinstance(client_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", client_id):
        raise ValueError("Invalid persisted Upbit client identifier.")
    try:
        row = exchange.privateGetOrder({"identifier": client_id})
    except ccxt.OrderNotFound:
        return []
    market = exchange.market(symbol)
    if (
        not isinstance(row, dict)
        or not regular_order(row)
        or row.get("identifier") != client_id
        or row.get("market") != market["id"]
        or row.get("ord_type") != "limit"
        or row.get("state") not in OPEN | TERMINAL
        or row.get("time_in_force") not in (None, "", "gtc")
        or row.get("smp_type") not in (None, "", "none")
        or (number(row.get("volume")) or 0) <= 0
        or (number(row.get("price")) or 0) <= 0
        or any(
            row.get(key) not in (None, "") and number(row[key]) != 0
            for key in ("prevented_volume", "prevented_locked")
        )
    ):
        raise ValueError("Upbit order evidence differs from the reviewed spot GTC limit.")
    return [parse_order(exchange, row, recent=row["state"] in TERMINAL)]
