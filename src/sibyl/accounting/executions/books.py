"""Decimal account/asset FIFO shared across all retained spot pairs.

The reporting unit is fixed for the entire replay. Books separate accounts and
environments, preserve transferred lot origins, and exclude unknown portions
from matched results. They never infer missing history, ownership or tax rules.
"""

from collections import Counter, defaultdict
from decimal import Decimal, localcontext

from sibyl.accounting.executions.group_lots import apply_group
from sibyl.services.portfolio.fifo import FifoBook, decimal, public
from sibyl.services.transfers.allocation import split_lots

ZERO = Decimal(0)


class AssetBooks:
    """Replay one environment using explicit source facts and dated conversion paths."""

    def __init__(self, currency, prices):
        self.currency, self.prices = currency, prices
        self.books = defaultdict(lambda: FifoBook([]))
        self.issues = defaultdict(set)
        self.disposals, self.conversions, self.transfers = [], [], []
        self.matched = defaultdict(lambda: ZERO)
        self.unknown_sold = defaultdict(lambda: ZERO)
        self.unconverted = defaultdict(int)
        self.funding_fees = defaultdict(lambda: ZERO)
        self.funding_fee_unknown = set()
        self.transit = {}

    def value(self, asset, quantity, timestamp, identity, *, hint=None):
        """Value an exact native quantity; retain each actual route or missing rate."""
        result = self.prices.rate(asset, self.currency, timestamp)
        if result is None and hint:
            other, implied = hint
            rate = self.prices.rate(other, self.currency, timestamp)
            if rate:
                result = (
                    rate[0] * implied,
                    [
                        {
                            "symbol": asset + "/" + other,
                            "execution_id": identity,
                            "rate": str(implied),
                            "kind": "reported_fill",
                        },
                        *rate[1],
                    ],
                )
        self.conversions.append(
            {
                "event_id": identity,
                "asset": asset,
                "quantity": str(quantity),
                "timestamp_ms": timestamp,
                "rate": str(result[0]) if result else None,
                "path": result[1] if result else [],
                "status": "identity" if asset == self.currency else "observed" if result else "unavailable",
            }
        )
        return quantity * result[0] if result else None

    def receive(self, key, quantity, cost, timestamp, identity, *, transferred=None):
        """Retain original acquisition ages when moving slices between account books."""
        if quantity <= 0:
            return
        self.books[key].receive(
            transferred
            if transferred is not None
            else [
                {
                    "quantity": quantity,
                    "cost": cost,
                    "acquired_at_ms": timestamp,
                    "origin_id": identity,
                    "origin_account": key[0],
                }
            ],
            transferred=transferred is not None,
        )

    def take(self, key, quantity, timestamp, identity):
        """A shortfall remains unknown instead of acquiring an invented zero-cost lot."""
        lots, shortfall = self.books[key].take(quantity, timestamp, identity)
        if shortfall:
            self.issues[key].add(
                "Disposed inventory exceeds retained acquisitions; opening or funding history is missing."
            )
            if key[1] == self.currency:
                # Reporting-unit principal has identity basis, even when quantity history is absent.
                for lot in lots:
                    if lot["cost"] is None:
                        lot["cost"] = lot["quantity"]
        return lots

    def dispose(self, key, quantity, proceeds, timestamp, identity, kind):
        """Record matched components and unknown proceeds/basis without merging them."""
        if quantity <= 0:
            raise ValueError("A disposal must have a positive net quantity.")
        lots = self.take(key, quantity, timestamp, identity)
        known = sum((lot["quantity"] for lot in lots if lot["cost"] is not None), ZERO)
        cost = sum((lot["cost"] for lot in lots if lot["cost"] is not None), ZERO)
        pnl = proceeds * known / quantity - cost if proceeds is not None else None
        if pnl is not None:
            self.matched[key] += pnl
        else:
            self.unconverted[key] += 1
        self.unknown_sold[key] += quantity - known
        self.disposals.append(
            {
                "event_id": identity,
                "account_id": key[0],
                "asset": key[1],
                "timestamp_ms": timestamp,
                "kind": kind,
                "quantity": public(quantity),
                "known_quantity": public(known),
                "unknown_quantity": public(quantity - known),
                "known_cost": public(cost),
                "proceeds": public(proceeds),
                "matched_realized": public(pnl),
            }
        )

    def fill(self, row):
        """Apply both sides and actual fee assets of one spot execution exactly once."""
        account, stamp, identity = row["account_id"], row["timestamp_ms"], row["id"]
        base, quote = row["symbol"].split("/")
        amount = decimal(row["quantity"])
        notional = decimal(row["notional"]) if row["notional"] is not None else amount * decimal(row["price"])
        fees = defaultdict(lambda: ZERO)
        keys = {(account, base), (account, quote)}
        for fee in row["fees"]:
            if fee["currency"] is not None and fee["cost"] is not None:
                fees[fee["currency"]] += decimal(fee["cost"])
                keys.add((account, fee["currency"]))
        if not row["fees_known"] or row["notional"] is None:
            for key in keys:
                self.issues[key].add(
                    "Execution fees or the native notional are incomplete; modeled net results remain provisional."
                )
        foreign_value = ZERO
        for asset, fee in sorted(fees.items()):
            if asset in {base, quote} or not fee:
                continue
            key = (account, asset)
            value = self.value(asset, abs(fee), stamp, identity)
            if fee > 0:
                self.dispose(key, fee, value, stamp, identity, "trade_fee_asset")
            else:
                self.receive(key, -fee, value, stamp, identity)
            if value is None:
                foreign_value = None
            elif foreign_value is not None:
                foreign_value += value if fee > 0 else -value
        if row["side"] == "buy":
            debit, received = notional + fees[quote], amount - fees[base]
            if debit < 0 or received <= 0:
                raise ValueError("A fill has inconsistent fee-adjusted purchase quantities.")
            principal = self.value(
                quote, debit, stamp, identity, hint=(base, amount / notional) if notional else None
            )
            if debit:
                self.dispose((account, quote), debit, principal, stamp, identity, "trade")
            cost = (
                principal + foreign_value
                if principal is not None and foreign_value is not None and row["fees_known"]
                else None
            )
            if cost is not None and cost < 0:
                cost = None
                self.issues[account, base].add(
                    "Rebates exceed purchase value; acquisition basis is unresolved."
                )
            self.receive((account, base), received, cost, stamp, identity)
        else:
            consumed, credit = amount + fees[base], notional - fees[quote]
            if consumed <= 0 or credit < 0:
                raise ValueError("A fill has inconsistent fee-adjusted sale quantities.")
            principal = self.value(
                quote, credit, stamp, identity, hint=(base, amount / notional) if notional else None
            )
            proceeds = (
                principal - foreign_value
                if principal is not None and foreign_value is not None and row["fees_known"]
                else None
            )
            self.dispose((account, base), consumed, proceeds, stamp, identity, "trade")
            self.receive((account, quote), credit, principal, stamp, identity)

    def funding(self, row):
        """Apply reviewed wallet effects; an unmatched incoming asset keeps unknown basis."""
        key = (row["account_id"], row["asset"])
        effect = row["balance_effect"]
        if effect["quantity"] is None:
            if row["status"] not in {"failed", "cancelled"}:
                self.issues[key].add(
                    "A retained funding movement has unresolved timing, wallet or amount effects."
                )
            return
        change = decimal(effect["quantity"])
        if not change:
            return
        stamp = row.get("posted_ms") or row["timestamp_ms"]
        if not row.get("posted_ms"):
            self.issues[key].add(
                "Funding uses its reported history timestamp; wallet posting time is unavailable."
            )
        if change > 0:
            self.receive(key, change, change if row["asset"] == self.currency else None, stamp, row["id"])
        else:
            self.take(key, -change, stamp, row["id"])
        self.issues[key].add(
            "Unpaired funding changes inventory but does not establish external-flow classification or acquisition basis."
        )

    def transfer(self, link, event, kind):
        """Carry reviewed one-to-one transfer lots across pairs and account boundaries."""
        if link.get("kind") == "group":
            return apply_group(self, link, event, kind)
        out, inc, plan = link["outgoing"], link["incoming"], link["plan"]
        key, stamp = (event["account_id"], event["asset"]), event.get("posted_ms") or event["timestamp_ms"]
        if kind == "dispatch":
            lots = self.take(key, decimal(plan["source_debit"]), stamp, event["id"])
            dispatched, fee = split_lots(lots, decimal(plan["dispatch_quantity"]))
            self.transit[link["id"]] = dispatched
            self._transfer_fee(key, fee, stamp, event["id"])
        else:
            if link["id"] not in self.transit:
                self.issues[key].add("Transfer receipt precedes dispatch; carryover is unavailable.")
                self.receive(key, decimal(plan["destination_credit"]), None, stamp, event["id"])
                return
            credit, fee = split_lots(self.transit.pop(link["id"]), decimal(plan["destination_credit"]))
            self.receive(
                key, decimal(plan["destination_credit"]), None, stamp, event["id"], transferred=credit
            )
            self._transfer_fee(key, fee, stamp, event["id"])
            self.transfers.append(
                {
                    "id": link["id"],
                    "asset": event["asset"],
                    "outgoing_account": out["account_id"],
                    "incoming_account": inc["account_id"],
                    "quantity": public(decimal(plan["destination_credit"])),
                    "known_cost": public(
                        sum((lot["cost"] for lot in credit if lot["cost"] is not None), ZERO)
                    ),
                    "unknown_quantity": public(
                        sum((lot["quantity"] for lot in credit if lot["cost"] is None), ZERO)
                    ),
                }
            )

    def _transfer_fee(self, key, lots, stamp, identity):
        if not lots:
            return
        quantity = sum((lot["quantity"] for lot in lots), ZERO)
        value = self.value(key[1], quantity, stamp, identity)
        cost = sum((lot["cost"] for lot in lots if lot["cost"] is not None), ZERO)
        known = sum((lot["quantity"] for lot in lots if lot["cost"] is not None), ZERO)
        if value is None or known != quantity:
            self.funding_fee_unknown.add(key)
        else:
            self.matched[key] += value - cost
            self.funding_fees[key] += value

    def summary(self):
        """Return asset-level modeled components, never a complete account-return claim."""
        items = []
        keys = set(self.books) | set(self.issues)
        for key in sorted(keys):
            book = self.books[key]
            quantity = sum((lot["quantity"] for lot in book.lots), ZERO)
            known_cost = sum((lot["cost"] for lot in book.lots if lot["cost"] is not None), ZERO)
            unknown = sum((lot["quantity"] for lot in book.lots if lot["cost"] is None), ZERO)
            issues = set(self.issues[key]) | set(book.issues)
            if self.unknown_sold[key]:
                issues.add(
                    "Some disposed units have unknown acquisition cost; their proceeds are excluded from matched results."
                )
            if self.unconverted[key]:
                issues.add(
                    "Historical conversion is unavailable for some disposals; their realized result is excluded."
                )
            if key in self.funding_fee_unknown:
                issues.add("Some funding fee value or inventory cost is unresolved.")
            matched = self.matched[key] - self.funding_fees[key]
            items.append(
                {
                    "account_id": key[0],
                    "asset": key[1],
                    "quantity": public(quantity),
                    "known_open_cost": public(known_cost),
                    "unknown_open_quantity": public(unknown),
                    "unknown_sold_quantity": public(self.unknown_sold[key]),
                    "matched_realized": public(matched),
                    "net_modeled_realized": public(matched) if not issues else None,
                    "funding_fee_value": public(self.funding_fees[key]),
                    "issues": sorted(issues),
                }
            )
        return {
            "items": items,
            "disposals": self.disposals[-500:][::-1],
            "disposal_count": len(self.disposals),
            "conversions": self.conversions[-500:][::-1],
            "conversion_count": len(self.conversions),
            "transfers": self.transfers[-100:],
            "transfer_count": len(self.transfers),
            "evidence_limits": {"disposals": 500, "conversions": 500, "transfers": 100},
        }


def replay(currency, prices, fills, funding, openings, transfers):
    """Use one deterministic timeline; equal native timestamps remain qualified."""
    with localcontext() as context:
        context.prec = 50
        books = AssetBooks(currency, prices)
        timeline = []
        mapped = {}
        for link in transfers:
            for side, kind in (("outgoing", "dispatch"), ("incoming", "receipt")):
                events = (
                    [leg["event"] for leg in link["plan"][side]]
                    if link.get("kind") == "group"
                    else [link[side]]
                )
                for event in events:
                    mapped[event["id"]] = link, kind
        touches = Counter()
        for row in fills:
            timeline.append((row["timestamp_ms"], 1, row["id"], "fill", row))
            for asset in set(row["symbol"].split("/")) | {
                f["currency"] for f in row["fees"] if f["currency"]
            }:
                touches[row["account_id"], asset, row["timestamp_ms"]] += 1
        dispatch_ties = Counter()
        for row in funding:
            if row["id"] in mapped and mapped[row["id"]][1] == "dispatch":
                dispatch_ties[
                    row["account_id"], row["asset"], row.get("posted_ms") or row["timestamp_ms"]
                ] += 1
        for (account, asset, _), count in dispatch_ties.items():
            if count > 1:
                books.issues[account, asset].add(
                    "Transfer dispatches share a timestamp; source FIFO slicing uses deterministic record-ID order and remains provisional."
                )
        for row in funding:
            timestamp = row.get("posted_ms") or row["timestamp_ms"]
            if row["id"] in mapped:
                link, kind = mapped[row["id"]]
                timeline.append((timestamp, 0 if kind == "dispatch" else 2, row["id"], kind, (link, row)))
            else:
                timeline.append((timestamp, 1, row["id"], "funding", row))
        for opening in openings:
            key = (opening["account_id"], opening["asset"])
            books.receive(
                key,
                decimal(opening["quantity"]),
                decimal(opening["total_cost"]) if opening["total_cost"] is not None else None,
                opening["timestamp_ms"],
                "opening:" + opening["id"],
            )
        for (account, asset, _), count in touches.items():
            if count > 1:
                books.issues[account, asset].add(
                    "Executions sharing this asset have equal native timestamps; FIFO ordering is ambiguous."
                )
        cutoffs = {(row["account_id"], row["asset"]): row["timestamp_ms"] for row in openings}
        for stamp, _, _identity, kind, row in sorted(timeline, key=lambda entry: entry[:3]):
            if kind == "fill":
                # Openings are validated strictly before every retained affected fill.
                books.fill(row)
            elif kind == "funding":
                if stamp > cutoffs.get((row["account_id"], row["asset"]), -1):
                    books.funding(row)
            else:
                link, event = row
                if stamp <= cutoffs.get((event["account_id"], event["asset"]), -1):
                    books.issues[event["account_id"], event["asset"]].add(
                        "Opening inventory overlaps a confirmed transfer; review the opening date."
                    )
                else:
                    books.transfer(link, event, kind)
        return books.summary()
