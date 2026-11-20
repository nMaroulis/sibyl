"""Exact-feed pricing and retained evidence for strategy fees in other assets."""

import json
import math
from decimal import Decimal

from sibyl.accounting.executions.prices import HistoricalPrices
from sibyl.strategies.execution.ownership.ledger import digest


def foreign_fees(db, job, fills):
    """Match each native fill's current fee facts against immutable approved values."""
    base, quote = job["parameters"]["symbol"].split("/")
    entries = []
    for fill in fills:
        amounts = [
            (fee["currency"], fee["cost"])
            for fee in fill["fees"]
            if fee["currency"] not in {None, base, quote} and fee["cost"]
        ]
        if amounts:
            entries.append(
                {
                    "fill_id": fill["id"],
                    "timestamp_ms": int(fill["timestamp_ms"]),
                    "fee_version": digest(
                        [
                            job["source"],
                            job["environment"],
                            fill["order_id"],
                            fill["timestamp_ms"],
                            fill["fees_known"],
                            fill["fees"],
                        ]
                    ),
                    "amounts": amounts,
                }
            )
    if not entries:
        return []
    receipts = {
        (row[0], row[1]): json.loads(row[2])
        for row in db.execute(
            "SELECT fill_id,fee_version,payload FROM strategy_fee_values WHERE job_id=?",
            (job["id"],),
        )
    }
    for entry in entries:
        entry["receipt"] = receipts.get((entry["fill_id"], entry["fee_version"]))
    return entries


def price_unreviewed(db, job, entries):
    """Estimate signed fees with closed candles dated at or before the fill."""
    if not entries:
        return []
    stamps = [entry["timestamp_ms"] for entry in entries]
    prices = HistoricalPrices(db, job["source"], job["environment"], min(stamps), max(stamps))
    quote = job["parameters"]["symbol"].split("/")[1]
    result = []
    for entry in entries:
        rows = []
        for asset, amount in entry["amounts"]:
            match = prices.rate(asset, quote, entry["timestamp_ms"])
            rate, legs = match or (0, [])
            value = float(Decimal(str(amount)) * rate)
            rows.append(
                {
                    "asset": asset,
                    "native_fee": amount,
                    "quote_fee": value if match and math.isfinite(value) else None,
                    "legs": legs,
                }
            )
        result.append(
            {
                "fill_id": entry["fill_id"],
                "timestamp_ms": entry["timestamp_ms"],
                "fee_version": entry["fee_version"],
                "rows": rows,
            }
        )
    return result


def marked_equity(job, price):
    """Recognize reviewed fee expenses/rebates in equity without posting quote cash."""
    return job["cash"] + job["quantity"] * price - job.get("foreign_fees_quote", 0.0)
