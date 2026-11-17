"""Read-only Gate cash spot order normalization and page contracts."""

import hashlib
import json

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.venue_history import identity

OPEN_LIMIT = 20
HISTORY_LIMIT = 100


def cash_order(row: dict) -> bool:
    """Admit ordinary cash spot records with the instrument's native quote asset."""
    instrument = row.get("currency_pair")
    return (
        isinstance(instrument, str)
        and bool(instrument)
        and row.get("account") == "spot"
        and row.get("type") in ("limit", "market")
        and row.get("trade_quote") in (None, "", instrument.rsplit("_", 1)[-1])
        and row.get("auto_borrow") in (None, False)
        and row.get("auto_repay") in (None, False)
    )


def finished_page(exchange, page, start, end, *, instrument=None):
    """Read a fixed finish-time window using native second-based bounds."""
    request = {
        "account": "spot",
        "status": "finished",
        "page": page,
        "limit": HISTORY_LIMIT,
        "from": start // 1000,
        "to": (end - 1) // 1000,
    }
    if instrument:
        request["currency_pair"] = instrument
    rows = exchange.privateSpotGetOrders(request)
    if (
        not isinstance(rows, list)
        or len(rows) > HISTORY_LIMIT
        or any(not isinstance(row, dict) for row in rows)
    ):
        raise ccxt.ExchangeError("Invalid Gate finished-order page.")
    return rows


def open_page(exchange, page):
    """Flatten a page of native instrument groups without assuming what each total counts."""
    groups = exchange.privateSpotGetOpenOrders({"account": "spot", "page": page, "limit": OPEN_LIMIT})
    if not isinstance(groups, list) or any(not isinstance(group, dict) for group in groups):
        raise ccxt.ExchangeError("Invalid Gate open-order groups.")
    rows, instruments = [], set()
    for group in groups:
        instrument, orders = group.get("currency_pair"), group.get("orders")
        if (
            not isinstance(instrument, str)
            or not instrument
            or instrument in instruments
            or not isinstance(orders, list)
            or len(orders) > OPEN_LIMIT
            or any(
                not isinstance(order, dict) or order.get("currency_pair") != instrument for order in orders
            )
        ):
            raise ccxt.ExchangeError("Invalid Gate open-order instrument page.")
        instruments.add(instrument)
        rows.extend(orders)
        if len(rows) > 1000:
            raise ccxt.NotSupported("Gate open-order page exceeds the reviewed row budget.")
    return rows


def next_page(rows, cursor):
    """Advance page-number pagination until empty and reject repeated native observations."""
    if not rows:
        return {}
    ids = sorted(identity(row.get("id")) for row in rows)
    if len(set(ids)) != len(ids):
        raise ccxt.ExchangeError("Duplicate Gate spot order identities.")
    digest = hashlib.sha256(json.dumps(ids).encode()).hexdigest()
    if digest == cursor.get("digest"):
        raise ccxt.ExchangeError("Gate returned a repeated order page.")
    return {"page": cursor.get("page", 1) + 1, "digest": digest}


def reviewed_limit(row: dict) -> bool:
    """Require terms Sibyl can compare to its reviewed GTC submission."""
    return (
        cash_order(row)
        and row.get("type") == "limit"
        and row.get("time_in_force") == "gtc"
        and row.get("status") in ("open", "closed", "cancelled")
        and (number(row.get("iceberg")) == 0 or row.get("iceberg") in (None, ""))
        and not row.get("stop_profit")
        and not row.get("stop_loss")
    )
