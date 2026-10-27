"""Read-only account/budget reviews and immutable, explicitly approved run creation."""

import json
import math
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sibyl.strategies.execution.contracts import ExchangeStrategyRequest, ExecutionGuard
from sibyl.strategies.execution.venue import observation


def now():
    return datetime.now(UTC).isoformat()


class StrategyApprovals:
    """Validate a scope twice, then create exactly one job for its reviewed identity."""

    def __init__(self, runner):
        self.runner = runner
        self.host, self.store, self.market = runner.host, runner.store, runner.market
        self.journal, self.lock = runner.journal, runner.lock
        with self.store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS strategy_reviews(id TEXT PRIMARY KEY,payload TEXT NOT NULL)"
            )

    def _validate(self, request, exclude=None):
        self.runner.enabled()
        connection = self.runner.account(request.connection_id)
        params = request.parameters
        quote = params.symbol.split("/")[1]
        reserved = 0.0
        for other in self.runner.jobs():
            if other["id"] == exclude or other["connection_id"] != connection.id:
                continue
            retained = (
                other["status"] not in {"stopped", "completed"}
                or other["quantity"] > 1e-12
                or other.get("pending")
            )
            if retained and other["parameters"]["symbol"] == params.symbol:
                raise ExecutionGuard(
                    "Another retained exchange strategy owns this account/pair. Stop it and resolve its orders/position first."
                )
            if (
                other["status"] not in {"stopped", "completed"}
                and other["parameters"]["symbol"].split("/")[1] == quote
            ):
                reserved += max(0, other["cash"])
        with self.market.adapter(connection) as client:
            observed = observation(client, params)
            available = float(client.fetch_balance().get("free", {}).get(quote) or 0)
        if not math.isfinite(available) or available < params.capital + reserved:
            raise ExecutionGuard(
                f"Not enough free {quote} for this budget and the other strategy allocations. Budgets do not reserve funds at the exchange."
            )
        if observed["spread_bps"] > request.risk.max_spread_bps:
            raise ExecutionGuard("Current spread exceeds the approved strategy limit.")
        return connection, observed

    def preview(self, request: ExchangeStrategyRequest):
        """Validate account, candles, funds and policy; never create an exchange order."""
        with self.lock:
            connection, observed = self._validate(request)
            risk_revision = self.runner.portfolio_limits.review(connection, request.parameters)
            limits = next(
                state
                for state in self.runner.portfolio_limits.state()["policies"]
                if state["environment"] == ("test" if connection.sandbox else "production")
            )
            review = {
                "id": uuid4().hex,
                "control_revision": self.runner.controls.require()["revision"],
                "risk_revision": risk_revision,
                "shared_limits": {"currency": "USDT", **limits["policy"]},
                "request": request.model_dump(),
                "account": connection.label,
                "exchange": connection.exchange,
                "sandbox": connection.sandbox,
                "environment": "test" if connection.sandbox else "production",
                "confirmation": f"START {'TEST' if connection.sandbox else 'LIVE'} {request.parameters.symbol}",
                "created_at": now(),
                "expires_at": (datetime.now(UTC) + timedelta(minutes=2)).isoformat(),
                "reference_price": observed["price"],
                "execution": self.runner.options()["execution"],
            }
            with self.store.db() as db:
                db.execute("INSERT INTO strategy_reviews VALUES(?,?)", (review["id"], json.dumps(review)))
            return review

    def start(self, review_id, confirmation):
        """Approve a fixed scope; prime the current candle and wait for a new close."""
        with self.lock:
            with self.store.db() as db:
                row = db.execute("SELECT payload FROM strategy_reviews WHERE id=?", (review_id,)).fetchone()
            if not row:
                raise LookupError("Strategy review not found.")
            review = json.loads(row[0])
            if confirmation != review["confirmation"]:
                raise ExecutionGuard("Type " + review["confirmation"] + " to approve this strategy.")
            if review.get("job_id"):
                return self.journal.job(review["job_id"])
            existing = next((job for job in self.host.jobs() if job["id"] == review_id), None)
            if existing:
                return existing
            if datetime.now(UTC) > datetime.fromisoformat(review["expires_at"]):
                raise ExecutionGuard("Strategy review expired. Review the current account and budget again.")
            if sum(job["status"] == "running" for job in self.host.jobs()) >= 10:
                raise ExecutionGuard("Pause another strategy before starting more than ten runs.")
            self.runner.controls.require(review.get("control_revision", 0))
            request = ExchangeStrategyRequest(**review["request"])
            connection, observed = self._validate(request)
            self.runner.portfolio_limits.review(
                connection, request.parameters, review.get("risk_revision", 0)
            )
            if (connection.exchange, connection.sandbox) != (review["exchange"], review["sandbox"]):
                raise ExecutionGuard("Execution account environment changed. Review it again.")
            identity = review_id  # Recover a crash between saving the job and acknowledging the review.
            job = {
                "id": identity,
                "mode": "exchange",
                "connection_id": connection.id,
                "account": connection.label,
                "exchange": connection.exchange,
                "sandbox": connection.sandbox,
                "environment": review["environment"],
                "parameters": request.parameters.model_dump(),
                "risk": request.risk.model_dump(),
                "status": "running",
                "source": "connection:" + connection.id,
                "cash": request.parameters.capital,
                "quantity": 0.0,
                "equity": request.parameters.capital,
                "last_candle": observed["candles"][-1]["timestamp"],
                "reference_price": observed["price"],
                "fills": [],
                "created_at": now(),
                "monitoring_since": now(),
                "approved_at": now(),
                "error": None,
                "statistics_complete": True,
                "journal_started": True,
                "realized_pnl": 0.0,
                "fees_paid": 0.0,
                "completed_returns": [],
                "round_trips": 0,
                "pending": None,
                "execution_state": "waiting_candle",
                "fill_versions": {},
            }
            self.journal.save(
                job,
                self.host._event(
                    job,
                    "START",
                    "Exchange strategy approved. Waiting for the next closed candle; existing account holdings are not adopted.",
                ),
            )
            review["job_id"] = identity
            with self.store.db() as db:
                db.execute(
                    "UPDATE strategy_reviews SET payload=? WHERE id=?", (json.dumps(review), review_id)
                )
            return job
