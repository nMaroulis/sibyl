"""Real closed-candle strategy acceptance through Sibyl's HTTP and worker lifecycle."""

import json
import time

from sibyl.strategies.execution.contracts import ExecutionParameters
from sibyl.strategies.execution.venue import is_dust, observation, order_book
from sibyl.strategies.signals import signals, strategy_indicators


class StrategyAcceptance:
    """Review one finite run, reconcile its entry, then separately approve its exit.

    No signals, candles, balances or fills are simulated. A bounded signal wait
    can finish without an entry; that is an incomplete check, never a success.
    Partial fills and dust remain owned in the retained workspace.
    """

    def __init__(self, client, account, report, transport):
        self.client, self.account = client, account
        self.report, self.transport = report, transport
        self.services = client.app.state.services
        self.job_id = report.values.get("job_id")

    def request(self, method, path, body=None, *, expected=None):
        response = self.client.request(method, "/api/v1" + path, json=body)
        if expected is not None and response.status_code == expected:
            return response.json()
        if response.status_code >= 400 or expected is not None:
            raise RuntimeError(f"Acceptance HTTP {response.status_code}: {path}")
        return response.json()

    def job(self):
        return self.request("GET", f"/strategies/jobs/{self.job_id}")["job"]

    def orders(self):
        """Read only this isolated run's durable intents, including ambiguous attempts."""
        with self.services.store.db() as db:
            rows = db.execute(
                "SELECT payload FROM exchange_orders WHERE json_extract(payload,'$.strategy_job_id')=? "
                "ORDER BY rowid",
                (self.job_id,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def limits(self, maximum=15):
        policies = self.request("GET", "/strategies/exchange/limits")["policies"]
        policy = next(row for row in policies if row["environment"] == "test")
        self.request(
            "POST",
            "/strategies/exchange/limits/test",
            {
                "revision": policy["revision"],
                "confirmation": "SAVE STRATEGY LIMITS",
                "enabled": True,
                "source": "binance",
                "max_allocated": maximum,
                "max_exposure": 30,
                "max_daily_loss": 10,
            },
        )

    def start(self):
        self.report.update(phase="strategy_review")
        self.limits()
        parameters = ExecutionParameters(
            strategy="ema",
            capital=12,
            candles=60,
            timeframe="1m",
            fast_period=2,
            slow_period=3,
            rsi_period=2,
            rsi_lower=49,
            rsi_upper=99,
        )
        with self.services.market.adapter(self.account) as venue:
            observed = observation(venue, parameters)
        direction = int(
            signals(strategy_indicators(observed["candles"], parameters), "ema", parameters).iloc[-1]
        )
        if direction != 1:
            parameters = parameters.model_copy(update={"strategy": "rsi"})
        review = self.request(
            "POST",
            "/strategies/exchange/preview",
            {
                "connection_id": self.account.id,
                "parameters": parameters.model_dump(),
                "risk": {
                    "max_order_quote": 12,
                    "max_orders_per_day": 2,
                    "max_loss_pct": 80,
                    "max_spread_bps": 50,
                    "price_limit_bps": 25,
                    "fee_reserve_bps": 10,
                    "order_lifetime_seconds": 120,
                },
            },
        )
        if review["environment"] != "test" or review["exchange"] != "binance-testnet":
            raise RuntimeError("Strategy review escaped the Testnet scope.")
        path = f"/strategies/exchange/reviews/{review['id']}/start"
        job = self.request("POST", path, {"confirmation": review["confirmation"]})
        self.job_id = job["id"]
        self.report.update(job_id=self.job_id, phase="waiting_for_real_signal")
        duplicate = self.request("POST", path, {"confirmation": review["confirmation"]})
        if duplicate["id"] != self.job_id:
            raise RuntimeError("Repeated start created another strategy.")
        self.report.record(
            "strategy_started_once",
            job_id=self.job_id,
            strategy=parameters.strategy,
            capital=parameters.capital,
            timeframe=parameters.timeframe,
            primed_candle=job["last_candle"],
        )

    def wait_for_entry(self, seconds):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            orders = self.orders()
            if orders and orders[0]["status"] != "preview":
                self.request("POST", f"/strategies/jobs/{self.job_id}/pause")
                if len(orders) != 1 or orders[0]["request"]["side"] != "buy":
                    raise RuntimeError("Strategy entry scope differed from the expected single buy.")
                if self.transport.lose_entry_response:
                    events = self.request("GET", f"/strategies/jobs/{self.job_id}/events?limit=100")
                    # The runner must pause on the ambiguous write, even if a fast
                    # background lookup has already recovered its native identity.
                    if not any("uncertain" in row.get("reason", "").lower() for row in events["items"]):
                        raise RuntimeError("The deliberately lost entry response did not pause the strategy.")
                detail = self.reconcile(orders[0]["id"])
                if self.transport.lose_entry_response:
                    recovery = detail["order"].get("recovery", {})
                    if recovery.get("state") != "found" or len(self.transport.attempts) != 1:
                        raise RuntimeError(
                            "The lost response did not recover through one native client-ID lookup."
                        )
                    self.report.record(
                        "lost_response_recovered_without_resubmission",
                        native_id=detail["order"]["exchange_order_id"],
                        lookup_pages=recovery.get("pages"),
                    )
                return detail
            job = self.job()
            if job["status"] != "running":
                raise RuntimeError("Strategy paused before an entry; inspect the retained journal.")
            time.sleep(2)
        self.request("POST", f"/strategies/jobs/{self.job_id}/pause")
        raise TimeoutError("No real entry signal arrived within the bounded acceptance wait.")

    def reconcile(self, identity):
        self.report.update(phase="native_reconciliation")
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            detail = self.request("GET", f"/exchange-orders/{identity}/reconciliation")
            order, summary = detail["order"], detail["reconciliation"]
            if not order.get("exchange_order_id"):
                if order["status"] not in {"unknown", "submitting"}:
                    raise RuntimeError("The native submission has no recoverable identity.")
                self.request("POST", f"/exchange-orders/{identity}/recover")
            else:
                detail = self.request("POST", f"/exchange-orders/{identity}/reconcile")
                order, summary = detail["order"], detail["reconciliation"]
                if order["status"] == "closed" and summary["status"] == "matched":
                    self.report.record(
                        "native_order_reconciled",
                        intent_id=identity,
                        native_id=order["exchange_order_id"],
                        side=order["request"]["side"],
                        quantity=summary["quantity"],
                        fees=summary["fees"],
                        fills=summary["fill_count"],
                    )
                    return detail
                if order["status"] in {"canceled", "rejected", "expired"}:
                    raise RuntimeError(
                        "Native order did not fully fill; ownership is retained for inspection."
                    )
            time.sleep(2)
        raise TimeoutError("Native fill reconciliation did not complete; do not repeat the write.")

    def prepare_restart(self):
        job = self.request("POST", f"/strategies/jobs/{self.job_id}/resume")
        if job["status"] != "running" or job["quantity"] <= 0 or job["unresolved_orders"]:
            raise RuntimeError("The reconciled run could not be resumed for restart acceptance.")
        self.report.record("resume_with_reconciled_ownership", quantity=job["quantity"])
        self.report.update(phase="restarting_with_retained_position")

    def after_restart(self):
        job = self.job()
        if job["status"] != "paused" or len(self.orders()) != 1:
            raise RuntimeError("Startup did not pause and retain exactly the original entry.")
        self.report.record("restart_paused_without_replay", quantity=job["quantity"])
        refusal = self.request(
            "POST",
            "/strategies/exchange/preview",
            {
                "connection_id": self.account.id,
                "parameters": {"symbol": "ETH/USDT", "capital": 6, "timeframe": "1m", "candles": 60},
                "risk": {"max_order_quote": 6},
            },
            expected=400,
        )
        if "shared strategy capital limit" not in refusal.get("detail", ""):
            raise RuntimeError("The second allocation was refused for an unexpected reason.")
        self.report.record("shared_allocation_limit_refused_second_run", cap=15, allocated=12, requested=6)
        self.request("POST", f"/strategies/jobs/{self.job_id}/resume")
        controls = self.request("GET", "/strategies/exchange/controls")
        self.request(
            "POST",
            "/strategies/exchange/controls",
            {"action": "halt", "revision": controls["revision"], "reason": "Testnet acceptance halt"},
        )
        refusal = self.request("POST", f"/strategies/jobs/{self.job_id}/resume", expected=400)
        if "Global strategy halt" not in refusal.get("detail", ""):
            raise RuntimeError("Resume was refused for an unexpected reason after the global halt.")
        if self.job()["status"] != "paused" or len(self.orders()) != 1:
            raise RuntimeError("Global halt failed to pause new strategy submissions.")
        self.report.record("global_halt_blocks_resume_without_liquidation")

    def close_position(self):
        self.report.update(phase="separately_reviewed_exit")
        review = self.request("POST", f"/strategies/exchange/jobs/{self.job_id}/stop-cancel-review")
        self.request(
            "POST",
            f"/strategies/exchange/stop-reviews/{review['id']}/confirm",
            {"confirmation": review["confirmation"]},
        )
        context = self.request("GET", f"/strategies/exchange/jobs/{self.job_id}/close-position")
        if not context["ready"]:
            raise RuntimeError("Native evidence is not ready for a separately approved exit.")
        self.transport.allow_sell(context["quantity"])
        review = self.request(
            "POST",
            f"/strategies/exchange/jobs/{self.job_id}/close-preview",
            {"price_limit_bps": 25, "fee_reserve_bps": 10, "order_lifetime_seconds": 120},
        )
        path = f"/strategies/exchange/close-reviews/{review['id']}/confirm"
        job = self.request("POST", path, {"confirmation": review["confirmation"]})
        intent = job["close_position"]["intent_id"]
        duplicate = self.request("POST", path, {"confirmation": review["confirmation"]})
        if duplicate["close_position"]["intent_id"] != intent or len(self.orders()) != 2:
            raise RuntimeError("Duplicate exit approval changed native submission identity.")
        self.reconcile(intent)
        job = self.request("POST", f"/strategies/jobs/{self.job_id}/stop")
        if job["unresolved_orders"] or job["accounting_incomplete"] or job["unvalued_fees"]:
            raise RuntimeError("The final strategy accounting is incomplete.")
        with self.services.market.adapter(self.account) as venue:
            observed = order_book(venue, job["parameters"]["symbol"])
            dust = is_dust(venue, job["parameters"]["symbol"], job["quantity"], observed["bid"])
        self.report.record(
            "owned_exit_reconciled_once",
            residual_quantity=job["quantity"],
            residual_is_dust=dust,
            realized_pnl=job["realized_pnl"],
        )

    def halt_on_failure(self):
        """Revoke future signals; never guess a cancellation or liquidation after an error."""
        controls = self.request("GET", "/strategies/exchange/controls")
        self.request(
            "POST",
            "/strategies/exchange/controls",
            {"action": "halt", "revision": controls["revision"], "reason": "Acceptance stopped"},
        )
