"""Read-only native funding pages; no addresses, raw payloads or write endpoints."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import quote, unquote

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.history import _token

DAY = 86_400_000


@dataclass(frozen=True)
class FundingPage:
    """A validated provider range is exhausted only after its native pagination ends."""

    items: list[dict]
    cursor: dict
    caught_up: bool


def funding_streams(exchange: str) -> list[str]:
    """Advertise reviewed reads without constructing a transport or inheriting production support."""
    return {
        "demo": ["deposit", "withdrawal", "transfer"],
        "binance": ["deposit", "withdrawal"],
        "kraken": ["deposit", "withdrawal", "transfer"],
        "bybit": ["withdrawal", "transfer"],
    }.get(exchange, [])


def _binance_row(row: dict, stream: str) -> dict:
    """Preserve native IDs, status and reported amount; never infer an address match."""
    if stream == "deposit":
        timestamp = number(row.get("insertTime"))
        status = {0: "pending", 1: "completed", 2: "failed", 6: "restricted", 7: "failed", 8: "pending"}.get(
            row.get("status"), "unknown"
        )
        fee = {"currency": None, "cost": None}
    else:
        timestamp = number(row.get("applyTime"))
        if timestamp is None and isinstance(row.get("applyTime"), str):
            try:
                timestamp = (
                    datetime.strptime(row["applyTime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).timestamp()
                    * 1000
                )
            except ValueError:
                pass
        status = {
            0: "pending",
            1: "cancelled",
            2: "pending",
            3: "failed",
            4: "pending",
            5: "failed",
            6: "completed",
        }.get(row.get("status"), "unknown")
        fee = {"currency": row.get("coin"), "cost": row.get("transactionFee")}
    completed = number(row.get("completeTime"))
    if completed is None and isinstance(row.get("completeTime"), str):
        try:
            completed = (
                datetime.strptime(row["completeTime"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).timestamp()
                * 1000
            )
        except ValueError:
            pass
    return {
        "native_id": row.get("id"),
        "reference": None,
        "asset": row.get("coin"),
        "timestamp_ms": timestamp,
        "posted_ms": completed,
        "kind": stream,
        "direction": "in" if stream == "deposit" else "out",
        "quantity": row.get("amount"),
        "fee": fee,
        "status": status,
        "internal": row.get("transferType") == 1,
        "amount_basis": "provider_reported",
        # Never interpret a missing walletType as Spot. Sibyl reads Spot balances.
        "wallet_scope": {0: "configured", 1: "outside"}.get(row.get("walletType"), "unknown")
        if type(row.get("walletType")) is int
        else "unknown",
    }


def fetch_funding_page(exchange, provider: str, stream: str, cursor: dict, limit: int = 50) -> FundingPage:
    """Read one page inside a user-selected frozen UTC range.

    Binance capital endpoints use offsets in windows shorter than 90 days.
    Kraken uses the ledger cursor API, with an exclusive lower time bound.
    Unknown status/fee data remains explicit; SDK auto-pagination is never used.
    """
    if stream not in funding_streams(provider):
        raise ccxt.NotSupported("Funding history is not reviewed for this provider/stream.")
    if not 1 <= limit <= 50:
        raise ValueError("Funding pages support 1–50 records.")
    start, end = cursor["start"], cursor["end"]
    if provider == "bybit" and stream == "transfer":
        return _bybit_wallet_transfers(exchange, cursor, limit)
    if provider == "bybit":
        # The endpoint permits less than thirty days per request. Freeze and
        # paginate each 29-day slice; the user-selected range can be longer.
        window_start = cursor.get("window_start", start)
        window_end = min(end, window_start + 29 * DAY - 1)
        request = {"startTime": window_start, "endTime": window_end, "withdrawType": 0, "limit": limit}
        if cursor.get("page"):
            request["cursor"] = cursor["page"]
        result = exchange.privateGetV5AssetWithdrawQueryRecord(request)["result"]
        raw, following = result["rows"], _token(result.get("nextPageCursor"))
        if (
            not isinstance(raw, list)
            or len(raw) > limit
            or (following and (not raw or following == cursor.get("page")))
        ):
            raise ccxt.ExchangeError("Invalid withdrawal history cursor.")
        if "nextPageCursor" not in result:
            raise ccxt.ExchangeError("Missing withdrawal history cursor.")
        rows = []
        for row in raw:
            if row.get("withdrawType") != 0 or (row.get("tax") not in (None, "") and number(row["tax"]) != 0):
                raise ccxt.NotSupported("Off-chain withdrawals and additional taxes are not reviewed.")
            asset = exchange.safe_currency_code(row.get("coin"))
            rows.append(
                {
                    "native_id": row.get("withdrawId"),
                    "reference": None,
                    "asset": asset,
                    "timestamp_ms": number(row.get("createTime")),
                    "kind": stream,
                    "direction": "out",
                    "quantity": row.get("amount"),
                    "fee": {"currency": asset, "cost": row.get("withdrawFee")},
                    "status": {
                        "success": "completed",
                        "CancelByUser": "cancelled",
                        "Reject": "failed",
                        "Fail": "failed",
                        "SecurityCheck": "pending",
                        "Pending": "pending",
                        "BlockchainConfirmed": "pending",
                        "MoreInformationRequired": "restricted",
                    }.get(row.get("status"), "unknown"),
                    "internal": False,
                    "amount_basis": "provider_reported",
                }
            )
        done = not following
        next_cursor = {**cursor, "window_start": window_start, "page": following}
        if done and window_end < end:
            next_cursor.update(window_start=window_end + 1, page=None)
            done = False
        return FundingPage(rows, next_cursor, done)
    if provider == "binance":
        if end - start >= 90 * DAY:
            raise ValueError("Binance funding ranges must be shorter than 90 days.")
        offset = cursor.get("offset", 0)
        request = {"startTime": start, "endTime": end, "offset": offset, "limit": limit}
        method = (
            exchange.sapiGetCapitalDepositHisrec
            if stream == "deposit"
            else exchange.sapiGetCapitalWithdrawHistory
        )
        rows = method(request)
        if not isinstance(rows, list) or len(rows) > limit:
            raise ccxt.ExchangeError("Invalid funding history page.")
        normalized = [_binance_row(row, stream) for row in rows]
        for row in normalized:
            row["asset"] = exchange.safe_currency_code(row["asset"])
            if row["fee"]["currency"] is not None:
                row["fee"]["currency"] = row["asset"]
        return FundingPage(
            normalized,
            {**cursor, "offset": offset + len(rows)},
            len(rows) < limit,
        )
    request = {
        "type": stream,
        "start": max(0, start // 1000 - 1),
        "end": (end + 999) // 1000,
        "with_cursor": True,
    }
    if cursor.get("page"):
        request["cursor"] = cursor["page"]
    result = exchange.privatePostLedgers(request)["result"]
    raw = result["ledger"]
    if not isinstance(raw, dict) or len(raw) > 50:
        raise ccxt.ExchangeError("Missing funding history cursor or invalid page.")
    if "cursor" not in result and (len(raw) >= 50 or (number(result.get("count")) or 0) > len(raw)):
        raise ccxt.ExchangeError("Missing funding history pagination cursor.")
    following = _token((result.get("cursor") or {}).get("next"))
    if following and (not raw or following == cursor.get("page")):
        raise ccxt.ExchangeError("Funding history cursor did not advance.")
    rows = []
    for identity, row in raw.items():
        amount = number(row.get("amount"))
        if row.get("type") != stream or amount is None:
            raise ccxt.ExchangeError("Unexpected funding ledger entry.")
        asset = exchange.safe_currency_code(row.get("asset"))
        rows.append(
            {
                "native_id": identity,
                "reference": row.get("refid"),
                "asset": asset,
                "timestamp_ms": number(row.get("time")) * 1000
                if number(row.get("time")) is not None
                else None,
                "kind": stream,
                "direction": "in" if amount >= 0 else "out",
                "quantity": abs(amount),
                "fee": {"currency": asset, "cost": row.get("fee")},
                "status": "completed",
                "internal": stream == "transfer",
                "amount_basis": "ledger_amount",
                "wallet_scope": "configured",
                "posted_ms": number(row.get("time")) * 1000 if number(row.get("time")) is not None else None,
            }
        )
    # Native integer-second bounds include surrounding milliseconds. Trim only this
    # deliberate expansion; the raw page still controls cursor advancement.
    rows = [row for row in rows if row["timestamp_ms"] is None or start <= row["timestamp_ms"] <= end]
    return FundingPage(rows, {**cursor, "page": following}, not following)


def _bybit_wallet_transfers(exchange, cursor, limit):
    """Read one bounded same-UID page and keep only movements across the UNIFIED wallet."""
    start, end = cursor["start"], cursor["end"]
    window_start = cursor.get("window_start", start)
    # Align internal slice boundaries to whole seconds, since Bybit ignores the
    # millisecond part of the bounds. Trim the outer edge after the native read.
    window_end = min(end, (window_start // 1000) * 1000 + 7 * DAY - 1)
    request = {
        "startTime": (window_start // 1000) * 1000,
        "endTime": window_end,
        "limit": limit,
    }
    if cursor.get("page"):
        # CCXT's Bybit signing strips one URL-encoding layer from parameters.
        request["cursor"] = quote(cursor["page"], safe="")
    result = exchange.privateGetV5AssetTransferQueryInterTransferList(request).get("result")
    if not isinstance(result, dict) or not isinstance(result.get("list"), list):
        raise ccxt.ExchangeError("Invalid Bybit wallet transfer page.")
    rows = result["list"]
    if "nextPageCursor" not in result:
        raise ccxt.ExchangeError("Missing Bybit wallet transfer cursor.")
    following = _token(result["nextPageCursor"])
    if following:
        following = unquote(following)
        if not following.isascii() or any(not 32 < ord(char) < 127 for char in following):
            raise ccxt.ExchangeError("Invalid Bybit wallet transfer cursor.")
    if len(rows) > limit or (following and (not rows or following == cursor.get("page"))):
        raise ccxt.ExchangeError("Bybit wallet transfer cursor did not advance.")

    items = []
    for row in rows:
        if not isinstance(row, dict):
            raise ccxt.ExchangeError("Invalid Bybit wallet transfer record.")
        source, target = row.get("fromAccountType"), row.get("toAccountType")
        if (
            not all(
                isinstance(wallet, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,23}", wallet)
                for wallet in (source, target)
            )
            or source == target
        ):
            raise ccxt.ExchangeError("Invalid Bybit wallet transfer route.")
        if "UNIFIED" not in (source, target):
            continue
        raw_stamp = row.get("timestamp")
        stamp = number(raw_stamp)
        if (
            isinstance(raw_stamp, bool)
            or stamp is None
            or not stamp.is_integer()
            or not request["startTime"] <= stamp <= window_end // 1000 * 1000 + 999
        ):
            raise ccxt.ExchangeError("Invalid Bybit wallet transfer time.")
        if not window_start <= stamp <= window_end:
            continue
        status = row.get("status")
        items.append(
            {
                "native_id": row.get("transferId"),
                "reference": None,
                "asset": exchange.safe_currency_code(row.get("coin")),
                "timestamp_ms": stamp,
                "kind": "transfer",
                "direction": "in" if target == "UNIFIED" else "out",
                "quantity": row.get("amount"),
                "fee": {"currency": None, "cost": None},
                "status": {"SUCCESS": "completed", "PENDING": "pending", "FAILED": "failed"}.get(
                    status, "unknown"
                )
                if isinstance(status, str)
                else "unknown",
                "internal": True,
                "amount_basis": "provider_reported",
                "wallet_scope": "configured",
                "wallet_route": {"from": source, "to": target},
            }
        )
    next_cursor = {**cursor, "window_start": window_start, "page": following}
    if not following and window_end < end:
        return FundingPage(items, {**next_cursor, "window_start": window_end + 1}, False)
    return FundingPage(items, next_cursor, not following)
