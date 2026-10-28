"""Resolve a movement in its account's configured wallet without guessing fee inclusion.

Kraken's posted ledger defines signed amount minus same-asset fee. Other nonzero
fee conventions require an explicit local review. Neither rule proves ownership,
external cash flow, settlement finality, tax basis or complete history coverage.
"""

import hashlib
import json
from decimal import Decimal, localcontext

KRAKEN_RULE = "kraken-ledger-v1"
KRAKEN_SOURCE = "https://support.kraken.com/articles/360001169383-how-to-interpret-ledger-history-fields"
FACTS = (
    "id",
    "account_id",
    "exchange",
    "environment",
    "kind",
    "asset",
    "timestamp_ms",
    "direction",
    "quantity",
    "status",
    "fee",
    "fee_known",
    "internal",
    "amount_basis",
)


def fingerprint(row):
    """Bind a review to material native facts, including the observed wallet scope."""
    facts = {key: row.get(key) for key in FACTS}
    facts["wallet_scope"] = row.get("wallet_scope", "unknown")
    facts["posted_ms"] = row.get("posted_ms")
    return hashlib.sha256(json.dumps(facts, sort_keys=True, allow_nan=False).encode()).hexdigest()


def reviewed_change(row, decision):
    """Validate a same-asset convention; a review cannot replace known provider facts."""
    scope = decision["wallet_scope"]
    native_scope = row.get("wallet_scope", "unknown")
    if native_scope != "unknown" and scope != native_scope:
        raise ValueError("The wallet choice contradicts the provider's wallet scope.")
    convention, asserted = decision.get("amount_convention"), decision.get("fee_quantity")
    if scope == "outside":
        if convention is not None or asserted is not None:
            raise ValueError("An outside-wallet review must not specify an amount convention or fee.")
        return Decimal(0)
    valid = {"total_debit", "principal"} if row["direction"] == "out" else {"net_credit", "gross_receipt"}
    if convention not in valid:
        raise ValueError("Choose the amount convention for this movement's direction.")
    fee = row["fee"]
    if fee["currency"] not in {None, row["asset"]}:
        raise ValueError("Only same-asset funding fees can be reviewed here.")
    if row["fee_known"]:
        cost = Decimal(str(fee["cost"]))
        if asserted is not None and Decimal(str(asserted)) != cost:
            raise ValueError("A review cannot override the reported fee.")
    else:
        if asserted is None:
            raise ValueError("Enter the missing same-asset fee explicitly, including zero if verified.")
        cost = Decimal(str(asserted))
        if fee["cost"] is not None and cost != Decimal(str(fee["cost"])):
            raise ValueError("A review cannot override the reported fee amount.")
    if not cost.is_finite() or not 0 <= cost <= Decimal("1e30"):
        raise ValueError("Manual fee reviews require a finite, nonnegative fee.")
    quantity = Decimal(str(row["quantity"]))
    if convention in {"total_debit", "gross_receipt"} and cost > quantity:
        raise ValueError("An included fee cannot exceed the reported amount.")
    with localcontext() as context:
        context.prec = 50
        return {
            "total_debit": -quantity,
            "principal": -quantity - cost,
            "net_credit": quantity,
            "gross_receipt": quantity - cost,
        }[convention]


def balance_effect(row, review=None):
    """Return a JSON-safe signed quantity with provenance, or an explicit unresolved reason."""
    version = fingerprint(row)
    result = {
        "version": 1,
        "source_version": version,
        "asset": row["asset"],
        "quantity": None,
        "provenance": "unresolved",
        "rule": None,
        "source_url": None,
        "wallet_scope": row.get("wallet_scope", "unknown"),
        "review_id": review["id"] if review else None,
        "review_status": "withdrawn"
        if review and review["action"] == "withdraw"
        else "stale"
        if review and review["source_version"] != version
        else "current"
        if review
        else None,
        "reviewable": False,
        "reason": "",
    }
    if row["status"] in {"failed", "cancelled"}:
        result.update(
            quantity="0", provenance="not_applied", reason="Failed or cancelled movement; not applied."
        )
        return result
    if row["status"] != "completed":
        result["reason"] = "The funding observation is not completed."
        return result
    scope, fee = result["wallet_scope"], row["fee"]
    kraken = row.get("exchange") == "kraken" and row.get("amount_basis") == "ledger_amount"
    with localcontext() as context:
        context.prec = 50
        signed = Decimal(str(row["quantity"])) * (1 if row["direction"] == "in" else -1)
        if scope == "outside":
            result.update(
                quantity="0",
                provenance="provider",
                rule="outside-wallet-v1",
                reason="The provider identifies a wallet outside the configured balance scope.",
            )
        elif scope == "configured" and kraken and row["fee_known"] and fee["currency"] == row["asset"]:
            result.update(
                quantity=str(signed - Decimal(str(fee["cost"]))),
                provenance="provider",
                rule=KRAKEN_RULE,
                source_url=KRAKEN_SOURCE,
                reason="Kraken posted ledger: signed amount minus same-asset fee.",
            )
        elif scope == "configured" and row["fee_known"] and fee["cost"] == 0:
            result.update(
                quantity=str(signed),
                provenance="provider",
                rule="zero-fee-v1",
                reason="Completed movement in the configured wallet with an explicit zero fee.",
            )
        else:
            result["reviewable"] = (
                not kraken
                and (fee["currency"] in {None, row["asset"]})
                and (fee["cost"] is None or fee["cost"] >= 0)
            )
            result["reason"] = (
                "The movement's wallet scope is unknown. Review it before applying a balance effect."
                if scope == "unknown"
                else "Funding fee inclusion in the reported amount is unresolved."
            )
            if review and result["review_status"] == "current" and result["reviewable"]:
                try:
                    change = reviewed_change(row, review["decision"])
                except ValueError:
                    result["reason"] = "The saved review is no longer applicable; review the source again."
                else:
                    result.update(
                        quantity=str(change),
                        provenance="user_review",
                        rule="user-convention-v1",
                        wallet_scope=review["decision"]["wallet_scope"],
                        reason="Your local wallet and amount-convention review; not a provider fact.",
                    )
    return result
