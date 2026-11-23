"""Causal FIFO slicing for explicit multi-record transfer matrices.

The caller has validated every source version and the complete group. Source
fees consume trailing lots once; destination fees consume the tail of the merged
arriving lots. Original ages/costs survive, including nullable unknown costs.
"""

from sibyl.services.portfolio.fifo import ZERO, decimal, public
from sibyl.services.transfers.allocation import lot_evidence, split_lots


def apply_group(books, group, event, kind):
    """Apply one timeline leg using only the reviewed, balanced allocation edges."""
    plan, identity = group["plan"], event["id"]
    side = "outgoing" if kind == "dispatch" else "incoming"
    leg = next(item for item in plan[side] if item["event"]["id"] == identity)
    key = event["account_id"], event["asset"]
    stamp = event.get("posted_ms") or event["timestamp_ms"]
    if kind == "dispatch":
        lots = books.take(key, decimal(leg["wallet_quantity"]), stamp, identity)
        principal, fees = split_lots(lots, decimal(leg["principal"]))
        books._transfer_fee(key, fees, stamp, identity)
        for edge in plan["edges"]:
            if edge["outgoing_id"] == identity:
                allocated, principal = split_lots(principal, decimal(edge["quantity"]))
                books.transit[group["id"], identity, edge["incoming_id"]] = allocated
        if principal:
            raise ValueError("Group conservation failed: source principal remains unallocated.")
        return
    incoming = []
    for edge in plan["edges"]:
        if edge["incoming_id"] == identity:
            slices = books.transit.pop((group["id"], edge["outgoing_id"], identity), None)
            if slices is None:
                raise ValueError("Group receipt has no preceding dispatched principal.")
            incoming.extend(slices)
    ages = {}
    for lot in incoming:
        if lot["acquired_at_ms"] in ages and ages[lot["acquired_at_ms"]] != lot["origin_id"]:
            books.issues[key].add("Merged lots share acquisition timestamps; FIFO ordering is ambiguous.")
        ages[lot["acquired_at_ms"]] = lot["origin_id"]
    incoming.sort(
        key=lambda lot: (lot["acquired_at_ms"] if lot["acquired_at_ms"] is not None else -1, lot["origin_id"])
    )
    credit, fees = split_lots(incoming, decimal(leg["wallet_quantity"]))
    books.receive(key, decimal(leg["wallet_quantity"]), None, stamp, identity, transferred=credit)
    books._transfer_fee(key, fees, stamp, identity)
    books.transfers.append(
        {
            "id": group["id"],
            "kind": "group",
            "incoming_event_id": identity,
            "asset": event["asset"],
            "incoming_account": event["account_id"],
            "outgoing_accounts": sorted({item["event"]["account_id"] for item in plan["outgoing"]}),
            "quantity": public(decimal(leg["wallet_quantity"])),
            "known_cost": public(sum((lot["cost"] for lot in credit if lot["cost"] is not None), ZERO)),
            "unknown_quantity": public(sum((lot["quantity"] for lot in credit if lot["cost"] is None), ZERO)),
            "credit_lots": lot_evidence(credit, 20),
            "fee_lots": lot_evidence(fees, 20),
        }
    )
