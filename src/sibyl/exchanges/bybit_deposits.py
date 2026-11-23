"""Read dated Bybit on-chain credits without inferring their UNIFIED wallet effect."""

import ccxt

from sibyl.exchanges.history import _token
from sibyl.exchanges.venue_history import identity, rows_list

WINDOW = 29 * 86_400_000
STATUS = {
    1: "pending",
    2: "pending",
    3: "completed",
    4: "failed",
    7: "restricted",
    10011: "pending",
    10012: "restricted",
    70011: "failed",
    70012: "completed",
    70013: "restricted",
}


def deposit_page(exchange, cursor, limit):
    """Advance a native cursor inside each frozen window of dated deposit evidence."""
    start, end = cursor["start"], cursor["end"]
    lower = cursor.get("window_start", start)
    if type(lower) is not int or not start <= lower <= end:
        raise ValueError("Invalid Bybit deposit checkpoint.")
    upper = min(end, lower + WINDOW - 1)
    # Bybit filters at second granularity. Retain precise local boundaries
    # and allow adjacent native seconds to overlap without duplicate writes.
    params = {"startTime": lower // 1000 * 1000, "endTime": upper // 1000 * 1000 + 999, "limit": limit}
    previous = cursor.get("page")
    if previous:
        params["cursor"] = previous
    envelope = exchange.privateGetV5AssetDepositQueryRecord(params)
    result = envelope.get("result") if isinstance(envelope, dict) and envelope.get("retCode") == 0 else None
    if not isinstance(result, dict) or "nextPageCursor" not in result:
        raise ccxt.ExchangeError("Invalid Bybit deposit history response.")
    raw = rows_list(result.get("rows"), limit)
    following = _token(result["nextPageCursor"])
    if following and (following == previous or not raw):
        raise ccxt.ExchangeError("Bybit deposit history cursor did not advance.")

    items, seen = [], set()
    for row in raw:
        # successAt is the only documented timestamp on a deposit row. An
        # undated observation cannot be assigned to a requested interval.
        if row.get("successAt") in (None, "", 0, "0"):
            continue
        stamp = int(identity(row["successAt"]))
        if not params["startTime"] <= stamp <= params["endTime"]:
            raise ccxt.ExchangeError("Bybit returned deposit evidence outside the requested credit interval.")
        if not lower <= stamp <= upper:
            continue
        key = identity(row.get("id"))
        symbol, chain = row.get("coin"), row.get("chain")
        if (
            key in seen
            or not isinstance(symbol, str)
            or not symbol
            or not isinstance(chain, str)
            or not chain
        ):
            raise ccxt.ExchangeError("Invalid Bybit on-chain deposit identity.")
        seen.add(key)
        code = row.get("status")
        status = STATUS.get(code, "unknown") if type(code) is int else "unknown"
        if status in {"pending", "completed"} and row.get("travelRuleStatus") in (1, 2, 3):
            status = "restricted"
        if status == "completed" and row.get("depositType") in ("10", "20", "50"):
            status = "restricted"
        fee = row.get("depositFee")
        items.append(
            {
                "native_id": key,
                "asset": exchange.safe_currency_code(symbol),
                "timestamp_ms": stamp,
                "kind": "deposit",
                "direction": "in",
                "quantity": row.get("amount"),
                "fee": {"currency": None, "cost": None if fee in (None, "") else fee},
                "status": status,
                "internal": False,
                "amount_basis": "provider_reported",
                "wallet_scope": "unknown",
            }
        )
    done = not following and upper == end
    return (
        items,
        {**cursor, "window_start": lower if following or done else upper + 1, "page": following},
        done,
    )
