"""Rebuild strategy ownership from linked native fills, including later corrections."""

import json
from collections import defaultdict
from contextlib import nullcontext

from sibyl.services.trading.reconciliation import summarize
from sibyl.strategies.execution.contracts import ExecutionGuard
from sibyl.strategies.execution.ownership.ledger import replay


def project(job, trading, *, db=None):
    """Attribute only this strategy's orders; account deposits and unrelated holdings are excluded.

    Recalculation prevents duplicate fills and incorporates late fee corrections.
    Base/quote fees affect owned units/cash. Other fee currencies remain explicit
    and block new orders until reviewed; no invented conversion enters P&L.
    """
    base, quote = job["parameters"]["symbol"].split("/")
    with trading.store.db() if db is None else nullcontext(db) as connection:
        if db is None:
            connection.execute("BEGIN")
        db = connection
        orders = [
            json.loads(row[0])
            for row in db.execute(
                "SELECT payload FROM exchange_orders WHERE json_extract(payload,'$.strategy_job_id')=? ORDER BY rowid",
                (job["id"],),
            )
        ]
        rows = db.execute(
            "SELECT f.payload FROM account_fills f JOIN exchange_orders o "
            "ON f.account_id=json_extract(o.payload,'$.request.connection_id') "
            "AND f.symbol=json_extract(o.payload,'$.request.symbol') "
            "AND json_extract(f.payload,'$.order_id')=json_extract(o.payload,'$.exchange_order_id') "
            "WHERE json_extract(o.payload,'$.strategy_job_id')=? ORDER BY f.timestamp_ms,o.rowid,f.id LIMIT 10001",
            (job["id"],),
        ).fetchall()
        ownership, ownership_stale = replay(db, job["id"])
        sync = {
            row[0]: json.loads(row[1])
            for row in db.execute(
                "SELECT s.intent_id,s.payload FROM order_fill_sync s JOIN exchange_orders o ON o.id=s.intent_id WHERE json_extract(o.payload,'$.strategy_job_id')=?",
                (job["id"],),
            )
        }
    if len(rows) > 10000:
        raise ExecutionGuard(
            "This strategy reached its 10,000-fill accounting limit. Review and start a new run."
        )
    fills = [json.loads(row[0]) for row in rows]
    grouped = defaultdict(list)
    for fill in fills:
        grouped[fill["order_id"]].append(fill)
    unresolved = []
    for order in orders:
        if order.get("strategy_abandoned"):
            continue
        if order["status"] == "rejected" and not order.get("exchange_order_id"):
            continue
        status = summarize(order, grouped[order.get("exchange_order_id")], sync.get(order["id"]))["status"]
        if order["status"] not in {"closed", "canceled", "expired"} or status != "matched":
            unresolved.append({"id": order["id"], "status": order["status"], "reconciliation": status})
    if len({fill["id"] for fill in fills}) != len(fills):
        raise ExecutionGuard("A native order identity is linked more than once. Review strategy orders.")
    cash, quantity, basis, realized = job["parameters"]["capital"], 0.0, 0.0, 0.0
    fees, returns, exits, rendered = defaultdict(float), [], {}, []
    unknown = ownership_stale
    net_value, consumed, next_event = 0.0, set(), 0

    def attributions():
        nonlocal quantity, basis, net_value, next_event, unknown
        while next_event < len(ownership) and set(ownership[next_event]["after_fills"]) <= consumed:
            event = ownership[next_event]
            quantity += event["quantity"]
            basis += event["cost_basis"]
            net_value += event["reference_value"]
            if quantity < -1e-10 or basis < -1e-8:
                unknown = True
            quantity, basis = max(0.0, quantity), max(0.0, basis)
            next_event += 1

    attributions()
    for fill in fills:
        unknown |= not fill["fees_known"] or fill["notional"] is None
        by_currency = defaultdict(float)
        for fee in fill["fees"]:
            if fee["currency"] and fee["cost"] is not None:
                fees[fee["currency"]] += fee["cost"]
                by_currency[fee["currency"]] += fee["cost"]
        cost = fill["notional"] if fill["notional"] is not None else fill["quantity"] * fill["price"]
        if fill["side"] == "buy":
            quantity += fill["quantity"] - by_currency[base]
            cash -= cost + by_currency[quote]
            basis += cost + by_currency[quote]
            if quantity < -1e-10:
                raise ExecutionGuard("Native base fees exceed acquired units. Review strategy accounting.")
        else:
            disposed = fill["quantity"] + by_currency[base]
            if disposed > quantity + max(1e-10, quantity * 1e-8) and not ownership_stale:
                raise ExecutionGuard(
                    "Native executions exceed the strategy-owned position. Review fills before resuming."
                )
            allocated = basis * min(1, disposed / quantity) if quantity else 0
            proceeds = cost - by_currency[quote]
            cash += proceeds
            quantity = max(0.0, quantity - disposed)
            basis -= allocated
            realized += proceeds - allocated
            totals = exits.setdefault(fill["order_id"], [0, 0])
            totals[0] += proceeds - allocated
            totals[1] += allocated
        consumed.add(fill["id"])
        attributions()
        rendered.append(
            {
                "id": fill["id"],
                "timestamp": fill["created_at"],
                "side": fill["side"],
                "price": fill["price"],
                "quantity": fill["quantity"],
                "fee": by_currency[quote] if fill["fees_known"] else None,
                "fees": fill["fees"],
                "event_recorded": True,
            }
        )
    if next_event != len(ownership):
        unknown = True
        ownership_stale = True
    for identity, (pnl, allocated) in exits.items():
        if allocated and any(
            o.get("exchange_order_id") == identity and o["status"] in {"closed", "canceled", "expired"}
            for o in orders
        ):
            returns.append(pnl / allocated * 100)
    return {
        "cash": cash,
        "ownership_net_value": net_value,
        "ownership_stale": ownership_stale,
        "ownership_events": [
            {
                key: event.get(key)
                for key in (
                    "id",
                    "action",
                    "quantity",
                    "cost_basis",
                    "reference_value",
                    "created_at",
                    "note",
                    "peer_id",
                )
            }
            for event in ownership[-100:]
        ],
        "ownership_event_count": len(ownership),
        "quantity": quantity,
        "entry_cost": basis,
        "entry_price": basis / quantity if quantity else 0,
        "realized_pnl": realized,
        "fees_paid": fees.get(quote, 0.0),
        "fee_assets": dict(fees),
        "unvalued_fees": {
            asset: value for asset, value in fees.items() if asset not in {base, quote} and value
        },
        "accounting_incomplete": unknown,
        "completed_returns": returns,
        "round_trips": len(returns),
        "fills": rendered[-100:],
        "native_fill_count": len(fills),
        "unresolved_orders": unresolved,
        "_native_fills": rendered,
        "orders": [
            {
                key: order.get(key)
                for key in (
                    "id",
                    "status",
                    "exchange_order_id",
                    "client_order_id",
                    "price",
                    "filled",
                    "remaining",
                    "message",
                    "request",
                    "strategy_abandoned",
                    "strategy_expires_at",
                    "strategy_cancellation",
                    "cancel_state",
                    "cancel_message",
                    "strategy_action",
                    "strategy_close_review_id",
                )
            }
            for order in orders[-100:]
        ],
    }
