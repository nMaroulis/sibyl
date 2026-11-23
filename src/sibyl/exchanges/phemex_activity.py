"""Phemex spot-only order and execution reads using reviewed native endpoints.

The spot and margin APIs are separate. Discovery requires selected exact pairs;
one market/page is read per checkpoint. Native Ev/Ep values use provider scales,
nanosecond identities stay integers, and quote budgets never become fill costs.
"""

import hashlib
import json
import re

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.history import TradePage, normalize_trade
from sibyl.exchanges.venue_history import identity, rows_list

DAY_MS = 86400000
OPEN = {"Created", "New", "PartiallyFilled"}
TERMINAL = {"Filled", "Canceled", "Rejected", "Suspended", "Deactivated"}


def key(value):
    """Keep native UUID/opaque identities exact without accepting floats or control characters."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ccxt.ExchangeError("Invalid Phemex native identity.")
    value = str(value)
    if not value or len(value) > 100 or any(ord(char) < 32 for char in value):
        raise ccxt.ExchangeError("Invalid Phemex native identity.")
    return value


def rows(response, maximum):
    """Accept documented raw lists or successful code/data spot envelopes."""
    if isinstance(response, dict):
        if str(response.get("code")) != "0" or "data" not in response:
            raise ccxt.ExchangeError("Invalid Phemex spot response.")
        response = response["data"]
    if isinstance(response, dict):
        response = response.get("rows")
    return rows_list(response, maximum)


def scaled_currency(exchange, value, currency):
    """Decode a native currency value only when its reported value scale is known."""
    raw = number(value)
    if raw is None:
        return None
    if raw == 0:
        return 0.0
    metadata = exchange.currencies.get(currency, {})
    scale = metadata.get("valueScale")
    if type(scale) is not int or not 0 <= scale <= 18:
        return None
    return number(exchange.from_en(str(value), scale))


def regular_order(row):
    """Select regular spot limits/markets without stop or derivative instructions."""
    return (
        row.get("ordType") in {"Limit", "Market"}
        and row.get("stopDirection") in (None, "", "UNSPECIFIED")
        and row.get("stopPxEp") in (None, "", 0, "0")
        and not any(row.get(name) for name in ("posSide", "closedPnl", "closedPnlRv", "marginMode"))
    )


def parse_order(exchange, row, market):
    """Normalize native spot quantities and creation time, preserving zero remainders."""
    parsed = exchange.parse_order(row, market)
    parsed["id"] = key(row.get("orderID"))
    if row.get("createTimeNs") is not None:
        parsed["timestamp"] = int(identity(row["createTimeNs"])) // 1000000
    for target, fields in {
        "filled": ("cumBaseQtyEv", "cumBaseValueEv", "cumBaseAmountEv"),
        "cost": ("cumQuoteQtyEv", "cumQuoteValueEv", "cumQuoteAmountEv"),
    }.items():
        value = next((row[name] for name in fields if row.get(name) is not None), None)
        parsed[target] = (
            number(exchange.from_ev(str(value), market))
            if target == "filled" and value is not None
            else scaled_currency(exchange, value, market["quote"])
        )
    if row.get("qtyType") == "ByQuote":
        parsed.update(amount=None, remaining=None)
    elif row.get("leavesBaseQtyEv") is not None:
        parsed["remaining"] = number(exchange.from_ev(str(row["leavesBaseQtyEv"]), market))
    return parsed


def next_offset(raw, cursor, identity_field):
    """Advance native offset pages and detect repeated or duplicate observations."""
    keys = [key(row.get(identity_field)) for row in raw]
    if len(set(keys)) != len(keys):
        raise ccxt.ExchangeError("Duplicate Phemex native identities.")
    digest = hashlib.sha256(json.dumps(sorted(keys)).encode()).hexdigest()
    if raw and digest == cursor.get("digest"):
        raise ccxt.ExchangeError("Phemex returned a repeated native page.")
    return {"offset": cursor.get("offset", 0) + len(raw), "digest": digest}


def discover_page(exchange, stream, cursor, start, end, symbols):
    """Read one selected pair's open snapshot or recent native offset page."""
    if not symbols:
        raise ValueError("Choose exact Phemex pairs for open and recent order discovery.")
    index = cursor.get("market", 0)
    if type(index) is not int or index < 0:
        raise ValueError("Invalid Phemex market checkpoint.")
    if index >= len(symbols):
        return [], {}, True, 0
    market = exchange.market(symbols[index])
    recent = stream == "recent"
    request = {"symbol": market["id"]}
    if recent:
        request.update(start=max(0, start - 1), end=end, offset=cursor.get("offset", 0), limit=100)
        raw = rows(exchange.privateGetApiDataSpotsOrders(request), 100)
        page = next_offset(raw, cursor, "orderID")
    else:
        raw = rows(exchange.privateGetSpotOrders(request), 1000)
        next_offset(raw, {}, "orderID")
    selected = []
    for row in raw:
        if row.get("symbol") != market["id"]:
            raise ccxt.ExchangeError("Phemex returned a different spot pair.")
        if not regular_order(row):
            continue
        if row.get("ordStatus") not in OPEN | TERMINAL or (not recent and row["ordStatus"] not in OPEN):
            raise ccxt.ExchangeError("Unexpected Phemex order state.")
        if recent and not start * 1000000 <= int(identity(row.get("createTimeNs"))) < end * 1000000:
            continue
        selected.append(parse_order(exchange, row, market))
    following = {"market": index, **page} if recent and len(raw) == 100 else {"market": index + 1}
    complete = following["market"] >= len(symbols)
    return selected, following if not complete else {}, complete, len(raw) - len(selected)


def lookup_order(exchange, client_id, symbol):
    """Read the exact clOrdID and require base-sized spot GTC limit or IOC market terms."""
    if not isinstance(client_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", client_id):
        raise ValueError("Invalid persisted Phemex client order ID.")
    market = exchange.market(symbol)
    try:
        found = rows(
            exchange.privateGetApiDataSpotsOrdersByOrderId({"symbol": market["id"], "clOrdID": client_id}), 1
        )
    except ccxt.OrderNotFound:
        return []
    if not found:
        return []
    row = found[0]
    if (
        not regular_order(row)
        or row.get("clOrdID") != client_id
        or row.get("symbol") != market["id"]
        or row.get("qtyType") != "ByBase"
        or (number(row.get("baseQtyEv")) or 0) <= 0
        or (row.get("ordType"), row.get("timeInForce"))
        not in {
            ("Limit", "GoodTillCancel"),
            ("Market", "ImmediateOrCancel"),
        }
        or row.get("ordStatus") not in OPEN | TERMINAL
        or row.get("side") not in {"Buy", "Sell"}
    ):
        raise ValueError("Phemex evidence differs from the reviewed base-sized spot order.")
    identity(row.get("createTimeNs"))
    return [parse_order(exchange, row, market)]


def normalize_fill(exchange, row, market, order_id=None):
    """Keep exact spot execution IDs, currency-scaled fees and nanosecond fill times."""
    if (
        row.get("symbol") != market["id"]
        or row.get("tradeType") != "Trade"
        or row.get("side") not in {"Buy", "Sell"}
        or (order_id is not None and key(row.get("orderID")) != order_id)
    ):
        raise ccxt.ExchangeError("Unexpected Phemex spot execution scope.")
    fill = normalize_trade(exchange.parse_trade(row, market))
    currency = row.get("feeCurrency")
    currency = (
        exchange.safe_currency_code(currency)
        if isinstance(currency, str) and currency and not currency.isdecimal()
        else None
    )
    fee = {"currency": currency, "cost": scaled_currency(exchange, row.get("execFeeEv"), currency)}
    if (number(row.get("ptFeeRv")) or 0) != 0:
        fee = {"currency": None, "cost": None}
    fill.update(
        id=key(row.get("execId")),
        order=key(row.get("orderID")),
        timestamp=int(identity(row.get("transactTimeNs"))) // 1000000,
        cost=scaled_currency(exchange, row.get("execQuoteQtyEv"), market["quote"]),
        fee=fee,
        fees=[fee],
    )
    return fill


def fetch_fill_page(exchange, symbol, cursor, limit, *, order_id=None):
    """Read exact-order executions or a frozen seven-day selected-pair history page."""
    market = exchange.market(symbol)
    if order_id is not None:
        order_id = key(order_id)
        raw = rows(
            exchange.privateGetApiDataSpotsTradesByOrderId({"symbol": market["id"], "orderID": order_id}),
            10000,
        )
        parsed = [normalize_fill(exchange, row, market, order_id) for row in raw]
        keys = [row["id"] for row in parsed]
        if len(keys) != len(set(keys)):
            raise ccxt.ExchangeError("Duplicate Phemex native executions.")
        after = key(cursor["after_id"]) if cursor.get("after_id") else ""
        remaining = sorted((row for row in parsed if row["id"] > after), key=lambda row: row["id"])
        selected = remaining[:limit]
        return TradePage(
            selected, {"after_id": selected[-1]["id"] if selected else after}, len(remaining) <= limit
        )
    end = cursor.get("end", exchange.milliseconds() + 1)
    start = cursor.get("start", max(1, end - 7 * DAY_MS))
    raw = rows(
        exchange.privateGetApiDataSpotsTrades(
            {
                "symbol": market["id"],
                "start": max(0, start - 1),
                "end": end,
                "offset": cursor.get("offset", 0),
                "limit": limit,
            }
        ),
        limit,
    )
    page = next_offset(raw, cursor, "execId")
    parsed = [
        normalize_fill(exchange, row, market)
        for row in raw
        if start * 1000000 <= int(identity(row.get("transactTimeNs"))) < end * 1000000
    ]
    complete = len(raw) < limit
    return TradePage(
        parsed,
        {"start": max(1, end - DAY_MS)} if complete else {**page, "start": start, "end": end},
        complete,
    )
