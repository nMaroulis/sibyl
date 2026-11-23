"""Bitfinex exchange-wallet executions with shared exact-order/history identities.

Native EXCHANGE types establish cash scope. Margin executions are excluded from
selected-market history; missing type evidence stops for review. Bitfinex fee
amounts are wallet effects, so charges are negated into Sibyl's positive-cost
convention and positive native rebates become negative costs.
"""

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.bitfinex_orders import arrays, read_window
from sibyl.exchanges.history import TradePage, normalize_trade
from sibyl.exchanges.venue_history import identity

DAY_MS = 86400000
CASH_TYPES = {
    "EXCHANGE " + kind for kind in ("LIMIT", "MARKET", "STOP", "STOP LIMIT", "TRAILING STOP", "FOK", "IOC")
}
MARGIN_TYPES = {kind.removeprefix("EXCHANGE ") for kind in CASH_TYPES}


def normalize_fill(exchange, row, market, *, order_id=None):
    """Require an exact cash execution and retain native fee currency without inference."""
    native_id, native_order = identity(row[0]), identity(row[3])
    quantity, price = number(row[4]), number(row[5])
    stamp = int(identity(row[2]))
    if (
        int(native_id) <= 0
        or int(native_order) <= 0
        or stamp <= 0
        or row[1] != market["id"]
        or row[6] not in CASH_TYPES
        or quantity is None
        or quantity == 0
        or price is None
        or price <= 0
        or (order_id is not None and native_order != order_id)
    ):
        raise ccxt.ExchangeError("Unexpected Bitfinex cash execution identity, market or order.")
    fill = normalize_trade(exchange.parse_trade({"result": row}, market))
    native_fee = number(row[9])
    currency = row[10]
    fee = {
        "currency": exchange.safe_currency_code(currency) if isinstance(currency, str) and currency else None,
        "cost": -native_fee if native_fee is not None else None,
    }
    fill.update(id=native_id, order=native_order, timestamp=stamp, fee=fee, fees=[fee])
    return fill


def fetch_fill_page(exchange, symbol, cursor, limit, *, order_id=None):
    """Read a bounded exact-order snapshot or split a frozen selected-market history range."""
    market = exchange.market(symbol)
    if order_id is not None:
        order_id = identity(order_id)
        rows = arrays(
            exchange.privatePostAuthROrderSymbolIdTrades({"symbol": market["id"], "id": int(order_id)}),
            10000,
            11,
        )
        fills = [normalize_fill(exchange, row, market, order_id=order_id) for row in rows]
        keys = [row["id"] for row in fills]
        if len(set(keys)) != len(keys):
            raise ccxt.ExchangeError("Duplicate Bitfinex order execution IDs.")
        after = int(identity(cursor.get("after_id", "0")))
        remaining = sorted((row for row in fills if int(row["id"]) > after), key=lambda row: int(row["id"]))
        selected = remaining[:limit]
        return TradePage(
            selected, {"after_id": selected[-1]["id"] if selected else str(after)}, len(remaining) <= limit
        )
    end = cursor.get("end", exchange.milliseconds() + 1)
    start = cursor.get("start", max(1, end - 90 * DAY_MS))
    rows, pending = read_window(
        exchange.privatePostAuthRTradesSymbolHist,
        {"symbol": market["id"], "sort": 1},
        cursor.get("windows") or [[start, end]],
        limit,
        timestamp=2,
    )
    arrays(rows, limit, 11)
    selected, keys = [], set()
    for row in rows:
        if row[1] != market["id"]:
            raise ccxt.ExchangeError("Bitfinex execution differs from the selected instrument.")
        native_id = identity(row[0])
        if native_id in keys:
            raise ccxt.ExchangeError("Duplicate Bitfinex native execution IDs.")
        keys.add(native_id)
        if row[6] in MARGIN_TYPES:
            continue
        selected.append(normalize_fill(exchange, row, market))
    following = (
        {"start": start, "end": end, "windows": pending} if pending else {"start": max(1, end - DAY_MS)}
    )
    return TradePage(selected, following, not pending)
