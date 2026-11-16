"""Cash-flow-adjusted lifetime estimates using retained native evidence and exact-market marks."""

import json
import math
from datetime import UTC, datetime
from itertools import chain

from sibyl.market_data.archive import milliseconds
from sibyl.services.portfolio.returns.calculation import dietz
from sibyl.strategies.execution.accounting import project
from sibyl.strategies.execution.cancellation import pending_evidence
from sibyl.strategies.execution.contracts import ExecutionGuard
from sibyl.strategies.execution.fees import price_unreviewed
from sibyl.strategies.execution.ownership.ledger import events
from sibyl.strategies.execution.venue import order_book

TERMINAL = {"stopped", "completed"}


def read_job(db, identity):
    """Load the saved exchange run within the caller's snapshot."""
    row = db.execute("SELECT payload FROM strategy_jobs WHERE id=?", (identity,)).fetchone()
    if row is None:
        raise LookupError("Strategy not found.")
    job = json.loads(row[0])
    if job.get("mode") != "exchange":
        raise ExecutionGuard("This report applies to exchange strategies.")
    return job


def economics(db, job, trading):
    """Collect current observed fills and attributed capital without using cached equity."""
    state = project(job, trading, db=db)
    receipts = events(db, job["id"])
    if state["unresolved_orders"] or pending_evidence(db, job["id"]):
        problem = "Resolve open or uncertain orders, fill reconciliation and cancellation follow-ups."
    elif state["ownership_stale"]:
        problem = "Ownership evidence changed. Review the affected receipts."
    elif state["accounting_incomplete"]:
        problem = "Native quantities, costs or reported fees are incomplete."
    else:
        problem = None
    return state, receipts, problem


def archive_blocker(job, state, problem):
    """Use native execution readiness even when the report can estimate foreign fees."""
    if job["status"] not in TERMINAL:
        return "Archive requires a stopped or completed run."
    if state["quantity"] > 0:
        return "This run still owns exchange units."
    if problem or state["unvalued_fees"]:
        return "Archive requires settled evidence in the execution ledger."
    return None


def third_currency_fees(db, job, entries):
    """Use approved marks where present and show estimates for remaining fills."""
    pending = [entry for entry in entries if not entry["receipt"]]
    estimates = {row["fill_id"]: row for row in price_unreviewed(db, job, pending)}
    evidence = [
        {
            **row,
            "fill_id": entry["fill_id"],
            "timestamp_ms": entry["timestamp_ms"],
            "approved": bool(entry["receipt"]),
        }
        for entry in entries
        for row in (entry["receipt"] or estimates[entry["fill_id"]])["rows"]
        if row["quote_fee"] is not None
    ]
    missing = sum(len(entry["amounts"]) for entry in entries) - len(evidence)
    try:
        total = math.fsum(entry["quote_fee"] for entry in evidence)
    except OverflowError:
        total = math.inf
    return total, evidence[-10:], missing


class StrategyPerformance:
    """Keep lifetime valuation and archival controls separate from execution admission."""

    def __init__(self, runner):
        self.runner = runner
        self.store = runner.store
        with self.store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS strategy_performance_marks (job_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )

    @staticmethod
    def _mark(db, identity):
        manual = db.execute(
            "SELECT payload FROM strategy_performance_marks WHERE job_id=?", (identity,)
        ).fetchone()
        worker = db.execute(
            "SELECT payload FROM strategy_observations WHERE job_id=? ORDER BY id DESC LIMIT 1", (identity,)
        ).fetchone()
        sources = []
        if worker:
            row = json.loads(worker[0])
            sources.append({"as_of": row["timestamp"], "price": row["price"], "kind": "worker_midpoint"})
        if manual:
            sources.append(json.loads(manual[0]))
        return max(sources, key=lambda row: milliseconds(row["as_of"]), default=None)

    def report(self, identity):
        """Read a single local snapshot. Incomplete inputs yield a reason and no return."""
        with self.store.db() as db:
            db.execute("BEGIN")
            job = read_job(db, identity)
            mark = self._mark(db, identity)
            status = dict(
                job_id=identity,
                quote=job["parameters"]["symbol"].split("/")[1],
                opening_at=job["created_at"],
                archived_at=job.get("archived_at"),
                mark=mark,
                method="Modified Dietz",
                metrics=None,
                fee_valuation=None,
                reason=None,
                flows=[],
                flow_count=0,
                archive_blocker=None,
            )
            try:
                state, receipts, problem = economics(db, job, self.runner.trading)
            except ExecutionGuard as exc:
                return {**status, "reason": str(exc), "archive_blocker": str(exc)}
            status["archive_blocker"] = archive_blocker(job, state, problem)
            fee_total = 0.0
            if not problem:
                try:
                    fee_total, evidence, missing = third_currency_fees(db, job, state["_foreign_fees"])
                except ValueError as exc:
                    problem = str(exc)
                else:
                    if evidence or missing:
                        status["fee_valuation"] = {
                            "source": job["source"],
                            "environment": job["environment"],
                            "quote_total": fee_total if not missing and math.isfinite(fee_total) else None,
                            "missing_count": missing,
                            "pending_count": sum(not entry["receipt"] for entry in state["_foreign_fees"]),
                            "recent": evidence,
                        }
                    if missing or not math.isfinite(fee_total):
                        problem = "Historical fee values are incomplete on the run's exact source."
        flat = state["quantity"] == 0
        opened = milliseconds(job["created_at"])
        flows = [
            {
                "timestamp_ms": milliseconds(e["created_at"]),
                "value": e["reference_value"],
                "action": e["action"],
            }
            for e in receipts
        ]
        status["flows"] = flows[-100:]
        status["flow_count"] = len(flows)
        if problem:
            return {**status, "reason": problem}
        if any(flow["timestamp_ms"] < opened for flow in flows):
            return {**status, "reason": "An ownership flow precedes the run opening."}
        latest_economics = max(
            chain(
                (milliseconds(fill["timestamp"]) for fill in state["_native_fills"]),
                (flow["timestamp_ms"] for flow in flows),
                (opened,),
            )
        )
        if flat and job["status"] in TERMINAL:
            # With no inventory, only quote cash is valued. Closing still includes
            # fills and ownership attributed after the stop.
            sampled = job.get("stopped_at") or job.get("updated_at") or job["created_at"]
            end = max(milliseconds(sampled), latest_economics)
            closing = state["cash"] - fee_total
            status["mark"] = {
                "kind": "flat_cash",
                "as_of": datetime.fromtimestamp(end / 1000, UTC).isoformat(),
                "price": None,
            }
        else:
            if not mark or not math.isfinite(mark["price"]) or mark["price"] <= 0:
                return {**status, "reason": "Refresh the exact exchange mark to value the run."}
            end = milliseconds(mark["as_of"])
            if end < latest_economics:
                return {
                    **status,
                    "reason": "The saved mark predates a fill or ownership change. Refresh the mark.",
                }
            closing = state["cash"] - fee_total + state["quantity"] * mark["price"]
        if not math.isfinite(closing):
            return {**status, "reason": "The closing valuation exceeds the supported numerical range."}
        if end <= opened:
            return {**status, "reason": "A closing valuation after the run opened is required."}
        # Handoff receipts can share the opening millisecond. Treat them as
        # opening contributions, with effectively full holding-period weight.
        start = opened - int(any(flow["timestamp_ms"] == opened for flow in flows))
        metrics = dietz(job["parameters"]["capital"], closing, start, end, flows)
        return {**status, "metrics": metrics, "reason": metrics["return_note"]}

    def refresh(self, identity):
        """Save one exact exchange book midpoint without touching the run or execution mark."""
        with self.runner.lock:
            with self.store.db() as db:
                job = read_job(db, identity)
                version = self.runner.ownership._credential_version(db, job["connection_id"])
            account = self.runner.account(job["connection_id"])
            if (account.exchange, account.sandbox) != (job["exchange"], job["sandbox"]):
                raise ExecutionGuard("The execution account environment changed.")
            symbol = job["parameters"]["symbol"]
            with self.runner.market.adapter(account) as client:
                observed = order_book(client, symbol)
            mark = {
                "kind": "reviewed_midpoint",
                "as_of": datetime.fromtimestamp(observed["observed_at"], UTC).isoformat(),
                "price": observed["price"],
                "native_book_timestamp": observed["native_book_timestamp"],
            }
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                if version != self.runner.ownership._credential_version(db, account.id):
                    raise ExecutionGuard("The execution account changed while reading the mark.")
                if not db.execute(
                    "SELECT 1 FROM active_accounts WHERE account_id=?", (account.id,)
                ).fetchone():
                    raise ExecutionGuard("The execution account was deactivated during the mark read.")
                db.execute(
                    "INSERT INTO strategy_performance_marks VALUES (?,?) "
                    "ON CONFLICT(job_id) DO UPDATE SET payload=excluded.payload",
                    (identity, json.dumps(mark, allow_nan=False)),
                )
        return self.report(identity)

    def archive(self, identity, archived):
        """Organize terminal settled flat runs while retaining all worker and audit visibility."""
        with self.runner.lock, self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            job = read_job(db, identity)
            if archived == bool(job.get("archived_at")):
                return job
            if archived:
                state, _, problem = economics(db, job, self.runner.trading)
                blocker = archive_blocker(job, state, problem)
                if blocker:
                    raise ExecutionGuard(blocker)
                job["archived_at"] = datetime.now(UTC).isoformat()
            else:
                job.pop("archived_at", None)
            event = self.runner.host._event(
                job,
                "ARCHIVE" if archived else "RESTORE",
                "Run archived with retained evidence." if archived else "Run restored to the strategy list.",
            )
            db.execute("UPDATE strategy_jobs SET payload=? WHERE id=?", (json.dumps(job), identity))
            db.execute(
                "INSERT INTO strategy_events(job_id,payload) VALUES(?,?)", (identity, json.dumps(event))
            )
        return job
