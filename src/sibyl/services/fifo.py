"""Decimal FIFO books shared by execution-only and transfer-aware reports.

Books contain derived lots only. They never write fills, funding records, wallet
balances or orders. A transferred slice retains its original acquisition key.
"""

import math
from collections import Counter, defaultdict, deque
from datetime import datetime
from decimal import Decimal, localcontext

ZERO = Decimal(0)


def decimal(value) -> Decimal:
    """Read finite recorded decimal text without binary arithmetic in the book."""
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("Non-finite accounting value.")
    return result


def public(value: Decimal | None) -> float | None:
    """Keep overflow and unsupported values nullable at the JSON boundary."""
    if value is None:
        return None
    result = float(value)
    return result if math.isfinite(result) else None


class FifoBook:
    """An incremental, long-only exact-market FIFO calculation with lot provenance."""

    def __init__(self, fills: list[dict], opening: dict | None = None):
        self.lots, self.issues, self.fees = deque(), [], defaultdict(lambda: ZERO)
        self.fills, self.disposals, self.curve = fills, [], []
        self.missing_fees = 0
        self.realized = self.known_sold = self.unknown_sold = ZERO
        self.blocked = self.estimated = False
        self.unconverted = set()
        self.ties = any(count > 1 for count in Counter(row["timestamp_ms"] for row in fills).values())
        if self.ties:
            self.issues.append("Some fills share a timestamp; their execution ordering is not established.")
        if opening:
            stamp = datetime.fromisoformat(opening["as_of"]).timestamp() * 1000 if opening.get("as_of") else 0
            self.receive(
                [
                    {
                        "quantity": decimal(opening["quantity"]),
                        "cost": decimal(opening["total_cost"]) if opening["total_cost"] is not None else None,
                        "acquired_at_ms": stamp,
                        "origin_id": "opening:" + opening.get("account_id", ""),
                        "origin_account": opening.get("account_id", ""),
                    }
                ]
            )

    @property
    def reliable(self) -> bool:
        """Unknown cost is allowed; uncertain inventory, fee or order coverage is not."""
        return not (self.missing_fees or self.unconverted or self.ties or self.blocked or self.estimated)

    def receive(self, lots: list[dict], *, transferred: bool = False) -> None:
        """Insert received slices by original acquisition order, never receipt order."""

        def key(lot):
            return (lot["acquired_at_ms"] if lot["acquired_at_ms"] is not None else -1, lot["origin_id"])

        # Ordinary chronological buys append in O(1); only incoming old lots need
        # a merge/sort. Distinct origins with equal ages have no native FIFO order.
        if transferred and self.lots:
            ages = defaultdict(set)
            for lot in self.lots:
                ages[lot["acquired_at_ms"]].add(lot["origin_id"])
            if any(ages.get(lot["acquired_at_ms"], set()) - {lot["origin_id"]} for lot in lots):
                self.ties = True
                self.issues.append(
                    "Received lots share an acquisition timestamp with another origin; FIFO ordering is ambiguous."
                )
        reorder = bool(self.lots and any(key(lot) < key(self.lots[-1]) for lot in lots))
        self.lots.extend(dict(lot) for lot in lots)
        if reorder:
            self.lots = deque(sorted(self.lots, key=key))
        if any(lot["acquired_at_ms"] is None for lot in lots):
            self.ties = True
            self.issues.append(
                "Transferred shortfall units have unknown acquisition dates; FIFO order remains provisional."
            )

    def take(self, quantity: Decimal, stamp: float, identity: str) -> tuple[list[dict], Decimal]:
        """Remove FIFO slices; an inventory shortfall becomes explicit unknown basis."""
        remaining, slices = quantity, []
        while remaining > 0 and self.lots:
            lot = self.lots[0]
            matched = min(remaining, lot["quantity"])
            cost = lot["cost"] * matched / lot["quantity"] if lot["cost"] is not None else None
            slices.append({**lot, "quantity": matched, "cost": cost})
            if cost is not None:
                lot["cost"] -= cost
            lot["quantity"] -= matched
            remaining -= matched
            if not lot["quantity"]:
                self.lots.popleft()
        if remaining:
            slices.append(
                {
                    "quantity": remaining,
                    "cost": None,
                    "acquired_at_ms": None,
                    "origin_id": "unknown:" + identity,
                    "origin_account": "",
                }
            )
        return slices, remaining

    def execute(self, row: dict) -> None:
        """Apply one normalized fill, retaining existing fee and partial-match semantics."""
        base, quote = row["symbol"].split("/")
        quantity = decimal(row["quantity"])
        notional = (
            decimal(row["notional"]) if row["notional"] is not None else quantity * decimal(row["price"])
        )
        self.estimated |= row["notional"] is None
        base_fee = quote_fee = ZERO
        if not row["fees_known"]:
            self.missing_fees += 1
        for fee in row["fees"]:
            currency, cost = fee["currency"], fee["cost"]
            if currency is None or cost is None:
                continue
            cost = decimal(cost)
            self.fees[currency] += cost
            if currency == base:
                base_fee += cost
            elif currency == quote:
                quote_fee += cost
            elif cost:
                self.unconverted.add(currency)
        if self.blocked:
            return
        if row["side"] == "buy":
            received, cost = quantity - base_fee, notional + quote_fee
            if received <= 0 or cost < 0:
                self.blocked = True
                self.issues.append(
                    "A fill has inconsistent net quantity or cost; subsequent lot matching is unavailable."
                )
                return
            self.receive(
                [
                    {
                        "quantity": received,
                        "cost": cost if row["fees_known"] else None,
                        "acquired_at_ms": row["timestamp_ms"],
                        "origin_id": row["id"],
                        "origin_account": row["account_id"],
                    }
                ]
            )
            return
        consumed, proceeds = quantity + base_fee, notional - quote_fee
        if consumed <= 0 or proceeds < 0:
            self.blocked = True
            self.issues.append(
                "A disposal has inconsistent net quantity or proceeds; subsequent lot matching is unavailable."
            )
            return
        slices, _ = self.take(consumed, row["timestamp_ms"], row["id"])
        known = sum((lot["quantity"] for lot in slices if lot["cost"] is not None), ZERO)
        matched_cost = sum((lot["cost"] for lot in slices if lot["cost"] is not None), ZERO)
        known_proceeds = proceeds * known / consumed
        pnl = known_proceeds - matched_cost
        self.realized += pnl
        self.known_sold += known
        self.unknown_sold += consumed - known
        self.disposals.append(
            {
                "id": row["id"],
                "trade_id": row["trade_id"],
                "timestamp": row["created_at"],
                "quantity": public(consumed),
                "known_quantity": public(known),
                "unknown_quantity": public(consumed - known),
                "matched_cost": public(matched_cost),
                "matched_proceeds": public(known_proceeds),
                "pnl_before_other_fees": public(pnl),
            }
        )
        self.curve.append({"timestamp": row["created_at"], "value": public(self.realized)})

    def summary(self) -> dict:
        """Produce a finite public snapshot; exclude unknown sold basis from matched P&L."""
        issues = list(self.issues)
        if self.missing_fees:
            issues.append(
                f"{self.missing_fees} fills have incomplete fee data; inventory and net P&L may be incomplete."
            )
        if self.unconverted:
            issues.append(
                "Fees/rebates in "
                + ", ".join(sorted(self.unconverted))
                + " are retained in native units, without historical quote conversion."
            )
        if self.estimated:
            issues.append(
                "Some execution notionals use reported price × quantity rather than a reported total."
            )
        if self.unknown_sold:
            issues.append(
                "Some disposed units have no opening/purchase cost basis; their proceeds are excluded from matched P&L."
            )
        quantity = sum((lot["quantity"] for lot in self.lots), ZERO)
        known = sum((lot["quantity"] for lot in self.lots if lot["cost"] is not None), ZERO)
        cost = sum((lot["cost"] for lot in self.lots if lot["cost"] is not None), ZERO)
        overflow = any(public(value) is None for value in (self.realized, quantity, cost, self.unknown_sold))
        if overflow:
            issues.append("Accounting values exceed the supported display range.")
        reliable = self.reliable and not overflow
        return {
            "fill_count": len(self.fills),
            "disposal_count": len(self.disposals),
            "matched_sold_quantity": public(self.known_sold),
            "unknown_sold_quantity": public(self.unknown_sold),
            "realized_before_other_fees": public(self.realized),
            "net_matched_realized": public(self.realized) if reliable else None,
            "open_quantity": public(quantity),
            "known_open_quantity": public(known),
            "known_open_cost": public(cost),
            "unknown_open_quantity": public(quantity - known),
            "fee_totals": {key: public(value) for key, value in self.fees.items()},
            "missing_fee_count": self.missing_fees,
            "unconverted_fee_currencies": sorted(self.unconverted),
            "net_known": reliable,
            "matching_blocked": self.blocked or overflow,
            "disposals": list(reversed(self.disposals[-100:])),
            "curve": self.curve[-500:],
            "issues": issues,
        }


def fifo(fills: list[dict], opening: dict | None = None) -> dict:
    """Replay a single account/market using the same book as transfer-aware calculations."""
    with localcontext() as context:
        context.prec = 50
        book = FifoBook(fills, opening)
        for row in sorted(fills, key=lambda item: (item["timestamp_ms"], item["id"])):
            book.execute(row)
        return book.summary()
