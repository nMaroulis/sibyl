"""Match requested historical acquisitions to reconciled same-account buy evidence."""

import json
import math
from collections import defaultdict
from decimal import Decimal

from sibyl.services.trading.lifecycle import TERMINAL
from sibyl.services.trading.reconciliation import READ_LIMIT, settlement_blocker, summarize
from sibyl.strategies.execution.contracts import ExecutionGuard
from sibyl.strategies.execution.ownership.ledger import digest

RECENT_BUYS = 30
CANDIDATES = 10
MANUAL_ORIGINS = {"sibyl", "replacement", "oco"}


class Acquisitions:
    """Read exact buy sources and count current linked funding claims in one snapshot."""

    def __init__(self, db):
        self.db = db
        self._sources = {}
        self._claims = {}

    def source(self, identity):
        if identity not in self._sources:
            self._sources[identity] = self._read_source(identity)
        return self._sources[identity]

    def _read_source(self, identity):
        row = self.db.execute("SELECT payload FROM account_fills WHERE id=?", (identity,)).fetchone()
        if not row:
            return None
        fill = json.loads(row[0])
        if (
            fill["side"] != "buy"
            or not fill["order_id"]
            or fill.get("trade_break")
            or fill["notional"] is None
            or not fill["fees_known"]
        ):
            return None
        orders = self.db.execute(
            "SELECT payload FROM exchange_orders "
            "WHERE json_extract(payload,'$.request.connection_id')=? "
            "AND json_extract(payload,'$.request.symbol')=? AND json_extract(payload,'$.exchange_order_id')=? LIMIT 2",
            (fill["account_id"], fill["symbol"], fill["order_id"]),
        ).fetchall()
        if len(orders) != 1:
            return None
        order = json.loads(orders[0][0])
        origin = order.get("origin", "sibyl")
        if (
            order.get("strategy_job_id")
            or (origin not in MANUAL_ORIGINS and not (origin == "imported" and order.get("read_only")))
            or order["status"] not in TERMINAL
            or order.get("cost") is None
            or order["request"]["side"] != "buy"
            or order["exchange"] != fill["exchange"]
            or order["environment"] != fill["environment"]
        ):
            return None
        sync = self.db.execute(
            "SELECT payload FROM order_fill_sync WHERE intent_id=?", (order["id"],)
        ).fetchone()
        if not sync:
            return None
        checkpoint = json.loads(sync[0])
        if not checkpoint.get("caught_up"):
            return None
        fills = [
            json.loads(row[0])
            for row in self.db.execute(
                "SELECT payload FROM account_fills WHERE account_id=? AND symbol=? "
                "AND json_extract(payload,'$.order_id')=? LIMIT ?",
                (fill["account_id"], fill["symbol"], fill["order_id"], READ_LIMIT + 1),
            )
        ]
        totals = summarize(order, fills, checkpoint)
        if totals["status"] != "matched" or totals["cost_difference"] is None or settlement_blocker(totals):
            return None
        fees = defaultdict(Decimal)
        for fee in fill["fees"]:
            fees[fee["currency"]] += Decimal(str(fee["cost"]))
        if set(fees) - {fill["base"], fill["quote"]}:
            return None
        quantity = Decimal(str(fill["quantity"])) - fees[fill["base"]]
        basis = Decimal(str(fill["notional"])) + fees[fill["quote"]]
        net_quantity, total_basis = float(quantity), float(basis)
        if (
            not math.isfinite(net_quantity)
            or net_quantity <= 0
            or not math.isfinite(total_basis)
            or total_basis < 0
        ):
            return None
        return {
            "fill_id": identity,
            "trade_id": fill["trade_id"],
            "order_id": fill["order_id"],
            "intent_id": order["id"],
            "account_id": fill["account_id"],
            "symbol": fill["symbol"],
            "exchange": fill["exchange"],
            "environment": fill["environment"],
            "timestamp_ms": fill["timestamp_ms"],
            "net_quantity": net_quantity,
            "total_basis": total_basis,
            "origin": "venue_discovered" if origin == "imported" else "sibyl_manual",
            "proof": digest(
                [
                    fill["quantity"],
                    fill["price"],
                    fill["notional"],
                    fill["fees"],
                    order["filled"],
                    order["cost"],
                ]
            ),
        }

    @staticmethod
    def eligible(source, sale):
        return (
            source
            and all(source[key] == sale[key] for key in ("account_id", "symbol", "exchange", "environment"))
            and source["timestamp_ms"] < sale["timestamp_ms"]
        )

    def still_matches(self, receipt, sale):
        """Check a linked buy on later reads; historical asserted-basis rows stay supported."""
        retained = receipt.get("acquisition")
        if not retained:
            return True
        source = self.source(retained["fill_id"])
        return self.eligible(source, sale) and source == retained

    def claims(self, identity):
        """Load active reservations only, keeping stale claims reserved until reviewed."""
        if identity not in self._claims:
            self._claims[identity] = {
                (row[0], row[1]): row[2]
                for row in self.db.execute(
                    "SELECT f.job_id,item.key,json_extract(item.value,'$.quantity') "
                    "FROM strategy_ownership_sale_funding AS f JOIN json_each(f.payload) AS item "
                    "WHERE f.sequence=(SELECT MAX(sequence) FROM strategy_ownership_sale_funding WHERE job_id=f.job_id) "
                    "AND json_extract(item.value,'$.acquisition.fill_id')=?",
                    (identity,),
                )
            }
        return self._claims[identity]

    def available(self, source, excluded_claim):
        used = sum(
            (
                Decimal(str(qty))
                for identity, qty in self.claims(source["fill_id"]).items()
                if identity != excluded_claim
            ),
            Decimal(0),
        )
        return Decimal(str(source["net_quantity"])) - used

    def candidates(self, job_id, sale, deficit):
        """List recent eligible buys; the explicit fill-ID path can select older retained fills."""
        choices = []
        for row in self.db.execute(
            "SELECT id FROM account_fills WHERE account_id=? AND symbol=? AND timestamp_ms<? "
            "AND json_extract(payload,'$.side')='buy' ORDER BY timestamp_ms DESC,id DESC LIMIT ?",
            (sale["account_id"], sale["symbol"], sale["timestamp_ms"], RECENT_BUYS),
        ):
            source = self.source(row[0])
            if self.eligible(source, sale) and self.available(source, (job_id, sale["id"])) >= Decimal(
                str(deficit)
            ):
                choices.append(
                    {
                        key: source[key]
                        for key in ("fill_id", "trade_id", "order_id", "timestamp_ms", "origin")
                    }
                    | {"estimated_basis": self.proportional_basis(source, deficit)}
                )
                if len(choices) == CANDIDATES:
                    break
        return choices

    @staticmethod
    def proportional_basis(source, quantity):
        return float(
            Decimal(str(source["total_basis"]))
            * Decimal(str(quantity))
            / Decimal(str(source["net_quantity"]))
        )

    def allocate(self, buy_id, sale, deficit):
        source = self.source(buy_id)
        if not self.eligible(source, sale):
            raise ExecutionGuard(
                "Choose an earlier reconciled non-strategy buy in the sale’s exact account, environment and pair."
            )
        if Decimal(str(deficit)) > Decimal(str(source["net_quantity"])):
            raise ExecutionGuard("The selected buy does not cover the sale shortfall after base fees.")
        return source, self.proportional_basis(source, deficit)

    def check_repair(self, changes):
        """Compare all proposed reservations together, allowing retirement and reuse atomically."""
        affected = set()
        for previous, _ in changes:
            for fill_id, row in previous.items():
                source = row.get("acquisition")
                if source:
                    identity = source["fill_id"]
                    self.claims(identity).pop((row["job_id"], fill_id), None)
        for _, proposed in changes:
            for fill_id, row in proposed.items():
                source = row.get("acquisition")
                if source:
                    identity = source["fill_id"]
                    affected.add(identity)
                    self.claims(identity)[(row["job_id"], fill_id)] = row["quantity"]
        for identity in affected:
            reservations = self.claims(identity)
            if not reservations:
                continue
            source = self.source(identity)
            if not source or self.available(source, None) < 0:
                raise ExecutionGuard(
                    "The linked buy quantities are already reserved by other sale funding receipts."
                )
