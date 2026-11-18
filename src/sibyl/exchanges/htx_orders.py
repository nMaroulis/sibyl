"""Account-bound HTX spot order reads, recovery and individual execution evidence.

All paths resolve the same unambiguous spot wallet as order placement. Native
IDs stay exact. Recent history uses bounded 48-hour windows and execution reads
retain individual fee observations rather than cumulative order fees.
"""

import re

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.history import TradePage, normalize_trade
from sibyl.exchanges.venue_history import identity, rows_list

DAY_MS = 86_400_000
OPEN = {"created", "submitted", "partial-filled"}
TERMINAL = {"filled", "partial-canceled", "canceled"}
ORDER_TYPES = {
    f"{side}-{kind}"
    for side in ("buy", "sell")
    for kind in ("limit", "market", "ioc", "limit-maker", "limit-fok")
}


def spot_account(exchange) -> str:
    """Require one native spot wallet before reading or submitting account activity."""
    accounts = [row for row in exchange.load_accounts() if row.get("type") == "spot"]
    if len(accounts) != 1 or not accounts[0].get("id"):
        raise ValueError("HTX requires one unambiguous spot account for balance and order access.")
    return identity(accounts[0]["id"])


def response_data(response):
    """Require the native success envelope before accepting order or fill evidence."""
    if not isinstance(response, dict) or response.get("status") != "ok" or "data" not in response:
        raise ccxt.ExchangeError("Invalid HTX spot response.")
    return response["data"]


def account_order(row, account, market=None):
    """Validate the exact spot wallet and optional instrument returned by an order read."""
    if not isinstance(row, dict) or identity(row.get("account-id")) != account:
        raise ccxt.ExchangeError("HTX order belongs to a different account.")
    if market is not None and row.get("symbol") != market["id"]:
        raise ccxt.ExchangeError("HTX order belongs to a different spot instrument.")
    identity(row.get("id"))
    if row.get("state") not in OPEN | TERMINAL:
        raise ccxt.ExchangeError("Unexpected HTX order state.")


def parse_order(exchange, row, market):
    """Normalize regular spot types and preserve the exact native order identity."""
    parsed = exchange.parse_order(row, market)
    parsed["id"] = identity(row["id"])
    return parsed


def lookup_order(exchange, client_id, symbol):
    """Recover one API-origin spot GTC limit using its original client-order-id."""
    if not isinstance(client_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", client_id):
        raise ValueError("Invalid persisted HTX client order ID.")
    account, market = spot_account(exchange), exchange.market(symbol)
    try:
        row = response_data(exchange.spotPrivateGetV1OrderOrdersGetClientOrder({"clientOrderId": client_id}))
    except ccxt.OrderNotFound:
        return []
    account_order(row, account, market)
    if (
        row.get("client-order-id") != client_id
        or row.get("type") not in ("buy-limit", "sell-limit")
        or row.get("source") != "spot-api"
        or (row.get("stop-price") not in (None, "") and number(row["stop-price"]) != 0)
        or row.get("operator")
        or (number(row.get("amount")) or 0) <= 0
        or (number(row.get("price")) or 0) <= 0
    ):
        raise ValueError("HTX order evidence differs from the reviewed spot limit submission.")
    identity(row.get("created-at"))
    return [parse_order(exchange, row, market)]


def discover_page(exchange, stream, cursor, start, end, symbols):
    """Read open native-ID pages or selected-pair recent windows, with durable checkpoints."""
    account = spot_account(exchange)
    if cursor.get("account", account) != account:
        raise ccxt.ExchangeError("HTX spot wallet changed during order discovery.")
    open_stream = stream == "open"
    if open_stream:
        request = {"account-id": account, "direct": "next", "size": 100}
        after = cursor.get("after")
        if after:
            request["from"] = after
        rows = rows_list(response_data(exchange.spotPrivateGetV1OrderOpenOrders(request)), 100)
        keys = [identity(row.get("id")) for row in rows]
        if len(set(keys)) != len(keys) or (after and any(int(key) > int(after) for key in keys)):
            raise ccxt.ExchangeError("HTX open-order cursor did not advance.")
        # Some native pages repeat the boundary order. Keep only older IDs.
        if after:
            rows = [row for row in rows if int(identity(row["id"])) < int(after)]
        following = {"account": account, "after": min(keys, key=int)} if rows else {}
        complete, instrument = not rows, None
    else:
        index = cursor.get("market", 0)
        if index >= len(symbols):
            return [], {}, True, 0
        instrument = exchange.market(symbols[index])["id"]
        windows = cursor.get("windows") or [[start, min(start + 2 * DAY_MS, end)]]
        (lower, upper), *pending = windows
        rows = rows_list(
            response_data(
                exchange.spotPrivateGetV1OrderOrders(
                    {
                        "symbol": instrument,
                        "states": "filled,partial-canceled,canceled",
                        "start-time": lower,
                        "end-time": upper - 1,
                        "direct": "next",
                        "size": 100,
                    }
                )
            ),
            100,
        )
        if len(rows) == 100:
            if upper - lower <= 1:
                raise ccxt.NotSupported("An HTX timestamp exceeds the reviewed order capacity.")
            middle = (lower + upper) // 2
            return (
                [],
                {
                    "account": account,
                    "market": index,
                    "windows": [[lower, middle], [middle, upper], *pending],
                },
                False,
                0,
            )
        if any(not lower <= int(identity(row.get("created-at"))) < upper for row in rows):
            raise ccxt.ExchangeError("HTX orders differ from the selected creation window.")
        if not pending and upper < end:
            pending = [[upper, min(upper + 2 * DAY_MS, end)]]
        index += int(not pending)
        following = {"account": account, "market": index, "windows": pending}
        complete = index >= len(symbols)
    orders = []
    for row in rows:
        account_order(row, account)
        native_symbol = row.get("symbol")
        if (
            not isinstance(native_symbol, str)
            or not native_symbol
            or (instrument and instrument != native_symbol)
        ):
            raise ccxt.ExchangeError("Unexpected HTX spot instrument.")
        if row.get("state") not in (OPEN if open_stream else TERMINAL):
            raise ccxt.ExchangeError("Unexpected HTX order state in the selected stream.")
        market = exchange.safe_market(native_symbol, marketType="spot")
        if not market.get("spot") or row.get("type") not in ORDER_TYPES:
            continue
        orders.append(parse_order(exchange, row, market))
    return orders, following, complete, len(rows) - len(orders)


def fetch_order_fills(exchange, order_id, symbol, cursor, limit):
    """Read a bounded exact-order execution list after validating its parent spot wallet."""
    order_id = identity(order_id)
    account, market = spot_account(exchange), exchange.market(symbol)
    parent = response_data(exchange.spotPrivateGetV1OrderOrdersOrderId({"order-id": order_id}))
    account_order(parent, account, market)
    if identity(parent["id"]) != order_id or parent.get("type") not in ORDER_TYPES:
        raise ccxt.ExchangeError("Unsupported HTX parent order evidence.")
    raw = rows_list(
        response_data(exchange.spotPrivateGetV1OrderOrdersOrderIdMatchresults({"order-id": order_id})), 10_000
    )
    parsed, keys = [], set()
    for row in raw:
        key = identity(row.get("id"))
        if key in keys:
            raise ccxt.ExchangeError("Duplicate HTX execution identity.")
        keys.add(key)
        parsed.append(normalize_fill(exchange, row, market, parent))
    after = int(identity(cursor.get("after_id", "0")))
    remaining = sorted((fill for fill in parsed if int(fill["id"]) > after), key=lambda fill: int(fill["id"]))
    selected = remaining[:limit]
    return TradePage(
        selected, {"after_id": selected[-1]["id"] if selected else str(after)}, len(remaining) <= limit
    )


def normalize_fill(exchange, row, market, parent):
    """Keep the parent-bound native execution identity and explicit fee-deduction gaps."""
    key, order_id = identity(row.get("id")), identity(parent.get("id"))
    if (
        identity(row.get("order-id")) != order_id
        or row.get("symbol") != market["id"]
        or row.get("type") != parent["type"]
        or row.get("source") not in {"spot-api", "spot-web", "spot-app", "api", "web", "app", "sys"}
    ):
        raise ccxt.ExchangeError("Unexpected HTX execution identity or account scope.")
    fill = normalize_trade(exchange.parse_trade(row, market))
    fill.update(id=key, order=order_id)
    if (
        row.get("fee-deduct-state") == "ongoing"
        or row.get("fee-deduct-currency")
        or (number(row.get("filled-points")) or 0) != 0
    ):
        fill.update(fee={"currency": None, "cost": None}, fees=[])
    return fill
