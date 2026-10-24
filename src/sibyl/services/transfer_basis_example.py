"""Isolated educational lot-carryover fixture, computed by the production replay."""

from collections import defaultdict

from sibyl.services.funding_ledger import funding_event
from sibyl.services.ledger import ledger_fill
from sibyl.services.transfer_allocation import TransferAllocation, allocate
from sibyl.services.transfer_basis import replay
from sibyl.services.transfer_reconciliation import comparison


def example(note: str, fees: bool = False) -> dict:
    """Buy on two accounts, move the older lot, then sell part of both origins.

    This function has no store or client, so it cannot write account history,
    create links, fetch prices, or submit orders.
    """
    stamp = 1_704_067_200_000
    scopes = {
        identity: {
            "account_id": identity,
            "account": label,
            "exchange": exchange,
            "environment": "demo",
            "symbol": "BTC/USDT",
        }
        for identity, label, exchange in (
            ("example-source", "Long-term wallet", "binance"),
            ("example-destination", "Trading wallet", "kraken"),
        )
    }
    fills = [
        ledger_fill(
            {
                "id": str(index),
                "symbol": "BTC/USDT",
                "timestamp": stamp + day * 86_400_000,
                "side": side,
                "amount": quantity,
                "price": price,
                "cost": quantity * price,
                "fees": [{"currency": "USDT", "cost": fee}],
            },
            scopes[account],
        )
        for index, (account, day, side, quantity, price, fee) in enumerate(
            [
                ("example-source", 0, "buy", 0.2, 40000, 0),
                ("example-destination", 1, "buy", 0.1, 50000, 0),
                ("example-destination", 3, "sell", 0.15, 60000, 9),
            ]
        )
    ]
    funding = [
        funding_event(
            {
                "native_id": "example-" + direction,
                "reference": None,
                "asset": "BTC",
                "timestamp_ms": stamp + 2 * 86_400_000 + delay,
                "kind": kind,
                "direction": direction,
                "quantity": 0.099 if fees and direction == "in" else 0.1,
                "status": "completed",
                "internal": False,
                "amount_basis": "provider_reported",
                "fee": {"currency": "BTC", "cost": 0.001 if fees and direction == "out" else 0},
            },
            {**scopes[account], "stream": kind, "start_ms": stamp, "end_ms": stamp + 4 * 86_400_000},
        )
        for account, direction, kind, delay in (
            ("example-source", "out", "withdrawal", 0),
            ("example-destination", "in", "deposit", 3_600_000),
        )
    ]
    review = comparison(*funding)
    link = {"id": "example-basis-link", "status": "confirmed", "reviewed": review, "current": review}
    if fees:
        link["allocation"] = allocate(
            *funding, TransferAllocation(outgoing_amount="total_debit", incoming_amount="net_credit")
        )
        review["allocation"] = link["allocation"]
    groups, markets = {}, defaultdict(set)
    for identity, scope in scopes.items():
        groups[(identity, scope["symbol"])] = {
            **scope,
            "executions": [row for row in fills if row["account_id"] == identity],
            "opening": None,
            "opening_applied": False,
            "cross_market": False,
            "initial_issues": [],
        }
        markets[(identity, "BTC")].add("BTC/USDT")
    calculated = replay(groups, [link], funding, markets)
    rows = [
        {
            **{key: value for key, value in group.items() if key not in {"executions", "initial_issues"}},
            **calculated["summaries"][key],
            "base": "BTC",
            "quote": "USDT",
            "active": False,
            "unrealized": None,
            "mark_price": None,
            "balance_quantity": None,
            "mark_status": "not_requested",
            "mark_note": "Isolated example; no current wallet balance or price is attached.",
        }
        for key, group in groups.items()
    ]
    return {
        "example": True,
        "example_kind": "transfer_fees" if fees else "transfers",
        "items": rows,
        "fill_count": len(fills),
        "complete_history": False,
        "as_of": "2024-01-05T00:00:00+00:00",
        "note": note,
        "basis_method": "FIFO by account and exact market, with eligible confirmed lot carryover",
        "dependency_fill_count": len(fills),
        "dependency_account_count": len(groups),
        "transfer_evidence": calculated["transfers"],
        "transfer_evidence_count": 1,
        "transfer_evidence_limit": 50,
        "transfer_summary": {
            "applied": 1,
            "unapplied": 0,
            "note": "An isolated reviewed same-asset fee allocation. Fee inventory cost stays separate; historical fee valuation is unavailable."
            if fees
            else "An isolated equal-amount, explicitly zero-fee own-account transfer.",
        },
        "totals": [
            {
                "environment": "demo",
                "quote": "USDT",
                "markets": 2,
                "matched_realized": sum(row["realized_before_other_fees"] for row in rows),
                "net_matched_realized": None if fees else sum(row["net_matched_realized"] for row in rows),
                "unrealized": None,
            }
        ],
    }
