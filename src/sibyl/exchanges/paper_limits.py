"""Durable virtual GTC orders and atomic paper-wallet reservations.

The simulator fills a whole remaining quantity at the reviewed limit when the
Demo bid/ask crosses it. There is no liquidity, queue or partial-fill simulation.
Reads alone do not match orders; the managed-order refresh/worker does.
"""

import json
import math
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import ccxt

from sibyl.exchanges.base import number


def reserved(db) -> dict[str, float]:
    """Sum open virtual holds inside the caller's wallet transaction."""
    result = defaultdict(float)
    for row in db.execute("SELECT payload FROM paper_limits WHERE status='open'"):
        order = json.loads(row[0])
        result[order["reserve_asset"]] += order["reserved"]
    return dict(result)


class PaperLimits:
    """Use the existing Demo wallet and fill ledger, with no credentials or network."""

    def __init__(self, store):
        self.store = store

    def place(self, symbol: str, side: str, quantity: float, price: float, key: str) -> dict:
        """Reserve available virtual funds once without creating a fill."""
        base, quote = symbol.split("/")
        if (
            side not in {"buy", "sell"}
            or not math.isfinite(quantity)
            or not math.isfinite(price)
            or quantity <= 0
            or price <= 0
        ):
            raise ValueError("Use positive finite paper limit quantities/prices and a buy/sell side.")
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT payload FROM paper_limits WHERE request_key=?", (key,)).fetchone()
            if old:
                order = json.loads(old[0])
                if (order["symbol"], order["side"], order["amount"], order["price"]) != (
                    symbol,
                    side,
                    quantity,
                    price,
                ):
                    raise ValueError("This paper order key belongs to different details.")
                return order
            if db.execute("SELECT 1 FROM orders WHERE idempotency_key=?", (key,)).fetchone():
                raise ValueError("This paper key belongs to a market order.")
            if not db.execute("SELECT 1 FROM active_accounts WHERE account_id='demo'").fetchone():
                raise ValueError("Demo preview is inactive.")
            balances = dict(db.execute("SELECT asset,quantity FROM balances"))
            holds = reserved(db)
            asset, needed = (
                (quote, float(Decimal(str(quantity)) * Decimal(str(price)) * Decimal("1.001")))
                if side == "buy"
                else (base, quantity)
            )
            if balances.get(asset, 0) - holds.get(asset, 0) < needed:
                raise ValueError("Insufficient available paper balance after open-order reservations.")
            stamp = datetime.now(UTC).isoformat()
            order = {
                "id": uuid4().hex,
                "clientOrderId": key,
                "symbol": symbol,
                "type": "limit",
                "side": side,
                "amount": quantity,
                "price": price,
                "filled": 0.0,
                "remaining": quantity,
                "average": None,
                "cost": None,
                "status": "open",
                "created_at": stamp,
                "reserve_asset": asset,
                "reserved": needed,
                "mode": "paper",
            }
            db.execute(
                "INSERT INTO paper_limits VALUES(?,?,?,?)", (order["id"], key, "open", json.dumps(order))
            )
        return order

    def read(self, identity: str, symbol: str) -> dict:
        """Read one resting/terminal virtual order without matching it."""
        with self.store.db() as db:
            row = db.execute("SELECT payload FROM paper_limits WHERE id=?", (identity,)).fetchone()
        if not row or json.loads(row[0])["symbol"] != symbol:
            raise ccxt.OrderNotFound("Paper limit order not found.")
        return json.loads(row[0])

    def open_orders(self, symbol: str) -> list[dict]:
        """Read open virtual orders, including after a restart."""
        with self.store.db() as db:
            return [
                order
                for row in db.execute("SELECT payload FROM paper_limits WHERE status='open'")
                if (order := json.loads(row[0]))["symbol"] == symbol
            ]

    def cancel(self, identity: str, symbol: str) -> dict:
        """Release a hold exactly once; a prior fill cannot be undone."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM paper_limits WHERE id=?", (identity,)).fetchone()
            if not row or json.loads(row[0])["symbol"] != symbol:
                raise ccxt.OrderNotFound("Paper limit order not found.")
            order = json.loads(row[0])
            if order["status"] == "open":
                order.update(status="canceled", reserved=0.0)
                db.execute(
                    "UPDATE paper_limits SET status='canceled',payload=? WHERE id=?",
                    (json.dumps(order), identity),
                )
        return order

    def match(self, identity: str, symbol: str, ticker: dict) -> dict:
        """Atomically fill at the limit, append one native paper fill and release funds."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM paper_limits WHERE id=?", (identity,)).fetchone()
            if not row:
                raise ccxt.OrderNotFound("Paper limit order not found.")
            order = json.loads(row[0])
            if order["symbol"] != symbol:
                raise ValueError("Paper market mismatch.")
            if (
                order["status"] != "open"
                or not db.execute("SELECT 1 FROM active_accounts WHERE account_id='demo'").fetchone()
            ):
                return order
            observed = number(ticker.get("ask" if order["side"] == "buy" else "bid"))
            if (
                observed is None
                or observed <= 0
                or (observed > order["price"] if order["side"] == "buy" else observed < order["price"])
            ):
                return order
            base, quote = symbol.split("/")
            quantity, price = order["amount"], order["price"]
            exact_notional = Decimal(str(quantity)) * Decimal(str(price))
            notional = float(exact_notional)
            fee = float(exact_notional * Decimal("0.001"))
            debit = order["reserved"] if order["side"] == "buy" else 0.0
            for asset, delta in (
                (base, quantity if order["side"] == "buy" else -quantity),
                (quote, -debit if order["side"] == "buy" else notional - fee),
            ):
                db.execute(
                    "INSERT INTO balances VALUES(?,?) ON CONFLICT(asset) DO UPDATE SET quantity=quantity+excluded.quantity",
                    (asset, delta),
                )
            stamp = datetime.now(UTC).isoformat()
            fill = {
                "id": uuid4().hex,
                "symbol": symbol,
                "side": order["side"],
                "quantity": quantity,
                "price": price,
                "notional": notional,
                "fee": fee,
                "status": "filled",
                "mode": "paper",
                "created_at": stamp,
                "order_id": identity,
            }
            db.execute(
                "INSERT INTO orders VALUES(?,?,?,?)",
                (fill["id"], "limit-fill:" + identity, json.dumps(fill), stamp),
            )
            order.update(
                status="closed", filled=quantity, remaining=0.0, average=price, cost=notional, reserved=0.0
            )
            db.execute(
                "UPDATE paper_limits SET status='closed',payload=? WHERE id=?", (json.dumps(order), identity)
            )
        return order
