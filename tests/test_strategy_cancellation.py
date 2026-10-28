"""Durable strategy expiry and reviewed stopping against simulated native orders."""

import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import ccxt
import pandas as pd
import pytest
from pydantic import ValidationError
from test_strategy_execution import Venue, reconcile, request, start, submit
from test_strategy_execution import execution as execution

from sibyl.models import ConnectionCreate, ExchangeOrderRequest
from sibyl.services.trading import ExchangeTrading
from sibyl.strategies import Strategies
from sibyl.strategies.execution import cancellation, runner, venue
from sibyl.strategies.execution.contracts import ExecutionRisk


def retained(trading, identity):
    with trading.store.db() as db:
        return trading.lifecycle.read(db, identity)


def save(trading, intent):
    with trading.store.db() as db:
        trading.lifecycle.write(db, intent)


def expiring(execution, lifetime=60):
    strategies, trading, native, _ = execution
    job, _ = start(execution, risk={"order_lifetime_seconds": lifetime})
    native.clock += 60
    strategies.tick()
    intent = strategies.execution._intent(strategies.journal.job(job["id"]))
    deadline = datetime.fromisoformat(intent["strategy_expires_at"]).timestamp()
    return job, intent, deadline


def approve_stop(strategies, identity):
    review = strategies.execution.stop_reviews.preview(identity)
    return strategies.execution.stop_reviews.confirm(review["id"], review["confirmation"])


@pytest.mark.parametrize("value", [59, 86401, -1, 60.5, "300", True])
def test_expiry_requires_an_explicit_bounded_integer(value):
    with pytest.raises(ValidationError):
        ExecutionRisk(order_lifetime_seconds=value)


def test_deadline_is_committed_at_submission_before_the_native_write(execution, monkeypatch):
    strategies, trading, native, _ = execution
    original = native.create_order

    def inspect_boundary(*args, **kwargs):
        intent = trading.list_orders()[0]
        assert intent["status"] == "submitting"
        assert intent["strategy_expiry_seconds"] == 300
        assert (
            datetime.fromisoformat(intent["strategy_expires_at"])
            - datetime.fromisoformat(intent["submitted_at"])
        ).total_seconds() == 300
        return original(*args, **kwargs)

    monkeypatch.setattr(native, "create_order", inspect_boundary)
    expiring(execution, 300)
    assert len(native.calls) == 1


def test_unspecified_policy_and_old_jobs_gain_no_cancellation_authority(execution):
    strategies, trading, native, _ = execution
    job, intent = submit(execution)
    assert ExecutionRisk().order_lifetime_seconds is None
    assert not intent.get("strategy_expires_at")
    job["risk"].pop("order_lifetime_seconds")  # Existing stored jobs predate this field.
    strategies.journal.save(job)
    native.clock += 86401
    strategies.tick()
    assert not native.cancels and retained(trading, intent["id"])["status"] == "open"


def test_deadline_cancels_once_and_waits_for_native_fill_reconciliation(execution):
    strategies, trading, native, _ = execution
    job, intent, deadline = expiring(execution)
    native.clock = deadline - 0.01
    strategies.tick()
    assert not native.cancels
    native.clock = deadline
    strategies.tick()
    order = retained(trading, intent["id"])
    assert native.cancels == [intent["exchange_order_id"]]
    assert order["status"] == "canceled" and order["cancel_state"] == "confirmed"
    assert order["strategy_cancellation"]["state"] == "reconciling"
    assert strategies.journal.job(job["id"])["unresolved_orders"]
    assert len(native.calls) == 1
    assert reconcile(trading, intent["id"])["reconciliation"]["status"] == "matched"
    strategies.status(job["id"], "paused")
    for _ in range(4):
        native.clock += 300
        strategies.tick()
    assert retained(trading, intent["id"])["strategy_cancellation"]["state"] == "reconciled"
    assert strategies.journal.job(job["id"])["execution_state"] == "paused"
    assert len(native.cancels) == len(native.calls) == 1


@pytest.mark.parametrize("state", ["paused", "stopped", "restart"])
def test_approved_expiry_survives_pause_stop_and_restart(execution, state):
    strategies, trading, native, _ = execution
    job, intent, deadline = expiring(execution)
    if state == "restart":
        strategies = Strategies(strategies.market, strategies.store)
        strategies.attach_execution(ExchangeTrading(strategies.market, strategies.store))
    else:
        strategies.status(job["id"], state)
    native.clock = deadline + 1
    strategies.tick()
    assert native.cancels == [intent["exchange_order_id"]]
    assert len(native.calls) == 1
    assert strategies.journal.job(job["id"])["status"] == ("paused" if state == "restart" else state)


def test_partial_fill_is_retained_and_late_fill_and_fee_corrections_rebuild_ownership(execution):
    strategies, trading, native, _ = execution
    job, intent, deadline = expiring(execution)
    native.settle(intent["exchange_order_id"], quantity=1, fee=0.1, terminal=False)
    reconcile(trading, intent["id"])
    strategies.status(job["id"], "paused")
    native.clock = deadline
    strategies.tick()
    assert strategies.journal.job(job["id"])["quantity"] == 1
    assert retained(trading, intent["id"])["filled"] == 1
    reconcile(trading, intent["id"])
    # Cancellation raced another execution. The next terminal status read must
    # discover its cumulative quantity even though normal order polling stopped.
    native.settle(intent["exchange_order_id"], quantity=0.5, fee=0.05, terminal=False)
    native.orders[intent["exchange_order_id"]].update(
        status="canceled", filled=1.5, cost=150, remaining=native.calls[0][1] - 1.5
    )
    native.clock += 30
    strategies.tick()
    assert retained(trading, intent["id"])["filled"] == 1.5
    assert retained(trading, intent["id"])["strategy_cancellation"]["state"] == "reconciling"
    reconcile(trading, intent["id"])
    native.fills[0]["fees"][0]["cost"] = 0.2
    reconcile(trading, intent["id"])
    strategies.tick()
    current = strategies.journal.job(job["id"])
    assert current["quantity"] == 1.5 and current["native_fill_count"] == 2
    assert not current["unresolved_orders"]
    assert current["cash"] == pytest.approx(849.75)
    assert current["fee_assets"] == {"USDT": pytest.approx(0.25)}
    assert len(native.calls) == len(native.cancels) == 1


@pytest.mark.parametrize("race", ["before_review", "during_cancel"])
def test_full_native_fill_wins_a_cancellation_race(execution, monkeypatch, race):
    strategies, trading, native, _ = execution
    job, intent, deadline = expiring(execution)
    strategies.status(job["id"], "paused")
    if race == "before_review":
        native.settle(intent["exchange_order_id"])
    else:
        original = native.cancel_order

        def fill_then_cancel(identity, symbol):
            native.settle(identity)
            return original(identity, symbol)

        monkeypatch.setattr(native, "cancel_order", fill_then_cancel)
    native.clock = deadline
    strategies.tick()
    assert retained(trading, intent["id"])["status"] == "closed"
    reconcile(trading, intent["id"])
    strategies.tick()
    assert strategies.journal.job(job["id"])["quantity"] == pytest.approx(native.calls[0][1])
    assert len(native.calls) == 1
    assert len(native.cancels) == (1 if race == "during_cancel" else 0)


@pytest.mark.parametrize("failure", [ccxt.RequestTimeout("PRIVATE-TOKEN"), RuntimeError("PRIVATE-TOKEN")])
def test_ambiguous_cancellation_is_never_automatically_retried_even_after_restart(execution, failure):
    strategies, trading, native, _ = execution
    job, intent, deadline = expiring(execution)
    native.cancel_failure = failure
    native.clock = deadline
    strategies.tick()
    assert retained(trading, intent["id"])["strategy_cancellation"]["state"] == "unknown"
    restarted = Strategies(strategies.market, strategies.store)
    restarted.attach_execution(ExchangeTrading(strategies.market, strategies.store))
    for _ in range(4):
        native.clock += 60
        restarted.tick()
    assert len(native.cancels) == len(native.calls) == 1
    assert "PRIVATE-TOKEN" not in json.dumps(restarted.jobs())
    assert "PRIVATE-TOKEN" not in json.dumps(restarted.journal.events(job["id"]))
    # Read-only recovery continues even if the server's order-writing switches are off.
    strategies.market.settings.allow_live_trading = False
    strategies.market.settings.allow_strategy_execution = False
    native.orders[intent["exchange_order_id"]]["status"] = "canceled"
    native.clock += 60
    restarted.tick()
    assert retained(trading, intent["id"])["cancel_state"] == "confirmed"
    assert len(native.cancels) == 1


def test_cancel_acknowledgment_does_not_invent_a_terminal_state(execution):
    strategies, trading, native, _ = execution
    job, intent, deadline = expiring(execution)
    native.cancel_terminal = False
    native.clock = deadline
    strategies.tick()
    order = retained(trading, intent["id"])
    assert order["status"] == "open" and order["strategy_cancellation"]["state"] == "requested"
    native.clock += 60
    strategies.tick()
    assert len(native.cancels) == 1 and len(native.calls) == 1
    assert strategies.journal.job(job["id"])["quantity"] == 0


@pytest.mark.parametrize("boundary", ["before_shared_boundary", "after_shared_boundary"])
def test_process_loss_never_repeats_a_durable_native_cancellation(execution, monkeypatch, boundary):
    strategies, trading, native, _ = execution
    job, intent, deadline = expiring(execution)
    native.clock = deadline

    def process_loss(*args, **kwargs):
        raise SystemExit("simulated process loss")

    with monkeypatch.context() as patch:
        if boundary == "before_shared_boundary":
            patch.setattr(trading.lifecycle, "cancel", process_loss)
        else:
            patch.setattr(native, "cancel_order", process_loss)
        with pytest.raises(SystemExit):
            strategies.tick()
    committed = retained(trading, intent["id"])
    assert bool(committed.get("cancel_requested_at")) == (boundary == "after_shared_boundary")
    restarted = Strategies(strategies.market, strategies.store)
    restarted.attach_execution(ExchangeTrading(strategies.market, strategies.store))
    native.clock += 60
    restarted.tick()
    assert len(native.cancels) == (1 if boundary == "before_shared_boundary" else 0)
    assert len(native.calls) == 1
    if boundary == "after_shared_boundary":
        assert retained(trading, intent["id"])["strategy_cancellation"]["state"] == "unknown"


def test_prior_manual_cancel_attempt_is_only_observed_by_expiry_worker(execution):
    strategies, trading, native, _ = execution
    job, intent, deadline = expiring(execution)
    native.cancel_failure = TimeoutError("reply lost")
    review = trading.lifecycle.preview_cancel(intent["id"])
    trading.lifecycle.cancel(intent["id"], review["id"], review["confirmation"])
    native.clock = deadline
    strategies.tick()
    native.clock += 60
    strategies.tick()
    assert len(native.cancels) == 1


@pytest.mark.parametrize("blocked", ["inactive", "live_flag", "strategy_flag", "environment"])
def test_expiry_rechecks_account_and_permissions_and_backs_off(execution, monkeypatch, blocked):
    strategies, trading, native, connection = execution
    job, intent, deadline = expiring(execution)
    if blocked == "inactive":
        strategies.store.activate_account(connection.id, False)
    elif blocked == "environment":
        monkeypatch.setattr(
            strategies.execution, "account", lambda identity: connection.model_copy(update={"sandbox": False})
        )
    else:
        setattr(
            strategies.market.settings,
            "allow_" + ("live_trading" if blocked == "live_flag" else "strategy_execution"),
            False,
        )
    native.clock = deadline
    strategies.tick()
    meta = retained(trading, intent["id"])["strategy_cancellation"]
    assert meta["state"] == "blocked" and meta["failures"] == 1
    strategies.tick()
    assert retained(trading, intent["id"])["strategy_cancellation"] == meta
    native.clock += 30
    strategies.tick()
    assert retained(trading, intent["id"])["strategy_cancellation"]["failures"] == 2
    assert not native.cancels


def test_permissions_are_rechecked_after_the_native_read_before_cancellation_write(execution, monkeypatch):
    strategies, trading, native, _ = execution
    _, intent, deadline = expiring(execution)
    original = trading.lifecycle.preview_cancel

    def revoke(identity):
        review = original(identity)
        strategies.market.settings.allow_strategy_execution = False
        return review

    monkeypatch.setattr(trading.lifecycle, "preview_cancel", revoke)
    native.clock = deadline
    strategies.tick()
    assert not native.cancels
    assert retained(trading, intent["id"])["strategy_cancellation"]["state"] == "blocked"


def test_unknown_submission_retains_deadline_but_cannot_cancel_without_a_native_identity(execution):
    strategies, trading, native, _ = execution
    native.failure = ccxt.RequestTimeout("lost submission reply")
    _, intent, deadline = expiring(execution)
    assert intent["status"] == "unknown" and not intent.get("exchange_order_id")
    native.clock = deadline
    strategies.tick()
    assert not native.cancels and len(native.calls) == 1
    assert retained(trading, intent["id"])["strategy_cancellation"]["state"] == "blocked"


def test_stop_review_is_read_only_typed_scoped_and_idempotent(execution):
    strategies, trading, native, _ = execution
    job, intent = submit(execution)
    service = strategies.execution.stop_reviews
    reads = len(native.reads)
    review = service.preview(job["id"])
    assert len(native.reads) == reads and not native.cancels
    assert review["orders"][0]["id"] == intent["id"]
    assert strategies.journal.job(job["id"])["status"] == "running"
    with pytest.raises(ValueError, match="Type STOP AND CANCEL TEST"):
        service.confirm(review["id"], "yes")
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: service.confirm(review["id"], review["confirmation"]), range(4)))
    assert all(row["status"] == "stopped" and row["stop_cancellation"] for row in results)
    assert not native.cancels  # The durable stop precedes any worker write.
    assert strategies.journal.events(job["id"], action="STOP_CANCEL")["matching_count"] == 1
    strategies.tick()
    assert native.cancels == [intent["exchange_order_id"]] and len(native.calls) == 1
    with pytest.raises(ValueError, match="terminal"):
        strategies.status(job["id"], "running")


@pytest.mark.parametrize("invalid", ["expired", "scope"])
def test_stale_stop_review_cannot_authorize_another_scope(execution, invalid):
    strategies, _, native, _ = execution
    job, _ = submit(execution)
    service = strategies.execution.stop_reviews
    review = service.preview(job["id"])
    if invalid == "expired":
        review["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    else:
        review["connection_id"] = "another-account"
    with strategies.store.db() as db:
        db.execute(
            "UPDATE strategy_stop_reviews SET payload=? WHERE id=?", (json.dumps(review), review["id"])
        )
    with pytest.raises(ValueError, match="expired|scope changed"):
        service.confirm(review["id"], review["confirmation"])
    assert strategies.journal.job(job["id"])["status"] == "running" and not native.cancels


def test_explicit_stop_queue_recovers_after_restart_with_strategy_submissions_disabled(execution):
    strategies, trading, native, _ = execution
    job, intent = submit(execution)
    approve_stop(strategies, job["id"])
    strategies.market.settings.allow_strategy_execution = False
    restarted = Strategies(strategies.market, strategies.store)
    restarted.attach_execution(ExchangeTrading(strategies.market, strategies.store))
    restarted.tick()
    assert native.cancels == [intent["exchange_order_id"]] and len(native.calls) == 1


def test_stop_commits_even_if_cancellation_access_is_disabled(execution):
    strategies, trading, native, _ = execution
    job, intent = submit(execution)
    strategies.market.settings.allow_live_trading = False
    approve_stop(strategies, job["id"])
    strategies.tick()
    assert strategies.journal.job(job["id"])["status"] == "stopped" and not native.cancels
    assert retained(trading, intent["id"])["strategy_cancellation"]["state"] == "blocked"


def test_stop_during_preparation_abandons_intent_without_submission(execution, monkeypatch):
    strategies, trading, native, _ = execution
    job, _ = start(execution)
    original = trading.preview

    def stop_while_preparing(body):
        intent = original(body)
        approve_stop(strategies, job["id"])
        return intent

    monkeypatch.setattr(trading, "preview", stop_while_preparing)
    native.clock += 60
    strategies.tick()
    strategies.tick()
    assert not native.calls and not native.cancels
    assert trading.list_orders()[0]["strategy_abandoned"]
    assert strategies.journal.job(job["id"])["status"] == "stopped"


def test_stop_cancels_only_owned_orders_and_never_sells_partial_holdings(execution):
    strategies, trading, native, connection = execution
    job, intent = submit(execution)
    manual = trading.preview(
        ExchangeOrderRequest(
            connection_id=connection.id,
            symbol="BTC/USDT",
            side="buy",
            quantity=0.02,
            order_type="limit",
            limit_price=99,
            idempotency_key="unrelated-manual-order",
        )
    )
    trading.execute(manual["id"], manual["confirmation"])
    native.settle(intent["exchange_order_id"], quantity=1, terminal=False)
    reconcile(trading, intent["id"])
    approve_stop(strategies, job["id"])
    strategies.tick()
    assert native.cancels == [intent["exchange_order_id"]]
    reconcile(trading, intent["id"])
    strategies.tick()
    assert strategies.journal.job(job["id"])["quantity"] == 1
    assert all(call[0] == "buy" for call in native.calls)
    assert retained(trading, manual["id"])["status"] == "open"


def test_terminal_native_checks_are_bounded_and_lifecycle_events_export(execution):
    strategies, trading, native, _ = execution
    job, intent, deadline = expiring(execution)
    strategies.status(job["id"], "paused")
    native.clock = deadline
    strategies.tick()
    reconcile(trading, intent["id"])
    for _ in range(4):
        native.clock += 300
        strategies.tick()
    assert retained(trading, intent["id"])["strategy_cancellation"]["terminal_checks"] == 3
    reads = len(native.reads)
    native.clock += 3600
    strategies.tick()
    assert len(native.reads) == reads
    actions = {e["action"] for e in strategies.journal.events(job["id"])["items"]}
    assert {"CANCEL_QUEUED", "CANCEL_RECONCILING", "CANCEL_RECONCILED"} <= actions
    rows = list(csv.DictReader(io.StringIO("".join(strategies.journal.export(job["id"])))))
    matched = [row for row in rows if row["action"] == "CANCEL_RECONCILED"]
    assert matched[0]["cancel_state"] == "reconciled"
    assert matched[0]["cancellation_id"] and matched[0]["expires_at"] == intent["strategy_expires_at"]


def test_http_stop_review_confirmation_and_monitor_event_filters(client, monkeypatch):
    services = client.app.state.services
    services.settings.allow_live_trading = services.settings.allow_strategy_execution = True
    connection = services.store.add_connection(
        ConnectionCreate(
            exchange="binance-testnet",
            label="Isolated cancellation API",
            api_key="FAKE",
            secret="FAKE",
        )
    )
    native = Venue()
    services.market._clients[connection.id] = native
    for module in (venue, runner, cancellation):
        monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda: native.clock))
    monkeypatch.setattr(runner, "signals", lambda frame, *args: pd.Series([1] * len(frame)))
    review = services.strategies.execution.preview(request(connection))
    job = services.strategies.execution.start(review["id"], review["confirmation"])
    native.clock += 60
    services.strategies.tick()
    base = "/api/v1/strategies/exchange"
    review_response = client.post(f"{base}/jobs/{job['id']}/stop-cancel-review")
    assert review_response.status_code == 200 and not native.cancels
    review = review_response.json()
    url = f"{base}/stop-reviews/{review['id']}/confirm"
    assert client.post(url, json={"confirmation": "yes"}).status_code == 400
    assert client.post(url, json={"confirmation": review["confirmation"]}).json()["status"] == "stopped"
    services.strategies.tick()
    events = client.get(f"/api/v1/strategies/jobs/{job['id']}/events?action=CANCEL_RECONCILING")
    assert events.status_code == 200 and events.json()["matching_count"] == 1
    monitor = client.get(f"/api/v1/strategies/jobs/{job['id']}").json()["job"]
    assert monitor["stop_cancellation"] and monitor["orders"][0]["strategy_cancellation"]
    assert len(native.cancels) == 1


@pytest.mark.parametrize(
    "provider",
    [
        "binance",
        "binanceus",
        "binance-testnet",
        "coinbase",
        "coinbase-sandbox",
        "kraken",
        "okx",
        "bybit",
        "kucoin",
    ],
)
def test_approved_expiry_uses_the_shared_pipeline_for_every_execution_provider(execution, provider):
    strategies, trading, native, _ = execution
    connection = strategies.store.add_connection(
        ConnectionCreate(
            exchange=provider,
            label="Simulated provider",
            api_key="FAKE",
            secret="FAKE",
            passphrase="FAKE",
        )
    )
    strategies.market._clients[connection.id] = native
    review = strategies.execution.preview(request(connection, risk={"order_lifetime_seconds": 60}))
    job = strategies.execution.start(review["id"], review["confirmation"])
    native.clock += 60
    strategies.tick()
    intent = strategies.execution._intent(strategies.journal.job(job["id"]))
    native.clock = datetime.fromisoformat(intent["strategy_expires_at"]).timestamp()
    strategies.tick()
    assert native.cancels == [intent["exchange_order_id"]]
    assert retained(trading, intent["id"])["status"] == "canceled"
