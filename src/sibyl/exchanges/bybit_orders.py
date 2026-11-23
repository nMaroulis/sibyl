"""Native Bybit UTA spot order reads used by discovery and identity recovery."""

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.history import _token

OPEN = {"Created", "New", "PartiallyFilled", "PendingCancel"}
TERMINAL = {"Filled", "Cancelled", "PartiallyFilledCanceled", "Rejected", "Deactivated"}


def read_spot_orders(exchange, *, history, **filters):
    """Read one native page and validate its product category and cursor."""
    read = exchange.privateGetV5OrderHistory if history else exchange.privateGetV5OrderRealtime
    response = read({"category": "spot", "orderFilter": "Order", "limit": 50, **filters})
    result = response.get("result") if isinstance(response, dict) and response.get("retCode") == 0 else None
    if not isinstance(result, dict) or result.get("category") != "spot" or "nextPageCursor" not in result:
        raise ccxt.ExchangeError("Invalid Bybit spot order response.")
    rows = result.get("list")
    if not isinstance(rows, list) or len(rows) > 50 or any(not isinstance(row, dict) for row in rows):
        raise ccxt.ExchangeError("Invalid Bybit order page.")
    token = _token(result.get("nextPageCursor"))
    if token and token == filters.get("cursor"):
        raise ccxt.ExchangeError("Bybit order cursor did not advance.")
    return rows, token


def regular_spot_order(row: dict) -> bool:
    """Scope observations to ordinary non-leveraged spot orders."""
    return (
        row.get("isLeverage") in ("0", 0)
        and not isinstance(row.get("isLeverage"), bool)
        and row.get("orderType") in ("Market", "Limit")
        and row.get("stopOrderType") in (None, "", "UNKNOWN", "None")
        and not row.get("blockTradeId")
        and not row.get("parentOrderLinkId")
        and all(
            row.get(key) in (None, "") or number(row[key]) == 0
            for key in ("triggerPrice", "takeProfit", "stopLoss")
        )
    )
