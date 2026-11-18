"""Reviewed Bitfinex exchange-wallet orders, separate from margin/derivatives.

Native arrays are validated before CCXT parsing. Creation times define recent
queries and recovery windows; the SDK normally exposes update time instead.
Closed-history partial fills have a cancelled remainder, unlike active partial
fills. Capped native ranges split and persist without skipping timestamp ties.
"""

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.venue_history import identity

LIMIT = 100
OPEN_LIMIT = 1000
CASH_TYPES = {"EXCHANGE LIMIT", "EXCHANGE MARKET"}


def arrays(response, maximum, width):
    """Validate a bounded native array response without accepting error envelopes."""
    if (
        not isinstance(response, list)
        or len(response) > maximum
        or any(not isinstance(row, list) or len(row) < width for row in response)
    ):
        raise ccxt.ExchangeError("Invalid or excessive Bitfinex native page.")
    return response


def read_window(read, params, windows, limit, *, timestamp):
    """Split saturated half-open ranges and keep native inclusive endpoints covered."""
    (lower, upper), *pending = windows
    if type(lower) is not int or type(upper) is not int or not 0 < lower < upper:
        raise ValueError("Invalid Bitfinex history range.")
    rows = arrays(read({**params, "start": lower, "end": upper - 1, "limit": limit}), limit, timestamp + 1)
    stamps = [int(identity(row[timestamp])) for row in rows]
    if any(not lower <= stamp < upper for stamp in stamps):
        raise ccxt.ExchangeError("Bitfinex evidence differs from the fixed history range.")
    if len(rows) == limit:
        if upper - lower <= 1:
            raise ccxt.NotSupported("Bitfinex timestamp boundary exceeds the reviewed page capacity.")
        middle = (lower + upper) // 2
        return [], [[lower, middle], [middle, upper], *pending]
    return rows, pending


def cash_order(row):
    """Select ordinary unflagged cash orders without time expiry or linked triggers."""
    return (
        row[8] in CASH_TYPES
        and row[12] in (0, "0")
        and not isinstance(row[12], bool)
        and row[10] in (None, 0)
        and row[25] in (None, 0)
        and all(row[index] in (None, "") or number(row[index]) == 0 for index in (18, 19))
    )


def order_status(value, *, recent):
    """Distinguish cancelled historical remainders from still-active partial fills."""
    if not isinstance(value, str):
        raise ccxt.ExchangeError("Missing Bitfinex order status.")
    if value.startswith("PARTIALLY FILLED"):
        return "canceled" if recent else "open"
    for prefix, state in (
        ("ACTIVE", "open"),
        ("EXECUTED", "closed"),
        ("CANCELED", "canceled"),
        ("INSUFFICIENT BALANCE", "canceled"),
        ("POSTONLY CANCELED", "canceled"),
        ("IOC CANCELED", "canceled"),
        ("FILLORKILL CANCELED", "canceled"),
        ("RSN_", "canceled"),
    ):
        if value.startswith(prefix):
            if (recent and state == "open") or (not recent and state != "open"):
                raise ccxt.ExchangeError("Unexpected Bitfinex order state in the selected stream.")
            return state
    raise ccxt.ExchangeError("Unknown Bitfinex order status.")


def parse_order(exchange, row, market=None, *, recent=False):
    """Preserve exact native IDs and creation time while using native array parsing."""
    arrays([row], 1, 26)
    native_id = identity(row[0])
    created = int(identity(row[4]))
    original = number(row[7])
    if int(native_id) <= 0 or created <= 0 or original is None or original == 0:
        raise ccxt.ExchangeError("Invalid Bitfinex order identity, quantity or creation time.")
    parsed = exchange.parse_order({"result": row}, market)
    parsed.update(id=native_id, timestamp=created, status=order_status(row[13], recent=recent))
    return parsed


def discover_page(exchange, stream, cursor, start, end):
    """Read an open cash snapshot or one restart-safe recent creation-time range."""
    recent = stream == "recent"
    if recent:
        rows, pending = read_window(
            exchange.privatePostAuthROrdersHist,
            {},
            cursor.get("windows") or [[start, end]],
            LIMIT,
            timestamp=4,
        )
        following = {"windows": pending} if pending else {}
    else:
        rows = arrays(exchange.privatePostAuthROrders({}), OPEN_LIMIT, 26)
        following = {}
    arrays(rows, LIMIT if recent else OPEN_LIMIT, 26)
    keys = [identity(row[0]) for row in rows]
    if len(set(keys)) != len(keys):
        raise ccxt.ExchangeError("Duplicate Bitfinex native order IDs.")
    selected = []
    for row in rows:
        if not cash_order(row):
            continue
        market = exchange.safe_market(row[3], marketType="spot")
        if not market.get("spot"):
            continue
        selected.append(parse_order(exchange, row, market, recent=recent))
    return selected, following, not following, len(rows) - len(selected)


def lookup_page(exchange, client_id, symbol, cursor, start, end):
    """Inspect open and bounded closed cash matches before adopting a saved int45 cid."""
    client_id = identity(client_id)
    if not 0 < int(client_id) < 2**45:
        raise ValueError("Invalid persisted Bitfinex int45 client ID.")
    market = exchange.market(symbol)
    recent = cursor.get("phase") == "history"
    if recent:
        rows, pending = read_window(
            exchange.privatePostAuthROrdersSymbolHist,
            {"symbol": market["id"]},
            cursor.get("windows") or [[start, end]],
            LIMIT,
            timestamp=4,
        )
        following = {"phase": "history", "windows": pending} if pending else {}
    else:
        rows = arrays(exchange.privatePostAuthROrdersSymbol({"symbol": market["id"]}), OPEN_LIMIT, 29)
        following = {"phase": "history", "windows": [[start, end]]}
    arrays(rows, LIMIT if recent else OPEN_LIMIT, 29)
    candidates = []
    for row in rows:
        if row[3] != market["id"]:
            raise ccxt.ExchangeError("Bitfinex lookup returned a different instrument.")
        if row[2] is None or identity(row[2]) != client_id:
            continue
        meta = row[31] if len(row) > 31 else None
        if (
            not cash_order(row)
            or row[1] not in (None, 0)
            or row[9] not in (None, "")
            or row[24] not in (None, 0)
            or row[28] != "API>BFX"
            or (meta is not None and not isinstance(meta, dict))
            or (
                isinstance(meta, dict)
                and (meta.get("$F7") not in (None, 0) or meta.get("$F33") not in (None, 0))
            )
        ):
            raise ValueError("Bitfinex evidence differs from the reviewed cash order.")
        candidates.append(parse_order(exchange, row, market, recent=recent))
    return candidates, following, not following


def read_order(exchange, order_id, market):
    """Read an exact active order, then reviewed native closed history on an active miss."""
    order_id = identity(order_id)
    if int(order_id) <= 0:
        raise ValueError("Invalid Bitfinex order ID.")
    params = {"symbol": market["id"], "id": [int(order_id)]}
    rows = arrays(exchange.privatePostAuthROrdersSymbol(params), 1, 26)
    recent = not rows
    if recent:
        rows = arrays(exchange.privatePostAuthROrdersSymbolHist({**params, "limit": 1}), 1, 26)
    if not rows:
        raise ccxt.OrderNotFound("Bitfinex order is unavailable in the reviewed history.")
    row = rows[0]
    if identity(row[0]) != order_id or row[3] != market["id"] or not cash_order(row):
        raise ccxt.ExchangeError("Unexpected Bitfinex cash order identity or instrument.")
    return parse_order(exchange, row, market, recent=recent)
