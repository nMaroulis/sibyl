"""Gate exact-order cash spot execution reads with explicit wallet and fee scope."""

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.gate_orders import cash_order, next_page
from sibyl.exchanges.history import TradePage, normalize_trade
from sibyl.exchanges.venue_history import identity, rows_list


def fetch_order_fills(exchange, order_id, symbol, cursor, limit):
    """Validate the spot parent, then read one native page of its individual fills.

    The fixed seven-day finish-time window survives pagination. A later pass
    starts a new window. The parent protects against the venue's deprecated
    account filter admitting unified or isolated-margin executions.
    """
    market, order_id = exchange.market(symbol), identity(order_id)
    request = {"order_id": order_id, "currency_pair": market["id"], "account": "spot"}
    parent = exchange.privateSpotGetOrdersOrderId(request)
    if (
        not isinstance(parent, dict)
        or not cash_order(parent)
        or identity(parent.get("id")) != order_id
        or parent.get("currency_pair") != market["id"]
        or parent.get("side") not in ("buy", "sell")
    ):
        raise ccxt.ExchangeError("Unexpected Gate parent order or cash spot wallet.")
    end = cursor.get("end", exchange.milliseconds() // 1000)
    start = cursor.get("start", max(1, end - 7 * 86_400))
    page = cursor.get("page", 1)
    request.update({"from": start, "to": end, "page": page, "limit": limit})
    rows = rows_list(exchange.privateSpotGetMyTrades(request), limit)
    following = next_page(rows, cursor)
    parsed = []
    for row in rows:
        parsed.append(normalize_fill(exchange, row, market, parent, order_id))
    return TradePage(parsed, {**following, "start": start, "end": end} if following else {}, not rows)


def normalize_fill(exchange, row, market, parent, order_id):
    """Share exact cash parent validation and fee observations across both import paths."""
    if (
        row.get("currency_pair") != market["id"]
        or identity(row.get("order_id")) != order_id
        or row.get("side") != parent["side"]
        or row.get("trade_quote") not in (None, "", market["quoteId"])
    ):
        raise ccxt.ExchangeError("Unexpected Gate execution market, order or direction.")
    if row.get("point_fee") not in (None, "") and number(row["point_fee"]) != 0:
        raise ccxt.NotSupported("Gate point-card fees require separate wallet accounting.")
    fill = normalize_trade(exchange.parse_trade(row, market))
    fill.update(id=identity(row.get("id")), order=order_id)
    stamp = number(row.get("create_time_ms"))
    if stamp is not None:
        fill["timestamp"] = stamp
    if fill["timestamp"] is None or fill["timestamp"] <= 0:
        raise ccxt.ExchangeError("Missing Gate execution time.")
    return fill
