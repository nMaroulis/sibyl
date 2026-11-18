"""Reviewed client-ID lookup pages; these endpoints only read existing orders."""

import re
from dataclasses import dataclass

import ccxt

from sibyl.exchanges import (
    bitfinex_orders,
    bitget_orders,
    bitmart_activity,
    coinex_activity,
    cryptocom_orders,
    gate_orders,
    htx_orders,
    mexc_activity,
    phemex_activity,
    poloniex_orders,
    upbit_orders,
)
from sibyl.exchanges.base import number
from sibyl.exchanges.bybit_orders import (
    OPEN,
    TERMINAL,
    read_spot_orders,
    regular_spot_order,
)
from sibyl.exchanges.history import _token
from sibyl.exchanges.venue_history import identity

RECOVERY_PROVIDERS = {
    "binance",
    "binanceus",
    "binance-testnet",
    "coinbase",
    "coinbase-sandbox",
    "kraken",
    "okx",
    "bybit",
    "kucoin",
    "gemini",
    "gate",
    "bitget",
    "mexc",
    "htx",
    "coinex",
    "bitmart",
    "bitfinex",
    "poloniex",
    "upbit",
    "phemex",
    "cryptocom",
    "demo",
}


RECOVERY_NOTES = {
    "cryptocom": "Recover ordinary cash GTC limits by exact client_oid with verified account, sizing and creation evidence. Missing or margin/advanced evidence remains uncertain.",
    "phemex": "Recover base-sized spot GTC limits by exact clOrdID on the selected pair. Original native terms and creation time must match; missing client evidence remains uncertain.",
    "bitfinex": "Recover ordinary EXCHANGE LIMIT orders by saved int45 cid, verified original terms and API origin. Open and bounded closed matches are inspected; closed history covers up to two weeks. Margin, flagged and linked orders are excluded.",
    "upbit": "Recover regular spot GTC limits on the default Upbit Korea endpoint using the exact saved identifier and original order details. Reserved, SMP and non-GTC instructions are excluded.",
    "okx": "Look up the saved client ID on the exact cash spot instrument. OKX returns the latest match, so Sibyl also verifies creation time and reviewed order details.",
    "bybit": "Look up the saved client ID in Bybit UTA spot realtime and dated history. Coverage depends on Bybit's order retention.",
    "kucoin": "Look up the saved client ID in KuCoin Classic spot, with a legacy fallback. History retention depends on native order status.",
    "gemini": "Look up a reviewed Gemini spot GTC limit order with its exact saved client ID and original order details.",
    "gate": "Look up a reviewed cash spot GTC limit by its saved client ID. A pending-order miss checks up to seven days of finished orders.",
    "bitget": "Recover a reviewed Classic spot limit using its exact clientOid and original terms. Bitget retains API-cancelled records for up to two hours.",
    "poloniex": "Recover reviewed unborrowed spot GTC limits through the exact saved client ID. Native retention and archived orders can limit lookup coverage.",
    "bitmart": "Recover reviewed spot limits through the exact saved client ID. BitMart limits API-cancelled unfilled order queries to 20 minutes.",
    "coinex": "Find reviewed cash spot GTC limits through pending and bounded finished-order pages. CoinEx deletes cancelled orders that had no fills; missing records remain uncertain.",
    "htx": "Look up the exact client ID for the verified spot wallet. HTX limits client-ID lookup to eight hours and API-cancelled records to two hours.",
    "mexc": "Recover a reviewed spot GTC limit by saved client ID on the exact pair. MEXC order lookup covers up to seven days.",
}


@dataclass(frozen=True)
class OrderLookupPage:
    """Exact client-ID candidates and private pagination; exhaustion never proves absence."""

    candidates: list[dict]
    cursor: dict
    complete: bool


def lookup_order_page(
    exchange, provider: str, client_id: str, symbol: str, cursor: dict, start: int, end: int
) -> OrderLookupPage:
    """Read one native page and discard unrelated orders before retaining any evidence.

    Binance, Exchange Sandbox and OKX use direct client-ID reads. Coinbase Advanced scans
    an exact-product creation window. Kraken reads client-filtered open orders,
    then closed orders with an opening-time window. No SDK auto-pagination runs.
    """
    if provider in {"binance", "binanceus", "binance-testnet", "coinbase-sandbox"}:
        params = (
            {"origClientOrderId": client_id}
            if provider != "coinbase-sandbox"
            else {"clientOrderId": client_id}
        )
        try:
            order = exchange.fetch_order(None, symbol, params=params)
        except ccxt.OrderNotFound:
            return OrderLookupPage([], {}, True)
        return OrderLookupPage([order], {}, True)

    if provider == "okx":
        return _okx_lookup(exchange, client_id, symbol)

    if provider == "bybit":
        return _bybit_lookup(exchange, client_id, symbol, cursor, start, end)

    if provider == "kucoin":
        return _kucoin_lookup(exchange, client_id, symbol, cursor)

    if provider == "gemini":
        return _gemini_lookup(exchange, client_id, symbol)

    if provider == "gate":
        return _gate_lookup(exchange, client_id, symbol, cursor, start)

    if provider == "bitget":
        return OrderLookupPage(bitget_orders.lookup_order(exchange, client_id, symbol), {}, True)

    if provider == "cryptocom":
        return OrderLookupPage(cryptocom_orders.lookup_order(exchange, client_id, symbol), {}, True)

    if provider == "phemex":
        return OrderLookupPage(phemex_activity.lookup_order(exchange, client_id, symbol), {}, True)

    if provider == "bitfinex":
        return OrderLookupPage(*bitfinex_orders.lookup_page(exchange, client_id, symbol, cursor, start, end))

    if provider == "upbit":
        return OrderLookupPage(upbit_orders.lookup_order(exchange, client_id, symbol), {}, True)

    if provider == "poloniex":
        return OrderLookupPage(poloniex_orders.lookup_order(exchange, client_id, symbol), {}, True)

    if provider == "bitmart":
        return OrderLookupPage(bitmart_activity.lookup_order(exchange, client_id, symbol), {}, True)

    if provider == "coinex":
        return OrderLookupPage(*coinex_activity.lookup_page(exchange, client_id, symbol, cursor))

    if provider == "htx":
        return OrderLookupPage(htx_orders.lookup_order(exchange, client_id, symbol), {}, True)

    if provider == "mexc":
        return OrderLookupPage(mexc_activity.lookup_order(exchange, client_id, symbol), {}, True)

    if provider == "coinbase":
        market = exchange.market(symbol)
        request = {
            "product_ids": [market["id"]],
            "product_type": "SPOT",
            "limit": 100,
            "start_date": exchange.iso8601(start),
            "end_date": exchange.iso8601(end),
        }
        if cursor.get("page"):
            request["cursor"] = cursor["page"]
        result = exchange.v3PrivateGetBrokerageOrdersHistoricalBatch(request)
        if result.get("proof_token_required"):
            raise ccxt.PermissionDenied("Additional order history verification is required.")
        rows, following, more = result["orders"], _token(result.get("cursor")), result.get("has_next")
        if (
            not isinstance(rows, list)
            or len(rows) > 100
            or not isinstance(more, bool)
            or (more and not following)
        ):
            raise ccxt.ExchangeError("Invalid order lookup page.")
        candidates = [exchange.parse_order(row) for row in rows if row.get("client_order_id") == client_id]
        return OrderLookupPage(candidates, {"page": following}, not more)

    if provider == "kraken":
        request = {"cl_ord_id": client_id, "trades": False}
        if cursor.get("phase", "open") == "open":
            rows = exchange.privatePostOpenOrders(request)["result"]["open"]
            if not isinstance(rows, dict) or len(rows) > 100:
                raise ccxt.ExchangeError("Excessive client-filtered open orders.")
            following, complete = {"phase": "closed", "offset": 0}, False
        else:
            offset = cursor.get("offset", 0)
            request.update(start=start // 1000, end=(end + 999) // 1000, closetime="open", ofs=offset)
            result = exchange.privatePostClosedOrders(request)["result"]
            rows, count = result["closed"], number(result.get("count"))
            if (
                not isinstance(rows, dict)
                or len(rows) > 50
                or count is None
                or count != int(count)
                or count < offset + len(rows)
                or (not rows and count > offset)
            ):
                raise ccxt.ExchangeError("Invalid closed-order lookup pagination.")
            following = {"phase": "closed", "offset": offset + len(rows)}
            complete = following["offset"] >= count
        candidates = [
            exchange.parse_order({**row, "id": identity})
            for identity, row in rows.items()
            if row.get("cl_ord_id") == client_id
        ]
        return OrderLookupPage(candidates, following, complete)
    raise ccxt.NotSupported("Client order ID recovery is not reviewed for this provider.")


def _okx_lookup(exchange, client_id: str, symbol: str) -> OrderLookupPage:
    """Read the latest OKX match for this exact cash spot instrument and client ID."""
    if not isinstance(client_id, str) or not re.fullmatch(r"[A-Za-z0-9]{1,32}", client_id):
        raise ValueError("Invalid persisted OKX client order ID.")
    instrument = exchange.market(symbol)["id"]
    try:
        response = exchange.privateGetTradeOrder({"instId": instrument, "clOrdId": client_id})
    except ccxt.OrderNotFound:
        return OrderLookupPage([], {}, True)
    rows = response.get("data") if isinstance(response, dict) and response.get("code") == "0" else None
    if not isinstance(rows, list) or len(rows) > 1 or any(not isinstance(row, dict) for row in rows):
        raise ccxt.ExchangeError("Invalid OKX order details response.")
    if not rows:
        return OrderLookupPage([], {}, True)
    row = rows[0]
    if (
        row.get("clOrdId") != client_id
        or row.get("instId") != instrument
        or row.get("instType") != "SPOT"
        or row.get("tdMode") != "cash"
        or row.get("algoId")
        or row.get("algoClOrdId")
        or row.get("attachAlgoOrds")
        or row.get("ordType") not in ("market", "limit")
        or row.get("state") not in ("live", "partially_filled", "filled", "canceled")
    ):
        raise ValueError("OKX order evidence differs from the reviewed cash spot submission.")
    order_id = identity(row.get("ordId"))
    if int(order_id) <= 0:
        raise ValueError("Invalid OKX native order ID.")
    market_order = row.get("ordType") == "market"
    unit = row.get("tgtCcy") or ("base_ccy" if row.get("side") == "sell" else "quote_ccy")
    if market_order and unit != "base_ccy":
        raise ValueError("The OKX market order has no verified requested base quantity.")
    parsed = exchange.parse_order(row)
    parsed["id"] = order_id
    return OrderLookupPage([parsed], {}, True)


def _bybit_lookup(exchange, client_id, symbol, cursor, start, end) -> OrderLookupPage:
    """Find an exact UTA order first in realtime, then in dated history on a miss."""
    market = exchange.market(symbol)
    history = cursor.get("phase") == "history"
    request = {"symbol": market["id"], "orderLinkId": client_id}
    if history:
        request.update(startTime=start, endTime=cursor["end"])
    if cursor.get("page"):
        request["cursor"] = cursor["page"]
    try:
        rows, token = read_spot_orders(exchange, history=history, **request)
    except ccxt.OrderNotFound:
        rows, token = [], None
    candidates = []
    for row in rows:
        if (
            not regular_spot_order(row)
            or row.get("orderLinkId") != client_id
            or row.get("symbol") != market["id"]
            or row.get("orderStatus") not in OPEN | TERMINAL
            or (row["orderType"] == "Market" and row.get("marketUnit") != "baseCoin")
            or (row["orderType"] == "Limit" and row.get("timeInForce") != "GTC")
        ):
            raise ValueError("Bybit order evidence differs from the reviewed cash spot submission.")
        candidates.append(exchange.parse_order(row, market))
    matched = bool(candidates or cursor.get("matched"))
    if token:
        return OrderLookupPage(candidates, {**cursor, "matched": matched, "page": token}, False)
    if not history and not matched:
        cutoff = min(end - 1, exchange.milliseconds())
        return OrderLookupPage([], {"phase": "history", "end": cutoff}, False)
    return OrderLookupPage(candidates, {}, True)


def _kucoin_lookup(exchange, client_id, symbol, cursor) -> OrderLookupPage:
    """Check Classic HF details, then the legacy order namespace used by older submissions."""
    if not isinstance(client_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", client_id):
        raise ValueError("Invalid persisted KuCoin client order ID.")
    market = exchange.market(symbol)
    legacy = cursor.get("phase") == "legacy"
    try:
        response = (
            exchange.privateGetOrderClientOrderClientOid({"clientOid": client_id})
            if legacy
            else exchange.privateGetHfOrdersClientOrderClientOid(
                {"clientOid": client_id, "symbol": market["id"]}
            )
        )
        if not isinstance(response, dict) or response.get("code") != "200000" or "data" not in response:
            raise ccxt.ExchangeError("Invalid KuCoin classic order details response.")
        row = response["data"]
    except ccxt.OrderNotFound:
        row = None
    if row is None:
        return OrderLookupPage([], {} if legacy else {"phase": "legacy"}, legacy)
    if not isinstance(row, dict):
        raise ccxt.ExchangeError("Invalid KuCoin classic order details response.")
    if (
        row.get("clientOid") != client_id
        or row.get("symbol") != market["id"]
        or row.get("tradeType") != "TRADE"
        or row.get("type") not in ("market", "limit")
        or not isinstance(row.get("active", row.get("isActive")), bool)
        or row.get("stop")
        or row.get("postOnly")
        or row.get("hidden")
        or row.get("iceberg")
        or (row["type"] == "limit" and row.get("timeInForce") != "GTC")
        or (row["type"] == "market" and (number(row.get("size")) or 0) <= 0)
    ):
        raise ValueError("KuCoin order evidence differs from the reviewed classic spot submission.")
    return OrderLookupPage([exchange.parse_order(row, market)], {}, True)


def _gemini_lookup(exchange, client_id, symbol) -> OrderLookupPage:
    """Match one Gemini spot GTC limit by its submitted client ID and explicit original size."""
    if not isinstance(client_id, str) or not re.fullmatch(r"[A-Za-z0-9:_#.\-]{1,36}", client_id):
        raise ValueError("Invalid persisted Gemini client order ID.")
    market = exchange.market(symbol)
    try:
        row = exchange.privatePostV1OrderStatus({"client_order_id": client_id, "include_trades": False})
    except ccxt.OrderNotFound:
        return OrderLookupPage([], {}, True)
    if not isinstance(row, dict):
        raise ccxt.ExchangeError("Invalid Gemini order status response.")
    instrument = row.get("symbol")
    live, canceled = row.get("is_live"), row.get("is_cancelled")
    if (
        row.get("client_order_id") != client_id
        or not isinstance(instrument, str)
        or instrument.upper() != market["id"].upper()
        or row.get("exchange") != "gemini"
        or row.get("type") != "exchange limit"
        or row.get("options") != []
        or not isinstance(live, bool)
        or not isinstance(canceled, bool)
        or (live and canceled)
        or row.get("was_forced")
        or row.get("is_hidden")
        or (number(row.get("original_amount")) or 0) <= 0
    ):
        raise ValueError("Gemini order evidence differs from the reviewed spot limit submission.")
    order_id = identity(row.get("order_id"))
    identity(row.get("timestampms"))
    if int(order_id) <= 0 or (row.get("id") is not None and identity(row["id"]) != order_id):
        raise ValueError("Conflicting Gemini native order ID.")
    parsed = exchange.parse_order(row, market)
    parsed["id"] = order_id
    return OrderLookupPage([parsed], {}, True)


def _gate_lookup(exchange, client_id, symbol, cursor, start) -> OrderLookupPage:
    """Read by native text while pending, then scan bounded finish history for an exact client ID."""
    if not isinstance(client_id, str) or not re.fullmatch(r"t-[A-Za-z0-9_.-]{1,28}", client_id):
        raise ValueError("Invalid persisted Gate client order ID.")
    market = exchange.market(symbol)
    instrument = market["id"]
    if "end" not in cursor:
        try:
            row = exchange.privateSpotGetOrdersOrderId(
                {
                    "order_id": client_id,
                    "currency_pair": instrument,
                    "account": "spot",
                }
            )
        except ccxt.OrderNotFound:
            end = exchange.milliseconds() + 1
            return OrderLookupPage([], {"end": end}, False)
        rows, following = [row], {}
    else:
        end = cursor["end"]
        lower = max(start, end - 7 * 86_400_000)
        page = cursor.get("page", 1)
        rows = gate_orders.finished_page(exchange, page, lower, end, instrument=instrument)
        if any(row.get("currency_pair") != instrument for row in rows):
            raise ValueError("Gate returned a different instrument for the recovery window.")
        following = gate_orders.next_page(rows, cursor)
        rows = [row for row in rows if row.get("text") == client_id]
    candidates = []
    for row in rows:
        if (
            not isinstance(row, dict)
            or row.get("text") != client_id
            or row.get("currency_pair") != instrument
            or not gate_orders.reviewed_limit(row)
        ):
            raise ValueError("Gate order evidence differs from the reviewed cash spot limit.")
        native_id = identity(row.get("id"))
        parsed = exchange.parse_order(row, market)
        parsed["id"] = native_id
        candidates.append(parsed)
    return OrderLookupPage(
        candidates, {**following, "end": cursor["end"]} if following else {}, not following
    )
