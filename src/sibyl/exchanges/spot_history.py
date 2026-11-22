"""Reviewed spot-history cursors for OKX, Bybit UTA, KuCoin classic and Bitget.

Each request reads one page. Native identities, rather than execution timestamps,
advance pages so simultaneous fills cannot disappear at a timestamp boundary.
"""

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.history import TradePage, _token, normalize_trade

DAY = 86_400_000
KINDS = {"okx-bill", "bybit-execution", "kucoin-hf", "bitget-id"}


def history_note(provider: str) -> str:
    """Describe the adapter's requested range, independently of credential readiness."""
    return {
        "okx": "Spot fills in the last 89 days; OKX retains up to three months. Pagination uses bill IDs; execution times use fillTime when reported.",
        "bybit": "UTA spot fills in the last 730 days, read in seven-day windows. Pre-upgrade/classic, margin and derivatives history are excluded.",
        "kucoin": "Classic spot HF fills in the last seven days. KuCoin limits inactive-order history to seven days; UTA and abandoned endpoints are excluded.",
        "bitget": "Classic spot fills in the last 89 days, including exact-order reads. Discounted fee breakdowns without verified wallet effects stay unknown. Bitget retains up to 90 days.",
        "bitfinex": "Exchange-wallet fills start with a frozen 90-day selected-market query and split capped time ranges. Margin fills are excluded; missing cash-type evidence requires review. Native trade IDs and fee-currency wallet effects are shared with exact-order reads. The order-trades endpoint covers trades up to ten days old; closed order details cover up to two weeks.",
        "poloniex": "Cash spot fills start with seven days and overlap one day on later passes. Native pageId advances history; exact-order checks share trade/order IDs and reported fees. Each distinct parent must prove unborrowed scope. Missing/archived parents or borrowed evidence require review. History commits at most 20 fills per page to bound parent reads.",
        "bitmart": "BitMart v4 selected-pair fill imports start with a seven-day query, split capped date ranges and overlap one day on later passes. Exact-order reads inspect the native execution list. Retention and timestamp saturation can limit coverage.",
        "coinex": "CoinEx v2 cash spot imports request the last 30 days by default and overlap one day on subsequent passes. Exact-order reads scan available native pages. Provider retention and page limits qualify coverage.",
        "gate": "Exact-order and selected-market cash fill imports verify the native parent wallet. History starts with seven days and overlaps one day, with at most 20 fills and parent checks per page. GT fees retain their currency; point-card fees need review.",
        "htx": "Selected-market cash history starts with seven days in saved 48-hour ranges. Exact-order and history imports verify one spot wallet. Unavailable parents need review; unverified fee deductions stay unknown. API-cancelled order details can expire after two hours.",
        "mexc": "Selected-pair spot fills and exact-order checks within a rolling 27-day window. Timestamp splits protect capped responses; a saturated single millisecond stops for review.",
        "bitstamp": "Selected spot transactions by ascending native IDs. Embedded order fill details require native market/side evidence; closed-order status is retained by Bitstamp for 30 days. Rescan to revisit old fill/fee corrections; settlement/bust accounting remains separate.",
        "gemini": "Selected spot history by millisecond boundary with retained edge IDs. Saturated 500-trade timestamp groups stop for review. Reported full busts void fills in accounting; manual and unverified breaks remain available for review. Master-key subaccount routing is pending. Exact-order reads use include_trades.",
        "cryptocom": "Crypto.com Exchange cash history starts with seven days in saved native one-day ranges. Exact-order reads cover at most thirty days since creation and share native trade IDs. Explicit parent execution flags and account identity exclude margin/advanced scope; missing parent proof stops for review. Fee-credit consumption remains unknown. Saturated timestamp groups require review.",
        "phemex": "Selected-pair spot history starts with seven days, saves native offsets and overlaps one day on later passes. Exact-order executions share native IDs. Unknown currency scales or unverified discount-token charges leave fees unknown. Open-order discovery also requires selected pairs.",
        "upbit": "Regular current open orders and closed orders created in the initial 30-day range supply native execution UUIDs through native seven-day pages. Older closed orders can be missing. Per-execution fees stay unknown because the order reports only an aggregate paid fee. Native trade-count gaps require review.",
        "demo": "Existing manual Demo fills only; strategy simulations use a separate ledger.",
    }.get(
        provider,
        "Selected spot market, subject to provider retention, permissions and available instruments.",
    )


def _numeric_token(value) -> str | None:
    """Keep potentially large native identifiers exact; never round through a float."""
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).isdecimal():
        raise ccxt.ExchangeError("Invalid spot history identity.")
    return _token(str(value))


def fetch_spot_page(exchange, kind, symbol, cursor, limit, *, order_id=None) -> TradePage:
    """Read a frozen provider range, optionally filtered to one native order.

    Bybit traverses fixed seven-day windows forward, using its opaque cursor
    inside each window. Other adapters walk newest to oldest using native IDs.
    A completed pass leaves a one-day overlap for the next incremental sync.
    Full rescans start again at the adapter's available retention boundary.
    """
    market = exchange.market(symbol)
    now = exchange.milliseconds()
    days = {"okx-bill": 89, "bybit-execution": 730, "kucoin-hf": 7, "bitget-id": 89}[kind]
    start, end = cursor.get("start", max(1, now - days * DAY)), cursor.get("end", now)
    request = {"limit": limit}
    page = cursor.get("page")
    if kind == "okx-bill":
        request.update(instType="SPOT", instId=market["id"], begin=start, end=end)
        if page:
            request["after"] = page
        if order_id:
            request["ordId"] = order_id
        raw = exchange.privateGetTradeFillsHistory(request)["data"]
        following = _numeric_token(raw[-1].get("billId")) if raw else None
    elif kind == "bybit-execution":
        window_start = cursor.get("window_start", start)
        window_end = min(end, window_start + 7 * DAY - 1)
        request.update(
            category="spot", symbol=market["id"], execType="Trade", startTime=window_start, endTime=window_end
        )
        if page:
            request["cursor"] = page
        if order_id:
            request["orderId"] = order_id
        result = exchange.privateGetV5ExecutionList(request)["result"]
        if result.get("category") != "spot":
            raise ccxt.ExchangeError("Unexpected execution category.")
        raw, following = result["list"], _token(result.get("nextPageCursor"))
    elif kind == "kucoin-hf":
        request.update(symbol=market["id"], startAt=start, endAt=end)
        if page:
            request["lastId"] = page
        if order_id:
            request["orderId"] = order_id
        result = exchange.privateGetHfFills(request)["data"]
        raw, following = result["items"], _numeric_token(result.get("lastId"))
    else:
        request.update(symbol=market["id"], startTime=start, endTime=end)
        if page:
            request["idLessThan"] = page
        if order_id:
            request["orderId"] = order_id
        response = exchange.privateSpotGetV2SpotTradeFills(request)
        raw = response.get("data") if isinstance(response, dict) and response.get("code") == "00000" else None
        if not isinstance(raw, list) or len(raw) > limit or any(not isinstance(row, dict) for row in raw):
            raise ccxt.ExchangeError("Invalid Bitget Classic fill page.")
        keys = [_numeric_token(row.get("tradeId")) for row in raw]
        if (
            any(key is None for key in keys)
            or len(set(keys)) != len(keys)
            or (page and any(int(key) >= int(page) for key in keys))
        ):
            raise ccxt.ExchangeError("Bitget fill cursor did not advance across native IDs.")
        following = min(keys, key=int) if keys else None

    if not isinstance(raw, list) or len(raw) > limit or any(not isinstance(row, dict) for row in raw):
        raise ccxt.ExchangeError("Invalid spot history page.")
    if raw and following and following == page:
        raise ccxt.ExchangeError("Spot history cursor did not advance.")
    if (raw and not following and kind != "bybit-execution") or (
        kind == "bybit-execution" and "nextPageCursor" not in result
    ):
        raise ccxt.ExchangeError("Missing spot history cursor.")
    if (
        raw
        and following
        and page
        and kind in {"okx-bill", "kucoin-hf", "bitget-id"}
        and int(following) >= int(page)
    ):
        raise ccxt.ExchangeError("Spot history identity did not move backwards.")
    if not raw and following and kind == "bybit-execution":
        raise ccxt.ExchangeError("Empty execution page has a continuation cursor.")
    parsed = []
    for row in raw:
        native_symbol = row.get("instId") if kind == "okx-bill" else row.get("symbol")
        native_order = row.get("ordId") if kind == "okx-bill" else row.get("orderId")
        if kind == "bitget-id" and isinstance(native_symbol, str):
            native_symbol = native_symbol.upper()
        if native_symbol != market["id"] or (order_id and str(native_order) != order_id):
            raise ccxt.ExchangeError("Unexpected market or order in spot history.")
        if kind == "okx-bill" and (row.get("instType") != "SPOT" or row.get("subType") not in {"1", "2"}):
            raise ccxt.NotSupported("Non-cash spot execution requires a separate adapter.")
        if kind == "bybit-execution" and (
            row.get("execType") != "Trade"
            or row.get("isLeverage") not in {None, "0", 0}
            or row.get("extraFees")
        ):
            raise ccxt.NotSupported("This execution type or additional fee is not reviewed.")
        if kind == "kucoin-hf" and (
            row.get("tradeType") != "TRADE" or (row.get("tax") not in (None, "") and number(row["tax"]) != 0)
        ):
            raise ccxt.NotSupported("Margin executions or additional tax require a separate adapter.")
        if kind == "bitget-id":
            detail = row.get("feeDetail")
            if detail is not None and not isinstance(detail, dict):
                raise ccxt.ExchangeError("Invalid Bitget Classic fee detail.")
            if detail and detail.get("deduction") not in (None, "", "no"):
                row = {**row, "feeDetail": None}
        trade = normalize_trade(exchange.parse_trade(row, market))
        if kind == "kucoin-hf":
            # tradeId identifies a match; id identifies this account's fill leg.
            # A self-trade may have two legs with the same tradeId.
            trade["id"] = _numeric_token(row.get("id"))
        if kind == "okx-bill" and row.get("fillTime") not in (None, ""):
            trade["timestamp"] = number(row["fillTime"])
        if (kind == "bybit-execution" and not row.get("feeCoin")) or (
            kind == "kucoin-hf" and not row.get("feeCurrency")
        ):
            # The SDK may infer the fee currency. Retain only reported facts.
            for fee in trade["fees"]:
                fee["currency"] = None
            trade["fee"]["currency"] = None
        parsed.append(trade)

    # A short ID page is not proof of exhaustion. Follow its native key until
    # an empty page; Bybit explicitly declares the end with its empty token.
    done = not following if kind == "bybit-execution" else not raw
    next_cursor = {"start": start, "end": end, "page": following}
    if kind == "bybit-execution":
        next_cursor["window_start"] = window_start
        if done and window_end < end:
            next_cursor.update(window_start=window_end + 1, page=None)
            done = False
    if done:
        next_cursor = {"start": max(1, end - DAY)}
    return TradePage(parsed, next_cursor, done)
