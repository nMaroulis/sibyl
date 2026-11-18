"""Native BitMart v4 spot activity with bounded date windows and exact order reads.

The v4 query endpoints use authenticated POST requests to read account data.
Capped lists have no continuation token, so saturated ranges split without
advancing over timestamp ties. One-order execution lists page locally by their
native IDs. All paths require reported spot scope and strip native metadata.
"""

import re

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.history import TradePage, normalize_trade
from sibyl.exchanges.venue_history import identity, rows_list

DAY_MS = 86_400_000
ORDER_LIMIT = 200
OPEN = {"new", "partially_filled"}
TERMINAL = {"filled", "canceled", "partially_canceled"}
INSTRUCTIONS = {"limit": "GTC", "limit_maker": "PO", "ioc": "IOC"}


def native_id(value) -> str:
    """Keep numeric or opaque native IDs exact, rejecting floats and control characters."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (str, int))
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", str(value))
        or (str(value).isdecimal() and int(value) <= 0)
    ):
        raise ccxt.ExchangeError("Invalid BitMart native identity.")
    return str(value)


def data(response):
    """Require the native success envelope before accepting any order or fill observation."""
    if not isinstance(response, dict) or str(response.get("code")) != "1000" or "data" not in response:
        raise ccxt.ExchangeError("Invalid BitMart activity response.")
    return response["data"]


def cash_order(row):
    """Select regular cash spot orders from the account's reported native mode."""
    return row.get("orderMode") == "spot" and row.get("type") in {*INSTRUCTIONS, "market"}


def parse_order(exchange, row, market):
    """Normalize an explicitly reported regular spot lifecycle observation."""
    if row.get("state") not in OPEN | TERMINAL:
        raise ccxt.ExchangeError("Unknown BitMart spot order state.")
    parsed = exchange.parse_order(row, market)
    parsed["id"] = native_id(row.get("orderId"))
    return parsed


def read_window(read, params, windows, limit):
    """Read a half-open range with boundary overlap and split saturated responses."""
    (lower, upper), *pending = windows
    if not 0 < lower < upper:
        raise ValueError("Invalid BitMart activity window.")
    # Both timestamp boundaries stay covered if the venue includes or excludes endpoints.
    request_start = max(1, lower - 1)
    rows = rows_list(
        data(read({**params, "startTime": request_start, "endTime": upper, "limit": limit})), limit
    )
    stamps = [int(identity(row.get("createTime"))) for row in rows]
    if any(not request_start <= stamp <= upper for stamp in stamps):
        raise ccxt.ExchangeError("BitMart activity lies outside the selected native window.")
    if len(rows) == limit:
        if upper - lower <= 1:
            raise ccxt.NotSupported("BitMart timestamp boundary exceeds the reviewed page capacity.")
        middle = (lower + upper) // 2
        return [], [[lower, middle], [middle, upper], *pending]
    return [row for row, stamp in zip(rows, stamps, strict=True) if lower <= stamp < upper], pending


def discover_page(exchange, stream, cursor, start, end):
    """Read account-wide open or recent spot orders through durable time-window splits."""
    recent = stream == "recent"
    windows = cursor.get("windows") or [[start if recent else 1, end]]
    read = (
        exchange.privatePostSpotV4QueryHistoryOrders if recent else exchange.privatePostSpotV4QueryOpenOrders
    )
    rows, pending = read_window(read, {"orderMode": "spot"}, windows, ORDER_LIMIT)
    orders, keys = [], set()
    for row in rows:
        key = native_id(row.get("orderId"))
        if key in keys:
            raise ccxt.ExchangeError("Duplicate BitMart order identity.")
        keys.add(key)
        if not cash_order(row):
            continue
        instrument = row.get("symbol")
        if not isinstance(instrument, str) or not instrument:
            raise ccxt.ExchangeError("Missing BitMart order instrument.")
        market = exchange.safe_market(instrument, marketType="spot")
        if not market.get("spot"):
            continue
        if row.get("state") not in (TERMINAL if recent else OPEN):
            raise ccxt.ExchangeError("Unexpected BitMart order state in the selected stream.")
        orders.append(parse_order(exchange, row, market))
    return orders, {"windows": pending} if pending else {}, not pending, len(rows) - len(orders)


def lookup_order(exchange, client_id, symbol):
    """Recover a reviewed spot limit from the exact client-ID query and original terms."""
    if not isinstance(client_id, str) or not re.fullmatch(r"[A-Za-z0-9]{1,32}", client_id):
        raise ValueError("Invalid persisted BitMart client order ID.")
    market = exchange.market(symbol)
    try:
        row = data(exchange.privatePostSpotV4QueryClientOrder({"clientOrderId": client_id}))
    except ccxt.OrderNotFound:
        return []
    if (
        not isinstance(row, dict)
        or not cash_order(row)
        or row.get("clientOrderId") != client_id
        or row.get("symbol") != market["id"]
        or row.get("type") != "limit"
        or row.get("state") not in OPEN | TERMINAL
        or (number(row.get("size")) or 0) <= 0
        or (number(row.get("price")) or 0) <= 0
        or any(
            row.get(key) not in (None, "") and number(row[key]) != 0
            for key in ("trigger_price", "triggerPrice")
        )
    ):
        raise ValueError("BitMart order evidence differs from the reviewed spot GTC limit.")
    identity(row.get("createTime"))
    return [parse_order(exchange, row, market)]


def normalize_fill(exchange, row, market, order_id=None):
    """Keep the exact native execution identity and only explicitly reported fee fields."""
    native_order = native_id(row.get("orderId"))
    if (
        row.get("orderMode") != "spot"
        or row.get("symbol") != market["id"]
        or row.get("side") not in ("buy", "sell")
        or (order_id is not None and native_order != order_id)
    ):
        raise ccxt.ExchangeError("Unexpected BitMart execution market, order or cash spot scope.")
    fill = normalize_trade(exchange.parse_trade(row, market))
    fill.update(id=native_id(row.get("tradeId")), order=native_order)
    # CCXT can infer a missing currency from the trade side; retain the reported facts.
    fee = {"currency": row.get("feeCoinName") or None, "cost": number(row.get("fee"))}
    fill.update(fee=fee, fees=[fee])
    return fill


def fetch_fill_page(exchange, symbol, cursor, limit, *, order_id=None):
    """Read exact-order executions or one bounded selected-market history window."""
    market = exchange.market(symbol)
    if order_id is not None:
        order_id = native_id(order_id)
        rows = rows_list(data(exchange.privatePostSpotV4QueryOrderTrades({"orderId": order_id})), 10_000)
        fills = [normalize_fill(exchange, row, market, order_id) for row in rows]
        keys = [row["id"] for row in fills]
        if len(set(keys)) != len(keys):
            raise ccxt.ExchangeError("Duplicate BitMart order execution identity.")
        after = native_id(cursor["after_id"]) if cursor.get("after_id") else ""
        remaining = sorted((row for row in fills if row["id"] > after), key=lambda row: row["id"])
        selected = remaining[:limit]
        return TradePage(
            selected, {"after_id": selected[-1]["id"] if selected else after}, len(remaining) <= limit
        )
    now = exchange.milliseconds()
    start, end = cursor.get("start", max(1, now - 7 * DAY_MS)), cursor.get("end", now + 1)
    windows = cursor.get("windows") or [[start, end]]
    rows, pending = read_window(
        exchange.privatePostSpotV4QueryTrades, {"symbol": market["id"], "orderMode": "spot"}, windows, limit
    )
    fills = [normalize_fill(exchange, row, market) for row in rows]
    keys = [(row["id"], row["order"]) for row in fills]
    if len(set(keys)) != len(keys):
        raise ccxt.ExchangeError("Duplicate BitMart spot execution identity.")
    following = (
        {"start": start, "end": end, "windows": pending} if pending else {"start": max(1, end - DAY_MS)}
    )
    return TradePage(fills, following, not pending)
