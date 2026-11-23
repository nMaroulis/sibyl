"""Poloniex cash spot executions shared by order reconciliation and Account history.

Fill pages do not report borrowing, so each distinct parent must prove cash spot
scope. History starts with seven days to align with short cancelled-parent
retention. Missing parents stop for review. Native pageId advances history while
native trade/order IDs identify ledger entries across both read paths.
"""

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.history import TradePage, normalize_trade
from sibyl.exchanges.poloniex_orders import cash_order
from sibyl.exchanges.venue_history import identity, rows_list

DAY_MS = 86_400_000
HISTORY_PAGE = 20


def parent_order(exchange, market, order_id):
    """Require the selected native parent to establish instrument, side and unborrowed scope."""
    order_id = identity(order_id)
    try:
        parent = exchange.privateGetOrdersId({"id": order_id})
    except ccxt.OrderNotFound as error:
        raise ccxt.NotSupported(
            "Poloniex parent is unavailable; cash execution scope needs review."
        ) from error
    if (
        not isinstance(parent, dict)
        or not cash_order(parent)
        or identity(parent.get("id")) != order_id
        or int(order_id) <= 0
        or parent.get("symbol") != market["id"]
        or parent.get("side") not in {"BUY", "SELL"}
    ):
        raise ccxt.ExchangeError("Unexpected Poloniex cash spot parent order.")
    return parent


def normalize_fill(exchange, row, market, parent):
    """Keep exact execution identities, reported costs and native fee currencies/signs."""
    native_id, native_order = identity(row.get("id")), identity(row.get("orderId"))
    stamp = int(identity(row.get("createTime")))
    if (
        int(native_id) <= 0
        or stamp <= 0
        or row.get("accountType") != "SPOT"
        or row.get("symbol") != market["id"]
        or native_order != identity(parent.get("id"))
        or row.get("side") != parent["side"]
        or row.get("type") not in {"LIMIT", "LIMIT_MAKER", "MARKET"}
    ):
        raise ccxt.ExchangeError("Unexpected Poloniex execution identity, market or direction.")
    fill = normalize_trade(exchange.parse_trade(row, market))
    currency = row.get("feeCurrency")
    fee = {
        "currency": exchange.safe_currency_code(currency) if isinstance(currency, str) and currency else None,
        "cost": number(row.get("feeAmount")),
    }
    fill.update(
        id=native_id, order=native_order, timestamp=stamp, cost=number(row.get("amount")), fee=fee, fees=[fee]
    )
    return fill


def fetch_fill_page(exchange, symbol, cursor, limit, *, order_id=None):
    """Read exact-order fills or a bounded, resumable selected-market cash history page."""
    market = exchange.market(symbol)
    if order_id is not None:
        parent = parent_order(exchange, market, order_id)
        rows = rows_list(exchange.privateGetOrdersIdTrades({"id": identity(order_id)}), 10000)
        fills = [normalize_fill(exchange, row, market, parent) for row in rows]
        keys = [row["id"] for row in fills]
        if len(set(keys)) != len(keys):
            raise ccxt.ExchangeError("Duplicate Poloniex order execution identity.")
        after = int(identity(cursor.get("after_id", "0")))
        remaining = sorted((row for row in fills if int(row["id"]) > after), key=lambda row: int(row["id"]))
        selected = remaining[:limit]
        return TradePage(
            selected, {"after_id": selected[-1]["id"] if selected else str(after)}, len(remaining) <= limit
        )

    now = exchange.milliseconds()
    end = cursor.get("end", now + 1)
    start = cursor.get("start", max(1, end - 7 * DAY_MS))
    if type(start) is not int or type(end) is not int or not 0 < end - start <= 7 * DAY_MS:
        raise ValueError("Poloniex cash history requires a fixed window of at most seven days.")
    after = identity(cursor.get("after", "0"))
    capacity = min(limit, HISTORY_PAGE)
    rows = rows_list(
        exchange.privateGetTrades(
            {
                "symbols": market["id"],
                "startTime": start,
                "endTime": end - 1,
                "from": after,
                "direction": "NEXT",
                "limit": capacity + 1,
            }
        ),
        capacity + 1,
    )
    keys = [identity(row.get("pageId")) for row in rows]
    if len(set(keys)) != len(keys) or any(int(key) < int(after) or int(key) <= 0 for key in keys):
        raise ccxt.ExchangeError("Poloniex execution page IDs did not advance.")
    fresh = sorted(
        (row for row in rows if int(identity(row["pageId"])) > int(after)), key=lambda row: int(row["pageId"])
    )[:capacity]
    parents, fills = {}, []
    for row in fresh:
        if row.get("symbol") != market["id"] or not start <= int(identity(row.get("createTime"))) < end:
            raise ccxt.ExchangeError("Poloniex execution differs from the selected market or time window.")
        native_order = identity(row.get("orderId"))
        if native_order not in parents:
            parents[native_order] = parent_order(exchange, market, native_order)
        fills.append(normalize_fill(exchange, row, market, parents[native_order]))
    if len({(row["id"], row["order"]) for row in fills}) != len(fills):
        raise ccxt.ExchangeError("Duplicate Poloniex cash execution identity.")
    following = (
        {"start": start, "end": end, "after": identity(fresh[-1]["pageId"])}
        if fresh
        else {"start": max(1, end - DAY_MS)}
    )
    return TradePage(fills, following, not fresh)
