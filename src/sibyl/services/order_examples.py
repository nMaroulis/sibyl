"""Isolated execution-monitor examples; never written to an account or import ledger."""

from sibyl.services.ledger import ledger_fill
from sibyl.services.order_reconciliation import summarize
from sibyl.services.order_recovery import MESSAGES


def order_examples() -> list[dict]:
    """Provide open, partial and canceled executions through the same read-only detail shape."""
    result = []
    for symbol, side, quantity, price, status, filled in [
        ("BTC/USDT", "buy", 0.02, 50000, "open", 0.008),
        ("ETH/USDT", "sell", 0.5, 3500, "open", 0.0),
        ("SOL/USDT", "buy", 3.0, 140, "canceled", 1.0),
        ("LINK/USDT", "buy", 5.0, 10, "unknown", None),
    ]:
        identity = "example-" + symbol.replace("/", "-") + "-" + status
        order = {
            "id": identity,
            "request": {
                "connection_id": "example",
                "symbol": symbol,
                "side": side,
                "quantity": quantity,
                "order_type": "limit",
                "limit_price": price,
            },
            "account": "Example account",
            "exchange": "demo",
            "sandbox": True,
            "environment": "illustrative",
            "mode": "paper",
            "status": status,
            "price": price,
            "filled": filled,
            "remaining": quantity - filled if filled is not None else None,
            "average": price if filled else None,
            "cost": filled * price if filled is not None else None,
            "tracking": status == "open",
            "client_order_id": "example-only",
            "exchange_order_id": "example-only",
        }
        if status == "unknown":
            order.pop("exchange_order_id")
            order.update(
                message=MESSAGES["not_found"],
                recovery={
                    "supported": True,
                    "eligible": True,
                    "state": "not_found",
                    "message": MESSAGES["not_found"],
                    "pages": 1,
                    "passes": 1,
                },
            )
        fills = []
        if filled:
            fills.append(
                ledger_fill(
                    {
                        "id": identity + "-fill",
                        "order": "example-only",
                        "symbol": symbol,
                        "side": side,
                        "amount": filled,
                        "price": price,
                        "cost": filled * price,
                        "timestamp": 1768478400000,
                        "fees": []
                        if status == "open"
                        else [{"currency": "USDT", "cost": filled * price * 0.001}],
                    },
                    {
                        "account_id": "example",
                        "account": "Example account",
                        "exchange": "demo",
                        "environment": "illustrative",
                        "symbol": symbol,
                    },
                )
            )
        summary = summarize(order, fills, {"state": "idle", "caught_up": True, "enabled": False, "pages": 1})
        result.append({"order": order, "reconciliation": summary, "fills": fills, "has_more": False})
    return result
