"""Read-only reports over recorded paper fills and reviewed exchange intents."""

from collections import defaultdict, deque


def trading_report(store, trading) -> dict:
    """Combine bounded local history and calculate FIFO P&L only for recorded paper lots.

    Seed balances have unknown cost basis, so unmatched sold quantities are excluded
    from realized P&L. Exchange intent notionals are reference values, not settlements.
    """
    paper, exchange = store.orders(), trading.list_orders()
    lots, realized, unmatched, pnl_curve = defaultdict(deque), defaultdict(float), 0.0, []
    for order in reversed(paper):
        quantity, price, fee = order["quantity"], order["price"], order["fee"]
        if order["side"] == "buy":
            lots[order["symbol"]].append([quantity, price + fee / quantity])
        else:
            remaining, pnl = quantity, 0.0
            while remaining > 1e-12 and lots[order["symbol"]]:
                lot = lots[order["symbol"]][0]
                matched = min(remaining, lot[0])
                pnl += matched * (price - fee / quantity - lot[1])
                lot[0] -= matched
                remaining -= matched
                if lot[0] <= 1e-12:
                    lots[order["symbol"]].popleft()
            unmatched += remaining
            quote = order["symbol"].split("/")[1]
            realized[quote] += pnl
            pnl_curve.append({"timestamp": order["created_at"], "value": realized[quote], "quote": quote})
    rows = [
        {
            **order,
            "account": "Manual paper wallet",
            "quote": order["symbol"].split("/")[1],
            "notional_kind": "Filled notional",
            "mode": "paper",
        }
        for order in paper
    ]
    for intent in exchange:
        request = intent["request"]
        rows.append(
            {
                "id": intent["id"],
                "created_at": intent["created_at"],
                "mode": "exchange",
                "account": intent["account"],
                "symbol": request["symbol"],
                "side": request["side"],
                "quantity": request["quantity"],
                "price": intent.get("average") or intent["price"],
                "notional": intent["notional"],
                "notional_kind": "Preview reference",
                "quote": request["symbol"].split("/")[1],
                "fee": None,
                "status": intent["status"],
                "client_order_id": intent["client_order_id"],
                "exchange_order_id": intent.get("exchange_order_id"),
            }
        )
    rows.sort(key=lambda row: row["created_at"], reverse=True)
    return {
        "items": rows,
        "realized_paper_pnl": dict(realized),
        "paper_pnl_curve": pnl_curve,
        "unmatched_sold_quantity": unmatched,
        "note": "Latest 200 paper fills and 100 exchange intents. FIFO paper P&L excludes opening balances and unmatched sales. Reference exchange notionals do not represent final settlement.",
    }
