"""Separately approved position exits; no private credentials or real venue writes."""

import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import ccxt
import pytest
from test_strategy_cancellation import approve_stop, retained
from test_strategy_execution import execution as execution
from test_strategy_execution import reconcile, request, submit

from sibyl.services.trading import ExchangeTrading
from sibyl.strategies import Strategies
from sibyl.strategies.execution.contracts import ClosePositionRequest


def owned(execution):
    strategies, trading, native, _ = execution
    job, entry = submit(execution)
    native.settle(entry["exchange_order_id"])
    reconcile(trading, entry["id"])
    strategies.status(job["id"], "stopped")
    return strategies.journal.job(job["id"]), entry


def preview(execution, **policy):
    strategies, _, _, _ = execution
    job, entry = owned(execution)
    review = strategies.execution.closing.preview(job["id"], ClosePositionRequest(**policy))
    return job, entry, review


def confirm(strategies, review):
    return strategies.execution.closing.confirm(review["id"], review["confirmation"])


def test_preview_is_read_only_and_sizes_only_owned_units_with_fee_reserve(execution):
    strategies, trading, native, _ = execution
    job, entry, review = preview(execution)
    assert len(native.calls) == 1 and not native.cancels
    assert len(trading.list_orders()) == 1  # No executable order is prepared by review.
    assert strategies.journal.job(job["id"])["status"] == "stopped"
    assert review["quantity"] + review["base_fee_reserve"] <= job["quantity"] + 1e-12
    assert review["quantity"] < native.free["BTC"]
    assert review["limit_price"] >= native.bid * 0.9975
    assert review["residual_before_fees"] == pytest.approx(job["quantity"] - review["quantity"])
    assert review["proceeds_before_fees"] == review["quantity"] * review["limit_price"]
    assert review["quote_fee_allowance"] > 0
    assert strategies.execution.closing.context(job["id"])["ready"]


def test_confirm_tracks_native_fills_realized_pnl_and_residual_without_auto_replacement(execution):
    strategies, trading, native, _ = execution
    job, _, review = preview(execution)
    result = confirm(strategies, review)
    exit_id = result["close_position"]["intent_id"]
    assert native.calls[-1][:3] == ("sell", review["quantity"], review["limit_price"])
    assert result["quantity"] == job["quantity"]  # Acknowledgment never disposes units.
    assert result["close_position"]["state"] == "submitted"
    order = retained(trading, exit_id)
    assert order["origin"] == "strategy" and order["strategy_action"] == "close"
    assert order["strategy_close_review_id"] == review["id"]
    with pytest.raises(ValueError, match="strategy approval"):
        trading.execute(exit_id, order["confirmation"])
    native.settle(order["exchange_order_id"], fee=0.2)
    trading.lifecycle.refresh(exit_id)
    strategies.tick()
    assert strategies.journal.job(job["id"])["close_position"]["state"] == "reconciling"
    reconcile(trading, exit_id)
    strategies.tick()
    final = strategies.journal.job(job["id"])
    assert final["close_position"]["state"] == "reconciled"
    assert final["quantity"] == pytest.approx(job["quantity"] - review["quantity"])
    assert final["realized_pnl"] == pytest.approx(
        review["quantity"] * 100 - 0.2 - job["entry_cost"] * review["quantity"] / job["quantity"]
    )
    assert final["status"] == "stopped" and len(native.calls) == 2
    native.fills[-1]["fees"][0]["cost"] = 0.3
    reconcile(trading, exit_id)
    strategies.tick()
    assert strategies.journal.job(job["id"])["realized_pnl"] == pytest.approx(final["realized_pnl"] - 0.1)
    assert confirm(strategies, review)["close_position"]["intent_id"] == exit_id
    assert len(native.calls) == 2


@pytest.mark.parametrize("cause", ["running", "paused", "pending", "fees", "no_position"])
def test_unready_runs_cannot_be_reviewed(execution, cause):
    strategies, trading, native, _ = execution
    job, entry = submit(execution)
    if cause != "no_position":
        native.settle(entry["exchange_order_id"], terminal=cause != "pending")
        if cause == "fees":
            native.fills[0]["fees"] = []
        reconcile(trading, entry["id"])
    if cause not in {"running", "paused"}:
        strategies.status(job["id"], "stopped")
    elif cause == "paused":
        strategies.status(job["id"], "paused")
    context = strategies.execution.closing.context(job["id"])
    assert not context["ready"] and context["reason"]
    with pytest.raises(ValueError):
        strategies.execution.closing.preview(job["id"], ClosePositionRequest())
    assert len(native.calls) == 1


def test_cancellation_late_status_checks_must_finish_before_review(execution):
    strategies, trading, native, _ = execution
    job, entry = submit(execution)
    native.settle(entry["exchange_order_id"], quantity=1, terminal=False)
    reconcile(trading, entry["id"])
    approve_stop(strategies, job["id"])
    strategies.tick()
    reconcile(trading, entry["id"])
    assert "three late native status checks" in strategies.execution.closing.context(job["id"])["reason"]
    for _ in range(3):
        native.clock += 300
        strategies.tick()
    assert strategies.execution.closing.context(job["id"])["ready"]


@pytest.mark.parametrize("cause", ["confirmation", "expiry", "ownership", "account", "flag", "scope"])
def test_confirmation_rechecks_authority_and_evidence(execution, cause):
    strategies, trading, native, connection = execution
    job, entry, review = preview(execution)
    phrase = review["confirmation"]
    if cause == "confirmation":
        phrase = "yes"
    elif cause == "expiry":
        review["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        with strategies.store.db() as db:
            db.execute(
                "UPDATE strategy_close_reviews SET payload=? WHERE id=?", (json.dumps(review), review["id"])
            )
    elif cause == "ownership":
        native.fills[0]["fees"] = [{"currency": "BTC", "cost": 0.01}]
        reconcile(trading, entry["id"])
    elif cause == "account":
        strategies.store.activate_account(connection.id, False)
    elif cause == "flag":
        strategies.market.settings.allow_live_trading = False
    else:
        job["sandbox"] = False
        strategies.journal.save(job)
    with pytest.raises(ValueError):
        strategies.execution.closing.confirm(review["id"], phrase)
    assert len(native.calls) == 1


def test_ownership_is_checked_inside_the_shared_submission_transaction(execution, monkeypatch):
    strategies, trading, native, _ = execution
    job, entry, review = preview(execution)
    original = trading.preview

    def correct_after_preview(*args, **kwargs):
        result = original(*args, **kwargs)
        native.fills[0]["fees"][0]["cost"] = 0.5
        reconcile(trading, entry["id"])
        return result

    monkeypatch.setattr(trading, "preview", correct_after_preview)
    with pytest.raises(ValueError, match="evidence changed"):
        confirm(strategies, review)
    latest = strategies.journal.job(job["id"])
    assert latest["close_position"]["state"] == "interrupted" and len(native.calls) == 1
    intent = retained(trading, latest["close_position"]["intent_id"])
    assert intent["strategy_abandoned"] and intent["status"] == "preview"
    confirm(strategies, review)
    assert len(native.calls) == 1


def test_concurrent_reviews_and_repeated_confirmation_can_only_create_one_pending_exit(execution):
    strategies, _, native, _ = execution
    job, _, review = preview(execution)
    second = strategies.execution.closing.preview(job["id"], ClosePositionRequest())
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: confirm(strategies, review), range(4)))
    assert len({row["close_position"]["intent_id"] for row in results}) == 1
    with pytest.raises(ValueError, match="outstanding"):
        confirm(strategies, second)
    assert len(native.calls) == 2


@pytest.mark.parametrize("boundary", ["prepared", "submitting", "native_timeout"])
def test_restart_never_replays_an_interrupted_exit(execution, monkeypatch, boundary):
    strategies, trading, native, _ = execution
    job, _, review = preview(execution)

    def die(*args, **kwargs):
        raise SystemExit("simulated process loss")

    with monkeypatch.context() as patch:
        if boundary == "prepared":
            patch.setattr(trading, "execute", die)
        elif boundary == "submitting":
            patch.setattr(native, "create_order", die)
        else:
            native.failure = ccxt.RequestTimeout("PRIVATE-KEY")
        if boundary == "native_timeout":
            confirm(strategies, review)
        else:
            with pytest.raises(SystemExit):
                confirm(strategies, review)
    count = len(native.calls)
    restarted = Strategies(strategies.market, strategies.store)
    restarted.attach_execution(ExchangeTrading(strategies.market, strategies.store))
    restarted.tick()
    again = confirm(restarted, review)
    assert len(native.calls) == count
    assert again["close_position"]["state"] == ("interrupted" if boundary == "prepared" else "unknown")
    assert "PRIVATE-KEY" not in json.dumps(again)


def test_stop_approval_does_not_cancel_a_later_exit_but_its_own_expiry_does(execution):
    strategies, trading, native, _ = execution
    job, _ = owned(execution)
    approve_stop(strategies, job["id"])
    strategies.market.settings.allow_strategy_execution = False
    review = strategies.execution.closing.preview(job["id"], ClosePositionRequest(order_lifetime_seconds=60))
    result = confirm(strategies, review)
    intent = retained(trading, result["close_position"]["intent_id"])
    strategies.tick()
    assert not native.cancels
    native.clock = datetime.fromisoformat(intent["strategy_expires_at"]).timestamp()
    strategies.tick()
    assert native.cancels == [intent["exchange_order_id"]]
    assert len(native.calls) == 2


def test_a_new_stop_cancellation_review_includes_an_already_submitted_exit(execution):
    strategies, trading, native, _ = execution
    job, _, review = preview(execution, order_lifetime_seconds=None)
    result = confirm(strategies, review)
    intent = retained(trading, result["close_position"]["intent_id"])
    approve_stop(strategies, job["id"])
    strategies.tick()
    assert native.cancels == [intent["exchange_order_id"]]
    assert len(native.calls) == 2


def test_review_expiry_is_rechecked_after_native_reads_at_submission_boundary(execution, monkeypatch):
    from sibyl.strategies.execution import closing

    strategies, trading, native, _ = execution
    job, _, review = preview(execution)
    original = trading.preview

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + timedelta(seconds=61)

    def delayed(*args, **kwargs):
        result = original(*args, **kwargs)
        monkeypatch.setattr(closing, "datetime", Later)
        return result

    monkeypatch.setattr(trading, "preview", delayed)
    with pytest.raises(ValueError, match="expired"):
        confirm(strategies, review)
    assert len(native.calls) == 1
    assert strategies.journal.job(job["id"])["close_position"]["state"] == "interrupted"


@pytest.mark.parametrize("cause", ["balance", "spread", "stale_book", "minimum", "provider_error"])
def test_native_preconditions_block_exit_without_leaking_provider_text(execution, monkeypatch, cause):
    strategies, _, native, _ = execution
    job, _ = owned(execution)
    if cause == "balance":
        native.free["BTC"] = 0.01
    elif cause == "spread":
        native.ask = 150
    elif cause == "minimum":
        native.markets["BTC/USDT"]["limits"]["cost"]["min"] = 1000
    elif cause == "stale_book":
        monkeypatch.setattr(
            native,
            "fetch_order_book",
            lambda *a, **k: {"timestamp": 1, "bids": [[100, 1]], "asks": [[100, 1]]},
        )
    else:

        def fail(*args, **kwargs):
            raise ValueError("PRIVATE-KEY")

        monkeypatch.setattr(native, "fetch_balance", fail)
    with pytest.raises(ValueError) as error:
        strategies.execution.closing.preview(job["id"], ClosePositionRequest())
    assert "PRIVATE-KEY" not in str(error.value) and len(native.calls) == 1


def test_exit_uses_native_maxima_and_a_separate_approval_instead_of_entry_order_cap(execution):
    strategies, _, native, _ = execution
    job, _ = owned(execution)
    native.bid, native.ask = 999.95, 1000.05
    native.markets["BTC/USDT"]["limits"]["amount"]["max"] = 2
    review = strategies.execution.closing.preview(job["id"], ClosePositionRequest())
    assert review["quantity"] == 2
    assert review["proceeds_before_fees"] > job["risk"]["max_order_quote"]
    assert review["residual_before_fees"] > 0
    confirm(strategies, review)
    assert native.calls[-1][1] == 2 and len(native.calls) == 2


def test_all_close_events_are_available_in_csv(execution):
    strategies, trading, native, _ = execution
    job, _, review = preview(execution)
    current = confirm(strategies, review)
    exit_id = current["close_position"]["intent_id"]
    native.settle(retained(trading, exit_id)["exchange_order_id"])
    reconcile(trading, exit_id)
    strategies.tick()
    rows = list(csv.DictReader(io.StringIO("".join(strategies.journal.export(job["id"])))))
    selected = [row for row in rows if row["action"].startswith("CLOSE_")]
    assert {row["action"] for row in selected} >= {"CLOSE_APPROVED", "CLOSE_SUBMITTED", "CLOSE_RECONCILED"}
    assert all(row["close_review_id"] == review["id"] and row["order_id"] == exit_id for row in selected)


def test_partially_filled_exit_expiry_retains_units_and_never_replaces_the_order(execution):
    strategies, trading, native, _ = execution
    job, _, review = preview(execution, order_lifetime_seconds=60)
    result = confirm(strategies, review)
    exit_id = result["close_position"]["intent_id"]
    order = retained(trading, exit_id)
    native.settle(order["exchange_order_id"], quantity=1, currency="BTC", fee=0.001, terminal=False)
    reconcile(trading, exit_id)
    native.clock = datetime.fromisoformat(order["strategy_expires_at"]).timestamp()
    strategies.tick()
    reconcile(trading, exit_id)
    for _ in range(3):
        native.clock += 300
        strategies.tick()
    current = strategies.journal.job(job["id"])
    assert current["quantity"] == pytest.approx(job["quantity"] - 1.001)
    assert current["close_position"]["state"] == "reconciled"
    assert current["close_position"]["native_status"] == "canceled"
    assert len(native.calls) == 2 and native.cancels == [order["exchange_order_id"]]
    assert strategies.execution.closing.context(job["id"])["ready"]


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
def test_close_pipeline_covers_all_supported_execution_variants(execution, provider):
    from sibyl.models import ConnectionCreate

    strategies, trading, native, _ = execution
    connection = strategies.store.add_connection(
        ConnectionCreate(
            exchange=provider, label="Simulated closing", api_key="FAKE", secret="FAKE", passphrase="FAKE"
        )
    )
    strategies.market._clients[connection.id] = native
    review = strategies.execution.preview(request(connection))
    job = strategies.execution.start(review["id"], review["confirmation"])
    native.clock += 60
    strategies.tick()
    entry = strategies.execution._intent(strategies.journal.job(job["id"]))
    native.settle(entry["exchange_order_id"])
    reconcile(trading, entry["id"])
    strategies.status(job["id"], "stopped")
    review = strategies.execution.closing.preview(job["id"], ClosePositionRequest())
    confirm(strategies, review)
    assert len(native.calls) == 2 and native.calls[-1][0] == "sell"


def test_http_readiness_preview_confirmation_and_monitor(client, monkeypatch):
    from types import SimpleNamespace

    import pandas as pd
    from test_strategy_execution import Venue

    from sibyl.models import ConnectionCreate
    from sibyl.strategies.execution import runner, venue

    s = client.app.state.services
    s.settings.allow_live_trading = s.settings.allow_strategy_execution = True
    connection = s.store.add_connection(
        ConnectionCreate(exchange="binance-testnet", label="Simulated exit", api_key="FAKE", secret="FAKE")
    )
    native = Venue()
    s.market._clients[connection.id] = native
    for module in (runner, venue):
        monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda: native.clock))
    monkeypatch.setattr(runner, "signals", lambda frame, *args: pd.Series([1] * len(frame)))
    review = s.strategies.execution.preview(request(connection))
    job = s.strategies.execution.start(review["id"], review["confirmation"])
    native.clock += 60
    s.strategies.tick()
    entry = s.strategies.execution._intent(s.strategies.journal.job(job["id"]))
    native.settle(entry["exchange_order_id"])
    reconcile(s.trading, entry["id"])
    s.strategies.status(job["id"], "stopped")
    base = f"/api/v1/strategies/exchange/jobs/{job['id']}"
    assert client.get(base + "/close-position").json()["ready"]
    response = client.post(base + "/close-preview", json={})
    assert response.status_code == 200 and len(native.calls) == 1
    review = response.json()
    url = f"/api/v1/strategies/exchange/close-reviews/{review['id']}/confirm"
    assert client.post(url, json={"confirmation": "yes"}).status_code == 400
    assert client.post(url, json={"confirmation": review["confirmation"]}).status_code == 200
    assert len(native.calls) == 2
    events = client.get(f"/api/v1/strategies/jobs/{job['id']}/events?action=CLOSE_SUBMITTED")
    assert events.status_code == 200 and events.json()["matching_count"] == 1
