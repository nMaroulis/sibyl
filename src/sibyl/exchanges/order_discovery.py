"""Reviewed, bounded reads of account-wide open orders and recent spot orders."""

from dataclasses import dataclass

import ccxt

from sibyl.exchanges import bitget_orders, gate_orders, htx_orders, kucoin_orders, mexc_activity
from sibyl.exchanges.base import number
from sibyl.exchanges.bybit_orders import (
    OPEN,
    TERMINAL,
    read_spot_orders,
    regular_spot_order,
)
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
    "bybit",
    "kucoin",
    "bitstamp",
    "gemini",
    "gate",
    "bitget",
    "mexc",
    "htx",
    "demo",
}
DAY_MS = 86_400_000
DISCOVERY_OPEN_ONLY = {"bitstamp", "gemini"}
DISCOVERY_HISTORY_PAIRS = {"binance", "binanceus", "binance-testnet", "kucoin", "mexc", "htx"}
DISCOVERY_NOTES = {
    "okx": "OKX retains unfilled cancellations for up to two hours. Recent history uses order creation time.",
    "bybit": "Bybit UTA covers ordinary cash spot orders. Recent history limits canceled, rejected and deactivated orders to the last 24 hours.",
    "kucoin": "KuCoin Classic open-order discovery uses Spot API permission. Recent history uses selected pairs, with up to two days for cancellations and seven days for filled orders.",
    "bitstamp": "Bitstamp discovery covers account-wide open spot limit orders. Individual order and fill checks are available for imported orders.",
    "gemini": "Gemini discovery covers account-wide open spot limit orders for the API key’s account.",
    "gate": "Gate scans open and recently finished cash spot orders. Recent history uses Gate’s finish time.",
    "bitget": "Bitget discovery covers open and recent ordinary Classic spot orders. API-cancelled orders are retained for up to two hours. Managed subaccount history depends on its binding time.",
    "htx": "HTX reads the verified spot wallet’s open orders and selected-pair history in 48-hour windows. API-cancelled orders are available for up to two hours.",
    "mexc": "MEXC reads account-wide open spot orders and up to seven days of history for selected pairs. A capped timestamp or open snapshot reports a coverage limit.",
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

    if provider == "bybit":
        return _bybit_page(exchange, stream, cursor, start, end)

    if provider == "kucoin":
        return _kucoin_page(exchange, stream, cursor, start, end, symbols)

    if provider == "bitstamp" and stream == "open":
        return _bitstamp_open(exchange)

    if provider == "gemini" and stream == "open":
        return _gemini_open(exchange)

    if provider == "gate":
        return _gate_page(exchange, stream, cursor, start, end)

    if provider == "bitget":
        return OrderDiscoveryPage(
            *bitget_orders.discover_page(exchange, stream == "recent", cursor, start, end)
        )

    if provider == "htx":
        return OrderDiscoveryPage(*htx_orders.discover_page(exchange, stream, cursor, start, end, symbols))

    if provider == "mexc":
        return OrderDiscoveryPage(*mexc_activity.discover_page(exchange, stream, cursor, start, end, symbols))

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


def _bybit_page(exchange, stream, cursor, start, end) -> OrderDiscoveryPage:
    """Use separate open and terminal streams with a fixed creation window for history."""
    history = stream == "recent"
    request = {"startTime": start, "endTime": end - 1} if history else {"openOnly": 0}
    if cursor.get("page"):
        request["cursor"] = cursor["page"]
    rows, token = read_spot_orders(exchange, history=history, **request)
    orders = []
    states = TERMINAL if history else OPEN
    for row in rows:
        if not regular_spot_order(row):
            continue
        if row.get("orderStatus") not in states:
            raise ccxt.ExchangeError("Unexpected Bybit order state in the selected stream.")
        stamp = number(row.get("createdTime"))
        if history and (stamp is None or not start <= stamp < end):
            raise ccxt.ExchangeError("Bybit order is outside the selected creation window.")
        market_id = row.get("symbol")
        if not isinstance(market_id, str) or not market_id:
            raise ccxt.ExchangeError("Missing Bybit spot instrument identity.")
        market = exchange.safe_market(market_id, marketType="spot")
        orders.append(exchange.parse_order(row, market))
    return OrderDiscoveryPage(
        orders, {"page": token} if token else {}, token is None, len(rows) - len(orders)
    )


def _kucoin_page(exchange, stream, cursor, start, end, symbols) -> OrderDiscoveryPage:
    """Persist an active-market snapshot, then advance one exact market page per tick."""
    recent = stream == "recent"
    if not recent and not cursor:
        markets, excluded = kucoin_orders.active_markets(exchange)
        return OrderDiscoveryPage([], {"symbols": markets} if markets else {}, not markets, excluded)
    markets = symbols if recent else cursor["symbols"]
    index = cursor.get("market", 0)
    if index >= len(markets):
        return OrderDiscoveryPage([], {}, True)
    orders, next_page, skipped = kucoin_orders.market_orders(
        exchange, markets[index], recent=recent, cursor=cursor, start=start, end=end
    )
    following = {"market": index if next_page else index + 1, **next_page}
    if not recent:
        following["symbols"] = markets
    return OrderDiscoveryPage(orders, following, following["market"] >= len(markets), skipped)


def _bitstamp_open(exchange) -> OrderDiscoveryPage:
    """Read the native account snapshot, retaining observed original size only."""
    rows = exchange.request("open_orders/", "private", "POST", {}, config={"cost": 1})
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ccxt.ExchangeError("Invalid Bitstamp open-order snapshot.")
    if len(rows) > 1000:
        raise ccxt.NotSupported("Bitstamp open-order snapshot exceeds the reviewed budget.")
    orders = []
    for row in rows:
        if (
            row.get("margin_mode") not in (None, "", "NONE", "SPOT", "CASH")
            or (row.get("leverage") not in (None, "") and number(row["leverage"]) not in (0, 1))
            or row.get("subtype") not in (None, "", "LIMIT")
            or row.get("reduce_only") not in (None, False)
            or any(
                row.get(key) not in (None, "") and number(row[key]) != 0
                for key in ("stop_price", "activation_price", "trailing_delta")
            )
        ):
            continue
        side = str(row.get("type"))
        if side not in ("0", "1"):
            raise ccxt.ExchangeError("Unknown Bitstamp order side.")
        pair = row.get("market") or row.get("currency_pair")
        if not isinstance(pair, str) or "/" not in pair:
            raise ccxt.ExchangeError("Missing Bitstamp spot market.")
        orders.append(
            {
                "id": identity(row.get("id")),
                "clientOrderId": row.get("client_order_id") or None,
                "symbol": pair.upper(),
                "side": "buy" if side == "0" else "sell",
                "status": "open",
                "type": "limit",
                "timestamp": exchange.parse8601(row.get("datetime")),
                "amount": row.get("amount_at_create"),
                "price": row.get("price"),
            }
        )
    return OrderDiscoveryPage(orders, {}, True, len(rows) - len(orders))


def _gemini_open(exchange) -> OrderDiscoveryPage:
    """Read the account's open snapshot, retaining only currently supported spot instruments."""
    rows = exchange.privatePostV1Orders({})
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ccxt.ExchangeError("Invalid Gemini open-order snapshot.")
    if len(rows) > 1000:
        raise ccxt.NotSupported("Gemini open-order snapshot exceeds the reviewed budget.")
    markets = {
        market["id"].upper(): market
        for market in exchange.markets.values()
        if market.get("spot") and market.get("active") is not False
    }
    orders = []
    for row in rows:
        instrument = row.get("symbol")
        if not isinstance(instrument, str) or not instrument:
            raise ccxt.ExchangeError("Missing Gemini order instrument.")
        market = markets.get(instrument.upper())
        if not market or row.get("type") != "exchange limit" or row.get("exchange") != "gemini":
            continue
        if row.get("is_live") is not True or row.get("is_cancelled") is not False:
            raise ccxt.ExchangeError("Unexpected Gemini open-order status.")
        native_id = identity(row.get("order_id"))
        parsed = exchange.parse_order(row, market)
        parsed["id"] = native_id
        orders.append(parsed)
    return OrderDiscoveryPage(orders, {}, True, len(rows) - len(orders))


def _gate_page(exchange, stream, cursor, start, end) -> OrderDiscoveryPage:
    """Import exact cash spot records from separate open and finished native streams."""
    page = cursor.get("page", 1)
    open_stream = stream == "open"
    rows = (
        gate_orders.open_page(exchange, page)
        if open_stream
        else gate_orders.finished_page(exchange, page, start, end)
    )
    following = gate_orders.next_page(rows, cursor)
    items = []
    for row in rows:
        if not gate_orders.cash_order(row):
            continue
        if row.get("status") not in (("open",) if open_stream else ("closed", "cancelled")):
            raise ccxt.ExchangeError("Unexpected Gate order status in the selected stream.")
        market = exchange.safe_market(row["currency_pair"], marketType="spot")
        items.append(exchange.parse_order(row, market))
    return OrderDiscoveryPage(items, following, not rows, len(rows) - len(items))
