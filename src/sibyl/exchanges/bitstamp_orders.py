"""Bitstamp read-only spot order checks for the account bound to the API key."""

import re

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.venue_history import identity, rows_list

OPEN = {"Open": "open", "Cancel pending": "canceling", "In Queue": "open"}
TERMINAL = {"Finished", "Canceled"}


def cash_limit(row: dict) -> bool:
    """Keep the ordinary spot limit scope used by open-order discovery."""
    return (
        row.get("margin_mode") in (None, "", "NONE", "SPOT", "CASH")
        and (row.get("leverage") in (None, "") or number(row["leverage"]) in (0, 1))
        and row.get("subtype") in (None, "", "LIMIT")
        and row.get("reduce_only") in (None, False)
        and all(
            row.get(key) in (None, "") or number(row[key]) == 0
            for key in ("stop_price", "activation_price", "trailing_delta")
        )
    )


def _resting_limit(row: dict) -> bool:
    """Exclude expiry, linked orders and special instructions from recovery."""
    return (
        cash_limit(row)
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
    """Match exact status to the resting order's original terms on the selected market."""
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
        or not _resting_limit(status)
        or int(order_id) <= 0
    ):
        raise ValueError("Bitstamp order status differs from the reviewed spot limit.")
    if state in TERMINAL:
        raise ValueError("The closed Bitstamp order has no reviewed source of original limit terms.")

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
        or not _resting_limit(row)
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
