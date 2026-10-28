"""Pure native-asset arithmetic; unknown fees and uncertain timing stay unresolved."""

from collections import Counter, defaultdict
from decimal import Decimal, localcontext

from sibyl.accounting.balance_checks.contracts import BOUNDARY_MS, NOTE
from sibyl.accounting.funding import balance_effect


class Movements:
    """Accumulate known trade/funding changes without inventing cash flows or fee semantics."""

    def __init__(self):
        self.trades = defaultdict(Decimal)
        self.funding = defaultdict(Decimal)
        self.issues = defaultdict(set)
        self.global_issues = set()

    @staticmethod
    def assets(row, kind):
        if kind == "fills":
            return set(row["symbol"].split("/")) | {fee["currency"] for fee in row["fees"] if fee["currency"]}
        return {row["asset"]} | ({row["fee"]["currency"]} if row["fee"]["currency"] else set())

    def block(self, assets, reason):
        for asset in assets:
            self.issues[asset].add(reason)

    def trade(self, row):
        """Net base/quote quantities across exact markets and subtract signed native fees."""
        base, quote = row["symbol"].split("/")
        sign = Decimal(1 if row["side"] == "buy" else -1)
        self.trades[base] += sign * Decimal(str(row["quantity"]))
        if row["notional"] is None:
            self.block({quote}, "A trade has no known quote cost.")
        else:
            self.trades[quote] -= sign * Decimal(str(row["notional"]))
        if not row["fees_known"]:
            self.global_issues.add("Some trade fees are unknown; their asset or amount cannot be assumed.")
        for fee in row["fees"]:
            if fee["currency"] and fee["cost"] is not None:
                self.trades[fee["currency"]] -= Decimal(str(fee["cost"]))

    def movement(self, row) -> bool:
        """Apply resolved wallet effects, keeping documented and user-reviewed evidence distinct."""
        if row["status"] in {"failed", "cancelled"}:
            return False
        if row["status"] != "completed":
            self.block(self.assets(row, "funding"), "A funding observation is not completed.")
        else:
            effect = row.get("balance_effect") or balance_effect(row)
            if effect["quantity"] is not None:
                self.funding[row["asset"]] += Decimal(effect["quantity"])
                return True
            self.block(self.assets(row, "funding"), effect["reason"])
            if row["fee"]["currency"] is None:
                self.global_issues.add("A funding fee has no known asset; its balance effect is unresolved.")
        return False


def _compare(checkpoint: dict, current: dict) -> dict:
    """Compare dated observations; backfills, corrections and boundary events do not become returns."""
    book = Movements()
    used = {"fills": 0, "funding": 0}
    funding_evidence = []
    for kind in used:
        before = {row["id"]: row for row in checkpoint[kind]}
        after = {row["id"]: row for row in current[kind]}
        for identity, row in before.items():
            stamp = row["timestamp_ms"] if kind == "fills" else row.get("posted_ms")
            if identity not in after:
                book.block(book.assets(row, kind), "A checkpoint execution or funding record is now missing.")
            if stamp is None:
                if row["status"] not in {"failed", "cancelled"}:
                    book.block(book.assets(row, kind), "A funding record has no known balance-posting time.")
            elif stamp >= checkpoint["started_ms"] - BOUNDARY_MS:
                book.block(book.assets(row, kind), "Activity overlaps the starting balance observation.")
            if kind == "funding" and row["status"] not in {"completed", "failed", "cancelled"}:
                book.block(book.assets(row, kind), "Funding was unresolved at the starting checkpoint.")
        for identity, row in after.items():
            fields = (
                ("timestamp_ms", "symbol", "side", "quantity", "notional", "fees", "fees_known")
                if kind == "fills"
                else (
                    "timestamp_ms",
                    "posted_ms",
                    "asset",
                    "direction",
                    "quantity",
                    "status",
                    "fee",
                    "fee_known",
                    "amount_basis",
                    "wallet_scope",
                    "balance_effect",
                )
            )
            previous = before.get(identity)
            if previous and all(row.get(key) == previous.get(key) for key in fields):
                continue
            assets = book.assets(row, kind)
            if identity in before:
                assets |= book.assets(before[identity], kind)
            stamp = row["timestamp_ms"] if kind == "fills" else row.get("posted_ms")
            if stamp is None:
                if row["status"] not in {"failed", "cancelled"}:
                    book.block(assets, "A funding record has no known balance-posting time.")
            elif stamp <= checkpoint["ended_ms"] + BOUNDARY_MS:
                book.block(
                    assets,
                    "Older activity was imported or corrected after the checkpoint; capture a new starting point after review.",
                )
            elif stamp >= current["started_ms"] - BOUNDARY_MS:
                book.block(
                    assets,
                    "Activity overlaps or follows the latest balance observation; check again after imports settle.",
                )
            elif identity in before:
                book.block(assets, "An execution already present at the checkpoint changed.")
            else:
                if kind == "fills":
                    used[kind] += 1
                    book.trade(row)
                else:
                    funding_evidence.append(
                        {
                            "id": row["id"],
                            "asset": row["asset"],
                            "balance_effect": row.get("balance_effect") or balance_effect(row),
                        }
                    )
                    used[kind] += int(book.movement(row))
    if not any(job["kind"] == "fills" for job in current["imports"]):
        book.global_issues.add("No trade-history imports are configured for this account.")
    for job in current["imports"]:
        if not job.get("caught_up") or job["status"] in {"paused", "error", "unsupported", "retrying"}:
            book.global_issues.add("Some configured history imports are unfinished, paused or unavailable.")
    rows = []
    assets = (
        {asset for asset, quantity in checkpoint["balances"].items() if quantity}
        | {asset for asset, quantity in current["balances"].items() if quantity}
        | set(book.trades)
        | set(book.funding)
        | set(book.issues)
    )
    with localcontext() as context:
        context.prec = 50
        for asset in sorted(assets):
            opening = Decimal(str(checkpoint["balances"].get(asset, 0)))
            actual = Decimal(str(current["balances"].get(asset, 0)))
            expected = opening + book.trades[asset] + book.funding[asset]
            tolerance = max(Decimal("1e-12"), max(abs(expected), abs(actual)) * Decimal("1e-10"))
            issues = sorted(book.issues[asset] | book.global_issues)
            known = not issues
            difference = actual - expected if known else None
            if opening == actual == book.trades[asset] == book.funding[asset] == 0 and not issues:
                continue
            rows.append(
                {
                    "asset": asset,
                    "opening": float(opening),
                    "trade_change": float(book.trades[asset]),
                    "funding_change": float(book.funding[asset]),
                    "observed": float(actual),
                    "expected": float(expected) if known else None,
                    "difference": float(difference) if difference is not None else None,
                    "tolerance": float(tolerance),
                    "issues": issues,
                    "status": "incomplete"
                    if not known
                    else "difference"
                    if abs(difference) > tolerance
                    else "observed_match",
                }
            )
    differences = sum(row["status"] == "difference" for row in rows)
    incomplete = sum(row["status"] == "incomplete" for row in rows)
    return {
        "status": "differences"
        if differences
        else "incomplete"
        if incomplete or book.global_issues
        else "observed_match",
        "rows": rows,
        "differences": differences,
        "incomplete": incomplete,
        "activity": used,
        "funding_evidence": funding_evidence[:100],
        "funding_evidence_limit": 100,
        "funding_effect_counts": dict(
            Counter(row["balance_effect"]["provenance"] for row in funding_evidence)
        ),
        "calculation_version": 2,
        "notes": sorted(book.global_issues),
        "coverage_complete": False,
        "settlement_final": False,
        "note": NOTE,
    }


def compare(checkpoint: dict, current: dict) -> dict:
    """Keep arithmetic at fifty-digit precision across every market and native fee asset."""
    with localcontext() as context:
        context.prec = 50
        return _compare(checkpoint, current)
