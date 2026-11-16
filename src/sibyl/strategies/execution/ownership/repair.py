"""Review corrected handoffs without modifying the original attribution receipts."""

import json
import math
from collections import defaultdict
from datetime import UTC, datetime
from graphlib import CycleError, TopologicalSorter

from sibyl.strategies.execution.accounting import project
from sibyl.strategies.execution.cancellation import pending_evidence
from sibyl.strategies.execution.contracts import ExecutionGuard
from sibyl.strategies.execution.liquidation import active_plan
from sibyl.strategies.execution.ownership import ledger
from sibyl.strategies.execution.ownership.acquisitions import Acquisitions
from sibyl.strategies.execution.ownership.sale_funding import SaleFundingReview

MAX_RUNS = 24
MAX_EVENTS = 80


class AttributionReplay:
    """Revalue receipts at their original fill checkpoints in one in-memory replay."""

    def __init__(self, events, transfers, *, allow_quantity_changes, repair_releases, sale_funding):
        self.events = events
        self.transfers = transfers
        self.allow_quantity_changes = allow_quantity_changes
        self.repair_releases = repair_releases
        self.sale_funding = sale_funding

    @staticmethod
    def _apply_quantity(event, units):
        """Keep the historical per-unit mark when superseding the effective quantity."""
        original_quantity = event["_original_quantity"]
        if original_quantity >= 0:
            raise ExecutionGuard("The original outgoing receipt has an invalid quantity.")
        original_price = event["_original_reference_value"] / original_quantity
        if not math.isfinite(original_price) or original_price <= 0:
            raise ExecutionGuard("The original receipt reference price is invalid.")
        reference_value = units * original_price
        if not math.isfinite(reference_value):
            raise ExecutionGuard("The corrected receipt reference value is outside the supported range.")
        event["quantity"] = units
        event["reference_value"] = reference_value

    def revalue(self, event, quantity, basis, consumed):
        if not math.isfinite(basis) or basis < 0:
            raise ExecutionGuard("Corrected fills produce an invalid basis at an ownership receipt.")
        if set(event["after_fills"]) != consumed:
            raise ExecutionGuard(
                "The fill order at an ownership receipt changed. The repair cannot be applied."
            )
        action = event["action"]
        units = event["quantity"]
        identity, peer = event["job_id"], event["peer_id"]
        if action == "adopt":
            return  # The user's original acquisition-cost assertion remains in force.
        if action == "handoff_in":
            value = self.transfers.get((peer, identity))
            if value is None:
                raise ExecutionGuard("The recorded handoff has no matching source receipt.")
            event["quantity"], event["cost_basis"], event["reference_value"] = value
            return
        if action == "handoff_out":
            changed = not math.isclose(-units, quantity, rel_tol=0, abs_tol=1e-10)
            if changed and not self.allow_quantity_changes:
                raise ExecutionGuard(
                    "Corrected fills cannot support the recorded quantity. Review with handoff quantity changes enabled."
                )
            if changed:
                units = -quantity if quantity else 0.0
                self._apply_quantity(event, units)
            if quantity > 0:
                event["cost_basis"] = -basis * min(1.0, -units / quantity)
            elif basis > 1e-8:
                raise ExecutionGuard("Corrected fills leave acquisition basis without any owned units.")
            else:
                event["cost_basis"] = 0.0
            self.transfers[(identity, peer)] = (-units, -event["cost_basis"], -event["reference_value"])
            return
        if action != "release" or units > 0 or event["_original_quantity"] >= 0:
            raise ExecutionGuard("The original outgoing ownership receipt is invalid.")
        if self.repair_releases:
            corrected = min(-event["_original_quantity"], quantity)
            if not math.isclose(-units, corrected, rel_tol=0, abs_tol=1e-10):
                units = -corrected if corrected else 0.0
                self._apply_quantity(event, units)
        elif -units > quantity + 1e-10:
            raise ExecutionGuard(
                f"Recorded release {event['id'][:8]} exceeds corrected ownership. Enable Fix underfunded releases."
            )
        if quantity <= 0:
            if basis > 1e-8:
                raise ExecutionGuard("Corrected fills leave acquisition basis without any owned units.")
            event["cost_basis"] = 0.0
        else:
            event["cost_basis"] = -basis * min(1.0, -units / quantity)


class OwnershipRepairs:
    """Rebuild one paused handoff family, then bind the exact preview to an atomic approval."""

    def __init__(self, runner):
        self.runner = runner
        self.store = runner.store
        with self.store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS strategy_ownership_repairs "
                "(id TEXT PRIMARY KEY,payload TEXT NOT NULL)"
            )

    def _family(self, db, selected):
        scope = ledger.scope(selected)
        jobs = {
            job["id"]: job
            for (raw,) in db.execute(
                "SELECT payload FROM strategy_jobs WHERE json_extract(payload,'$.mode')='exchange' "
                "AND json_extract(payload,'$.connection_id')=? "
                "AND json_extract(payload,'$.parameters.symbol')=? ORDER BY id LIMIT 101",
                (scope["connection_id"], scope["symbol"]),
            )
            for job in [json.loads(raw)]
        }
        if len(jobs) > 100:
            raise ExecutionGuard(
                "Ownership repair supports at most 100 retained runs in this account and pair."
            )
        receipts = {identity: ledger.events(db, identity, with_original=True) for identity in jobs}
        links = defaultdict(set)
        outgoing, incoming = defaultdict(list), defaultdict(list)
        for identity, events in receipts.items():
            for event in events:
                if event["action"] == "handoff_out":
                    outgoing[(identity, event["peer_id"])].append(event)
                elif event["action"] == "handoff_in":
                    incoming[(event["peer_id"], identity)].append(event)
                else:
                    continue
                links[identity].add(event["peer_id"])
                links[event["peer_id"]].add(identity)
        family, waiting = set(), [selected["id"]]
        while waiting:
            identity = waiting.pop()
            if identity not in family:
                family.add(identity)
                waiting.extend(links[identity] - family)
        if not family <= jobs.keys():
            raise ExecutionGuard("An ownership handoff is missing its original source or destination.")
        if len(family) > MAX_RUNS or sum(len(receipts[i]) for i in family) > MAX_EVENTS:
            raise ExecutionGuard("This handoff family exceeds the supported repair scope.")
        graph = {identity: set() for identity in sorted(family)}
        for source, target in sorted(outgoing.keys() | incoming.keys()):
            if source not in family:
                continue
            out, received = outgoing[(source, target)], incoming[(source, target)]
            if (
                len(out) != 1
                or len(received) != 1
                or out[0]["quantity"] != -received[0]["quantity"]
                or out[0]["reference_value"] != -received[0]["reference_value"]
                or out[0]["_original_quantity"] >= 0
                or received[0]["_original_quantity"] != -out[0]["_original_quantity"]
            ):
                raise ExecutionGuard("The original handoff does not have matching paired receipts.")
            graph[target].add(source)
        try:
            sequence = tuple(TopologicalSorter(graph).static_order())
        except CycleError as exc:
            raise ExecutionGuard("Ownership handoffs form a cycle. The repair cannot be applied.") from exc
        return [(jobs[identity], receipts[identity]) for identity in sequence]

    @staticmethod
    def _rebind(db, evidence):
        row = db.execute("SELECT payload FROM strategy_jobs WHERE id=?", (evidence["job_id"],)).fetchone()
        if not row:
            raise ExecutionGuard("An original handoff source is missing.")
        job = json.loads(row[0])
        native = ledger.native(db, job, evidence["order_ids"])
        if (
            ledger.scope(job) != evidence["scope"]
            or [row["order"]["id"] for row in native] != evidence["order_ids"]
        ):
            raise ExecutionGuard("An original handoff order is missing or changed scope.")
        return {**evidence, "digest": ledger.digest(native)}

    def _preview(
        self, db, selected, *, allow_quantity_changes, repair_releases, review_sale_funding, sale_funding
    ):
        transfers, rebound, adjustments, summaries, inputs = {}, {}, [], [], []
        acquisitions = Acquisitions(db)
        funding_review = SaleFundingReview(review_sale_funding, sale_funding, acquisitions)
        funding_updates, funding_changes, reservation_changes = {}, [], []
        seen_fills = set()
        has_correction = False
        family = self._family(db, selected)
        members = {job["id"] for job, _ in family}
        for job, receipts in family:
            identity = job["id"]
            if job["status"] not in {"paused", "stopped", "completed"} or active_plan(db, identity):
                raise ExecutionGuard(
                    "Pause all affected runs and stop active liquidation plans before repair."
                )
            if (job["exchange"], job["sandbox"], job["environment"]) != (
                selected["exchange"],
                selected["sandbox"],
                selected["environment"],
            ):
                raise ExecutionGuard("A handoff crosses the reviewed venue or environment.")
            originals = {event["id"]: event.copy() for event in receipts}
            for event in receipts:
                pins = []
                for pin in event["pins"]:
                    if pin["job_id"] not in members:
                        raise ExecutionGuard(
                            "An original ownership dependency lies outside the handoff family."
                        )
                    key = ledger.digest(pin)
                    if key not in rebound:
                        rebound[key] = self._rebind(db, pin)
                    current = rebound[key]
                    has_correction |= pin != current
                    pins.append(current)
                event["pins"] = pins
            values = project(
                job,
                self.runner.trading,
                db=db,
                repair=AttributionReplay(
                    receipts,
                    transfers,
                    allow_quantity_changes=allow_quantity_changes,
                    repair_releases=repair_releases,
                    sale_funding=funding_review,
                ),
            )
            if (
                values["ownership_stale"]
                or values["accounting_incomplete"]
                or values["unresolved_orders"]
                or pending_evidence(db, identity)
            ):
                raise ExecutionGuard(
                    "Reconcile every affected run’s orders, fees and cancellation follow-ups before repair."
                )
            if values["unvalued_fees"]:
                raise ExecutionGuard(
                    f"Approve other-asset fee prices for run {identity[:8]} before repairing its basis."
                )
            fill_ids = {row["id"] for row in values["_native_fills"]}
            if seen_fills & fill_ids:
                raise ExecutionGuard("A native fill is linked to more than one run in this handoff family.")
            seen_fills.update(fill_ids)
            approved, proposed = values["_previous_sale_funding"], values["_sale_funding"]
            if approved != proposed:
                has_correction = True
                funding_updates[identity] = proposed
                reservation_changes.append((approved, proposed))
                funding_changes.extend(
                    {**row, "status": "approved"}
                    for fill_id, row in proposed.items()
                    if approved.get(fill_id) != row
                )
                funding_changes.extend(
                    {**row, "status": "retired"}
                    for fill_id, row in approved.items()
                    if fill_id not in proposed
                )
            summaries.append(
                {
                    "job_id": identity,
                    "symbol": job["parameters"]["symbol"],
                    "status": job["status"],
                    "quantity": values["quantity"],
                    "entry_cost": values["entry_cost"],
                    "realized_pnl": values["realized_pnl"],
                }
            )
            inputs.append(
                {
                    "job": identity,
                    "status": job["status"],
                    "capital": job["parameters"]["capital"],
                    "orders": ledger.pin(db, job),
                    "funding_version": values["_sale_funding_version"],
                }
            )
            adjustments.extend(
                {
                    "event_id": event["id"],
                    "job_id": identity,
                    "action": event["action"],
                    "previous_cost_basis": originals[event["id"]]["cost_basis"],
                    "previous_quantity": originals[event["id"]]["quantity"],
                    "previous_reference_value": originals[event["id"]]["reference_value"],
                    "previous_repair_id": event.get("repair_id"),
                    "cost_basis": event["cost_basis"],
                    "quantity": event["quantity"],
                    "reference_value": event["reference_value"],
                    "pins": event["pins"],
                }
                for event in receipts
            )
        funding_review.check_assertions()
        acquisitions.check_repair(reservation_changes)
        if not has_correction:
            raise ExecutionGuard("This handoff family has no corrected source evidence to review.")
        pending = any(row["missing_basis"] for row in funding_review.required)
        review_id = (
            ledger.digest(
                [
                    selected["id"],
                    allow_quantity_changes,
                    repair_releases,
                    review_sale_funding,
                    inputs,
                    adjustments,
                    summaries,
                    funding_updates,
                ]
            )
            if not pending
            else None
        )
        verb = (
            "CONFIRM SALE FUNDING"
            if review_sale_funding
            else "REPAIR RELEASES"
            if repair_releases
            else "REPAIR QUANTITIES"
            if allow_quantity_changes
            else "REPAIR"
        )
        return {
            "id": review_id,
            "allow_quantity_changes": allow_quantity_changes,
            "repair_releases": repair_releases,
            "review_sale_funding": review_sale_funding,
            "job_id": selected["id"],
            "symbol": selected["parameters"]["symbol"],
            "runs": [] if pending else summaries,
            "adjustments": [] if pending else adjustments,
            "funding_requirements": funding_review.required,
            "funding_changes": [] if pending else funding_changes,
            "funding_updates": funding_updates,
            "confirmation": f"{verb} {selected['parameters']['symbol']} {review_id[:8]}"
            if review_id
            else None,
        }

    @staticmethod
    def _public(review):
        public = {key: value for key, value in review.items() if key != "funding_updates"}
        for key, hidden_key in (
            ("adjustments", "pins"),
            ("funding_requirements", "proof"),
            ("funding_changes", "proof"),
        ):
            public[key] = [
                {field: value for field, value in row.items() if field != hidden_key}
                for row in review.get(key, [])
            ]
        for row in public["funding_changes"]:
            if source := row.get("acquisition"):
                row["acquisition"] = {
                    key: source[key] for key in ("fill_id", "trade_id", "order_id", "origin", "timestamp_ms")
                }
        return public

    def preview(
        self,
        identity,
        *,
        allow_quantity_changes=False,
        repair_releases=False,
        review_sale_funding=False,
        sale_funding=(),
    ):
        """Preview exact ledger changes and any sale funding facts still needed."""
        with self.store.db() as db:
            db.execute("BEGIN")
            return self._public(
                self._preview(
                    db,
                    self.runner.ownership._job(identity, db),
                    allow_quantity_changes=allow_quantity_changes,
                    repair_releases=repair_releases,
                    review_sale_funding=review_sale_funding,
                    sale_funding=sale_funding,
                )
            )

    def receipt(self, identity, review_id):
        """Read immutable evidence through any affected run in the family."""
        with self.store.db() as db:
            row = db.execute(
                "SELECT payload FROM strategy_ownership_repairs WHERE id=?", (review_id,)
            ).fetchone()
            review = json.loads(row[0]) if row else None
            if not review or not any(run["job_id"] == identity for run in review["runs"]):
                raise LookupError("Ownership repair receipt not found.")
            return self._public(review)

    def approve(
        self,
        identity,
        review_id,
        confirmation,
        *,
        allow_quantity_changes=False,
        repair_releases=False,
        review_sale_funding=False,
        sale_funding=(),
    ):
        """Recompute the exact review and commit superseding values plus audit together."""
        with self.runner.lock, self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT payload FROM strategy_ownership_repairs WHERE id=?", (review_id,)
            ).fetchone()
            if previous:
                review = json.loads(previous[0])
                if (
                    review["job_id"] != identity
                    or confirmation != review["confirmation"]
                    or review.get("allow_quantity_changes", False) != allow_quantity_changes
                    or review.get("repair_releases", False) != repair_releases
                    or review.get("review_sale_funding", False) != review_sale_funding
                ):
                    raise ExecutionGuard("The repair approval does not match this review.")
                return self._public(review)
            review = self._preview(
                db,
                self.runner.ownership._job(identity, db),
                allow_quantity_changes=allow_quantity_changes,
                repair_releases=repair_releases,
                review_sale_funding=review_sale_funding,
                sale_funding=sale_funding,
            )
            if not review["id"] or review_id != review["id"] or confirmation != review["confirmation"]:
                raise ExecutionGuard(
                    "Repair evidence or confirmation changed. Review the current proposal again."
                )
            stamp = datetime.now(UTC).isoformat()
            review["approved_at"] = stamp
            for item in review["adjustments"]:
                adjustment = {
                    key: item[key] for key in ("cost_basis", "quantity", "reference_value", "pins")
                } | {"repair_id": review_id}
                db.execute(
                    "INSERT INTO strategy_ownership_adjustments(event_id,payload) VALUES (?,?)",
                    (item["event_id"], json.dumps(adjustment, allow_nan=False)),
                )
            for job_id, funding in review["funding_updates"].items():
                db.execute(
                    "INSERT INTO strategy_ownership_sale_funding(job_id,repair_id,payload) VALUES (?,?,?)",
                    (job_id, review_id, json.dumps(funding, allow_nan=False)),
                )
            db.execute(
                "INSERT INTO strategy_ownership_repairs VALUES (?,?)",
                (review_id, json.dumps(review, allow_nan=False)),
            )
            for row in review["runs"]:
                job = self.runner.ownership._job(row["job_id"], db)
                event = self.runner.host._event(
                    job,
                    "OWNERSHIP_REPAIR",
                    "Approved historical sale funding and ownership corrections."
                    if review_sale_funding
                    else "Approved corrected ownership releases, quantities and basis."
                    if repair_releases
                    else "Approved corrected ownership quantities and basis across the handoff family."
                    if allow_quantity_changes
                    else "Approved corrected ownership basis across the handoff family.",
                    ownership_repair_id=review_id,
                )
                db.execute(
                    "INSERT INTO strategy_events(job_id,payload) VALUES (?,?)",
                    (row["job_id"], json.dumps(event, allow_nan=False)),
                )
            return self._public(review)
