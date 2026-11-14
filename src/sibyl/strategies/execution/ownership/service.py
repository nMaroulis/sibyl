"""On-demand exchange checks and reviewed local ownership changes.

No operation here submits an order or infers which strategy a manual trade belongs
to. A fresh balance bounds adoption, immutable receipts carry asserted/carryover
basis, and the submission worker remains independently authorized. Snapshots are
point-in-time observations, not native reservations or complete wallet accounting.
"""

import json
import math
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sibyl.strategies.execution.accounting import project
from sibyl.strategies.execution.cancellation import pending_evidence
from sibyl.strategies.execution.contracts import ExecutionGuard
from sibyl.strategies.execution.ownership import ledger
from sibyl.strategies.execution.ownership.inspection import amount, observe


def now():
    return datetime.now(UTC).isoformat()


class PositionOwnership:
    """Serialize attribution reviews with strategy orders and final SQLite admission."""

    def __init__(self, runner):
        self.runner, self.store = runner, runner.store
        self.journal, self.market = runner.journal, runner.market
        with self.store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS strategy_position_checks(job_id TEXT PRIMARY KEY,payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS strategy_ownership_reviews(id TEXT PRIMARY KEY,payload TEXT NOT NULL);
            """)

    def _job(self, identity, db):
        row = db.execute("SELECT payload FROM strategy_jobs WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise LookupError("Strategy not found.")
        job = json.loads(row[0])
        if job.get("mode") != "exchange":
            raise ExecutionGuard("Ownership review applies only to exchange strategies.")
        return job

    def _credential_version(self, db, identity):
        row = db.execute("SELECT credentials FROM connections WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise ExecutionGuard("The strategy account is no longer connected.")
        import hashlib

        return hashlib.sha256(row[0]).hexdigest()

    def _values(self, job, db):
        return {**job, **project(job, self.runner.trading, db=db)}

    def _rows(self, job, db):
        base = job["parameters"]["symbol"].split("/")[0]
        candidates = [
            json.loads(row[0])
            for row in db.execute(
                "SELECT payload FROM strategy_jobs WHERE json_extract(payload,'$.mode')='exchange' "
                "AND json_extract(payload,'$.connection_id')=? ORDER BY id LIMIT 101",
                (job["connection_id"],),
            )
        ]
        if len(candidates) > 100:
            raise ExecutionGuard("Position checks support at most 100 retained runs per account.")
        return [
            self._values(row, db) for row in candidates if row["parameters"]["symbol"].split("/")[0] == base
        ]

    def _evidence(self, job, db):
        return ledger.digest(
            {
                "credential_version": self._credential_version(db, job["connection_id"]),
                "runs": [
                    {
                        "scope": ledger.scope(row),
                        "status": row["status"],
                        "pin": ledger.pin(db, row),
                        "events": [e["id"] for e in ledger.events(db, row["id"])],
                        "quantity": row["quantity"],
                        "basis": row["entry_cost"],
                        "incomplete": row["accounting_incomplete"],
                        "unresolved": row["unresolved_orders"],
                    }
                    for row in self._rows(job, db)
                ],
            }
        )

    @staticmethod
    def _settled(job, db):
        """Allow local changes only with settled, complete native and ownership evidence."""
        if job["ownership_event_count"] >= 100:
            raise ExecutionGuard(
                "This run reached its 100 ownership-receipt limit. Review a separate native exit instead."
            )
        if job["status"] == "running":
            raise ExecutionGuard("Pause or stop the strategy before changing its recorded ownership.")
        if job["unresolved_orders"] or pending_evidence(db, job["id"]):
            raise ExecutionGuard(
                "Resolve outstanding orders, native fills and late cancellation checks first."
            )
        if job["accounting_incomplete"] or job["unvalued_fees"]:
            raise ExecutionGuard("Reconcile complete costs, fees and any stale ownership evidence first.")

    def state(self, identity):
        """Read the last explicit balance check and ownership receipts; no provider call."""
        with self.store.db() as db:
            db.execute("BEGIN")
            job = self._values(self._job(identity, db), db)
            check = db.execute(
                "SELECT payload FROM strategy_position_checks WHERE job_id=?", (identity,)
            ).fetchone()
            latest = json.loads(check[0]) if check else None
            if latest:
                latest["current"] = latest.pop("evidence") == self._evidence(job, db)
            return {
                "job_id": identity,
                "symbol": job["parameters"]["symbol"],
                "quantity": job["quantity"],
                "entry_cost": job["entry_cost"],
                "net_reference_flow": job["ownership_net_value"],
                "stale": job["ownership_stale"],
                "history": job["ownership_events"],
                "event_count": job["ownership_event_count"],
                "check": latest,
            }

    def inspect(self, identity):
        """Fetch actual balance/book once and compare all same-account base-asset owners."""
        with self.runner.lock:
            with self.store.db() as db:
                db.execute("BEGIN")
                job = self._values(self._job(identity, db), db)
                evidence = self._evidence(job, db)
            observed = observe(self.runner, job)
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                if evidence != self._evidence(job, db):
                    raise ExecutionGuard("Ownership changed during the exchange read. Check again.")
                rows = self._rows(job, db)
                owned = math.fsum(row["quantity"] for row in rows)
                unknown = any(
                    row["accounting_incomplete"] or row["unvalued_fees"] or row["unresolved_orders"]
                    for row in rows
                )
                base = job["parameters"]["symbol"].split("/")[0]
                manual = [
                    json.loads(row[0])
                    for row in db.execute(
                        "SELECT f.payload FROM account_fills f WHERE f.account_id=? AND f.symbol LIKE ? "
                        "AND NOT EXISTS (SELECT 1 FROM exchange_orders o WHERE json_extract(o.payload,'$.request.connection_id')=f.account_id "
                        "AND json_extract(o.payload,'$.request.symbol')=f.symbol AND json_extract(o.payload,'$.exchange_order_id')=json_extract(f.payload,'$.order_id') "
                        "AND json_extract(o.payload,'$.strategy_job_id') IS NOT NULL) ORDER BY f.timestamp_ms DESC,f.id DESC LIMIT 20",
                        (job["connection_id"], base + "/%"),
                    )
                ]
                result = {
                    **observed,
                    "evidence": evidence,
                    "strategy_owned": owned,
                    "unassigned": max(0, observed["total"] - owned),
                    "shortfall": max(0, owned - observed["total"]),
                    "coverage_incomplete": bool(unknown),
                    "owners": [
                        {
                            "id": r["id"],
                            "symbol": r["parameters"]["symbol"],
                            "quantity": r["quantity"],
                            "status": r["status"],
                        }
                        for r in rows
                    ],
                    "unattributed_fills": [
                        {k: r.get(k) for k in ("id", "created_at", "symbol", "side", "quantity", "price")}
                        for r in manual
                    ],
                }
                db.execute(
                    "INSERT INTO strategy_position_checks VALUES(?,?) ON CONFLICT(job_id) DO UPDATE SET payload=excluded.payload",
                    (identity, json.dumps(result, allow_nan=False)),
                )
            return self.state(identity)

    def preview(self, identity, request):
        """Review local adoption/release from fresh native facts without placing any order."""
        with self.runner.lock:
            self.inspect(identity)
            with self.store.db() as db:
                db.execute("BEGIN")
                job = self._values(self._job(identity, db), db)
                self._settled(job, db)
                check = json.loads(
                    db.execute(
                        "SELECT payload FROM strategy_position_checks WHERE job_id=?", (identity,)
                    ).fetchone()[0]
                )
                if check["coverage_incomplete"]:
                    raise ExecutionGuard(
                        "Reconcile all same-account base-asset strategy owners before attribution."
                    )
                if request.action == "adopt":
                    if job["status"] != "paused":
                        raise ExecutionGuard(
                            "Adoption requires a paused, nonterminal run. A stopped run can hand off to a new run."
                        )
                    available = min(check["unassigned"], check["free"])
                    if request.quantity > available + 1e-10:
                        raise ExecutionGuard(
                            "Adoption exceeds free, unassigned units after all strategy owners are counted."
                        )
                    basis = request.cost_basis
                else:
                    if job["status"] not in {"stopped", "completed"}:
                        raise ExecutionGuard(
                            "Stop the run before releasing ownership to unmanaged account holdings."
                        )
                    if job["quantity"] <= 1e-12 or request.quantity > job["quantity"] + 1e-10:
                        raise ExecutionGuard("Release exceeds this run's recorded units.")
                    basis = job["entry_cost"] * min(1, request.quantity / job["quantity"])
                review = {
                    "id": uuid4().hex,
                    "job_id": identity,
                    "request": request.model_dump(),
                    "cost_basis": basis,
                    "check": check,
                    "created_at": now(),
                    "expires_at": (datetime.now(UTC) + timedelta(seconds=60)).isoformat(),
                    "confirmation": f"{request.action.upper()} {job['parameters']['symbol']} {identity[:8]}",
                }
            with self.store.db() as db:
                db.execute(
                    "INSERT INTO strategy_ownership_reviews VALUES(?,?)", (review["id"], json.dumps(review))
                )
            return self._public_review(review)

    @staticmethod
    def _public_review(review):
        return {k: v for k, v in review.items() if k != "check"} | {
            "reference_bid": review["check"]["reference_bid"],
            "native_total": review["check"]["total"],
            "native_free": review["check"]["free"],
        }

    def _event(self, job, action, quantity, basis, mark, db, *, note, peer_id=None, pins=None):
        return {
            "id": uuid4().hex,
            "job_id": job["id"],
            "action": action,
            "quantity": quantity,
            "cost_basis": basis,
            "reference_value": quantity * mark,
            "created_at": now(),
            "note": note,
            "peer_id": peer_id,
            "after_fills": [f["id"] for f in job["_native_fills"]],
            "pins": pins if pins is not None else ledger.dependencies(db, job),
        }

    def _save(self, db, event):
        ledger.append(db, event)
        db.execute(
            "INSERT INTO strategy_events(job_id,payload) VALUES(?,?)",
            (
                event["job_id"],
                json.dumps(
                    {
                        "timestamp": event["created_at"],
                        "action": "OWNERSHIP",
                        "kind": "ownership",
                        "reason": event["note"],
                        "quantity": event["quantity"],
                        "ownership_action": event["action"],
                        "ownership_event_id": event["id"],
                        "ownership_peer": event["peer_id"],
                    }
                ),
            ),
        )
        # Never keep pre-attribution metrics as if they covered an unchanged capital base.
        job = self._job(event["job_id"], db)
        job.update(statistics_complete=False)
        job.pop("metrics", None)
        db.execute("UPDATE strategy_jobs SET payload=? WHERE id=?", (json.dumps(job), job["id"]))

    def confirm(self, identity, confirmation):
        """Commit one exact local receipt once, rechecking fresh balances and pinned evidence."""
        with self.runner.lock:
            with self.store.db() as db:
                row = db.execute(
                    "SELECT payload FROM strategy_ownership_reviews WHERE id=?", (identity,)
                ).fetchone()
            if not row:
                raise LookupError("Ownership review not found.")
            review = json.loads(row[0])
            if confirmation != review["confirmation"]:
                raise ExecutionGuard(
                    "Type " + review["confirmation"] + " to approve this local ownership change."
                )
            if review.get("event_id"):
                return self.state(review["job_id"])
            if datetime.now(UTC) > datetime.fromisoformat(review["expires_at"]):
                raise ExecutionGuard("Ownership review expired. Review fresh account evidence.")
            with self.store.db() as db:
                job = self._values(self._job(review["job_id"], db), db)
            delta = review["request"]["quantity"] * (1 if review["request"]["action"] == "adopt" else -1)
            fresh = observe(self.runner, {**job, "quantity": max(0, job["quantity"] + delta)})
            old = review["check"]
            if (
                any(abs(fresh[k] - old[k]) > max(1e-10, old[k] * 1e-8) for k in ("total", "free"))
                or abs(fresh["reference_bid"] / old["reference_bid"] - 1) > 0.005
            ):
                raise ExecutionGuard("Account balances or reference price changed. Review ownership again.")
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                job = self._values(self._job(review["job_id"], db), db)
                self._settled(job, db)
                if datetime.now(UTC) > datetime.fromisoformat(review["expires_at"]):
                    raise ExecutionGuard("Ownership review expired during the native read. Review again.")
                if review["check"]["evidence"] != self._evidence(job, db):
                    raise ExecutionGuard("Native fill, account or ownership evidence changed. Review again.")
                direction = 1 if review["request"]["action"] == "adopt" else -1
                event = self._event(
                    job,
                    review["request"]["action"],
                    direction * review["request"]["quantity"],
                    direction * review["cost_basis"],
                    old["reference_bid"],
                    db,
                    note=review["request"]["note"],
                )
                self._save(db, event)
                review["event_id"] = event["id"]
                # Attribution moves no native funds. Reuse this confirmation's fresh
                # balance read with the now-committed local owner projection.
                rows = self._rows(job, db)
                owned = math.fsum(row["quantity"] for row in rows)
                checked = {
                    **old,
                    **fresh,
                    "strategy_owned": owned,
                    "unassigned": max(0, fresh["total"] - owned),
                    "shortfall": max(0, owned - fresh["total"]),
                    "evidence": self._evidence(job, db),
                    "owners": [
                        {
                            "id": row["id"],
                            "symbol": row["parameters"]["symbol"],
                            "quantity": row["quantity"],
                            "status": row["status"],
                        }
                        for row in rows
                    ],
                }
                db.execute(
                    "INSERT INTO strategy_position_checks VALUES(?,?) ON CONFLICT(job_id) DO UPDATE SET payload=excluded.payload",
                    (job["id"], json.dumps(checked, allow_nan=False)),
                )
                db.execute(
                    "UPDATE strategy_ownership_reviews SET payload=? WHERE id=?",
                    (json.dumps(review), identity),
                )
            self.journal.save(self.runner._project(self.journal.job(job["id"])))
            return self.state(job["id"])

    def sources(self):
        """List locally settled handoff candidates without contacting a provider."""
        result = []
        with self.store.db() as db:
            db.execute("BEGIN")
            for snapshot in self.runner.jobs():
                if snapshot["status"] not in {"stopped", "completed"}:
                    continue
                try:
                    value = self.source(
                        snapshot["id"], snapshot["connection_id"], snapshot["parameters"]["symbol"], db
                    )
                except ExecutionGuard:
                    continue
                result.append(
                    {
                        "id": value["id"],
                        "connection_id": value["connection_id"],
                        "symbol": value["parameters"]["symbol"],
                        "quantity": value["quantity"],
                        "cost_basis": value["entry_cost"],
                    }
                )
        return result

    def source(self, identity, connection_id, symbol, db):
        """Require one terminal, settled exact-account/pair source for a new-run handoff."""
        source = self._values(self._job(identity, db), db)
        self._settled(source, db)
        if (
            source["status"] not in {"stopped", "completed"}
            or source["connection_id"] != connection_id
            or source["parameters"]["symbol"] != symbol
            or source["quantity"] <= 1e-12
        ):
            raise ExecutionGuard(
                "Choose a stopped/completed owner with retained units on this exact account and pair."
            )
        return source

    def handoff(self, db, source, target, mark):
        """Atomically carry all remaining units/basis to a newly approved run; no cash moves."""
        pins = ledger.dependencies(db, source)
        out = self._event(
            source,
            "handoff_out",
            -source["quantity"],
            -source["entry_cost"],
            mark,
            db,
            note="Reviewed handoff to a new strategy; no exchange trade.",
            peer_id=target["id"],
            pins=pins,
        )
        incoming = self._event(
            {**target, "_native_fills": []},
            "handoff_in",
            source["quantity"],
            source["entry_cost"],
            mark,
            db,
            note="Carried original basis from the stopped source run; no exchange trade.",
            peer_id=source["id"],
            pins=pins,
        )
        self._save(db, out)
        self._save(db, incoming)

    def needs_backing(self, job, db=None):
        """Avoid extra private reads for accounts/base assets without attribution receipts."""
        if db is None:
            with self.store.db() as connection:
                return self.needs_backing(job, connection)
        return (
            db.execute(
                "SELECT 1 FROM strategy_ownership_events e JOIN strategy_jobs j ON j.id=e.job_id "
                "WHERE json_extract(j.payload,'$.connection_id')=? "
                "AND substr(json_extract(j.payload,'$.parameters.symbol'),1,instr(json_extract(j.payload,'$.parameters.symbol'),'/')-1)=? LIMIT 1",
                (job["connection_id"], job["parameters"]["symbol"].split("/")[0]),
            ).fetchone()
            is not None
        )

    def require_backed(self, job, balance, db=None):
        """Block execution when observed account units cannot back attributed strategy owners."""
        if db is None:
            with self.store.db() as connection:
                connection.execute("BEGIN")
                return self.require_backed(job, balance, connection)
        if not self.needs_backing(job, db):
            return
        rows = self._rows(job, db)
        base = job["parameters"]["symbol"].split("/")[0]
        total = amount(balance, "total", base)
        if any(row["accounting_incomplete"] for row in rows) or math.fsum(
            row["quantity"] for row in rows
        ) > total + max(1e-10, total * 1e-8):
            raise ExecutionGuard(
                "Account units no longer back attributed strategy ownership. Pause and review Position ownership."
            )
