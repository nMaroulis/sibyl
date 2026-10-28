"""Explicit amount/fee conventions for one-to-one own-account transfers.

These are user-reviewed computational allocations, not provider facts or tax
rules. Only nonnegative fees in the transferred asset are supported. Source
records stay immutable and all arithmetic uses their recorded decimal values.
"""

from decimal import Decimal, localcontext
from typing import Literal

from pydantic import Field

from sibyl.models import Request
from sibyl.services.fifo import ZERO, decimal, public


class TransferAllocation(Request):
    """State whether each reported amount includes its own distinct fee charge.

    Optional fee quantities fill missing source fee data in transferred-asset
    units. Known reported fees cannot be overridden. Both fees must be distinct
    charges; a repeated display of the same fee must not be counted twice.
    """

    outgoing_amount: Literal["total_debit", "principal"]
    incoming_amount: Literal["net_credit", "gross_receipt"]
    outgoing_fee_quantity: Decimal | None = Field(default=None, ge=0, le=Decimal("1e30"))
    incoming_fee_quantity: Decimal | None = Field(default=None, ge=0, le=Decimal("1e30"))
    fee_policy: Literal["separate_inventory_cost"] = "separate_inventory_cost"
    distinct_fees_confirmed: bool = False


def _fee(event: dict, assertion: Decimal | None) -> tuple[Decimal, str]:
    """Use reported fees or an explicit missing-data assertion, never a silent zero."""
    fee = event["fee"]
    if fee["currency"] not in {None, event["asset"]} and fee["cost"] != 0:
        raise ValueError("Fees in another currency are not supported by this transfer allocation.")
    if event["fee_known"]:
        cost = decimal(fee["cost"])
        if cost < 0:
            raise ValueError("Transfer fee rebates require separate accounting and are not supported yet.")
        if assertion is not None and assertion != cost:
            raise ValueError("A known reported fee cannot be overridden; correct the source record first.")
        return cost, "reported"
    if assertion is None:
        raise ValueError(
            "Enter an explicit transferred-asset fee quantity for each source with missing fee data."
        )
    # Even a partially reported nonnegative amount must not be contradicted.
    if fee["cost"] is not None and decimal(fee["cost"]) != assertion:
        raise ValueError("The asserted fee contradicts a partially reported fee amount.")
    return assertion, "user_asserted"


def allocate(outgoing: dict, incoming: dict, request: TransferAllocation) -> dict:
    """Require exact debit = credit + two distinct fees, in one native asset.

    Received units are allocated first, outgoing fee units next at dispatch;
    incoming fee units come from the tail of arriving slices before receipt.
    Fee inventory cost is disclosed separately, never capitalized or treated as
    zero-proceeds trading P&L. Historical fee valuation remains unavailable.
    """
    with localcontext() as context:
        context.prec = 50
        if outgoing["asset"] != incoming["asset"]:
            raise ValueError("Allocation requires the same transferred asset.")
        outgoing_fee, outgoing_source = _fee(outgoing, request.outgoing_fee_quantity)
        incoming_fee, incoming_source = _fee(incoming, request.incoming_fee_quantity)
        if outgoing_fee and incoming_fee and not request.distinct_fees_confirmed:
            raise ValueError(
                "Explicitly confirm that outgoing and incoming fees are distinct charges, not the same fee reported twice."
            )
        outgoing_quantity, incoming_quantity = decimal(outgoing["quantity"]), decimal(incoming["quantity"])
        values = [
            value for value in (outgoing_quantity, incoming_quantity, outgoing_fee, incoming_fee) if value
        ]
        if (
            any(value.as_tuple().exponent < -30 or len(value.as_tuple().digits) > 50 for value in values)
            or max(value.adjusted() for value in values)
            - min(value.as_tuple().exponent for value in values)
            + 2
            > 50
        ):
            raise ValueError(
                "Quantities exceed the supported allocation precision: at most 30 fractional places within the 50-digit arithmetic budget."
            )
        debit = outgoing_quantity + (outgoing_fee if request.outgoing_amount == "principal" else ZERO)
        dispatch = debit - outgoing_fee
        credit = incoming_quantity - (incoming_fee if request.incoming_amount == "gross_receipt" else ZERO)
        if dispatch <= 0 or credit <= 0:
            raise ValueError("Dispatch and destination credit must remain positive after fees.")
        if debit != credit + outgoing_fee + incoming_fee:
            raise ValueError(
                "Allocation does not balance: source debit must equal destination credit plus the two distinct fee charges."
            )
        return {
            "request": request.model_dump(mode="json"),
            "source_debit": str(debit),
            "dispatch_quantity": str(dispatch),
            "destination_credit": str(credit),
            "outgoing_fee": str(outgoing_fee),
            "incoming_fee": str(incoming_fee),
            "fee_sources": {"outgoing": outgoing_source, "incoming": incoming_source},
            "fee_policy": request.fee_policy,
            "lot_order": "principal_first_outgoing_fee_last; credit_first_incoming_fee_last",
        }


def movement_plan(link: dict, outgoing: dict, incoming: dict) -> dict:
    """Rebuild a reviewed allocation, or retain the original explicit zero-fee rule."""
    saved = link.get("allocation") or link["reviewed"].get("allocation")
    if saved:
        return allocate(outgoing, incoming, TransferAllocation.model_validate(saved["request"]))
    if decimal(outgoing["quantity"]) != decimal(incoming["quantity"]):
        raise ValueError(
            "Reported amounts differ. Review an explicit fee allocation; split/merged carryover is not supported."
        )
    if any(not event["fee_known"] or decimal(event["fee"]["cost"]) != 0 for event in (outgoing, incoming)):
        raise ValueError(
            "Both source records must explicitly report zero fees, or have a reviewed fee allocation."
        )
    result = allocate(
        outgoing, incoming, TransferAllocation(outgoing_amount="total_debit", incoming_amount="net_credit")
    )
    result["fee_sources"] = {"outgoing": "reported", "incoming": "reported"}
    return result


def split_lots(lots: list[dict], quantity: Decimal) -> tuple[list[dict], list[dict]]:
    """Split derived FIFO slices without changing origins or mutating caller data."""
    head, tail, remaining = [], [], quantity
    for original in lots:
        lot = dict(original)
        take = min(remaining, lot["quantity"])
        if take:
            cost = lot["cost"] * take / lot["quantity"] if lot["cost"] is not None else None
            head.append({**lot, "quantity": take, "cost": cost})
            lot["quantity"] -= take
            if cost is not None:
                lot["cost"] -= cost
            remaining -= take
        if lot["quantity"]:
            tail.append(lot)
    if remaining:
        raise ValueError("Transfer slice allocation exceeded the dispatched quantity.")
    return head, tail


def lot_evidence(lots: list[dict], limit: int) -> dict:
    """Expose known/unknown portions and bounded origins; unknown cost stays nullable."""
    quantity = sum((lot["quantity"] for lot in lots), ZERO)
    known = sum((lot["quantity"] for lot in lots if lot["cost"] is not None), ZERO)
    return {
        "quantity": public(quantity),
        "known_quantity": public(known),
        "unknown_quantity": public(quantity - known),
        "known_cost": public(sum((lot["cost"] for lot in lots if lot["cost"] is not None), ZERO)),
        "lot_count": len(lots),
        "lot_limit": limit,
        "lots": [
            {
                **{key: lot[key] for key in ("acquired_at_ms", "origin_id", "origin_account")},
                "quantity": public(lot["quantity"]),
                "cost": public(lot["cost"]),
            }
            for lot in lots[:limit]
        ],
    }
