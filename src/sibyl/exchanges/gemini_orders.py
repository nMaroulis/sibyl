"""Bounded Gemini closed-order discovery through the native account history API.

The published timestamp paging guidance is ambiguous about direction and tied
boundaries. A full 500-order response therefore reports a coverage limit rather
than advancing a cursor that could skip closed orders or unfilled cancellations.
"""

import ccxt

from sibyl.exchanges.venue_history import identity, rows_list


def recent_page(exchange, cursor, start, end, symbols):
    """Read a bounded native closed-order snapshot, including unfilled cancellations."""
    rows = rows_list(
        exchange.request("v1/orders/history", "private", "POST", {"timestamp": start, "limit_orders": 500}),
        500,
    )
    if len(rows) == 500:
        raise ccxt.NotSupported("Gemini closed-order snapshot reached its reviewed history capacity.")
    markets = {
        row["id"].upper(): row
        for row in exchange.markets.values()
        if row.get("spot") and row.get("active") is not False
    }
    selected, keys = [], set()
    for row in rows:
        native_id = identity(row.get("order_id"))
        if native_id in keys:
            raise ccxt.ExchangeError("Duplicate Gemini closed-order identities.")
        keys.add(native_id)
        stamp = int(identity(row.get("timestampms")))
        if not start <= stamp < end:
            continue
        instrument = row.get("symbol")
        market = markets.get(instrument.upper()) if isinstance(instrument, str) else None
        if not market or row.get("exchange") != "gemini" or row.get("type") != "exchange limit":
            continue
        if row.get("is_live") is not False or not isinstance(row.get("is_cancelled"), bool):
            raise ccxt.ExchangeError("Unexpected Gemini closed-order state.")
        parsed = exchange.parse_order(row, market)
        parsed["id"] = native_id
        selected.append(parsed)
    return selected, {}, True, len(rows) - len(selected)
