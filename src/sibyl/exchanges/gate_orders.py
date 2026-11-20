"""Gate cash spot order sizing, normalization and history contracts."""

import hashlib
import json
import re
from decimal import Decimal, InvalidOperation

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


def market_sell_terms(exchange, market, amount) -> tuple[str, dict]:
    """Read current exact-pair rules and validate the reviewed base quantity."""
    rules = exchange.publicSpotGetCurrencyPairsCurrencyPair({"currency_pair": market["id"]})
    if not isinstance(rules, dict) or (rules.get("id"), rules.get("base"), rules.get("quote")) != (
        market["id"],
        market["baseId"],
        market["quoteId"],
    ):
        raise ValueError("Gate returned rules for a different pair.")
    now = exchange.seconds()
    if (
        rules.get("trade_status") not in ("sellable", "tradable")
        or rules.get("type") not in (None, "normal")
        or (number(rules.get("sell_start")) or 0) > now
        or 0 < (number(rules.get("delisting_time")) or 0) <= now
    ):
        raise ValueError("Gate market sells are unavailable for this pair.")

    digits = rules.get("amount_precision")
    if type(digits) is not int or not 0 <= digits <= 30:
        raise ValueError("Gate did not report valid base quantity precision.")
    quantity = Decimal(str(amount))
    precise = exchange.amount_to_precision(market["symbol"], amount)
    if Decimal(precise) != quantity or quantity.normalize().as_tuple().exponent < -digits:
        raise ValueError("Quantity exceeds the Gate market's base precision.")

    minimum = pair_limit(rules, "min_base_amount")
    allowed = [
        value
        for key in ("max_base_amount", "market_order_max_stock")
        if (value := pair_limit(rules, key)) is not None
    ]
    maximum = min(allowed, default=None)
    if minimum is not None and quantity < minimum:
        raise ValueError(f"Order is below the Gate minimum base quantity of {minimum}.")
    if maximum is not None and quantity > maximum:
        raise ValueError(f"Order exceeds the Gate maximum base quantity of {maximum}.")
    return precise, {
        "cost": {
            bound: float(value)
            for bound, key in (("min", "min_quote_amount"), ("max", "max_quote_amount"))
            if (value := pair_limit(rules, key)) is not None
        }
    }


def pair_limit(rules, key) -> Decimal | None:
    """Parse a documented optional positive market limit without float rounding."""
    raw = rules.get(key)
    if raw is None:
        return None
    try:
        value = Decimal(str(raw))
    except InvalidOperation as error:
        raise ValueError(f"Gate returned an invalid {key} rule.") from error
    if not value.is_finite() or value < 0:
        raise ValueError(f"Gate returned an invalid {key} rule.")
    return value or None


def valid_client_id(client_id) -> bool:
    """Recognize a complete user-generated native Gate text ID."""
    return isinstance(client_id, str) and bool(re.fullmatch(r"t-[A-Za-z0-9_.-]{1,28}", client_id))


def reviewed_market_sell(row: dict) -> bool:
    """Only attribute an ordinary cash IOC sell with original base sizing."""
    return (
        cash_order(row)
        and row.get("type") == "market"
        and row.get("side") == "sell"
        and row.get("time_in_force") == "ioc"
        and row.get("status") in ("open", "closed", "cancelled")
        and (number(row.get("amount")) or 0) > 0
        and (number(row.get("iceberg")) == 0 or row.get("iceberg") in (None, ""))
        and row.get("amend_text") in (None, "", "-")
        and not row.get("stop_profit")
        and not row.get("stop_loss")
    )


def market_sell_status(row) -> str:
    """Keep partial terminal market sells distinct from fully filled orders."""
    state, reason = row.get("status"), row.get("finish_as")
    if state == "open" and reason in (None, "", "open"):
        return "open"
    if state not in ("closed", "cancelled") or reason == "open":
        return "unknown"
    try:
        quantity, filled = (Decimal(str(row.get(key))) for key in ("amount", "filled_amount"))
    except InvalidOperation:
        return "unknown"
    if not (quantity.is_finite() and filled.is_finite() and 0 <= filled <= quantity and quantity > 0):
        return "unknown"
    if filled == quantity and state == "closed" and reason in (None, "", "filled"):
        return "closed"
    if filled < quantity and reason != "filled":
        return "canceled"
    return "unknown"


def parse_market_sell_ack(exchange, market, request, row) -> dict:
    """Verify original reviewed terms before attaching the native order ID."""
    try:
        if (
            not isinstance(row, dict)
            or not reviewed_market_sell(row)
            or any(row.get(key) != request[key] for key in ("currency_pair", "text"))
            or Decimal(str(row.get("amount"))) != Decimal(request["amount"])
        ):
            raise ValueError("Gate did not confirm the original market sell.")
        native_id = identity(row.get("id"))
        if int(native_id) <= 0:
            raise ValueError("Invalid Gate order identity.")
        parsed = exchange.parse_order(row, market)
    except (ccxt.ExchangeError, InvalidOperation) as error:
        raise ValueError("Gate did not confirm usable market sell details.") from error
    parsed["id"] = native_id
    return parsed


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
