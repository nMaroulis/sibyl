"""Reviewed, bounded reads of account-wide open orders and recent spot orders."""

from dataclasses import dataclass

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.history import _token
from sibyl.exchanges.venue_history import identity

DISCOVERY_PROVIDERS = {
    "binance",
    "binanceus",
    "binance-testnet",
    "coinbase",
    "coinbase-sandbox",
    "kraken",
    "okx",
    "demo",
}
DAY_MS = 86_400_000
DISCOVERY_NOTES = {
    "okx": "OKX retains unfilled cancellations for up to two hours. Recent history uses order creation time.",
}


def _binance_order(exchange, row):
    """Preserve Binance's unavailable historical-cost sentinel as unknown."""
    parsed = exchange.parse_order(row)
    if (number(row.get("cummulativeQuoteQty")) or 0) < 0:
        parsed.update(cost=None, average=None)
    return parsed


@dataclass(frozen=True)
class OrderDiscoveryPage:
    """One native read with a private next cursor; complete applies only to this stream."""

    items: list[dict]
    cursor: dict
    complete: bool
    skipped: int = 0


def discovery_page(exchange, provider, stream, cursor, start, end, symbols) -> OrderDiscoveryPage:
    """Read one page without SDK auto-pagination, account mutations or market fan-out.

    Binance history needs selected markets and splits saturated time windows rather
    than skipping timestamp ties. Other clients use native cursors/offsets. Open
    snapshots without native pagination fail explicitly above 1,000 orders.
    """
    if provider in {"binance", "binanceus", "binance-testnet"}:
        if stream == "open":
            rows = exchange.privateGetOpenOrders({})
            if not isinstance(rows, list) or len(rows) > 1000:
                raise ccxt.NotSupported("Open-order snapshot exceeds the reviewed budget.")
            return OrderDiscoveryPage([_binance_order(exchange, row) for row in rows], {}, True)
        index = cursor.get("market", 0)
        if index >= len(symbols):
            return OrderDiscoveryPage([], {}, True)
        symbol = symbols[index]
        market = exchange.market(symbol)
        windows = cursor.get("windows") or [[start, min(start + DAY_MS, end)]]
        lower, upper = windows[0]
        rows = exchange.privateGetAllOrders(
            {"symbol": market["id"], "startTime": lower, "endTime": upper - 1, "limit": 1000}
        )
        if not isinstance(rows, list) or len(rows) > 1000:
            raise ccxt.ExchangeError("Invalid recent-order page.")
        if len(rows) == 1000:
            if upper - lower <= 1:
                raise ccxt.NotSupported("A timestamp exceeds the reviewed order-page capacity.")
            middle = (lower + upper) // 2
            return OrderDiscoveryPage(
                [], {"market": index, "windows": [[lower, middle], [middle, upper], *windows[1:]]}, False
            )
        pending = windows[1:]
        if not pending and upper < end:
            pending = [[upper, min(upper + DAY_MS, end)]]
        if not pending:
            index += 1
        following = {"market": index, "windows": pending}
        return OrderDiscoveryPage(
            [_binance_order(exchange, row) for row in rows], following, index >= len(symbols)
        )

    if provider == "coinbase":
        request = {"product_type": "SPOT", "limit": 100, "order_placement_source": "RETAIL_ADVANCED"}
        if stream == "open":
            request["order_status"] = ["OPEN", "PENDING", "QUEUED", "CANCEL_QUEUED", "EDIT_QUEUED"]
        else:
            request.update(start_date=exchange.iso8601(start), end_date=exchange.iso8601(end))
        if cursor.get("page"):
            request["cursor"] = cursor["page"]
        result = exchange.v3PrivateGetBrokerageOrdersHistoricalBatch(request)
        if result.get("proof_token_required"):
            raise ccxt.PermissionDenied("Additional verification is required.")
        rows, more, token = result["orders"], result.get("has_next"), _token(result.get("cursor"))
        if (
            not isinstance(rows, list)
            or len(rows) > 100
            or not isinstance(more, bool)
            or (more and not token)
        ):
            raise ccxt.ExchangeError("Invalid account order pagination.")
        return OrderDiscoveryPage([exchange.parse_order(row) for row in rows], {"page": token}, not more)

    if provider == "coinbase-sandbox":
        request = {"limit": 100}
        if stream == "recent":
            request.update(status="all", start_date=exchange.iso8601(start), end_date=exchange.iso8601(end))
        if cursor.get("after"):
            request["after"] = cursor["after"]
        rows = exchange.privateGetOrders(request)
        if not isinstance(rows, list) or len(rows) > 100:
            raise ccxt.ExchangeError("Invalid sandbox order page.")
        headers = {key.lower(): value for key, value in (exchange.last_response_headers or {}).items()}
        token = _token(headers.get("cb-after"))
        if len(rows) == 100 and not token:
            raise ccxt.ExchangeError("Sandbox order continuation is missing.")
        return OrderDiscoveryPage(
            [exchange.parse_order(row) for row in rows], {"after": token}, not rows or not token
        )

    if provider == "okx":
        return _okx_page(exchange, stream, cursor, start, end)

    if provider == "kraken":
        if stream == "open":
            rows = exchange.privatePostOpenOrders({"trades": False})["result"]["open"]
            if not isinstance(rows, dict) or len(rows) > 1000:
                raise ccxt.NotSupported("Open-order snapshot exceeds the reviewed budget.")
            following, complete = {}, True
        else:
            offset = cursor.get("offset", 0)
            result = exchange.privatePostClosedOrders(
                {
                    "trades": False,
                    "start": start // 1000 - 1,
                    "end": end // 1000,
                    "closetime": "close",
                    "ofs": offset,
                }
            )["result"]
            rows, count = result["closed"], number(result.get("count"))
            if (
                not isinstance(rows, dict)
                or len(rows) > 50
                or count is None
                or count != int(count)
                or count < offset + len(rows)
                or (not rows and count > offset)
            ):
                raise ccxt.ExchangeError("Invalid closed-order pagination.")
            following = {"offset": offset + len(rows)}
            complete = following["offset"] >= count
        spot = [
            (identity, row)
            for identity, row in rows.items()
            if (row.get("descr") or {}).get("leverage", "none") in {"none", "0", 0, None}
        ]
        return OrderDiscoveryPage(
            [exchange.parse_order({**row, "id": identity}) for identity, row in spot],
            following,
            complete,
            len(rows) - len(spot),
        )
    raise ccxt.NotSupported("Account order discovery is not reviewed for this provider.")


def _okx_page(exchange, stream, cursor, start, end) -> OrderDiscoveryPage:
    """Page cash spot orders by exact native ID, including pages with excluded orders."""
    request = {"instType": "SPOT", "limit": "100"}
    after = identity(cursor["after"]) if "after" in cursor else None
    if after is not None:
        request["after"] = after
    if stream == "open":
        result = exchange.privateGetTradeOrdersPending(request)
        states = {"live", "partially_filled"}
    else:
        request.update(begin=str(start), end=str(end - 1))
        result = exchange.privateGetTradeOrdersHistory(request)
        states = {"filled", "canceled"}
    rows = result.get("data") if isinstance(result, dict) and result.get("code") == "0" else None
    if not isinstance(rows, list) or len(rows) > 100 or any(not isinstance(row, dict) for row in rows):
        raise ccxt.ExchangeError("Invalid OKX account order page.")
    ids = [identity(row.get("ordId")) for row in rows]
    numeric_ids = list(map(int, ids))
    before = int(after) if after is not None else None
    if len(set(numeric_ids)) != len(ids) or any(
        value <= 0 or (before is not None and value >= before) for value in numeric_ids
    ):
        raise ccxt.ExchangeError("OKX order IDs did not advance.")
    selected = []
    for order_id, row in zip(ids, rows, strict=True):
        if row.get("instType") != "SPOT" or row.get("tdMode") != "cash":
            continue
        if row.get("state") not in states:
            raise ccxt.ExchangeError("Unexpected OKX order state in the selected stream.")
        if stream == "recent" and not start <= int(identity(row.get("cTime"))) < end:
            raise ccxt.ExchangeError("OKX order is outside the selected creation window.")
        parsed = exchange.parse_order(row)
        # A triggered child is a regular order. CCXT may prefer its parent algo ID.
        parsed["id"] = order_id
        selected.append(parsed)
    return OrderDiscoveryPage(
        selected, {"after": min(ids, key=int)} if ids else {}, not rows, len(rows) - len(selected)
    )
