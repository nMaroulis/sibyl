"""Upbit Korea individual executions and resumable regular-order fill imports.

Single-order responses contain native execution UUIDs but only an aggregate
paid_fee. Per-execution fees stay unknown rather than allocating a guessed fee.
History covers current regular open orders and regular closed orders created in
the selected seven-day range; older closed-order coverage remains incomplete.
"""

import ccxt

from sibyl.exchanges.history import TradePage, normalize_trade
from sibyl.exchanges.upbit_orders import discover_page, native_id
from sibyl.exchanges.venue_history import rows_list

DAY_MS = 86400000


def order_fills(exchange, market, order_id, after, limit, *, start=None, end=None):
    """Read one native execution snapshot, validating its parent and trade count."""
    order_id = native_id(order_id)
    parent = exchange.privateGetOrder({"uuid": order_id})
    if (
        not isinstance(parent, dict)
        or parent.get("uuid") != order_id
        or parent.get("market") != market["id"]
        or parent.get("side") not in {"bid", "ask"}
    ):
        raise ccxt.ExchangeError("Unexpected Upbit parent identity, spot market or side.")
    rows = rows_list(parent.get("trades"), 10000)
    count = parent.get("trades_count")
    if type(count) is not int or count != len(rows):
        raise ccxt.NotSupported("Upbit execution snapshot is incomplete; trade count needs review.")
    fills, keys = [], set()
    for row in rows:
        key = native_id(row.get("uuid"))
        if key in keys or row.get("market") != market["id"] or row.get("side") != parent["side"]:
            raise ccxt.ExchangeError("Unexpected or duplicate Upbit execution identity.")
        keys.add(key)
        fill = normalize_trade(exchange.parse_trade(row, market))
        fill.update(id=key, order=order_id, fee={"currency": None, "cost": None}, fees=[])
        stamp = fill.get("timestamp")
        if stamp is None:
            raise ccxt.ExchangeError("Missing Upbit execution time.")
        if start is None or start <= stamp < end:
            fills.append(fill)
    remaining = sorted((row for row in fills if row["id"] > after), key=lambda row: row["id"])
    selected = remaining[:limit]
    return TradePage(
        selected, {"after_id": selected[-1]["id"] if selected else after}, len(remaining) <= limit
    )


def fetch_fill_page(exchange, symbol, cursor, limit, *, order_id=None):
    """Read exact executions or checkpoint regular open/closed-order discovery and details."""
    market = exchange.market(symbol)
    if order_id is not None:
        return order_fills(exchange, market, order_id, cursor.get("after_id", ""), limit)
    end = cursor.get("end", exchange.milliseconds() + 1)
    start = cursor.get("start", max(1, end - 7 * DAY_MS))
    state = {"start": start, "end": end, "phase": cursor.get("phase", "open"), **cursor}
    pending = state.get("ids", [])
    if pending:
        page = order_fills(
            exchange, market, pending[0], state.get("after_id", ""), limit, start=start, end=end
        )
        if page.caught_up:
            state["ids"] = pending[1:]
            visited = state.get("seen_orders", [])
            if len(visited) >= 10000:
                raise ccxt.NotSupported("Upbit order history exceeds the reviewed parent budget.")
            state["seen_orders"] = [*visited, pending[0]]
            state.pop("after_id", None)
        else:
            state.update(page.cursor)
        complete = not state["ids"] and state["phase"] == "done"
        return TradePage(page.items, {"start": max(1, end - DAY_MS)} if complete else state, complete)
    phase = state["phase"]
    if phase == "done":
        return TradePage([], {"start": max(1, end - DAY_MS)}, True)
    rows, following, complete, _ = discover_page(
        exchange,
        "open" if phase == "open" else "recent",
        state.get("listing", {}),
        start,
        end,
        instrument=market["id"],
    )
    seen = set(state.get("seen_orders", []))
    state["ids"] = list(
        dict.fromkeys(row["id"] for row in rows if row["symbol"] == symbol and row["id"] not in seen)
    )
    if complete:
        state.update(phase="closed" if phase == "open" else "done", listing={})
    else:
        state["listing"] = following
    complete = state["phase"] == "done" and not state["ids"]
    return TradePage([], {"start": max(1, end - DAY_MS)} if complete else state, complete)
