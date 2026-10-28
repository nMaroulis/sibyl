"""Portfolio admission policy, independent of agent decisions and exchange permissions.

Provider reads happen outside SQLite writes and the strategy lifecycle lock. The
native submission boundary rebuilds ownership under its existing write transaction
using still-fresh reference prices. This serializes competing entries without a
parallel reservation ledger. No risk action submits, cancels or liquidates an order.
"""

import json

from sibyl.strategies.execution.contracts import ExecutionGuard
from sibyl.strategies.execution.controls import ControlConflict
from sibyl.strategies.execution.risk import prices
from sibyl.strategies.execution.risk.contracts import (
    RELEASE_CONFIRMATION,
    SAVE_CONFIRMATION,
    LimitPolicy,
)
from sibyl.strategies.execution.risk.ledger import MAX_RUNS, positions, totals


def load(db, environment):
    row = db.execute(
        "SELECT payload FROM strategy_portfolio_limits WHERE environment=?", (environment,)
    ).fetchone()
    if row is None:
        raise ExecutionGuard("Shared strategy controls are unavailable. No automatic order was admitted.")
    return json.loads(row[0])


def write(db, state):
    db.execute(
        "UPDATE strategy_portfolio_limits SET payload=? WHERE environment=?",
        (json.dumps(state, allow_nan=False), state["environment"]),
    )


class PortfolioLimits:
    """One explicit shared policy per production/test environment, across all accounts."""

    def __init__(self, runner):
        self.runner, self.store = runner, runner.store
        with self.store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS strategy_portfolio_limits (
                    environment TEXT PRIMARY KEY, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS strategy_limit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, environment TEXT NOT NULL, payload TEXT NOT NULL
                );
            """)
            for environment in ("production", "test"):
                state = dict(
                    environment=environment,
                    revision=0,
                    policy=LimitPolicy().model_dump(),
                    locked=False,
                    tripped_day=None,
                    period=None,
                    sample=None,
                    error=None,
                    changed_at=None,
                )
                db.execute(
                    "INSERT OR IGNORE INTO strategy_portfolio_limits VALUES(?,?)",
                    (environment, json.dumps(state)),
                )

    def state(self):
        """Read bounded local evidence only; an old assessment is explicitly stale."""
        with self.store.db() as db:
            db.execute("BEGIN")
            states = [load(db, environment) for environment in ("production", "test")]
            for state in states:
                state["history"] = [
                    {"id": row[0], **json.loads(row[1])}
                    for row in db.execute(
                        "SELECT id,payload FROM strategy_limit_events WHERE environment=? ORDER BY id DESC LIMIT 20",
                        (state["environment"],),
                    )
                ]
                # Feed fingerprints are private guards, not model-facing evidence.
                sample = state.get("sample")
                try:
                    if not sample:
                        raise ExecutionGuard("No complete assessment yet.")
                    prices.fresh(sample, prices.utcnow())
                    if sample["configuration"] != prices.configuration(db, state["policy"]["source"]):
                        raise ExecutionGuard("Reference feed configuration changed.")
                    state["fresh"] = not state["error"]
                except ExecutionGuard:
                    state["fresh"] = False
                if sample:
                    sample.pop("configuration", None)
        return {
            "currency": "USDT",
            "policies": states,
            "save_confirmation": SAVE_CONFIRMATION,
            "release_confirmation": RELEASE_CONFIRMATION,
            "assessment_max_age_seconds": prices.MAX_AGE,
            "scope": "All retained exchange strategies; production and test funds are separate. Manual trades and unrelated account holdings are excluded.",
        }

    def _pause(self, db, environment, reason):
        """Pause affected runs and invalidate unsent signal intents in the caller's transaction."""
        identities = []
        for row in db.execute(
            "SELECT payload FROM strategy_jobs WHERE json_extract(payload,'$.mode')='exchange' "
            "AND json_extract(payload,'$.environment')=? AND json_extract(payload,'$.status')='running'",
            (environment,),
        ).fetchall():
            job = json.loads(row[0])
            job.update(status="paused", error=reason, updated_at=prices.utcnow().isoformat())
            event = self.runner.host._event(job, "PAUSE", reason)
            db.execute("UPDATE strategy_jobs SET payload=? WHERE id=?", (json.dumps(job), job["id"]))
            db.execute(
                "INSERT INTO strategy_events(job_id,payload) VALUES(?,?)", (job["id"], json.dumps(event))
            )
            identities.append(job["id"])
        for row in db.execute(
            "SELECT payload FROM exchange_orders WHERE json_extract(payload,'$.origin')='strategy' "
            "AND json_extract(payload,'$.environment')=? AND json_extract(payload,'$.status')='preview' "
            "AND json_extract(payload,'$.strategy_close_review_id') IS NULL",
            (environment,),
        ).fetchall():
            intent = json.loads(row[0])
            intent.update(strategy_abandoned=True, tracking=False)
            self.runner.trading.lifecycle.write(db, intent)
        return identities

    @staticmethod
    def _audit(db, state, action, reason, paused=()):
        event = dict(
            action=action,
            timestamp=prices.utcnow().isoformat(),
            revision=state["revision"],
            reason=reason,
            paused_job_ids=list(paused),
            policy=state["policy"],
        )
        if state["sample"]:
            event["metrics"] = {
                key: state["sample"][key] for key in ("as_of", "allocated", "exposure", "daily_loss", "day")
            }
        db.execute(
            "INSERT INTO strategy_limit_events(environment,payload) VALUES(?,?)",
            (state["environment"], json.dumps(event)),
        )
        db.execute(
            "DELETE FROM strategy_limit_events WHERE environment=? AND id NOT IN "
            "(SELECT id FROM strategy_limit_events WHERE environment=? ORDER BY id DESC LIMIT 200)",
            (state["environment"], state["environment"]),
        )

    def save(self, environment, request):
        """Save deliberate limits, pause this environment's runs and retain the day's baseline."""
        if request.confirmation != SAVE_CONFIRMATION:
            raise ExecutionGuard("Type " + SAVE_CONFIRMATION + " to change shared strategy limits.")
        policy = LimitPolicy(**request.model_dump(exclude={"revision", "confirmation"})).model_dump()
        # Resolve configuration without a DB writer; this never contacts providers.
        if policy["enabled"]:
            with self.runner.market.snapshot(policy["source"]):
                metadata = self.runner.market.metadata()
                if metadata["environment"] != "production" or metadata["source"] == "demo":
                    raise ExecutionGuard("Choose an observed production reference feed, even for test funds.")
        with self.runner.lock, self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            state = load(db, environment)
            if state["revision"] != request.revision:
                raise ControlConflict("Shared limits changed. Refresh before saving.")
            if state["locked"] and not policy["enabled"]:
                raise ExecutionGuard("Release the prior day's daily-loss lock before disabling its policy.")
            if state["policy"] != policy:
                state.update(
                    policy=policy,
                    revision=state["revision"] + 1,
                    sample=None,
                    error=None,
                    changed_at=prices.utcnow().isoformat(),
                )
                reason = (
                    "Shared strategy limits changed. Review the portfolio assessment, then Resume each run."
                )
                paused = self._pause(db, environment, reason)
                self._audit(db, state, "saved", reason, paused)
                write(db, state)
        return self.state()

    def _metrics(self, db, state, sample, candidate=None):
        """Recompute actual ownership against pinned prices and the persistent daily baseline."""
        prices.fresh(sample, prices.utcnow())
        if sample["configuration"] != prices.configuration(db, state["policy"]["source"]):
            raise ExecutionGuard("Reference feed settings changed. Refresh the shared strategy assessment.")
        rows = positions(db, self.runner.trading, state["environment"])
        try:
            metrics = totals(rows, sample["rates"], candidate)
        except KeyError as error:
            raise ExecutionGuard(
                "A strategy asset changed. Refresh the shared portfolio assessment."
            ) from error
        current = {row["id"]: row["pnl"] for row in metrics["runs"]}
        day = prices.utcnow().date().isoformat()
        period = state["period"]
        if period is None:
            period = dict(day=day, started_at=sample["as_of"], baseline=current.copy(), latest=current.copy())
        elif day < period["day"]:
            raise ExecutionGuard("The UTC clock moved backwards. Shared strategy submissions are blocked.")
        elif day != period["day"]:
            # Carry the last observed P&L through midnight, including a restart gap.
            period = dict(day=day, started_at=sample["as_of"], baseline=period["latest"].copy(), latest={})
        if set(period["baseline"]) - set(current):
            raise ExecutionGuard(
                "A tracked strategy is missing. Restore its ledger before submitting orders."
            )
        for identity in current:
            period["baseline"].setdefault(identity, 0.0)
        daily_pnl = sum(value - period["baseline"][identity] for identity, value in current.items())
        period["latest"] = current
        state["period"] = period
        return {
            **sample,
            **metrics,
            "day": day,
            "period_started_at": period["started_at"],
            "daily_pnl": daily_pnl,
            "daily_loss": max(0.0, -daily_pnl),
        }

    def _record(self, db, state, sample):
        state.update(sample=sample, error=None)
        if not state["locked"] and sample["daily_loss"] >= state["policy"]["max_daily_loss"]:
            state.update(locked=True, tripped_day=sample["day"], revision=state["revision"] + 1)
            reason = (
                "Shared daily-loss limit reached. Automatic strategy orders are locked for this environment."
            )
            paused = self._pause(db, state["environment"], reason)
            self._audit(db, state, "daily_loss_locked", reason, paused)
        write(db, state)

    def require(self, environment, revision=None):
        with self.store.db() as db:
            state = load(db, environment)
        if revision is not None and state["revision"] != revision:
            raise ExecutionGuard("Shared strategy limits changed. Create a new strategy review.")
        if state["locked"]:
            raise ExecutionGuard("Shared daily-loss lock is active. Review portfolio limits in Strategies.")
        return state

    def check(self, environment, extra=None):
        """Read public conversion evidence, then commit only against the current policy and ledger."""
        with self.store.db() as db:
            db.execute("BEGIN")
            initial = load(db, environment)
            if not initial["policy"]["enabled"]:
                return initial
            config = prices.configuration(db, initial["policy"]["source"])
        started = prices.utcnow()
        try:
            with self.store.db() as db:
                db.execute("BEGIN")
                rows = positions(db, self.runner.trading, environment)
            if extra:
                rows.append(dict(symbol=extra["symbol"], retained=True))
            rates, source = prices.read(self.runner.market, initial["policy"]["source"], rows)
            sample = dict(as_of=started.isoformat(), rates=rates, source=source, configuration=config)
            with self.runner.lock, self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                state = load(db, environment)
                if state["revision"] != initial["revision"]:
                    raise ControlConflict(
                        "Shared limits changed during assessment. Refresh before trying again."
                    )
                if state["sample"] and state["sample"]["as_of"] > sample["as_of"]:
                    raise ControlConflict(
                        "A newer shared assessment already committed. Refresh the current evidence."
                    )
                sample = self._metrics(db, state, sample)
                self._record(db, state, sample)
            return state
        except ControlConflict:
            raise
        except Exception as error:
            message = (
                str(error)
                if isinstance(error, ExecutionGuard)
                else "Shared risk prices are unavailable. No automatic order is permitted."
            )
            self.unavailable(environment, initial["revision"], message)
            raise ExecutionGuard(message) from error

    def unavailable(self, environment, revision, message):
        """Fail closed without discarding the last complete sample or daily baseline."""
        with self.runner.lock, self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            state = load(db, environment)
            if state["revision"] != revision or not state["policy"]["enabled"]:
                return
            state["error"] = message
            paused = self._pause(db, environment, message)
            if paused:
                self._audit(db, state, "assessment_unavailable", message, paused)
            write(db, state)

    def review(self, connection, parameters, revision=None):
        """Check shared headroom for an added allocation; a review itself reserves nothing."""
        environment = "test" if connection.sandbox else "production"
        self.require(environment, revision)
        state = self.check(environment, extra=dict(symbol=parameters.symbol))
        if state["locked"]:
            self.require(environment)
        if state["policy"]["enabled"]:
            if len(state["sample"]["runs"]) >= MAX_RUNS:
                raise ExecutionGuard("This environment reached its 100 retained-run shared accounting limit.")
            rate = state["sample"]["rates"][parameters.symbol.split("/")[1]]["price"]
            if state["sample"]["allocated"] + parameters.capital * rate > state["policy"]["max_allocated"]:
                raise ExecutionGuard("This allocation exceeds the shared strategy capital limit.")
        return state["revision"]

    def admit(self, db, intent):
        """Return a refusal after persisting a possible loss trip in the native-write transaction.

        The caller must commit refusals before raising. Updating the intent to
        submitting in this same transaction makes its buy capacity visible to the
        next admission. No cached job balances or UI-supplied totals are trusted.
        """
        state = load(db, intent["environment"])
        if state["locked"]:
            return "Shared daily-loss lock is active. No automatic order was submitted."
        if state["revision"] != intent.get("strategy_risk_revision", 0):
            return "Shared strategy limits changed. Resume with a fresh assessment."
        if not state["policy"]["enabled"]:
            return None
        try:
            if state["error"] or not state["sample"]:
                raise ExecutionGuard("A complete shared strategy assessment is required before submission.")
            # Record actual P&L/exposure first; hypothetical order headroom never enters the daily sample.
            sample = self._metrics(db, state, state["sample"])
            self._record(db, state, sample)
            if state["locked"]:
                return "Shared daily-loss limit reached. No automatic order was submitted."
            projected = self._metrics(db, state, sample, candidate=intent)
            if intent["request"]["side"] == "buy" and projected["exposure"] > state["policy"]["max_exposure"]:
                return "This buy exceeds shared strategy exposure, including outstanding buys."
        except ExecutionGuard as error:
            state["error"] = str(error)
            paused = self._pause(db, state["environment"], str(error))
            if paused:
                self._audit(db, state, "assessment_unavailable", str(error), paused)
            write(db, state)
            return str(error)
        return None

    def release(self, environment, request):
        """Unlock only a previous day's breach after fresh complete evidence; preserve today's baseline."""
        if request.confirmation != RELEASE_CONFIRMATION:
            raise ExecutionGuard("Type " + RELEASE_CONFIRMATION + " to release the daily-loss lock.")
        with self.store.db() as db:
            initial = load(db, environment)
        if initial["revision"] != request.revision:
            raise ControlConflict("Shared limits changed. Refresh before releasing.")
        if not initial["locked"]:
            return self.state()
        if initial["tripped_day"] >= prices.utcnow().date().isoformat():
            raise ExecutionGuard("Today's daily-loss lock cannot be released before the next UTC day.")
        self.check(environment)
        with self.runner.lock, self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            state = load(db, environment)
            if state["revision"] != request.revision:
                raise ControlConflict("Shared limits changed. Refresh before releasing.")
            sample = self._metrics(db, state, state["sample"])
            if sample["daily_loss"] >= state["policy"]["max_daily_loss"]:
                raise ExecutionGuard("The new UTC day's observed loss also exceeds its limit.")
            state.update(locked=False, tripped_day=None, revision=state["revision"] + 1, sample=sample)
            self._audit(
                db, state, "released", "Previous UTC day's daily-loss lock released. Runs remain paused."
            )
            write(db, state)
        return self.state()
