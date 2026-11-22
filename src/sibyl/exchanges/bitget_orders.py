"""Bitget Classic spot market rules, order details and paginated discovery."""

import re
from decimal import Decimal, InvalidOperation

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.venue_history import identity

OPEN = {"new", "live", "partially_filled"}
TERMINAL = {"filled", "cancelled", "canceled"}
LIMIT = 100


def order_rows(response, limit):
    """Require a successful Classic spot order response with a bounded list."""
    rows = response.get("data") if isinstance(response, dict) and response.get("code") == "00000" else None
    if not isinstance(rows, list) or len(rows) > limit or any(not isinstance(row, dict) for row in rows):
        raise ccxt.ExchangeError("Invalid Bitget Classic spot order page.")
    return rows


def valid_client_id(client_id) -> bool:
    """Recognize the complete saved Bitget client order ID."""
    return isinstance(client_id, str) and bool(re.fullmatch(r"[A-Za-z0-9_-]{1,32}", client_id))


def market_terms(exchange, market, side, amount) -> tuple[str, dict]:
    """Validate the current Classic spot pair and the order's native sizing units."""
    rows = order_rows(exchange.publicSpotGetV2SpotPublicSymbols({"symbol": market["id"]}), 1)
    if not rows or (rows[0].get("symbol"), rows[0].get("baseCoin"), rows[0].get("quoteCoin")) != (
        market["id"],
        market["baseId"],
        market["quoteId"],
    ):
        raise ValueError("Bitget returned rules for a different pair.")
    rules = rows[0]
    if rules.get("status") != "online" or 0 < (number(rules.get("offTime")) or 0) <= exchange.milliseconds():
        raise ValueError("Bitget Classic market orders are unavailable for this pair.")
    digits = str(rules.get("quotePrecision" if side == "buy" else "quantityPrecision"))
    if not re.fullmatch(r"[0-9]{1,2}", digits) or int(digits) > 30:
        raise ValueError("Bitget did not report valid base or quote precision.")
    quantity = Decimal(str(amount))
    precise = format(quantity.normalize(), "f")
    if side == "sell":
        precise = exchange.amount_to_precision(market["symbol"], amount)
    if Decimal(precise) != quantity or quantity.normalize().as_tuple().exponent < -int(digits):
        raise ValueError(
            f"Order exceeds the Bitget market's {'quote' if side == 'buy' else 'base'} precision."
        )
    # These bounds are in USDT even for pairs whose quote is another currency.
    cost = {}
    if market["quoteId"] == "USDT":
        for bound, key in (("min", "minTradeUSDT"), ("max", "maxMarketOrderValue")):
            raw = rules.get(key)
            if raw not in (None, ""):
                value = number(raw)
                if value is None or value < 0:
                    raise ValueError(f"Bitget returned an invalid {key} rule.")
                if value:
                    cost[bound] = value
    if side == "buy" and (amount < cost.get("min", 0) or ("max" in cost and amount > cost["max"])):
        raise ValueError("Quote budget is outside the Bitget market limits.")
    return precise, {"cost": cost}


def market_ack(response, client_id) -> dict:
    """Accept the exact native ID and clientOid from the placement acknowledgment."""
    row = response.get("data") if isinstance(response, dict) and response.get("code") == "00000" else None
    if not isinstance(row, dict) or row.get("clientOid") != client_id:
        raise ValueError("Bitget did not confirm the submitted client order ID.")
    try:
        order_id = identity(row.get("orderId"))
    except ccxt.ExchangeError as error:
        raise ValueError("Bitget did not confirm a usable market order ID.") from error
    if int(order_id) <= 0:
        raise ValueError("Invalid Bitget native order ID.")
    return {"id": order_id, "clientOrderId": client_id}


def market_quantities(row, *, detail=False) -> dict:
    """Read actual fills and expose original base size only on exact sell details."""
    amount = remaining = None
    if detail and row.get("side") == "sell":
        try:
            size = Decimal(str(row.get("size")))
            executed = Decimal(str(row["baseVolume"])) if row.get("baseVolume") is not None else None
        except InvalidOperation as error:
            raise ccxt.ExchangeError("Invalid Bitget market sell quantities.") from error
        if (
            not size.is_finite()
            or (number(size) or 0) <= 0
            or (executed is not None and (not executed.is_finite() or not 0 <= executed <= size))
            or (row.get("status") == "filled" and executed != size)
        ):
            raise ccxt.ExchangeError("Conflicting Bitget market sell quantities.")
        amount = float(size)
        remaining = float(size - executed) if executed is not None else None
    return {
        "amount": amount,
        "remaining": remaining,
        "filled": number(row.get("baseVolume")),
        "cost": number(row.get("quoteVolume")),
        "average": number(row.get("priceAvg", row.get("basePrice"))),
    }


def parse_order(exchange, row, market, *, detail=False):
    """Normalize Classic fields and discard raw payloads after selecting sizing units."""
    order = exchange.parse_order({**row, "symbol": market["id"], "feeDetail": None}, market)
    if row.get("orderType") == "market":
        order.update(market_quantities(row, detail=detail))
        if detail and row.get("side") == "buy":
            order["quote_budget"] = number(row.get("size"))
    elif row.get("orderType") == "limit" and row.get("price") not in (None, ""):
        order["price"] = number(row["price"])
    order["id"] = identity(row.get("orderId"))
    order.pop("info", None)
    return order


def order_detail(exchange, market, **query) -> dict | None:
    """Read one exact Classic order with matching symbol and asset evidence."""
    try:
        rows = order_rows(exchange.privateSpotGetV2SpotTradeOrderInfo(query), 1)
    except ccxt.OrderNotFound:
        return None
    if not rows:
        return None
    row = rows[0]
    instrument = row.get("symbol")
    if (
        not isinstance(instrument, str)
        or instrument.upper() != market["id"]
        or row.get("baseCoin") not in (None, "", market["baseId"])
        or row.get("quoteCoin") not in (None, "", market["quoteId"])
        or row.get("executionType") not in (None, "", "exchange")
        or int(identity(row.get("orderId"))) <= 0
        or any(str(row.get(key)) != value for key, value in query.items())
    ):
        raise ValueError("Bitget order detail differs from the requested Classic spot order.")
    return row


def lookup_order(exchange, client_id, symbol):
    """Recover a reviewed Classic spot GTC limit or market order."""
    if not valid_client_id(client_id):
        raise ValueError("Invalid persisted Bitget client order ID.")
    market = exchange.market(symbol)
    row = order_detail(exchange, market, clientOid=client_id)
    if row is None:
        return []
    limit = (
        row.get("orderType") == "limit"
        and row.get("orderSource") == "normal"
        and row.get("force") in (None, "", "gtc", "GTC")
        and (number(row.get("price")) or 0) > 0
    )
    market_order = (
        row.get("orderType") == "market"
        and row.get("side") in ("buy", "sell")
        and row.get("orderSource") in ("market", "normal")
        and row.get("stpMode") in (None, "", "none")
    )
    if (
        not (limit or market_order)
        or row.get("status") not in OPEN | TERMINAL
        or row.get("tpslType") != "normal"
        or row.get("enterPointSource") != "API"
        or any(
            row.get(key) not in (None, "") and number(row[key]) != 0
            for key in ("triggerPrice", "presetTakeProfitPrice", "presetStopLossPrice")
        )
        or (number(row.get("size")) or 0) <= 0
    ):
        raise ValueError("Bitget order evidence differs from the reviewed Classic spot submission.")
    identity(row.get("cTime"))
    return [parse_order(exchange, row, market, detail=True)]


def discover_page(exchange, recent, cursor, start, end):
    """Read ordinary spot orders and advance the native idLessThan boundary."""
    request = {"tpslType": "normal", "limit": LIMIT}
    after = cursor.get("after")
    if after:
        request["idLessThan"] = after
    if recent:
        request.update(startTime=start, endTime=end - 1)
    read = (
        exchange.privateSpotGetV2SpotTradeHistoryOrders
        if recent
        else exchange.privateSpotGetV2SpotTradeUnfilledOrders
    )
    rows = order_rows(read(request), LIMIT)
    keys = [identity(row.get("orderId")) for row in rows]
    if len(set(keys)) != len(keys) or (after and any(int(key) >= int(after) for key in keys)):
        raise ccxt.ExchangeError("Bitget order IDs did not advance.")
    items = []
    for row in rows:
        if (
            row.get("tpslType") not in (None, "", "normal")
            or row.get("orderType") not in ("market", "limit")
            or row.get("orderSource") not in (None, "", "normal", "market")
        ):
            continue
        if row.get("status") not in (TERMINAL if recent else OPEN):
            raise ccxt.ExchangeError("Unexpected Bitget order state in the selected stream.")
        stamp = number(row.get("cTime"))
        if recent and (stamp is None or not start <= stamp < end):
            raise ccxt.ExchangeError("Bitget order is outside the selected creation window.")
        symbol = row.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            raise ccxt.ExchangeError("Missing Bitget spot market.")
        market = exchange.safe_market(symbol.upper(), marketType="spot")
        if not market.get("spot"):
            continue
        items.append(parse_order(exchange, row, market))
    after = min(keys, key=int) if keys else None
    return items, {"after": after} if after else {}, not rows, len(rows) - len(items)
