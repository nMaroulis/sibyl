"""Native Poloniex cash spot order discovery and reviewed client-ID recovery.

Separate open/history endpoints advance exact native IDs. History bounds apply
to order updates, preserving older orders that changed recently. Borrowed spot
and smart-order evidence stays outside these reviewed cash-order paths.
"""

import re
from decimal import Decimal

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


def market_terms(exchange, market, side, amount):
    """Read exact-pair cash market rules and validate the native sizing scale."""
    row = exchange.publicGetMarketsSymbol({"symbol": market["id"]})
    if not isinstance(row, dict) or (
        row.get("symbol"),
        row.get("baseCurrencyName"),
        row.get("quoteCurrencyName"),
    ) != (
        market["id"],
        market["baseId"],
        market["quoteId"],
    ):
        raise ValueError("Poloniex did not return rules for the selected pair.")
    if row.get("state") != "NORMAL" or (number(row.get("tradableStartTime")) or 0) > exchange.milliseconds():
        raise ValueError("Poloniex market orders are unavailable for this pair.")
    limits = row.get("symbolTradeLimit")
    if not isinstance(limits, dict) or limits.get("symbol") not in (None, market["id"]):
        raise ValueError("Poloniex did not report valid market limits.")
    digits = limits.get("amountScale" if side == "buy" else "quantityScale")
    value = Decimal(str(amount))
    if type(digits) is not int or not 0 <= digits <= 30 or value.normalize().as_tuple().exponent < -digits:
        raise ValueError("Order exceeds the Poloniex market precision.")
    minimum, maximum = (number(limits.get(key)) for key in ("minAmount", "maxAmount"))
    if minimum is None or minimum < 0 or (maximum is not None and maximum < 0):
        raise ValueError("Poloniex did not report valid quote limits.")
    cost = {"min": minimum or None, "max": maximum or None}
    if side == "buy":
        if amount < minimum or (maximum and amount > maximum):
            raise ValueError("Quote budget is outside the Poloniex market limits.")
    else:
        minimum, maximum = (number(limits.get(key)) for key in ("minQuantity", "maxQuantity"))
        if minimum is None or minimum < 0 or (maximum is not None and maximum < 0):
            raise ValueError("Poloniex did not report valid base quantity limits.")
        if amount < minimum or (maximum and amount > maximum):
            raise ValueError("Quantity is outside the Poloniex market limits.")
    return format(value.normalize(), "f"), {"cost": cost}


def submit_market(exchange, market, side, amount, client_id):
    """Submit once with explicit SPOT scope, no borrowing and native sizing units."""
    if not isinstance(client_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", client_id):
        raise ccxt.InvalidOrder("Invalid Poloniex client order ID.")
    try:
        size, _ = market_terms(exchange, market, side, amount)
    except (ValueError, ccxt.NetworkError) as error:
        raise ccxt.InvalidOrder("Poloniex market rules could not be satisfied.") from error
    row = exchange.privatePostOrders(
        {
            "symbol": market["id"],
            "side": side.upper(),
            "type": "MARKET",
            "timeInForce": "IOC",
            "accountType": "SPOT",
            "allowBorrow": False,
            "clientOrderId": client_id,
            "amount" if side == "buy" else "quantity": size,
        }
    )
    try:
        if not isinstance(row, dict) or row.get("clientOrderId") != client_id:
            raise ValueError("Poloniex did not acknowledge the submitted client order ID.")
        order_id = identity(row.get("id"))
    except ccxt.ExchangeError as error:
        raise ValueError("Poloniex did not confirm a usable order ID.") from error
    if int(order_id) <= 0:
        raise ValueError("Invalid Poloniex native order ID.")
    return {"id": order_id, "clientOrderId": client_id}


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
    """Recover a reviewed API-origin cash order through its exact client ID."""
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
        or row.get("side") not in ("BUY", "SELL")
        or row.get("orderSource") != "API"
        or not (
            (
                row.get("type") == "LIMIT"
                and row.get("timeInForce") == "GTC"
                and (number(row.get("price")) or 0) > 0
                and (number(row.get("quantity")) or 0) > 0
            )
            or (
                row.get("type") == "MARKET"
                and row.get("timeInForce") == "IOC"
                and (number(row.get("amount" if row["side"] == "BUY" else "quantity")) or 0) > 0
            )
        )
    ):
        raise ValueError("Poloniex order evidence differs from the reviewed cash spot submission.")
    identity(row.get("createTime"))
    return [parse_order(exchange, row, market)]
