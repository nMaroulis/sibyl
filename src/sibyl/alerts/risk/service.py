"""Durable, opt-in account risk watches. Notifications cannot control execution."""

import json
import threading
import time
from datetime import UTC, datetime
from uuid import uuid4

from sibyl.alerts.contracts import AlertAction, AlertConflict
from sibyl.alerts.inbox import NotificationInbox
from sibyl.alerts.risk.conditions import assess_risk, baseline
from sibyl.alerts.risk.contracts import RiskAlertCreate, RiskAlertUpdate
from sibyl.alerts.risk.journal import RiskJournal
from sibyl.alerts.risk.observations import RiskObservations, RiskReadError
from sibyl.market_data.control import ProviderDeferred


class RiskAlerts:
    """Check one due fixed account set per tick, outside database transactions.

    Commit revalidates revision, current configuration and evidence age before
    atomically saving a sample, peak/incident state and optional inbox entry.
    This is a local single-worker polling convenience, never an execution guard.
    """

    limit = 25

    def __init__(self, market, store, *, clock=time.time):
        self.market, self.store, self.clock = market, store, clock
        self.reader = RiskObservations(market, store, clock=clock)
        self.journal = RiskJournal(store, clock=clock)
        self.inbox = NotificationInbox(store)
        self._worker = threading.Lock()
        self._closed = False

    def _stamp(self):
        return datetime.fromtimestamp(self.clock(), UTC).isoformat()

    def _capacity(self, db):
        if (
            db.execute("SELECT COUNT(*) FROM risk_alerts WHERE status!='archived'").fetchone()[0]
            >= self.limit
        ):
            raise ValueError("Keep at most 25 non-archived account risk rules. Archive an old rule first.")

    @staticmethod
    def _revision(rule, revision):
        if rule["revision"] != revision:
            raise AlertConflict("This account risk rule changed. Reopen it to review the latest settings.")

    def rules(self, include_archived=False, offset=0):
        """Read saved rules/budgets only; opening Alerts never fetches private balances."""
        if not 0 <= offset <= 1_000_000:
            raise ValueError("Choose a valid account-risk page.")
        with self.store.db() as db:
            db.execute("BEGIN")
            rows = db.execute(
                "SELECT payload FROM risk_alerts WHERE ? OR status!='archived' ORDER BY rowid DESC LIMIT 50 OFFSET ?",
                (include_archived, offset),
            ).fetchall()
            total = db.execute(
                "SELECT COUNT(*) FROM risk_alerts WHERE ? OR status!='archived'", (include_archived,)
            ).fetchone()[0]
            count = db.execute("SELECT COUNT(*) FROM risk_alerts WHERE status!='archived'").fetchone()[0]
        return dict(
            items=[json.loads(row[0]) for row in rows],
            total=total,
            count=count,
            offset=offset,
            page_size=50,
            limit=self.limit,
            check_interval_seconds=60,
            max_accounts=10,
            delivery="in_app",
            requires_running_server=True,
        )

    def create(self, request: RiskAlertCreate):
        """Arm reviewed limits for exactly these active accounts; no balance read in this method."""
        config, guard = self.reader.configuration(request.account_ids, request.source)
        now = self._stamp()
        rule = dict(
            id=uuid4().hex,
            **request.model_dump(),
            **config,
            status="armed",
            revision=1,
            cycle=0,
            notifications=0,
            created_at=now,
            updated_at=now,
            armed_at=now,
            next_check=0,
        )
        baseline(rule)
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._capacity(db)
            # Selection may change after initial validation; never expand the fixed set.
            self.reader.current(rule, guard, db)
            db.execute("INSERT INTO risk_alerts VALUES(?,?,?,?)", (rule["id"], "armed", 0, json.dumps(rule)))
        return rule

    def edit(self, identity: str, request: RiskAlertUpdate):
        """Save reviewed settings paused; validate outside the write transaction and recheck revision."""
        with self.store.db() as db:
            previous = self.journal.read(db, identity)
        self._revision(previous, request.revision)
        config = {key: previous[key] for key in ("accounts", "environment", "source_info")}
        guard = None
        if (request.account_ids, request.source) != (previous["account_ids"], previous["source"]):
            config, guard = self.reader.configuration(request.account_ids, request.source)
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rule = self.journal.read(db, identity)
            self._revision(rule, request.revision)
            if rule["status"] == "archived":
                raise ValueError("Restore this rule before editing it.")
            rule.update(request.model_dump(exclude={"revision"}))
            if guard is not None:
                self.reader.current(rule, guard, db)
            rule.update(
                **config,
                status="paused",
                revision=rule["revision"] + 1,
                updated_at=self._stamp(),
                next_check=0,
            )
            baseline(rule)
            self.journal.write(db, rule)
        return rule

    def change(self, identity: str, request: AlertAction):
        """Pause/archive stop reads. Resume resets the observation window, including its peak."""
        config, guard = None, None
        with self.store.db() as db:
            previous = self.journal.read(db, identity)
        self._revision(previous, request.revision)
        if request.action == "arm" and previous["status"] != "armed":
            config, guard = self.reader.configuration(previous["account_ids"], previous["source"])
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rule = self.journal.read(db, identity)
            self._revision(rule, request.revision)
            target = {"pause": "paused", "arm": "armed", "archive": "archived", "restore": "paused"}[
                request.action
            ]
            if request.action == "restore":
                if rule["status"] != "archived":
                    return rule
                self._capacity(db)
            elif request.action != "archive" and rule["status"] == "archived":
                raise ValueError("Restore this rule before resuming it.")
            if rule["status"] == target:
                return rule
            if request.action == "arm":
                self.reader.current(rule, guard, db)
                rule.update(config)
                baseline(rule)
                rule["armed_at"] = self._stamp()
            rule.update(status=target, revision=rule["revision"] + 1, next_check=0, updated_at=self._stamp())
            self.journal.write(db, rule)
        return rule

    def _notify(self, db, rule, sample, action):
        rule.update(
            cycle=rule["cycle"] + 1, notifications=rule["notifications"] + 1, last_notified_at=self._stamp()
        )
        payload = dict(
            kind="risk",
            rule_id=rule["id"],
            rule_revision=rule["revision"],
            label=rule["label"],
            source=rule["source"],
            source_label=rule["source_info"]["source_label"],
            environment=rule["environment"],
            pricing_environment=rule["source_info"]["environment"],
            accounts=rule["accounts"],
            account_ids=rule["account_ids"],
            metric=rule["metric"],
            asset=rule["asset"],
            threshold=rule["threshold"],
            reset_threshold=rule["reset_threshold"],
            action=action,
            metric_value=sample["metric_value"],
            total=sample["total"],
            currency=sample["currency"],
            peak=sample["peak"],
            peak_at=sample["peak_at"],
            observed_at=sample["as_of"],
            sample_id=rule["last_sample_id"],
            cycle=rule["cycle"],
        )
        db.execute(
            "INSERT INTO alert_notifications VALUES(?,?,?,?,NULL,?)",
            (
                uuid4().hex,
                rule["id"],
                rule["cycle"],
                rule["last_notified_at"],
                json.dumps(payload, allow_nan=False),
            ),
        )

    def _evaluate(self, identity):
        with self.store.db() as db:
            rule = self.journal.read(db, identity)
        if rule["status"] != "armed":
            return rule
        deferred, error, sample, guard = None, None, None, None
        try:
            sample, guard = self.reader.read(rule)
        except ProviderDeferred as exc:
            deferred, error = exc, "Reads are queued or cooling down; no risk assessment was recorded."
        except RiskReadError as exc:
            error = str(exc)
        except Exception:
            error = "A selected account or reference feed is unavailable; no risk assessment was recorded."
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.journal.read(db, identity)
            if (
                current["status"] != "armed"
                or current["revision"] != rule["revision"]
                or current["checks"] != rule["checks"]
            ):
                return current
            if sample is not None:
                try:
                    self.reader.current(current, guard, db)
                    self.reader.fresh(sample)
                    previous = current["last_observation"]
                    if previous and sample["as_of"] <= previous["as_of"]:
                        raise RiskReadError("Snapshot time did not advance.")
                except (ValueError, LookupError):
                    error = "Account/feed configuration or evidence freshness changed during this check; waiting for a new check."
            current.update(last_checked_at=self._stamp(), error=error, checks=current["checks"] + 1)
            if error:
                failures = min(10, current["failures"] + int(deferred is None))
                current.update(
                    failures=failures,
                    next_check=self.clock()
                    + (deferred.retry_after if deferred else min(900, 30 * 2**failures)),
                )
            else:
                action = assess_risk(current, sample, self.clock())
                sample["policy"] = {
                    key: current[key] for key in ("metric", "asset", "threshold", "reset_threshold", "label")
                }
                current["last_sample_id"] = self.journal.append(db, current, sample, self.clock())
                current.update(
                    last_observation={
                        key: sample[key]
                        for key in ("total", "currency", "metric_value", "peak", "peak_at", "as_of")
                    },
                    failures=0,
                    next_check=self.clock() + 60,
                )
                if action:
                    self._notify(db, current, sample, action)
            self.journal.write(db, current)
        return current

    def check(self, identity):
        """Request a due check without bypassing scheduling, cooldown or read backoff."""
        with self._worker:
            with self.store.db() as db:
                rule = self.journal.read(db, identity)
            if self._closed or rule["status"] != "armed" or rule["next_check"] > self.clock():
                return rule
            return self._evaluate(identity)

    def tick(self):
        """Read at most one due account set, independently of other alert workers."""
        with self._worker:
            if self._closed:
                return
            with self.store.db() as db:
                row = db.execute(
                    "SELECT id FROM risk_alerts WHERE status='armed' AND next_check<=? ORDER BY next_check,rowid LIMIT 1",
                    (self.clock(),),
                ).fetchone()
            if row:
                self._evaluate(row[0])

    def close(self):
        """Wait for the current bounded read before shared provider clients close."""
        with self._worker:
            self._closed = True
