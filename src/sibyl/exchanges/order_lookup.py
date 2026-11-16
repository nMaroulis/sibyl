"""Reviewed client-ID lookup pages; these endpoints only read existing orders."""

import re
from dataclasses import dataclass

import ccxt

from sibyl.exchanges.base import number
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
    "demo",
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
