"""Read-only native funding pages; no addresses, raw payloads or write endpoints."""

from dataclasses import dataclass
from datetime import UTC, datetime

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
    return {
        "native_id": row.get("id"),
        "reference": None,
        "asset": row.get("coin"),
        "timestamp_ms": timestamp,
        "kind": stream,
        "direction": "in" if stream == "deposit" else "out",
        "quantity": row.get("amount"),
        "fee": fee,
        "status": status,
        "internal": row.get("transferType") == 1,
        "amount_basis": "provider_reported",
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
            }
        )
    # Native integer-second bounds include surrounding milliseconds. Trim only this
    # deliberate expansion; the raw page still controls cursor advancement.
    rows = [row for row in rows if row["timestamp_ms"] is None or start <= row["timestamp_ms"] <= end]
    return FundingPage(rows, {**cursor, "page": following}, not following)
