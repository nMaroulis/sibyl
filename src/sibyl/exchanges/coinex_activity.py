"""CoinEx v2 cash spot order and fill reads using explicit native pagination.

Order history has no date filter, so recent discovery scans bounded native
pages and filters creation time locally. Every request pins market_type=SPOT.
Recovery examines pending and finished pages before accepting one saved client
ID, and native fill identities are shared by Account history and Trade.
"""

import hashlib
import json
import re

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.history import TradePage, normalize_trade
from sibyl.exchanges.venue_history import identity

DAY_MS = 86_400_000
ORDER_LIMIT = 100
STATUS = {
    "open": "open",
    "part_filled": "open",
    "filled": "closed",
    "part_canceled": "canceled",
    "canceled": "canceled",
}
INSTRUCTIONS = {"limit": "GTC", "maker_only": "PO", "ioc": "IOC", "fok": "FOK"}


def data(response):
    """Require CoinEx's native success code before considering the response payload."""
    if not isinstance(response, dict) or str(response.get("code")) != "0" or "data" not in response:
        raise ccxt.ExchangeError("Invalid CoinEx spot response.")
    return response["data"]


def read_page(read, params, cursor, limit, *, key):
    """Validate native has_next and reject duplicate or repeated page identities."""
    page = cursor.get("page", 1)
    response = read({**params, "page": page, "limit": limit})
    rows = data(response)
    pagination = response.get("pagination")
    if (
        not isinstance(rows, list)
        or len(rows) > limit
        or any(not isinstance(row, dict) for row in rows)
        or not isinstance(pagination, dict)
        or not isinstance(pagination.get("has_next"), bool)
        or (not rows and pagination["has_next"])
    ):
        raise ccxt.ExchangeError("Invalid CoinEx spot pagination.")
    keys = sorted((identity(row.get(key)), identity(row.get("order_id"))) for row in rows)
    if len(set(keys)) != len(keys):
        raise ccxt.ExchangeError("Duplicate CoinEx spot identities.")
    digest = hashlib.sha256(json.dumps(keys).encode()).hexdigest()
    if rows and digest == cursor.get("digest"):
        raise ccxt.ExchangeError("CoinEx returned a repeated native page.")
    following = {"page": page + 1, "digest": digest} if pagination["has_next"] else {}
    return rows, following


def cash_order(row):
    """Recognize ordinary cash spot orders without trigger or margin instructions."""
    return (
        row.get("market_type") == "SPOT"
        and row.get("type") in {*INSTRUCTIONS, "market"}
        and not row.get("margin_market")
        and not row.get("stop_id")
        and not row.get("trigger_price")
    )


def parse_order(exchange, row, market, *, recent=False):
    """Normalize native status and amount units, including quote-sized market requests."""
    parsed = exchange.parse_order(row, market)
    parsed["id"] = identity(row.get("order_id"))
    state = row.get("status")
    if state is not None:
        if state not in STATUS:
            raise ccxt.ExchangeError("Unknown CoinEx order status.")
        parsed["status"] = STATUS[state]
        if recent and parsed["status"] == "open":
            raise ccxt.ExchangeError("Unexpected open CoinEx order in finished history.")
        if not recent and parsed["status"] != "open":
            raise ccxt.ExchangeError("Unexpected terminal CoinEx order in pending history.")
    elif recent:
        remaining = number(row.get("unfilled_amount"))
        if remaining is None or remaining < 0:
            raise ccxt.ExchangeError("Missing CoinEx finished-order remainder.")
        if row["type"] == "market":
            parsed["status"] = "unknown"
        else:
            parsed["status"] = "canceled" if remaining > 0 else "closed"
    else:
        parsed["status"] = "open"
    kind = row["type"]
    if kind in INSTRUCTIONS:
        parsed.update(type="limit", timeInForce=INSTRUCTIONS[kind])
    elif kind == "market" and row.get("ccy") != market["baseId"]:
        parsed.update(amount=None, remaining=None)
    return parsed


def order_page(exchange, recent, cursor, *, instrument=None, client_id=None):
    """Read one account or exact-instrument page from separate pending/finished endpoints."""
    params = {"market_type": "SPOT"}
    if instrument:
        params["market"] = instrument
    if client_id and not recent:
        params["client_id"] = client_id
    read = exchange.v2PrivateGetSpotFinishedOrder if recent else exchange.v2PrivateGetSpotPendingOrder
    return read_page(read, params, cursor, ORDER_LIMIT, key="order_id")


def discover_page(exchange, stream, cursor, start, end):
    """Import native open orders or creation-window matches from bounded finished pages."""
    recent = stream == "recent"
    rows, following = order_page(exchange, recent, cursor)
    selected = []
    for row in rows:
        if not cash_order(row):
            continue
        instrument = row.get("market")
        if not isinstance(instrument, str) or not instrument:
            raise ccxt.ExchangeError("Missing CoinEx spot instrument.")
        market = exchange.safe_market(instrument, marketType="spot")
        if not market.get("spot"):
            continue
        created = int(identity(row.get("created_at")))
        if recent and not start <= created < end:
            continue
        selected.append(parse_order(exchange, row, market, recent=recent))
    return selected, following, not following, len(rows) - len(selected)


def lookup_page(exchange, client_id, symbol, cursor):
    """Inspect all bounded pending and finished matches for one reviewed client ID."""
    if not isinstance(client_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", client_id):
        raise ValueError("Invalid persisted CoinEx client order ID.")
    market = exchange.market(symbol)
    recent = cursor.get("phase") == "finished"
    rows, following = order_page(exchange, recent, cursor, instrument=market["id"], client_id=client_id)
    candidates = []
    for row in rows:
        if row.get("market") != market["id"]:
            raise ccxt.ExchangeError("CoinEx recovery returned a different instrument.")
        if not recent and row.get("client_id") != client_id:
            raise ccxt.ExchangeError("CoinEx ignored the pending client-ID filter.")
        if row.get("client_id") != client_id:
            continue
        if (
            not cash_order(row)
            or row.get("type") != "limit"
            or row.get("ccy") not in (None, "", market["baseId"])
            or row.get("is_hide") not in (None, False)
            or (number(row.get("amount")) or 0) <= 0
            or (number(row.get("price")) or 0) <= 0
        ):
            raise ValueError("CoinEx order evidence differs from the reviewed spot GTC limit.")
        candidates.append(parse_order(exchange, row, market, recent=recent))
    if following:
        return candidates, {**following, "phase": "finished" if recent else "pending"}, False
    if not recent:
        return candidates, {"phase": "finished"}, False
    return candidates, {}, True


def fetch_fill_page(exchange, symbol, cursor, limit, *, order_id=None):
    """Read exact-order or dated selected-market fills with shared native deal/order identities."""
    market = exchange.market(symbol)
    params = {"market": market["id"], "market_type": "SPOT"}
    if order_id is not None:
        order_id = identity(order_id)
        params["order_id"] = order_id
        read = exchange.v2PrivateGetSpotOrderDeals
    else:
        now = exchange.milliseconds()
        start, end = cursor.get("start", max(1, now - 30 * DAY_MS)), cursor.get("end", now + 1)
        params.update(start_time=start, end_time=end - 1)
        read = exchange.v2PrivateGetSpotUserDeals
    rows, following = read_page(read, params, cursor, limit, key="deal_id")
    fills = []
    for row in rows:
        native_id, native_order = identity(row.get("deal_id")), identity(row.get("order_id"))
        if (
            row.get("market") != market["id"]
            or row.get("market_type") not in (None, "SPOT")
            or row.get("margin_market")
            or row.get("position_id") is not None
            or row.get("side") not in ("buy", "sell")
            or (order_id is not None and native_order != order_id)
        ):
            raise ccxt.ExchangeError("Unexpected CoinEx execution market, order or cash spot scope.")
        stamp = int(identity(row.get("created_at")))
        if order_id is None and not start <= stamp < end:
            raise ccxt.ExchangeError("CoinEx fill lies outside the fixed history window.")
        fill = normalize_trade(exchange.parse_trade(row, market))
        fill.update(id=native_id, order=native_order, timestamp=stamp)
        fills.append(fill)
    complete = not following
    if order_id is None:
        following = (
            {**following, "start": start, "end": end} if following else {"start": max(1, end - DAY_MS)}
        )
    return TradePage(fills, following, complete)
