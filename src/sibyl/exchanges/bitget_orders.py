"""Bitget Classic spot order pages using exact native order IDs."""

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.venue_history import identity

OPEN = {"new", "live", "partially_filled"}
TERMINAL = {"filled", "cancelled", "canceled"}
LIMIT = 100


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
    response = read(request)
    rows = response.get("data") if isinstance(response, dict) and response.get("code") == "00000" else None
    if not isinstance(rows, list) or len(rows) > LIMIT or any(not isinstance(row, dict) for row in rows):
        raise ccxt.ExchangeError("Invalid Bitget Classic spot order page.")
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
        # Exact-order fills supply fee evidence; order summaries can contain empty fee JSON.
        order = {**row, "symbol": symbol.upper(), "feeDetail": None}
        items.append(exchange.parse_order(order, market))
    after = min(keys, key=int) if keys else None
    return items, {"after": after} if after else {}, not rows, len(rows) - len(items)
