"""Bounded native order-fill reads; no generic timestamp pagination or order writes."""

import ccxt

from sibyl.exchanges.history import TradePage, _token, normalize_trade


def fetch_order_fill_page(
    exchange, kind: str, order_id: str, symbol: str, cursor: dict, limit: int
) -> TradePage:
    """Read one native page, retaining provider IDs and fee currency/sign.

    Kraken first snapshots an order's individual trade IDs, then reads at most
    twenty IDs per page. Other providers filter by the exact order at source.
    Cursors are private server state and a new pass starts from the beginning.
    """
    market = exchange.market(symbol)
    if kind == "binance-id":
        after = int(cursor.get("from_id", "0"))
        rows = exchange.fetch_my_trades(
            symbol, limit=limit, params={"orderId": order_id, "fromId": str(after)}
        )
        identities = [str(row.get("id", "")) for row in rows]
        if any(not value.isdecimal() or int(value) < after for value in identities):
            raise ccxt.ExchangeError("Invalid order execution IDs.")
        following = str(max(map(int, identities)) + 1) if rows else str(after)
        return TradePage([normalize_trade(row) for row in rows], {"from_id": following}, not rows)

    if kind in {"coinbase-cursor", "coinbase-exchange-cursor"}:
        if kind == "coinbase-cursor":
            request = {"order_ids": [order_id], "product_ids": [market["id"]], "limit": limit}
            if cursor.get("page"):
                request["cursor"] = cursor["page"]
            response = exchange.v3PrivateGetBrokerageOrdersHistoricalFills(request)
            if response.get("proof_token_required"):
                raise ccxt.PermissionDenied("Additional provider history verification is required.")
            rows, following = response["fills"], _token(response.get("cursor"))
        else:
            request = {"order_id": order_id, "product_id": market["id"], "limit": limit}
            if cursor.get("page"):
                request["after"] = cursor["page"]
            rows = exchange.privateGetFills(request)
            headers = {key.lower(): value for key, value in (exchange.last_response_headers or {}).items()}
            following = _token(headers.get("cb-after"))
            if len(rows) >= limit and not following:
                raise ccxt.ExchangeError("Missing order execution pagination header.")
        parsed = exchange.parse_trades(rows, market)
        if len(parsed) != len(rows):
            raise ccxt.ExchangeError("Unexpected order execution market.")
        return TradePage(
            [normalize_trade(row) for row in parsed], {"page": following}, not rows or not following
        )

    if kind == "kraken-cursor":
        identities = cursor.get("ids")
        if identities is None:
            result = exchange.privatePostQueryOrders(
                {"txid": order_id, "trades": True, "consolidate_taker": False}
            )["result"]
            identities = result[order_id].get("trades")
            if not isinstance(identities, list) or len(identities) > 10_000:
                raise ccxt.ExchangeError("Missing or excessive order trade identities.")
            if any(not isinstance(value, str) or not value or len(value) > 256 for value in identities):
                raise ccxt.ExchangeError("Invalid order trade identities.")
            if len(set(identities)) != len(identities):
                raise ccxt.ExchangeError("Duplicate order trade identities.")
        offset = cursor.get("offset", 0)
        batch = identities[offset : offset + min(20, limit)]
        rows = []
        if batch:
            trades = exchange.privatePostQueryTrades({"txid": ",".join(batch), "consolidate_taker": False})[
                "result"
            ]
            if set(trades) != set(batch):
                raise ccxt.ExchangeError("Incomplete order trade response.")
            rows = exchange.parse_trades([{**value, "id": key} for key, value in trades.items()], market)
            if len(rows) != len(batch):
                raise ccxt.ExchangeError("Unexpected order trade market.")
        following = offset + len(batch)
        return TradePage(
            [normalize_trade(row) for row in rows],
            {"ids": identities, "offset": following},
            following >= len(identities),
        )
    raise ccxt.NotSupported("Order execution imports are not reviewed for this provider.")
