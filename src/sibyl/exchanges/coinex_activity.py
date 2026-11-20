"""CoinEx v2 cash spot order and fill reads using explicit native pagination.

Order history has no date filter, so recent discovery scans bounded native
pages and filters creation time locally. Every request pins market_type=SPOT.
Recovery examines pending and finished pages before accepting one saved client
ID, and native fill identities are shared by Account history and Trade.
"""

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation

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


def market_order_amount(exchange, market, amount) -> str:
    """Read current exact-market rules and preserve the reviewed base amount."""
    rows = data(exchange.v2PublicGetSpotMarket({"market": market["id"]}))
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("CoinEx did not return rules for the selected pair.")
    rules = rows[0]
    if (rules.get("market"), rules.get("base_ccy"), rules.get("quote_ccy")) != (
        market["id"],
        market["baseId"],
        market["quoteId"],
    ):
        raise ValueError("CoinEx returned rules for a different pair.")
    if rules.get("status") != "online" or rules.get("is_api_trading_available") is not True:
        raise ValueError("Spot market orders are unavailable for this CoinEx pair.")
    digits = rules.get("base_ccy_precision")
    if type(digits) is not int or not 0 <= digits <= 30:
        raise ValueError("CoinEx did not report valid base quantity precision.")
    quantity = Decimal(str(amount))
    precise = exchange.amount_to_precision(market["symbol"], amount)
    if Decimal(precise) != quantity or quantity.normalize().as_tuple().exponent < -digits:
        raise ValueError("Quantity exceeds the CoinEx market's base precision.")
    try:
        minimum = Decimal(str(rules.get("min_amount")))
    except InvalidOperation as error:
        raise ValueError("CoinEx did not report a valid minimum base quantity.") from error
    if not minimum.is_finite() or minimum < 0:
        raise ValueError("CoinEx did not report a valid minimum base quantity.")
    if quantity < minimum:
        raise ValueError(f"Order is below the CoinEx minimum base quantity of {minimum}.")
    return precise


def market_order_ack(exchange, market, request, response) -> dict:
    """Require native identity and original terms before attaching the acknowledgment."""
    try:
        row = data(response)
        fields = ("market", "market_type", "side", "type", "ccy", "client_id")
        if (
            not isinstance(row, dict)
            or not cash_order(row)
            or any(row.get(field) != request[field] for field in fields)
            or Decimal(str(row.get("amount"))) != Decimal(request["amount"])
        ):
            raise ValueError("CoinEx did not confirm the original market order terms.")
        order_id = identity(row.get("order_id"))
        if int(order_id) <= 0:
            raise ValueError("Invalid CoinEx order identity.")
        parsed = exchange.parse_order(row, market)
    except (ccxt.ExchangeError, InvalidOperation) as error:
        raise ValueError("CoinEx did not confirm usable market order details.") from error
    parsed["id"] = order_id
    return parsed


def market_quantities(row, base_id) -> dict:
    """Retain fills and cost, and use original sizing only with explicit base units."""
    base_sized = base_id is not None and row.get("ccy") == base_id
    filled, cost = number(row.get("filled_amount")), number(row.get("filled_value"))
    return {
        "amount": number(row.get("amount")) if base_sized else None,
        "remaining": number(row.get("unfilled_amount")) if base_sized else None,
        "filled": filled,
        "cost": cost,
        "average": cost / filled if filled and filled > 0 and cost is not None else None,
    }


def _finished_market_status(row, base_id) -> str:
    """Resolve a statusless finished market row when base quantities agree."""
    if row.get("ccy") != base_id:
        return "unknown"
    try:
        amount, filled, left = (
            Decimal(str(row.get(key))) for key in ("amount", "filled_amount", "unfilled_amount")
        )
    except InvalidOperation:
        return "unknown"
    if not (amount.is_finite() and filled.is_finite() and left.is_finite()):
        return "unknown"
    if not (filled > 0 and left >= 0 and amount - filled == left):
        return "unknown"
    return "canceled" if left else "closed"


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
            parsed["status"] = _finished_market_status(row, market["baseId"])
        else:
            parsed["status"] = "canceled" if remaining > 0 else "closed"
    else:
        parsed["status"] = "open"
    kind = row["type"]
    if kind in INSTRUCTIONS:
        parsed.update(type="limit", timeInForce=INSTRUCTIONS[kind])
    elif kind == "market":
        parsed.update(market_quantities(row, market["baseId"]))
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
            or row.get("type") not in ("limit", "market")
            or row.get("side") not in ("buy", "sell")
            or row.get("is_hide") not in (None, False)
            or (number(row.get("amount")) or 0) <= 0
        ):
            raise ValueError("CoinEx order evidence differs from the reviewed spot order.")
        if row["type"] == "market":
            if row.get("ccy") != market["baseId"] or row.get("stp_mode") not in (None, ""):
                raise ValueError(
                    "CoinEx market recovery requires the original base currency and ordinary cash terms."
                )
        elif row.get("ccy") not in (None, "", market["baseId"]) or (number(row.get("price")) or 0) <= 0:
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
