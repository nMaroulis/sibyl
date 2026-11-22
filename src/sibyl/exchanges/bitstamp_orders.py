"""Bitstamp read-only spot order checks for the account bound to the API key."""

import re
from decimal import Decimal
from uuid import UUID

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.venue_history import identity, rows_list

OPEN = {"Open": "open", "Cancel pending": "canceling", "In Queue": "open"}
TERMINAL = {"Finished", "Canceled"}


def cash_order(row: dict) -> bool:
    """Exclude derivatives, stop instructions and liquidation evidence."""
    return (
        row.get("margin_mode") in (None, "", "NONE", "SPOT", "CASH")
        and (row.get("leverage") in (None, "") or number(row["leverage"]) in (0, 1))
        and row.get("reduce_only") in (None, False)
        and row.get("is_liquidation") in (None, False)
        and all(
            row.get(key) in (None, "") or number(row[key]) == 0
            for key in ("stop_price", "activation_price", "trailing_delta")
        )
    )


def cash_limit(row: dict) -> bool:
    """Keep the ordinary spot limit scope used by open-order discovery."""
    return cash_order(row) and row.get("subtype") in (None, "", "LIMIT")


def _regular_order(row: dict) -> bool:
    """Exclude expiry, linked orders and special instructions from recovery."""
    return (
        cash_order(row)
        and all(
            row.get(key) in (None, "") or number(row[key]) == 0
            for key in ("limit_price", "expire_time", "reserved_margin")
        )
        and all(
            row.get(key) in (None, "", False)
            for key in ("ioc_order", "fok_order", "daily_order", "gtd_order", "moc_order")
        )
    )


def lookup_order(exchange, client_id: str, symbol: str) -> list[dict]:
    """Match exact status to independently corroborated original spot terms."""
    if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", client_id):
        raise ValueError("Invalid persisted Bitstamp client order ID.")
    market = exchange.market(symbol)
    try:
        status = exchange.privatePostOrderStatus({"client_order_id": client_id, "omit_transactions": "True"})
    except ccxt.OrderNotFound:
        return []

    if not isinstance(status, dict):
        raise ccxt.ExchangeError("Invalid Bitstamp order status response.")
    state = status.get("status")
    if state not in OPEN and state not in TERMINAL:
        raise ccxt.ExchangeError("Unexpected Bitstamp order status.")
    order_id = identity(status.get("id"))
    side = str(status.get("type"))
    if (
        status.get("client_order_id") != client_id
        or str(status.get("market", "")).upper() != symbol
        or side not in ("0", "1")
        or status.get("subtype") not in (None, "", "LIMIT", "MARKET")
        or not _regular_order(status)
        or int(order_id) <= 0
    ):
        raise ValueError("Bitstamp order status differs from the reviewed spot limit.")
    if state in TERMINAL or status.get("subtype") == "MARKET":
        return _lookup_creation(exchange, status, market, client_id, order_id)

    rows = rows_list(exchange.privatePostOpenOrdersPair({"pair": market["id"]}), 1000)
    matches = [row for row in rows if row.get("client_order_id") == client_id]
    if not matches:
        # The open list is cached and a new order may take time to appear.
        return []
    if len(matches) != 1:
        raise ValueError("Bitstamp open orders contain duplicate client order IDs.")
    row = matches[0]
    stamp = exchange.parse8601(row.get("datetime"))
    status_stamp = exchange.parse8601(status.get("datetime"))
    amount = number(row.get("amount_at_create"))
    price = number(row.get("price"))
    if (
        identity(row.get("id")) != order_id
        or str(row.get("market") or row.get("currency_pair") or "").upper() != symbol
        or str(row.get("type")) != side
        or row.get("subtype") != "LIMIT"
        or not _regular_order(row)
        or stamp is None
        or status_stamp is None
        or stamp // 1000 != status_stamp // 1000
        or amount is None
        or amount <= 0
        or price is None
        or price <= 0
    ):
        raise ValueError("Bitstamp open-order evidence differs from the reviewed spot limit.")

    return [
        {
            "id": order_id,
            "clientOrderId": client_id,
            "symbol": symbol,
            "side": "buy" if side == "0" else "sell",
            "type": "limit",
            "status": OPEN[state],
            "timestamp": stamp,
            "amount": amount,
            "price": price,
        }
    ]


def _lookup_creation(exchange, status, market, client_id: str, order_id: str) -> list[dict]:
    """Use the venue's recent private creation event when the open snapshot is unavailable."""
    kind = status.get("subtype")
    if kind not in {"LIMIT", "MARKET"}:
        raise ValueError("Missing Bitstamp evidence for the original order type.")
    symbol = market["symbol"]
    rows = rows_list(
        exchange.request(
            "account_order_data/", "private", "POST", {"market": symbol, "order_source": "orderbook"}
        ),
        10000,
    )
    matches = [
        row
        for row in rows
        if row.get("event") == "order_created"
        and isinstance(row.get("data"), dict)
        and str(row["data"].get("id_str")) == order_id
    ]
    if not matches:
        # The default native event range is the last 24 hours.
        return []
    if len(matches) != 1:
        raise ValueError("Bitstamp returned conflicting order creation events.")
    observation = matches[0]
    row = observation["data"]
    try:
        UUID(observation["event_id"])
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise ValueError("Invalid Bitstamp creation event ID.") from error
    stamp = int(identity(row.get("microtimestamp"))) // 1000
    status_stamp = exchange.parse8601(status.get("datetime"))
    amount, remaining = number(row.get("amount_at_create")), number(status.get("amount_remaining"))
    price = number(row.get("price_str"))
    side = str(status["type"])
    account = observation.get("trade_account_id")
    if (
        observation.get("order_source") != "orderbook"
        or account is None
        or row.get("trade_account_id") != account
        or (status.get("trade_account_id") is not None and status["trade_account_id"] != account)
        or identity(row.get("id")) != order_id
        or row.get("client_order_id") != client_id
        or str(row.get("order_type")) != side
        or row.get("is_liquidation") is not False
        or not _regular_order(row)
        or status_stamp is None
        or status_stamp // 1000 != stamp // 1000
        or amount is None
        or amount <= 0
        or remaining is None
        or not 0 <= remaining <= amount
        or (kind == "LIMIT" and (price is None or price <= 0))
    ):
        raise ValueError("Bitstamp creation evidence differs from the reviewed spot order.")
    state = status["status"]
    if state in TERMINAL:
        normalized_state = "closed" if state == "Finished" and remaining == 0 else "canceled"
    else:
        normalized_state = OPEN[state]
    return [
        {
            "id": order_id,
            "clientOrderId": client_id,
            "symbol": symbol,
            "side": "buy" if side == "0" else "sell",
            "type": kind.lower(),
            "status": normalized_state,
            "timestamp": stamp,
            "amount": amount,
            "remaining": remaining,
            "filled": float(Decimal(str(amount)) - Decimal(str(remaining))),
            "price": price if kind == "LIMIT" else None,
        }
    ]
