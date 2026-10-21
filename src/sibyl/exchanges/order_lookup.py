"""Reviewed client-ID lookup pages; these endpoints only read existing orders."""

from dataclasses import dataclass

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.history import _token

RECOVERY_PROVIDERS = {"binance", "binance-testnet", "coinbase", "coinbase-sandbox", "kraken", "demo"}


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

    Binance/Exchange Sandbox use direct client-ID reads. Coinbase Advanced scans
    an exact-product creation window. Kraken reads client-filtered open orders,
    then closed orders with an opening-time window. No SDK auto-pagination runs.
    """
    if provider in {"binance", "binance-testnet", "coinbase-sandbox"}:
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
