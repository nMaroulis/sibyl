"""Apply reviewed historical funding only to its exact reconciled sale shortfall."""

import json
import math

from sibyl.strategies.execution.contracts import ExecutionGuard
from sibyl.strategies.execution.ownership.ledger import digest

MAX_FUNDING = 50
UNIT_TOLERANCE = 1e-10


def active_funding(db, job_id):
    """Read the latest immutable set, including an explicitly retired empty set."""
    row = db.execute(
        "SELECT repair_id,payload FROM strategy_ownership_sale_funding "
        "WHERE job_id=? ORDER BY sequence DESC LIMIT 1",
        (job_id,),
    ).fetchone()
    return (row[0], json.loads(row[1])) if row else (None, {})


def fill_proof(fill):
    """Pin fill identity, time, quantity, cost and reported fee facts."""
    return digest(
        {
            key: fill[key]
            for key in (
                "id",
                "order_id",
                "timestamp_ms",
                "side",
                "quantity",
                "price",
                "notional",
                "fees_known",
                "fees",
            )
        }
    )


def matches_funding(receipt, fill, deficit):
    """Keep an approval only while the exact fill and required shortage still match."""
    return (
        deficit > UNIT_TOLERANCE
        and math.isclose(deficit, receipt["quantity"], rel_tol=0, abs_tol=UNIT_TOLERANCE)
        and receipt["proof"] == fill_proof(fill)
    )


class SaleFundingReview:
    """Gather historical shortages and bind each user-asserted basis to its fill."""

    def __init__(self, enabled, assertions):
        self.enabled = enabled
        self.assertions = {row["fill_id"]: row for row in assertions}
        if len(self.assertions) != len(assertions):
            raise ExecutionGuard("Each sale can have only one funding assertion.")
        if assertions and not enabled:
            raise ExecutionGuard("Enable the sale funding review before entering cost basis.")
        if len(assertions) > MAX_FUNDING or any(
            not math.isfinite(row["cost_basis"])
            or not 0 <= row["cost_basis"] <= 1e12
            or not row["note"].strip()
            or len(row["note"]) > 300
            for row in assertions
        ):
            raise ExecutionGuard("Each sale funding assertion requires a finite basis and source note.")
        self.used = set()
        self.required = []

    def resolve(self, job, fill, deficit, previous):
        """Return one provisional or retained funding entry, or let accounting block."""
        if previous and matches_funding(previous, fill, deficit):
            return previous
        if not self.enabled:
            if previous:
                raise ExecutionGuard("Historical sale funding changed. Enable Review sale funding.")
            return None
        if deficit <= UNIT_TOLERANCE:
            return None
        if len(self.required) >= MAX_FUNDING:
            raise ExecutionGuard("This repair has too many sales for one funding review.")
        reference = deficit * fill["price"]
        if not math.isfinite(reference) or reference <= 0:
            raise ExecutionGuard("A historical sale has no usable reference value.")
        entry = {
            "job_id": job["id"],
            "fill_id": fill["id"],
            "order_id": fill["order_id"],
            "timestamp_ms": fill["timestamp_ms"],
            "quantity": deficit,
            "reference_value": reference,
            "proof": fill_proof(fill),
        }
        assertion = self.assertions.get(fill["id"])
        self.required.append({**entry, "missing_basis": assertion is None})
        if assertion is None:
            # Replay provisionally to locate later shortages. This can never be approved.
            return {**entry, "cost_basis": 0.0, "note": ""}
        self.used.add(fill["id"])
        return {**entry, "cost_basis": assertion["cost_basis"], "note": assertion["note"]}

    def check_assertions(self):
        """Reject extra claims for any fill outside the current replay shortages."""
        if self.used != self.assertions.keys():
            raise ExecutionGuard("The sale funding assertions no longer match the current shortages.")
