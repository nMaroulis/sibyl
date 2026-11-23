"""Bounded KuCoin Classic spot order responses for the discovery worker."""

import ccxt

from sibyl.exchanges.venue_history import identity

PAGE_SIZE = 50


def _data(response):
    data = response.get("data") if isinstance(response, dict) and response.get("code") == "200000" else None
    if not isinstance(data, dict):
        raise ccxt.ExchangeError("Invalid KuCoin Classic order response.")
    return data


def active_markets(exchange):
    """Find account markets with resting orders without querying the whole catalog."""
    symbols = _data(exchange.privateGetHfOrdersActiveSymbols({})).get("symbols")
    if not isinstance(symbols, list) or any(
        not isinstance(symbol, str) or not symbol or len(symbol) > 80 for symbol in symbols
    ):
        raise ccxt.ExchangeError("Invalid KuCoin active-order markets.")
    if len(symbols) >= 100:
        raise ccxt.NotSupported("KuCoin active markets exceed the discovery page budget.")
    known = {
        market["id"]: symbol
        for symbol, market in exchange.markets.items()
        if market.get("spot") and market.get("active") is not False
    }
    supported = sorted({known[symbol] for symbol in symbols if symbol in known})
    return supported, len(set(symbols) - known.keys())


def market_orders(exchange, symbol, *, recent, cursor, start, end):
    """Read one exact-pair page using Classic's active-page number or closed lastId."""
    market = exchange.market(symbol)
    if recent:
        request = {"symbol": market["id"], "limit": PAGE_SIZE, "startAt": start, "endAt": end - 1}
        if cursor.get("last_id"):
            request["lastId"] = cursor["last_id"]
        data = _data(exchange.privateGetHfOrdersDone(request))
    else:
        page = cursor.get("page", 1)
        request = {"symbol": market["id"], "pageNum": page, "pageSize": PAGE_SIZE}
        # The installed CCXT SDK does not generate this newer native endpoint.
        data = _data(exchange.request("hf/orders/active/page", "private", "GET", request, config={"cost": 2}))
    rows = data.get("items")
    if not isinstance(rows, list) or len(rows) > PAGE_SIZE or any(not isinstance(row, dict) for row in rows):
        raise ccxt.ExchangeError("Invalid KuCoin order page.")
    if recent:
        token = data.get("lastId")
        if len(rows) == PAGE_SIZE and token is None:
            raise ccxt.ExchangeError("KuCoin closed-order continuation is missing.")
        token = identity(token) if token is not None else None
        if rows and token and int(token) and token == cursor.get("last_id"):
            raise ccxt.ExchangeError("KuCoin order cursor did not advance.")
        following = {"last_id": token} if rows and token and int(token) else {}
    else:
        total_pages = data.get("totalPage")
        if (
            type(total_pages) is not int
            or total_pages < 0
            or type(data.get("currentPage")) is not int
            or data["currentPage"] != page
            or (rows and page > total_pages)
            or (not rows and page < total_pages)
        ):
            raise ccxt.ExchangeError("Invalid KuCoin active order pagination.")
        following = {"page": page + 1} if page < total_pages else {}
    orders = []
    expected_active = not recent
    for row in rows:
        if row.get("symbol") != market["id"]:
            raise ccxt.ExchangeError("Unexpected instrument in KuCoin order history.")
        if row.get("tradeType") != "TRADE" or row.get("stop") or row.get("type") not in ("limit", "market"):
            continue
        if row.get("active") is not expected_active:
            raise ccxt.ExchangeError("Unexpected KuCoin order state in the selected stream.")
        orders.append(exchange.parse_order(row, market))
    return orders, following, len(rows) - len(orders)
