"""Native Poloniex cash spot order discovery and reviewed client-ID recovery.

Separate open/history endpoints advance exact native IDs. History bounds apply
to order updates, preserving older orders that changed recently. Borrowed spot
and smart-order evidence stays outside these reviewed cash-order paths.
"""

import re

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.venue_history import identity, rows_list

LIMIT = 100
OPEN = {"NEW", "PARTIALLY_FILLED", "PENDING_CANCEL"}
TERMINAL = {"FILLED", "CANCELED", "PARTIALLY_CANCELED", "FAILED"}
STATUS = {
    **dict.fromkeys(OPEN, "open"),
    "FILLED": "closed",
    "CANCELED": "canceled",
    "PARTIALLY_CANCELED": "canceled",
    "FAILED": "rejected",
}


def cash_order(row):
    """Require explicit cash spot evidence and exclude borrowed or conditional orders."""
    return (
        row.get("accountType") == "SPOT"
        and row.get("loan") is False
        and row.get("allowBorrow") in (None, False)
        and row.get("type") in {"LIMIT", "LIMIT_MAKER", "MARKET"}
        and not row.get("smartOrderId")
        and all(row.get(key) in (None, "") or number(row[key]) == 0 for key in ("stopPrice", "triggerPrice"))
    )


def parse_order(exchange, row, market):
    """Normalize one supported native spot observation and preserve its exact order ID."""
    native_id = identity(row.get("id"))
    if int(native_id) <= 0 or row.get("state") not in OPEN | TERMINAL:
        raise ccxt.ExchangeError("Invalid Poloniex native order identity or state.")
    parsed = exchange.parse_order(row, market)
    parsed["id"] = native_id
    return parsed


def discover_page(exchange, stream, cursor, start, end):
    """Read one native ID page, keeping fixed update-time bounds for recent history."""
    recent = stream == "recent"
    after = identity(cursor.get("after", "0"))
    request = {"from": after, "direction": "NEXT", "limit": LIMIT}
    if recent:
        request.update(accountType="SPOT", startTime=start, endTime=end - 1)
    read = exchange.privateGetOrdersHistory if recent else exchange.privateGetOrders
    rows = rows_list(read(request), LIMIT)
    keys = [identity(row.get("id")) for row in rows]
    if len(set(keys)) != len(keys) or any(int(key) < int(after) or int(key) <= 0 for key in keys):
        raise ccxt.ExchangeError("Poloniex native order cursor did not advance.")
    # Inclusive native boundaries can repeat the final ID from the preceding page.
    fresh = [row for row in rows if int(identity(row["id"])) > int(after)]
    orders = []
    for row in fresh:
        if not cash_order(row):
            continue
        instrument = row.get("symbol")
        if not isinstance(instrument, str) or not instrument:
            raise ccxt.ExchangeError("Missing Poloniex spot instrument.")
        if row.get("state") not in (TERMINAL if recent else OPEN):
            raise ccxt.ExchangeError("Unexpected Poloniex order state in the selected stream.")
        if recent and not start <= int(identity(row.get("updateTime"))) < end:
            raise ccxt.ExchangeError("Poloniex history differs from the selected update window.")
        market = exchange.safe_market(instrument, marketType="spot")
        if not market.get("spot"):
            continue
        orders.append(parse_order(exchange, row, market))
    following = {"after": max(keys, key=int)} if fresh else {}
    return orders, following, not fresh, len(fresh) - len(orders)


def lookup_order(exchange, client_id, symbol):
    """Recover an API-origin cash GTC limit using the exact saved client-ID route."""
    if not isinstance(client_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", client_id):
        raise ValueError("Invalid persisted Poloniex client order ID.")
    market = exchange.market(symbol)
    try:
        row = exchange.privateGetOrdersId({"id": "cid:" + client_id})
    except ccxt.OrderNotFound:
        return []
    if (
        not isinstance(row, dict)
        or not cash_order(row)
        or row.get("clientOrderId") != client_id
        or row.get("symbol") != market["id"]
        or row.get("type") != "LIMIT"
        or row.get("timeInForce") != "GTC"
        or row.get("orderSource") != "API"
        or (number(row.get("quantity")) or 0) <= 0
        or (number(row.get("price")) or 0) <= 0
    ):
        raise ValueError("Poloniex order evidence differs from the reviewed cash spot GTC limit.")
    identity(row.get("createTime"))
    return [parse_order(exchange, row, market)]
