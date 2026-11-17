"""Bitget Classic spot order pages using exact native order IDs."""

import re

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.venue_history import identity

OPEN = {"new", "live", "partially_filled"}
TERMINAL = {"filled", "cancelled", "canceled"}
LIMIT = 100


def order_rows(response, limit):
    """Require a successful Classic spot order response with a bounded list."""
    rows = response.get("data") if isinstance(response, dict) and response.get("code") == "00000" else None
    if not isinstance(rows, list) or len(rows) > limit or any(not isinstance(row, dict) for row in rows):
        raise ccxt.ExchangeError("Invalid Bitget Classic spot order page.")
    return rows


def parse_order(exchange, row, market):
    """Normalize the market casing and leave fee evidence to the exact-order fills."""
    order = {**row, "symbol": market["id"], "feeDetail": None}
    return exchange.parse_order(order, market)


def lookup_order(exchange, client_id, symbol):
    """Match one Classic spot limit from Bitget's clientOid detail endpoint."""
    if not isinstance(client_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", client_id):
        raise ValueError("Invalid persisted Bitget client order ID.")
    market = exchange.market(symbol)
    try:
        rows = order_rows(exchange.privateSpotGetV2SpotTradeOrderInfo({"clientOid": client_id}), 1)
    except ccxt.OrderNotFound:
        return []
    if not rows:
        return []
    row = rows[0]
    instrument = row.get("symbol")
    if (
        row.get("clientOid") != client_id
        or not isinstance(instrument, str)
        or instrument.upper() != market["id"]
        or row.get("status") not in OPEN | TERMINAL
        or row.get("orderType") != "limit"
        or row.get("tpslType") != "normal"
        or row.get("orderSource") != "normal"
        or row.get("enterPointSource") != "API"
        or row.get("force") not in (None, "", "gtc", "GTC")
        or any(
            row.get(key) not in (None, "") and number(row[key]) != 0
            for key in ("triggerPrice", "presetTakeProfitPrice", "presetStopLossPrice")
        )
        or (number(row.get("size")) or 0) <= 0
        or (number(row.get("price")) or 0) <= 0
    ):
        raise ValueError("Bitget order evidence differs from the reviewed Classic spot limit submission.")
    order_id = identity(row.get("orderId"))
    identity(row.get("cTime"))
    if int(order_id) <= 0:
        raise ValueError("Invalid Bitget native order ID.")
    order = parse_order(exchange, row, market)
    order["id"] = order_id
    return [order]


def discover_page(exchange, recent, cursor, start, end):
    """Read ordinary spot orders and advance the native idLessThan boundary."""
    request = {"tpslType": "normal", "limit": LIMIT}
    after = cursor.get("after")
    if after:
        request["idLessThan"] = after
    if recent:
        request.update(startTime=start, endTime=end - 1)
    read = (
        exchange.privateSpotGetV2SpotTradeHistoryOrders
        if recent
        else exchange.privateSpotGetV2SpotTradeUnfilledOrders
    )
    rows = order_rows(read(request), LIMIT)
    keys = [identity(row.get("orderId")) for row in rows]
    if len(set(keys)) != len(keys) or (after and any(int(key) >= int(after) for key in keys)):
        raise ccxt.ExchangeError("Bitget order IDs did not advance.")
    items = []
    for row in rows:
        if (
            row.get("tpslType") not in (None, "", "normal")
            or row.get("orderType") not in ("market", "limit")
            or row.get("orderSource") not in (None, "", "normal", "market")
        ):
            continue
        if row.get("status") not in (TERMINAL if recent else OPEN):
            raise ccxt.ExchangeError("Unexpected Bitget order state in the selected stream.")
        stamp = number(row.get("cTime"))
        if recent and (stamp is None or not start <= stamp < end):
            raise ccxt.ExchangeError("Bitget order is outside the selected creation window.")
        symbol = row.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise ccxt.ExchangeError("Missing Bitget spot market.")
        market = exchange.safe_market(symbol.upper(), marketType="spot")
        if not market.get("spot"):
            continue
        items.append(parse_order(exchange, row, market))
    after = min(keys, key=int) if keys else None
    return items, {"after": after} if after else {}, not rows, len(rows) - len(items)
