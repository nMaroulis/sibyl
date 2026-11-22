"""Exact, read-only OKX funding observations and Trading wallet transfer bills."""

from decimal import Decimal, InvalidOperation

import ccxt

from sibyl.exchanges.venue_history import identity, rows_list

DAY = 86_400_000
TRANSFER_LOOKBACK = 89 * DAY
WALLETS = {"6": "FUNDING", "18": "TRADING"}
DEPOSIT_STATES = {
    "0": "pending",
    "1": "restricted",
    "2": "completed",
    "8": "pending",
    "11": "restricted",
    "12": "restricted",
    "13": "restricted",
    "14": "restricted",
    "17": "restricted",
}
WITHDRAWAL_STATES = {
    **dict.fromkeys(("-3", "0", "1", "7", "10", "15", "19"), "pending"),
    **dict.fromkeys(("4", "5", "6", "8", "9", "12", "16", "17"), "restricted"),
    "-2": "cancelled",
    "-1": "failed",
    "2": "completed",
}


def rows(response, limit):
    """Check OKX's status envelope and native page bound."""
    if not isinstance(response, dict) or response.get("code") != "0":
        raise ccxt.ExchangeError("Invalid OKX funding response.")
    return rows_list(response.get("data"), limit)


def decimal(value):
    """Parse native decimal evidence without coercing booleans or nonfinite values."""
    try:
        result = Decimal(str(value))
    except InvalidOperation as error:
        raise ccxt.ExchangeError("Invalid OKX funding amount.") from error
    if not result.is_finite():
        raise ccxt.ExchangeError("Invalid OKX funding amount.")
    return result


def currency(exchange, raw):
    """Require a currency identity before applying the SDK's alias mapping."""
    if not isinstance(raw, str) or not raw or raw.strip() != raw:
        raise ccxt.ExchangeError("Missing OKX funding currency.")
    return exchange.safe_currency_code(raw)


def exact_id(value):
    """Keep large provider counters exact and require a positive native value."""
    key = identity(value)
    if int(key) <= 0:
        raise ccxt.ExchangeError("Invalid OKX funding identity.")
    return key


def onchain_page(exchange, stream, cursor, limit):
    """Split capped creation-time ranges so a busy millisecond cannot be skipped."""
    start, end = cursor["start"], cursor["end"]
    (lower, upper), *remaining = cursor.get("windows") or [[start, end]]
    if not 0 < start <= lower <= upper <= end:
        raise ValueError("Invalid OKX on-chain funding window.")
    is_deposit = stream == "deposit"
    read = exchange.privateGetAssetDepositHistory if is_deposit else exchange.privateGetAssetWithdrawalHistory
    # Keep each boundary millisecond inside the request even if the venue treats
    # the parameters as exclusive. Trim deliberate edge overlaps after reading.
    data = rows(
        read({"before": str(lower - 1), "after": str(upper + 1), "type": "4", "limit": str(limit)}),
        limit,
    )
    timestamps = [int(exact_id(row.get("ts"))) for row in data]
    if any(not lower - 1 <= stamp <= upper + 1 for stamp in timestamps):
        raise ccxt.ExchangeError("OKX returned activity outside the requested funding window.")
    if len(data) == limit:
        if lower == upper:
            raise ccxt.NotSupported("OKX funding history is saturated at a single timestamp.")
        middle = (lower + upper) // 2
        return [], {**cursor, "windows": [[lower, middle], [middle + 1, upper], *remaining]}, False

    items = []
    for row, stamp in zip(data, timestamps, strict=True):
        if not lower <= stamp <= upper:
            continue
        if (
            row.get("type") not in (None, "", "4")
            or row.get("fromWdId") not in (None, "")
            or not isinstance(row.get("chain"), str)
            or not row["chain"].strip()
        ):
            raise ccxt.ExchangeError("OKX returned a movement without reviewed on-chain scope.")
        converted_amount = row.get("xstockShareAmount")
        if row.get("xstockShareName") or (
            converted_amount not in (None, "") and decimal(converted_amount) != 0
        ):
            raise ccxt.NotSupported("Converted xStock deposits require separate accounting.")
        quantity = decimal(row.get("amt"))
        fee = None if is_deposit or row.get("fee") in (None, "") else decimal(row["fee"])
        if quantity <= 0 or (fee is not None and fee < 0):
            raise ccxt.ExchangeError("Invalid OKX on-chain amount or fee.")
        states = DEPOSIT_STATES if is_deposit else WITHDRAWAL_STATES
        fee_currency = currency(exchange, row["feeCcy"]) if fee is not None and row.get("feeCcy") else None
        items.append(
            {
                "native_id": exact_id(row.get("depId" if is_deposit else "wdId")),
                "asset": currency(exchange, row.get("ccy")),
                "timestamp_ms": stamp,
                "kind": stream,
                "direction": "in" if is_deposit else "out",
                "quantity": str(quantity),
                "fee": {"currency": fee_currency, "cost": str(fee) if fee is not None else None},
                "status": states.get(row.get("state"), "unknown"),
                "internal": False,
                "amount_basis": "provider_reported",
                "wallet_scope": "unknown",
            }
        )
    return items, {**cursor, "windows": remaining}, not remaining


def transfer_page(exchange, cursor, limit):
    """Read posted Trading wallet changes by native ID and confirm the Funding route."""
    start, end = cursor["start"], cursor["end"]
    if start < exchange.milliseconds() - TRANSFER_LOOKBACK:
        raise ccxt.NotSupported("Choose an OKX Trading wallet transfer range within the last 89 days.")
    after = cursor.get("after")
    lower, upper = start - 1, end + 1
    params = {"type": "1", "begin": str(lower), "end": str(upper), "limit": str(limit)}
    if after is not None:
        params["after"] = exact_id(after)
    data = rows(exchange.privateGetAccountBillsArchive(params), limit)
    keys = [exact_id(row.get("billId")) for row in data]
    if len(set(keys)) != len(keys) or (after is not None and any(int(key) >= int(after) for key in keys)):
        raise ccxt.ExchangeError("OKX Trading wallet transfer cursor did not advance.")

    items = []
    for row, key in zip(data, keys, strict=True):
        stamp = int(exact_id(row.get("ts")))
        if not lower <= stamp <= upper:
            raise ccxt.ExchangeError("OKX returned a transfer outside the requested wallet window.")
        if not start <= stamp <= end:
            continue
        source, target = WALLETS.get(row.get("from")), WALLETS.get(row.get("to"))
        change = decimal(row.get("balChg"))
        incoming = target == "TRADING"
        if (
            row.get("type") != "1"
            or {source, target} != {"FUNDING", "TRADING"}
            or row.get("subType") != ("11" if incoming else "12")
            or (change <= 0 if incoming else change >= 0)
            or row.get("instType") not in (None, "")
            or row.get("mgnMode") not in (None, "")
        ):
            raise ccxt.ExchangeError("OKX bill does not prove a posted Trading/Funding wallet transfer.")
        asset = currency(exchange, row.get("ccy"))
        native_fee = row.get("fee")
        fee = decimal(native_fee) if native_fee not in (None, "") else None
        items.append(
            {
                "native_id": key,
                "asset": asset,
                "timestamp_ms": stamp,
                "posted_ms": stamp,
                "kind": "transfer",
                "direction": "in" if incoming else "out",
                "quantity": str(change.copy_abs()),
                "fee": {
                    "currency": asset if fee is not None else None,
                    "cost": str(fee.copy_negate()) if fee is not None else None,
                },
                "status": "completed",
                "internal": True,
                "amount_basis": "ledger_amount",
                "wallet_scope": "configured",
                "wallet_route": {"from": source, "to": target},
            }
        )
    return items, {**cursor, "after": min(keys, key=int) if keys else after}, not keys


def cash_snapshot(exchange):
    """Read trading cash balances for quantity reconciliation, excluding mark-to-market equity."""
    (account,) = rows(exchange.privateGetAccountBalance({}), 1)
    details = rows_list(account.get("details"), 2000)
    totals = {}
    for detail in details:
        asset = currency(exchange, detail.get("ccy"))
        amount = decimal(detail.get("cashBal"))
        if asset in totals or not 0 <= amount <= Decimal("1e30"):
            raise ccxt.ExchangeError("Incomplete or unsupported OKX Trading wallet cash balance.")
        totals[asset] = float(amount)
    stamp = int(exact_id(account["uTime"])) if account.get("uTime") not in (None, "") else None
    return {"total": totals, "free": {}, "used": {}, "timestamp": stamp}
