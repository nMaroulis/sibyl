"""Approved strategy cancellations, with durable state on the owned order intent.

Deadlines are local best-effort policy, not native exchange time-in-force. The
shared cancellation pipeline persists its write boundary. A prior attempt is
only observed afterwards, including after a crash; it is never auto-retried.
"""

import json
import time
from datetime import UTC, datetime

from sibyl.services.order_lifecycle import TERMINAL
from sibyl.strategies.execution.contracts import ExecutionGuard

# Both cancellation scheduling and exit readiness use this predicate. A ledger
# correction reopens a completed check before the strategy worker next runs.
PENDING_EVIDENCE = (
    "json_extract(o.payload,'$.strategy_cancellation') IS NOT NULL AND ("
    "json_extract(o.payload,'$.strategy_cancellation.state')!='reconciled' "
    "OR COALESCE(json_extract(o.payload,'$.strategy_cancellation.terminal_checks'),0)<3 "
    "OR COALESCE(json_extract(o.payload,'$.strategy_cancellation.fill_revision'),-1)"
    "!=COALESCE(v.revision,0) "
    "OR json_extract(o.payload,'$.strategy_cancellation.terminal_observation[0]') "
    "IS NOT json_extract(o.payload,'$.status') "
    "OR json_extract(o.payload,'$.strategy_cancellation.terminal_observation[1]') "
    "IS NOT json_extract(o.payload,'$.filled') "
    "OR json_extract(o.payload,'$.strategy_cancellation.terminal_observation[2]') "
    "IS NOT json_extract(o.payload,'$.cost'))"
)
EVIDENCE_JOIN = (
    "LEFT JOIN account_order_revisions v "
    "ON v.account_id=json_extract(o.payload,'$.request.connection_id') "
    "AND v.symbol=json_extract(o.payload,'$.request.symbol') "
    "AND v.order_id=json_extract(o.payload,'$.exchange_order_id') "
)


def pending_evidence(db, identity, *, ignore=None):
    """Check dated cancellation evidence in the caller's ledger/submission snapshot."""
    return (
        db.execute(
            "SELECT 1 FROM exchange_orders o "
            + EVIDENCE_JOIN
            + "WHERE json_extract(o.payload,'$.strategy_job_id')=? "
            "AND o.id!=? AND COALESCE(json_extract(o.payload,'$.strategy_abandoned'),0)=0 "
            f"AND ({PENDING_EVIDENCE}) LIMIT 1",
            (identity, ignore or ""),
        ).fetchone()
        is not None
    )


def now():
    return datetime.now(UTC).isoformat()


class StrategyCancellations:
    """Cancel only orders owned by one explicitly approved strategy account/pair."""

    def __init__(self, runner):
        self.runner, self.trading = runner, runner.trading
        self.store, self.journal = runner.store, runner.journal

    def orders(self, identity):
        """Read outstanding local orders and unfinished cancellation observations."""
        with self.store.db() as db:
            rows = db.execute(
                "SELECT o.payload FROM exchange_orders o "
                + EVIDENCE_JOIN
                + "WHERE json_extract(o.payload,'$.strategy_job_id')=? "
                "AND COALESCE(json_extract(o.payload,'$.strategy_abandoned'),0)=0 "
                "AND (json_extract(o.payload,'$.status') NOT IN ('closed','canceled','expired','rejected') "
                f"OR ({PENDING_EVIDENCE})) ORDER BY o.rowid LIMIT 100",
                (identity,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def _allowed(self, job, *, explicit):
        """Recheck access before reads and again immediately before a native write."""
        if explicit:
            self.trading._enabled()
        else:
            self.runner.enabled(submissions=False)
        return self._readable(job)

    def _readable(self, job):
        """Read-only outcome recovery needs active account access, not order-writing flags."""
        connection = self.runner.account(job["connection_id"])
        if (connection.exchange, connection.sandbox) != (job["exchange"], job["sandbox"]):
            raise ExecutionGuard("Execution account environment changed; manage the order in Trade.")
        return connection

    def pending(self, identity):
        """Read whether this run still needs matching cancellation follow-up checks."""
        with self.store.db() as db:
            return pending_evidence(db, identity)

    def _save(self, job, intent, state, message, **details):
        """Commit progress with its journal event, retaining the shared write evidence."""
        previous = intent.get("strategy_cancellation", {})
        meta = {**previous, **details, "state": state, "message": message, "checked_at": now()}
        intent["strategy_cancellation"] = meta
        event = None
        if (state, message) != (previous.get("state"), previous.get("message")):
            event = self.runner.host._event(
                job,
                "CANCEL_" + state.upper(),
                message,
                order_id=intent["id"],
                cancel_state=state,
                expires_at=intent.get("strategy_expires_at"),
                cancellation_id=meta.get("review_id"),
            )
        with self.store.db() as db:
            self.trading.lifecycle.write(db, intent)
            if event:
                db.execute(
                    "INSERT INTO strategy_events(job_id,payload) VALUES(?,?)", (job["id"], json.dumps(event))
                )
        return intent

    def _observed(self, job, intent, *, native_check=False):
        """Require three matching native checks against unchanged fill/fee evidence."""
        if intent["status"] in TERMINAL:
            detail = self.trading.reconciliation.detail(intent["id"])
            evidence, revision = detail["reconciliation"], detail["fill_revision"]
            matched = evidence["status"] == "matched"
            previous = intent.get("strategy_cancellation", {})
            observation = [intent.get(key) for key in ("status", "filled", "cost")]
            changed = observation != previous.get("terminal_observation") or revision != previous.get(
                "fill_revision"
            )
            checks = 0 if changed or not matched else previous.get("terminal_checks", 0)
            checks = min(3, checks + int(native_check and matched))
            complete = matched and checks == 3
            return self._save(
                job,
                intent,
                "reconciled" if complete else "reconciling",
                f"Native order is {intent['status']}. "
                + (
                    "Three native status checks match the retained fills and fees; later corrections reopen these checks."
                    if complete
                    else "Retained fills match; waiting for three matching native status checks after the last execution change."
                    if matched
                    else "Waiting for native fill/fee evidence; no further strategy order is allowed."
                ),
                outcome=intent["status"],
                terminal_checks=checks,
                terminal_observation=observation,
                fill_revision=revision,
                next_check=time.time() + {0: 0, 1: 60, 2: 240}.get(checks, 30),
            )
        uncertain = intent.get("cancel_state") in {"unknown", "submitting"}
        return self._save(
            job,
            intent,
            "unknown" if uncertain else "requested",
            "Cancellation outcome is uncertain. Native status checks continue; this write is never automatically retried. Review the order in Trade."
            if uncertain
            else "Cancellation was requested. The order can still fill until the exchange confirms a terminal state.",
            next_check=time.time() + 30,
        )

    def step(self, identity):
        """Process at most one due owned order per run; recover by reading, never resending."""
        with self.runner.lock:
            job = self.journal.job(identity)
            for snapshot in self.orders(identity):
                # A later, separately reviewed closing order is not part of an
                # earlier Stop & cancel approval. Its own expiry still applies.
                closing = snapshot.get("strategy_action") == "close"
                stop = job.get("stop_cancellation")
                explicit = bool(stop) and (
                    not closing
                    or datetime.fromisoformat(snapshot["created_at"])
                    <= datetime.fromisoformat(stop["requested_at"])
                )
                due = snapshot.get("strategy_expires_at")
                expired = due and time.time() >= datetime.fromisoformat(due).timestamp()
                if not (explicit or expired or snapshot.get("strategy_cancellation")):
                    continue
                with self.trading.lifecycle.lock(snapshot["id"]):
                    with self.store.db() as db:
                        intent = self.trading.lifecycle.read(db, snapshot["id"])
                    if (
                        intent.get("strategy_job_id") != identity
                        or intent.get("origin") != "strategy"
                        or intent["request"]["connection_id"] != job["connection_id"]
                        or intent["request"]["symbol"] != job["parameters"]["symbol"]
                    ):
                        raise ExecutionGuard(
                            "Order ownership does not match this strategy; no cancellation was sent."
                        )
                    meta = intent.get("strategy_cancellation")
                    if meta and meta.get("next_check", 0) > time.time():
                        continue
                    if not meta:
                        intent["strategy_cancellation"] = {
                            "reason": "stop" if explicit else "expiry",
                            "created_at": now(),
                        }
                        intent = self._save(
                            job, intent, "queued", "This run's outstanding order is queued for cancellation."
                        )
                    if intent["status"] == "preview":
                        # The runner rechecks run state before executing any prepared intent.
                        if explicit:
                            intent.update(strategy_abandoned=True, tracking=False)
                            self._save(
                                job,
                                intent,
                                "reconciled",
                                "Prepared order abandoned without a native submission.",
                                outcome="not_submitted",
                            )
                        continue
                    try:
                        self._readable(job)
                        if intent["status"] in TERMINAL:
                            intent = self.trading.lifecycle.refresh(intent["id"])
                            self._observed(job, intent, native_check=True)
                            return
                        if intent.get("cancel_requested_at"):
                            # Shared manual/automatic attempts, including 'submitting'
                            # at process loss, all cross the same durable write boundary.
                            intent = self.trading.lifecycle.refresh(intent["id"])
                        else:
                            self._allowed(job, explicit=explicit or closing)
                            try:
                                review = self.trading.lifecycle.preview_cancel(intent["id"])
                            except ValueError:
                                with self.store.db() as db:
                                    intent = self.trading.lifecycle.read(db, intent["id"])
                                if intent["status"] in TERMINAL:
                                    self._observed(job, intent)
                                    return
                                raise
                            self._allowed(self.journal.job(identity), explicit=explicit or closing)
                            # Record which shared review was authorized, before its
                            # own durable 'submitting' transition and native write.
                            with self.store.db() as db:
                                intent = self.trading.lifecycle.read(db, intent["id"])
                            self._save(
                                job,
                                intent,
                                "queued",
                                "Fresh native order checked; cancellation is queued.",
                                review_id=review["id"],
                            )
                            intent = self.trading.lifecycle.cancel(
                                intent["id"], review["id"], review["confirmation"]
                            )
                        self._observed(job, intent)
                    except Exception:
                        with self.store.db() as db:
                            intent = self.trading.lifecycle.read(db, snapshot["id"])
                        if intent.get("cancel_requested_at"):
                            self._save(
                                job,
                                intent,
                                "unknown",
                                "Cancellation outcome needs native verification. No cancellation write will be retried automatically.",
                                next_check=time.time() + 30,
                            )
                        else:
                            failures = min(5, intent.get("strategy_cancellation", {}).get("failures", 0) + 1)
                            self._save(
                                job,
                                intent,
                                "blocked",
                                "Cancellation is waiting for active account access, server permission and a verifiable open native order. Check Trade; no write was retried.",
                                failures=failures,
                                next_check=time.time() + min(900, 30 * 2 ** (failures - 1)),
                            )
                    return
