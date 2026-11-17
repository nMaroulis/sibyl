"""Native MEXC spot activity reads and bounded time-window pagination."""

import json
import re

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.history import TradePage, normalize_trade
from sibyl.exchanges.venue_history import identity

DAY_MS = 86_400_000
FILL_HISTORY_DAYS = 27
OPEN = {"NEW", "PARTIALLY_FILLED"}
TERMINAL = {"FILLED", "CANCELED", "PARTIALLY_CANCELED"}
TYPES = {"LIMIT", "MARKET", "LIMIT_MAKER", "IMMEDIATE_OR_CANCEL", "FILL_OR_KILL"}
ORDER_LIMIT = 1000


def order_identity(value) -> str:
    """Preserve native numeric and opaque spot IDs without passing through a float."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, str))
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", str(value))
        or (str(value).isdecimal() and int(value) <= 0)
    ):
        raise ccxt.ExchangeError("Invalid MEXC spot identity.")
    return str(value)


def parse_order(exchange, row, market):
    """Preserve the exact ID and supply the SDK's expected native quantity key."""
    parsed = exchange.parse_order({**row, "origQty": row.get("origQty", row.get("Qty"))}, market)
    parsed["id"] = order_identity(row.get("orderId"))
    return parsed


def lookup_order(exchange, client_id, symbol):
    """Read an exact client ID and require plain GTC limit evidence before recovery."""
    if not isinstance(client_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", client_id):
        raise ValueError("Invalid persisted MEXC client order ID.")
    market = exchange.market(symbol)
    try:
        row = exchange.spotPrivateGetOrder({"symbol": market["id"], "origClientOrderId": client_id})
    except ccxt.OrderNotFound:
        return []
    except ccxt.BadRequest as error:
        # The SDK reports MEXC's documented missing-record response as BadRequest.
        try:
            response = json.loads(str(error).removeprefix(f"{exchange.id} "))
        except ValueError:
            response = None
        if isinstance(response, dict) and str(response.get("code")) == "22222":
            return []
        raise
    if (
        not isinstance(row, dict)
        or row.get("symbol") != market["id"]
        or row.get("clientOrderId", row.get("origClientOrderId")) != client_id
        or row.get("origClientOrderId") not in (None, "", client_id)
        or row.get("status") not in OPEN | TERMINAL
        or row.get("type") != "LIMIT"
        or row.get("timeInForce") != "GTC"
        or row.get("orderListId") not in (None, -1, "-1")
        or any(
            row.get(key) not in (None, "") and number(row[key]) != 0 for key in ("stopPrice", "icebergQty")
        )
        or (number(row.get("origQty", row.get("Qty"))) or 0) <= 0
        or (number(row.get("price")) or 0) <= 0
    ):
        raise ValueError("MEXC order evidence differs from the reviewed spot limit submission.")
    identity(row.get("time"))
    parsed = parse_order(exchange, row, market)
    parsed["clientOrderId"] = client_id
    return [parsed]


def _read_rows(rows, limit):
    """Reject malformed or over-capacity native responses as a single invalid page."""
    if not isinstance(rows, list) or len(rows) > limit or any(not isinstance(row, dict) for row in rows):
        raise ccxt.ExchangeError("Invalid MEXC spot activity page.")
    return rows


def _read_window(read, params, windows, limit):
    """Bisect capped half-open ranges to avoid discarding same-time native records."""
    (start, end), *pending = windows
    rows = _read_rows(read({**params, "startTime": start, "endTime": end - 1, "limit": limit}), limit)
    if len(rows) == limit:
        if end - start <= 1:
            raise ccxt.NotSupported("A MEXC timestamp exceeds the reviewed page capacity.")
        middle = (start + end) // 2
        return [], [[start, middle], [middle, end], *pending]
    if any(not start <= int(identity(row.get("time"))) < end for row in rows):
        raise ccxt.ExchangeError("MEXC returned spot activity outside the selected time window.")
    return rows, pending


def discover_page(exchange, stream, cursor, start, end, symbols):
    """Read an account-wide open snapshot or one selected-market history window."""
    open_stream = stream == "open"
    index = cursor.get("market", 0)
    if open_stream:
        rows = _read_rows(exchange.spotPrivateGetOpenOrders({}), ORDER_LIMIT)
        if len(rows) == ORDER_LIMIT:
            raise ccxt.NotSupported("MEXC open-order snapshot reached the reviewed capacity.")
        instrument, following, complete = None, {}, True
    elif index == len(symbols):
        return [], {}, True, 0
    else:
        instrument = exchange.market(symbols[index])["id"]
        rows, pending = _read_window(
            exchange.spotPrivateGetAllOrders,
            {"symbol": instrument},
            cursor.get("windows") or [[start, end]],
            ORDER_LIMIT,
        )
        index += int(not pending)
        following, complete = {"market": index, "windows": pending}, index == len(symbols)
    orders, seen = [], set()
    for row in rows:
        native_market = row.get("symbol")
        if (
            not isinstance(native_market, str)
            or not native_market
            or (instrument and native_market != instrument)
        ):
            raise ccxt.ExchangeError("Unexpected MEXC spot order instrument.")
        key = native_market, order_identity(row.get("orderId"))
        if key in seen:
            raise ccxt.ExchangeError("Duplicate MEXC spot order identity.")
        seen.add(key)
        market = exchange.safe_market(native_market, marketType="spot")
        if not market.get("spot") or row.get("type") not in TYPES:
            continue
        if row.get("status") not in (OPEN if open_stream else OPEN | TERMINAL):
            raise ccxt.ExchangeError("Unexpected MEXC order state in the selected stream.")
        orders.append(parse_order(exchange, row, market))
    return orders, following, complete, len(rows) - len(orders)


def fetch_fill_page(exchange, symbol, cursor, limit, *, order_id=None):
    """Import selected-market fills or exact-order executions with the same native identities."""
    market = exchange.market(symbol)
    now = exchange.milliseconds()
    cutoff = max(1, now - FILL_HISTORY_DAYS * DAY_MS)
    start, end = max(cutoff, cursor.get("start", cutoff)), cursor.get("end", now + 1)
    params = {"symbol": market["id"]}
    if order_id is not None:
        params["orderId"] = order_identity(order_id)
    windows = cursor.get("windows") or [[start, end]]
    if windows[0][0] < now - 28 * DAY_MS:
        raise ccxt.NotSupported("The saved MEXC fill window has aged beyond its reviewed coverage.")
    rows, pending = _read_window(exchange.spotPrivateGetMyTrades, params, windows, limit)
    fills, seen = [], set()
    for row in rows:
        trade_id = order_identity(row.get("id"))
        native_order = order_identity(row.get("orderId"))
        key = trade_id, native_order
        if (
            row.get("symbol") != market["id"]
            or (order_id is not None and native_order != order_id)
            or not isinstance(row.get("isBuyer"), bool)
            or row.get("positionMode") is not None
            or key in seen
        ):
            raise ccxt.ExchangeError("Unexpected market, order or identity in MEXC spot fills.")
        seen.add(key)
        fill = normalize_trade(exchange.parse_trade(row, market))
        fill.update(id=trade_id, order=native_order, side="buy" if row["isBuyer"] else "sell")
        fills.append(fill)
    following = (
        {"start": start, "end": end, "windows": pending} if pending else {"start": max(1, end - DAY_MS)}
    )
    return TradePage(fills, following, not pending)
