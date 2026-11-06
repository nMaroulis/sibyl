"""Reviewed Bitstamp/Gemini spot fills, with native identity and explicit pagination limits.

Bitstamp walks increasing transaction IDs. Gemini follows its documented
millisecond history boundary and retains identities at the inclusive edge;
saturated timestamp groups stop rather than silently discarding executions.
Exact-order reads use native embedded trade details, never invented fills.
"""

import ccxt

from sibyl.exchanges.history import TradePage, normalize_trade

KINDS = {"bitstamp-transactions", "gemini-trades"}


def identity(value):
    """Preserve large native IDs exactly and reject rounded floats/booleans."""
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, str))
        or not str(value).isdecimal()
        or len(str(value)) > 80
    ):
        raise ccxt.ExchangeError("Invalid native execution identity.")
    return str(value)


def rows_list(rows, maximum):
    if not isinstance(rows, list) or len(rows) > maximum or any(not isinstance(row, dict) for row in rows):
        raise ccxt.ExchangeError("Invalid or excessive native execution page.")
    return rows


def gemini_trade(exchange, row, market, order_id=None):
    """Retain reported fees; reject bust/reversal flags until their accounting is implemented."""
    if row.get("break"):
        raise ccxt.ExchangeError("Gemini trade reversal requires separate settlement review.")
    if row.get("symbol", market["id"]).upper() != market["id"].upper():
        raise ccxt.ExchangeError("Unexpected Gemini execution market.")
    native_id = identity(row.get("tid"))
    native_order = identity(row.get("order_id", order_id))
    if order_id and native_order != order_id:
        raise ccxt.ExchangeError("Unexpected Gemini execution order.")
    stamp = row.get("timestampms")
    if stamp is None:
        stamp = float(row.get("timestamp"))
        if stamp < 100_000_000_000:
            stamp *= 1000
    parsed = exchange.parse_trade(
        {**row, "timestampms": stamp, "tid": native_id, "order_id": native_order}, market
    )
    return normalize_trade(parsed)


def fetch_venue_page(exchange, kind, symbol, cursor, limit):
    """Read one bounded app page; native batch sizes never relax the 100-fill commit budget."""
    market = exchange.market(symbol)
    if kind == "bitstamp-transactions":
        after = int(identity(cursor.get("after_id", "0")))
        raw = rows_list(
            exchange.privatePostUserTransactionsPair(
                {"pair": market["id"], "sort": "asc", "since_id": str(after), "limit": 1000}
            ),
            1000,
        )
        ids = [int(identity(row.get("id"))) for row in raw]
        if ids != sorted(set(ids)) or any(value < after for value in ids):
            raise ccxt.ExchangeError("Bitstamp transaction IDs did not advance in ascending order.")
        selected = raw[:limit]
        parsed = []
        for row in selected:
            if str(row.get("type")) == "2":
                identity(row.get("order_id"))
                parsed.append(normalize_trade(exchange.parse_trade(row, market)))
        following = str(int(identity(selected[-1]["id"])) + 1) if selected else str(after)
        return TradePage(parsed, {"after_id": following}, len(raw) <= limit)
    if kind != "gemini-trades":
        raise ccxt.NotSupported("Unknown reviewed venue history.")
    after = cursor.get("after_ms", 0)
    seen = cursor.get("seen_ids", [])
    if type(after) is not int or after < 0 or not isinstance(seen, list) or len(seen) > 500:
        raise ccxt.ExchangeError("Invalid Gemini history checkpoint.")
    seen = {identity(value) for value in seen}
    raw = rows_list(
        exchange.privatePostV1Mytrades({"symbol": market["id"], "timestamp": after, "limit_trades": 500}), 500
    )
    parsed = [gemini_trade(exchange, row, market) for row in raw]
    if any(row["timestamp"] is None or row["timestamp"] < after for row in parsed) or len(
        {row["id"] for row in parsed}
    ) != len(parsed):
        raise ccxt.ExchangeError("Gemini history ignored its timestamp boundary or repeated an execution ID.")
    ordered = sorted(parsed, key=lambda row: (row["timestamp"], int(row["id"])))
    remaining = [row for row in ordered if row["timestamp"] != after or row["id"] not in seen]
    if not remaining and len(raw) == 500:
        raise ccxt.ExchangeError(
            "Gemini timestamp group saturated; its complete history cannot be proven. Check native exports."
        )
    selected = remaining[:limit]
    stamp = int(selected[-1]["timestamp"]) if selected else after
    boundary = seen if stamp == after else set()
    boundary.update(row["id"] for row in selected if row["timestamp"] == stamp)
    return TradePage(
        selected,
        {"after_ms": stamp, "seen_ids": sorted(boundary)},
        len(raw) < 500 and len(remaining) <= limit,
    )


def fetch_venue_order_page(exchange, kind, order_id, symbol, cursor, limit):
    """Read exact native order trade details, paging their IDs without inventing cumulative fills."""
    market = exchange.market(symbol)
    order_id = identity(order_id)
    after = int(identity(cursor.get("after_id", "0")))
    if kind == "gemini-trades":
        document = exchange.privatePostV1OrderStatus({"order_id": order_id, "include_trades": True})
        if (
            identity(document.get("order_id")) != order_id
            or document.get("symbol", "").upper() != market["id"].upper()
        ):
            raise ccxt.ExchangeError("Unexpected Gemini order identity or market.")
        raw = rows_list(document.get("trades"), 10_000)
        parsed = [gemini_trade(exchange, row, market, order_id) for row in raw]
    elif kind == "bitstamp-transactions":
        document = exchange.privatePostOrderStatus({"id": order_id})
        if (
            identity(document.get("id")) != order_id
            or document.get("market", "").upper() != symbol
            or str(document.get("type")) not in {"0", "1"}
        ):
            raise ccxt.ExchangeError("Missing Bitstamp spot order market or side evidence.")
        raw = rows_list(document.get("transactions"), 10_000)
        parsed = []
        for row in raw:
            native_id = identity(row.get("tid"))
            if row.get("order_id") is not None and identity(row["order_id"]) != order_id:
                raise ccxt.ExchangeError("Unexpected Bitstamp execution order.")
            # Embedded transactions use positive amounts; their authoritative parent
            # order supplies side. User-transaction history instead has signed amounts.
            payload = {**row, "tid": native_id, "order_id": order_id, "type": str(document["type"])}
            payload.pop("id", None)
            trade = exchange.parse_trade(payload, market)
            parsed.append(normalize_trade(trade))
    else:
        raise ccxt.NotSupported("Unknown reviewed order execution adapter.")
    ids = [identity(row["id"]) for row in parsed]
    if len(set(ids)) != len(ids) or any(
        row["order"] != order_id or row["symbol"] != symbol for row in parsed
    ):
        raise ccxt.ExchangeError("Native order execution identities do not agree.")
    remaining = sorted((row for row in parsed if int(row["id"]) > after), key=lambda row: int(row["id"]))
    selected = remaining[:limit]
    following = selected[-1]["id"] if selected else str(after)
    return TradePage(selected, {"after_id": following}, len(remaining) <= limit)
