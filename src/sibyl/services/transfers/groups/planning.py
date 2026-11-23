"""Exact Decimal transfer conservation and source-version binding.

A group never supplies missing acquisition cost. It describes inventory movement
only; all dispatches must precede all receipts for causal batch carryover.
"""

import hashlib
import json
from decimal import localcontext

from sibyl.services.portfolio.fifo import ZERO, decimal
from sibyl.services.transfers.allocation import _fee
from sibyl.services.transfers.reconciliation import TransferConflict, eligible, fingerprint


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def source_version(event):
    """Bind native facts, posting/wallet scope and the current separate funding review."""
    effect = event.get("balance_effect") or {}
    return digest(
        {
            "facts": fingerprint(event),
            "posted_ms": event.get("posted_ms"),
            "wallet_scope": event.get("wallet_scope", "unknown"),
            "effect": {
                key: effect.get(key) for key in ("source_version", "review_id", "review_status", "quantity")
            },
        }
    )


def plan(request, events):
    """Require exact row/column sums, current facts and compatible known wallet effects."""
    with localcontext() as context:
        context.prec = 50
        sides, amounts, warnings, fee_count = {}, [], [], 0
        for name, direction in (("outgoing", "out"), ("incoming", "in")):
            legs = []
            for leg in getattr(request, name):
                row = events.get(leg.event_id)
                if row is None:
                    raise LookupError("Funding observation not found.")
                if source_version(row) != leg.source_version:
                    raise TransferConflict(
                        "Funding facts or balance review changed. Reload and preview the group again."
                    )
                if not eligible(row, direction):
                    raise ValueError(
                        "Use positive completed withdrawal/transfer-out and deposit/transfer-in records."
                    )
                modes = (
                    {"total_debit", "principal"} if direction == "out" else {"net_credit", "gross_receipt"}
                )
                if leg.amount not in modes:
                    raise ValueError("Choose an amount convention matching the leg's direction.")
                fee, fee_source = _fee(row, leg.fee_quantity)
                quantity = decimal(row["quantity"])
                amounts.extend([quantity, fee])
                fee_count += bool(fee)
                debit = quantity + fee if leg.amount == "principal" else quantity
                credit = quantity - fee if leg.amount == "gross_receipt" else quantity
                principal = debit - fee if direction == "out" else credit + fee
                if principal <= 0 or (direction == "in" and credit <= 0):
                    raise ValueError("Each dispatch and net receipt must remain positive after fees.")
                effect = row.get("balance_effect") or {}
                if row.get("wallet_scope") == "outside" or effect.get("wallet_scope") == "outside":
                    raise ValueError("A group cannot override an outside-wallet source or review.")
                expected = -debit if direction == "out" else credit
                if effect.get("quantity") is not None and decimal(effect["quantity"]) != expected:
                    raise ValueError(
                        "The allocation contradicts a documented or reviewed funding balance effect."
                    )
                if effect.get("quantity") is None:
                    warnings.append(
                        "Some wallet/amount effects are established only by this group's explicit local assertion; independent balance checks remain unresolved."
                    )
                legs.append(
                    {
                        "event": row,
                        "source_version": leg.source_version,
                        "amount": leg.amount,
                        "fee": str(fee),
                        "fee_source": fee_source,
                        "principal": str(principal),
                        "wallet_quantity": str(debit if direction == "out" else credit),
                    }
                )
            sides[name] = legs
        all_events = [leg["event"] for legs in sides.values() for leg in legs]
        if len({(row["asset"], row["environment"]) for row in all_events}) != 1:
            raise ValueError("All legs must use the same asset and environment.")
        out_accounts = {leg["event"]["account_id"] for leg in sides["outgoing"]}
        in_accounts = {leg["event"]["account_id"] for leg in sides["incoming"]}
        if out_accounts & in_accounts:
            raise ValueError("Source and destination account sets must be disjoint.")

        def timestamp(row):
            return row.get("posted_ms") or row["timestamp_ms"]

        if max(timestamp(leg["event"]) for leg in sides["outgoing"]) > min(
            timestamp(leg["event"]) for leg in sides["incoming"]
        ):
            raise ValueError(
                "Every dispatch must precede or share the first receipt's timestamp; no future lots can fund a receipt."
            )
        if fee_count > 1 and not request.distinct_fees_confirmed:
            raise ValueError(
                "Confirm that the nonzero fees are distinct charges, not repeated displays of the same fee."
            )
        out_ids = {leg.event_id for leg in request.outgoing}
        in_ids = {leg.event_id for leg in request.incoming}
        for edge in request.edges:
            if edge.outgoing_id not in out_ids or edge.incoming_id not in in_ids:
                raise ValueError("Every matrix edge must connect selected outgoing and incoming records.")
            amounts.append(edge.quantity)
        nonzero = [value for value in amounts if value]
        if (
            any(value.as_tuple().exponent < -30 or len(value.as_tuple().digits) > 48 for value in nonzero)
            or max(value.adjusted() for value in nonzero)
            - min(value.as_tuple().exponent for value in nonzero)
            + 3
            > 50
        ):
            raise ValueError(
                "Group quantities exceed the 50-digit arithmetic budget or 30 fractional places."
            )
        for side, field in (("outgoing", "outgoing_id"), ("incoming", "incoming_id")):
            for leg in sides[side]:
                total = sum(
                    (edge.quantity for edge in request.edges if getattr(edge, field) == leg["event"]["id"]),
                    ZERO,
                )
                if total != decimal(leg["principal"]):
                    raise ValueError(
                        "Matrix row and column sums must exactly equal each leg's dispatched/arriving principal."
                    )
        debit = sum((decimal(leg["wallet_quantity"]) for leg in sides["outgoing"]), ZERO)
        credit = sum((decimal(leg["wallet_quantity"]) for leg in sides["incoming"]), ZERO)
        fees = sum((decimal(leg["fee"]) for legs in sides.values() for leg in legs), ZERO)
        if debit != credit + fees:
            raise ValueError("Source debits must exactly equal destination credits plus all distinct fees.")
        asset, environment = all_events[0]["asset"], all_events[0]["environment"]
        result = {
            "version": 1,
            "asset": asset,
            "environment": environment,
            **sides,
            "edges": [edge.model_dump(mode="json") for edge in request.edges],
            "source_debit": str(debit),
            "destination_credit": str(credit),
            "fee_quantity": str(fees),
            "lot_order": "Listed edges slice source FIFO principal in order; each receipt merges by original acquisition age. Fees consume the tail after principal/credit.",
            "warnings": sorted(set(warnings)),
            "note": "User-asserted own-account movement, not independent ownership, settlement or external-flow proof. Unknown basis stays unknown. Group carryover applies in Across pairs; By market and balance checks retain their own narrower rules.",
        }
        result["review_fingerprint"] = digest(result)
        return result
