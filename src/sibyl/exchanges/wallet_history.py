"""Resumable Gate and HTX cash-fill history using their reviewed parent contracts.

Selected-market reads freeze seven days and verify each distinct native parent.
At most twenty fills and parent reads are considered per page. Both history and
exact-order reconciliation reuse the same normalizers and execution identities.
"""

import ccxt

from sibyl.exchanges import gate_fills, gate_orders, htx_orders
from sibyl.exchanges.history import TradePage
from sibyl.exchanges.venue_history import identity, rows_list

DAY_MS = 86400000


def fetch_wallet_page(exchange, kind, symbol, cursor, limit):
    """Read one cash history page without using margin/unified wallet substitutions."""
    if kind == "gate-cash":
        return gate_page(exchange, symbol, cursor, min(limit, 20))
    return htx_page(exchange, symbol, cursor, min(limit, 20))


def gate_page(exchange, symbol, cursor, limit):
    """Resume native numbered pages under the same fixed seven-day second-based bounds."""
    market = exchange.market(symbol)
    end = cursor.get("end", exchange.milliseconds() // 1000)
    start = cursor.get("start", max(1, end - 7 * 86400))
    raw = rows_list(
        exchange.privateSpotGetMyTrades(
            {
                "currency_pair": market["id"],
                "account": "spot",
                "from": start,
                "to": end,
                "page": cursor.get("page", 1),
                "limit": limit,
            }
        ),
        limit,
    )
    following = gate_orders.next_page(raw, cursor)
    parents, fills = {}, []
    for row in raw:
        native_order = identity(row.get("order_id"))
        if native_order not in parents:
            parent = exchange.privateSpotGetOrdersOrderId(
                {"order_id": native_order, "currency_pair": market["id"], "account": "spot"}
            )
            if (
                not isinstance(parent, dict)
                or not gate_orders.cash_order(parent)
                or identity(parent.get("id")) != native_order
                or parent.get("currency_pair") != market["id"]
                or parent.get("side") not in {"buy", "sell"}
            ):
                raise ccxt.NotSupported("Gate cash parent is unavailable or needs wallet-scope review.")
            parents[native_order] = parent
        fill = gate_fills.normalize_fill(exchange, row, market, parents[native_order], native_order)
        if not start <= fill["timestamp"] / 1000 < end + 1:
            raise ccxt.ExchangeError("Gate execution differs from the frozen history window.")
        fills.append(fill)
    return TradePage(
        fills,
        {**following, "start": start, "end": end} if following else {"start": max(1, end - 86400)},
        not raw,
    )


def htx_page(exchange, symbol, cursor, limit):
    """Read fixed 48-hour ranges, splitting saturated execution timestamps before commit."""
    market, account = exchange.market(symbol), htx_orders.spot_account(exchange)
    if cursor.get("account", account) != account:
        raise ValueError("HTX spot wallet changed during the import.")
    end = cursor.get("end", exchange.milliseconds())
    start = cursor.get("start", max(1, end - 7 * DAY_MS))
    windows = cursor.get("windows") or [
        [value, min(value + 2 * DAY_MS, end)] for value in range(start, end, 2 * DAY_MS)
    ]
    (lower, upper), *pending = windows
    raw = rows_list(
        htx_orders.response_data(
            exchange.spotPrivateGetV1OrderMatchresults(
                {"symbol": market["id"], "start-time": lower, "end-time": upper - 1, "size": limit}
            )
        ),
        limit,
    )
    stamps = [int(identity(row.get("created-at"))) for row in raw]
    if any(not lower <= stamp < upper for stamp in stamps):
        raise ccxt.ExchangeError("HTX execution differs from the frozen history window.")
    if len(raw) == limit:
        if upper - lower <= 1:
            raise ccxt.NotSupported("HTX timestamp boundary exceeds the reviewed fill capacity.")
        middle = (lower + upper) // 2
        return TradePage(
            [],
            {
                "start": start,
                "end": end,
                "account": account,
                "windows": [[lower, middle], [middle, upper], *pending],
            },
            False,
        )
    parents, fills, keys = {}, [], set()
    for row in raw:
        native_id, native_order = identity(row.get("id")), identity(row.get("order-id"))
        if native_id in keys:
            raise ccxt.ExchangeError("Duplicate HTX history execution identity.")
        keys.add(native_id)
        if native_order not in parents:
            parent = htx_orders.response_data(
                exchange.spotPrivateGetV1OrderOrdersOrderId({"order-id": native_order})
            )
            htx_orders.account_order(parent, account, market)
            if identity(parent["id"]) != native_order or parent.get("type") not in htx_orders.ORDER_TYPES:
                raise ccxt.ExchangeError("Unexpected HTX cash parent.")
            parents[native_order] = parent
        fills.append(htx_orders.normalize_fill(exchange, row, market, parents[native_order]))
    following = (
        {"start": start, "end": end, "account": account, "windows": pending}
        if pending
        else {"start": max(1, end - DAY_MS)}
    )
    return TradePage(fills, following, not pending)
