"""Coherent, provider-free strategy accounting inside the caller's SQLite snapshot."""

import json
import math

from sibyl.strategies.execution.accounting import project
from sibyl.strategies.execution.contracts import ExecutionGuard

MAX_RUNS = 100


def positions(db, trading, environment):
    """Rebuild every retained exchange run, including stopped positions and late fills.

    An unknown write or a mismatch between observed cumulative fills and the native
    ledger blocks assessment. Ordinary open orders with reconciled partial fills
    remain assessable; their unfilled buy quantity consumes shared exposure.
    """
    jobs = [
        json.loads(row[0])
        for row in db.execute(
            "SELECT payload FROM strategy_jobs WHERE json_extract(payload,'$.mode')='exchange' "
            "AND json_extract(payload,'$.environment')=? ORDER BY id LIMIT ?",
            (environment, MAX_RUNS + 1),
        )
    ]
    if len(jobs) > MAX_RUNS:
        raise ExecutionGuard("Shared limits support at most 100 retained exchange runs per environment.")
    results = []
    for job in jobs:
        accounting = project(job, trading, db=db)
        if accounting["accounting_incomplete"] or accounting["unvalued_fees"]:
            raise ExecutionGuard(
                "Strategy fills have missing costs or unvalued fees. Reconcile them in Trade."
            )
        rows = db.execute(
            "SELECT o.payload,COALESCE(SUM(json_extract(f.payload,'$.quantity')),0) AS imported "
            "FROM exchange_orders o LEFT JOIN account_fills f "
            "ON f.account_id=json_extract(o.payload,'$.request.connection_id') "
            "AND f.symbol=json_extract(o.payload,'$.request.symbol') "
            "AND json_extract(f.payload,'$.order_id')=json_extract(o.payload,'$.exchange_order_id') "
            "WHERE json_extract(o.payload,'$.strategy_job_id')=? GROUP BY o.id",
            (job["id"],),
        ).fetchall()
        pending = []
        for row in rows:
            order, imported = json.loads(row[0]), row[1]
            if order.get("strategy_abandoned") or order["status"] == "preview":
                continue
            if order["status"] == "rejected" and not order.get("exchange_order_id"):
                continue
            if order["status"] in {"unknown", "submitting"} or order.get("filled") is None:
                raise ExecutionGuard(
                    "A strategy order has an uncertain outcome. Resolve its native fills in Trade."
                )
            if abs(order["filled"] - imported) > max(1e-10, imported * 1e-8):
                raise ExecutionGuard(
                    "Strategy order quantities and imported fills differ. Reconcile them in Trade."
                )
            unresolved = any(item["id"] == order["id"] for item in accounting["unresolved_orders"])
            reconciliation = next(
                (
                    item["reconciliation"]
                    for item in accounting["unresolved_orders"]
                    if item["id"] == order["id"]
                ),
                "matched",
            )
            if reconciliation not in {"pending", "matched"} or (
                unresolved and order["status"] in {"closed", "canceled", "expired"}
            ):
                raise ExecutionGuard(
                    "Strategy order costs or execution pages are incomplete. Reconcile them in Trade."
                )
            if order["request"]["side"] == "buy" and unresolved:
                pending.append(
                    {
                        "quantity": max(0, order["request"]["quantity"] - imported),
                        "price": order["request"]["limit_price"],
                    }
                )
        results.append(
            {
                "id": job["id"],
                "account": job["account"],
                "connection_id": job["connection_id"],
                "symbol": job["parameters"]["symbol"],
                "status": job["status"],
                "capital": job["parameters"]["capital"],
                "cash": accounting["cash"],
                "quantity": accounting["quantity"],
                "retained": job["status"] not in {"stopped", "completed"}
                or accounting["quantity"] > 1e-12
                or bool(accounting["unresolved_orders"]),
                "pending_buys": pending,
            }
        )
    return results


def totals(rows, rates, candidate=None):
    """Value owned units plus outstanding buys; never net a pending sell against exposure.

    Buy headroom uses the higher of its limit notional and current reference value.
    Native fees affect reconciled cash/units; this is gross exposure, not a fee quote.
    All conversions come from dated observations, including stablecoins and fiat.
    """
    items = []
    for row in rows:
        base, quote = row["symbol"].split("/")
        quote_rate = rates[quote]["price"]
        base_rate = rates[base]["price"] if row["quantity"] or row["pending_buys"] else 0
        position = row["quantity"] * base_rate
        pending = math.fsum(
            order["quantity"] * max(order["price"] * quote_rate, base_rate) for order in row["pending_buys"]
        )
        if candidate and candidate["strategy_job_id"] == row["id"] and candidate["request"]["side"] == "buy":
            request = candidate["request"]
            pending += request["quantity"] * max(request["limit_price"] * quote_rate, rates[base]["price"])
        items.append(
            {
                **{key: row[key] for key in ("id", "account", "connection_id", "symbol", "status")},
                "allocated": row["capital"] * quote_rate if row["retained"] else 0,
                "position": position,
                "pending_buys": pending,
                "pnl": (row["cash"] - row["capital"]) * quote_rate + position,
            }
        )
    values = {
        "allocated": math.fsum(row["allocated"] for row in items),
        "position": math.fsum(row["position"] for row in items),
        "pending_buys": math.fsum(row["pending_buys"] for row in items),
    }
    values["exposure"] = values["position"] + values["pending_buys"]
    if any(not math.isfinite(value) for value in values.values()) or any(
        not math.isfinite(row["pnl"]) for row in items
    ):
        raise ExecutionGuard("Shared strategy accounting produced an invalid reference value.")
    return {**values, "runs": items}
