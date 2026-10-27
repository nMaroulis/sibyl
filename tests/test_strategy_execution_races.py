"""Late execution evidence must reopen cancellation checks before another exit."""

import json
from datetime import UTC, datetime

import ccxt
import pandas as pd
import pytest
from test_strategy_cancellation import approve_stop, expiring, retained
from test_strategy_execution import execution as execution
from test_strategy_execution import reconcile, submit

from sibyl.services.ledger import AccountLedger, ledger_fill, now_iso
from sibyl.services.trading import ExchangeTrading
from sibyl.strategies import Strategies
from sibyl.strategies.execution import runner
from sibyl.strategies.execution.contracts import ClosePositionRequest


def fill(native, identity, quantity, *, status="canceled", currency="USDT", fee=0.05):
    """Append an individual execution while maintaining realistic cumulative native totals."""
    native.settle(identity, quantity, currency=currency, fee=fee, terminal=False)
    # Worker scheduling uses a virtual clock; native evidence must remain dated
    # against the real validator clock, even after several follow-up intervals.
    native.fills[-1]["timestamp"] = int(datetime.now(UTC).timestamp() * 1000)
    executions = [row for row in native.fills if row["order"] == identity]
    total = sum(row["amount"] for row in executions)
    order = native.orders[identity]
    requested = next(row[1] for row in native.calls if row[3] == order["clientOrderId"])
    order.update(status=status, filled=total, remaining=requested - total, cost=total * 100)


def finish_checks(strategies, native, count=3):
    for _ in range(count):
        native.clock += 300
        strategies.tick()


def canceled_partial(execution, checks=3):
    strategies, trading, native, _ = execution
    job, intent = submit(execution)
    native.settle(intent["exchange_order_id"], quantity=1, terminal=False)
    reconcile(trading, intent["id"])
    approve_stop(strategies, job["id"])
    strategies.tick()
    reconcile(trading, intent["id"])
    finish_checks(strategies, native, checks)
    return job, intent


def test_mismatched_totals_cannot_exhaust_the_late_status_checks(execution):
    strategies, trading, native, _ = execution
    job, intent = canceled_partial(execution, checks=2)
    identity = intent["exchange_order_id"]
    older = native.orders[identity].copy()
    fill(native, identity, 0.5)
    newer = native.orders[identity].copy()
    native.orders[identity] = older  # Fill history becomes visible before cumulative order status.
    detail = trading.reconciliation.sync(intent["id"], manual=True)
    assert detail["reconciliation"]["status"] == "mismatch"
    finish_checks(strategies, native, 1)
    meta = retained(trading, intent["id"])["strategy_cancellation"]
    assert meta["terminal_checks"] == 0
    assert not strategies.execution.closing.context(job["id"])["ready"]
    native.orders[identity] = newer
    finish_checks(strategies, native, 1)
    assert retained(trading, intent["id"])["filled"] == 1.5
    assert retained(trading, intent["id"])["strategy_cancellation"]["terminal_checks"] == 1
    finish_checks(strategies, native, 2)
    assert strategies.execution.closing.context(job["id"])["ready"]
    assert strategies.journal.job(job["id"])["quantity"] == 1.5
    assert len(native.calls) == len(native.cancels) == 1


@pytest.mark.parametrize("correction", ["new_fill", "base_fee"])
def test_history_import_reopens_completed_checks_and_invalidates_an_exit_review(execution, correction):
    strategies, trading, native, _ = execution
    job, intent = canceled_partial(execution)
    assert strategies.execution.closing.context(job["id"])["ready"]
    review = strategies.execution.closing.preview(job["id"], ClosePositionRequest())
    if correction == "new_fill":
        fill(native, intent["exchange_order_id"], 0.5)
        # Exercise the same central ledger writer as account-history imports,
        # without refreshing the native order or the strategy beforehand.
        metadata = {key: intent[key] for key in ("account", "exchange", "environment")}
        metadata.update(account_id=intent["request"]["connection_id"], symbol="BTC/USDT")
        changed = ledger_fill(native.fills[-1], metadata)
    else:
        native.fills[0]["fees"] = [{"currency": "BTC", "cost": 0.01}]
        with strategies.store.db() as db:
            changed = json.loads(db.execute("SELECT payload FROM account_fills").fetchone()[0])
        changed["fees"] = native.fills[0]["fees"]
    with strategies.store.db() as db:
        AccountLedger.upsert_fills(db, [changed], now_iso())
    assert not strategies.execution.closing.context(job["id"])["ready"]
    with pytest.raises(ValueError, match="late native status checks|reconcile their native fills"):
        strategies.execution.closing.confirm(review["id"], review["confirmation"])
    assert len(native.calls) == 1
    finish_checks(strategies, native, 1)
    reconcile(trading, intent["id"])
    finish_checks(strategies, native, 3)
    assert strategies.execution.closing.context(job["id"])["ready"]
    fresh = strategies.execution.closing.preview(job["id"], ClosePositionRequest())
    expected = 1.5 if correction == "new_fill" else 0.99
    assert fresh["owned_quantity"] == pytest.approx(expected)
    assert fresh["quantity"] + fresh["base_fee_reserve"] <= expected + 1e-12
    assert len(native.calls) == len(native.cancels) == 1


def test_identical_reimports_do_not_restart_completed_cancellation_checks(execution):
    strategies, trading, native, _ = execution
    job, intent = canceled_partial(execution)
    assert strategies.execution.closing.context(job["id"])["ready"]
    for _ in range(3):
        reconcile(trading, intent["id"])
    reads = len(native.reads)
    finish_checks(strategies, native, 1)
    assert len(native.reads) == reads
    assert strategies.execution.closing.context(job["id"])["ready"]
    assert retained(trading, intent["id"])["strategy_cancellation"]["terminal_checks"] == 3


def test_full_fill_wins_a_rejected_cancellation_and_recovers_after_restart_with_writes_off(
    execution, monkeypatch
):
    strategies, trading, native, _ = execution
    job, intent = submit(execution)
    identity = intent["exchange_order_id"]
    native.settle(identity, quantity=1, currency="BTC", fee=0.001, terminal=False)
    reconcile(trading, intent["id"])

    def fill_before_rejection(identity, symbol):
        native.cancels.append(identity)
        fill(native, identity, native.calls[0][1] - 1, status="closed")
        raise ccxt.OrderNotFound("PRIVATE provider detail")

    monkeypatch.setattr(native, "cancel_order", fill_before_rejection)
    approve_stop(strategies, job["id"])
    strategies.tick()
    assert retained(trading, intent["id"])["strategy_cancellation"]["state"] == "unknown"
    strategies.market.settings.allow_live_trading = False
    strategies.market.settings.allow_strategy_execution = False
    restarted = Strategies(strategies.market, strategies.store)
    restarted.attach_execution(ExchangeTrading(strategies.market, strategies.store))
    finish_checks(restarted, native, 1)
    reconcile(trading, intent["id"])
    finish_checks(restarted, native, 3)
    result = restarted.journal.job(job["id"])
    assert retained(trading, intent["id"])["status"] == "closed"
    assert result["quantity"] == pytest.approx(native.calls[0][1] - 0.001)
    assert not result["unresolved_orders"]
    assert len(native.calls) == len(native.cancels) == 1
    assert "PRIVATE" not in json.dumps(restarted.journal.events(job["id"]))


@pytest.mark.parametrize("boundary_change", [None, "fees", "native_totals"])
def test_automatic_exit_waits_and_rechecks_cancellation_evidence_at_submission(
    execution, monkeypatch, boundary_change
):
    strategies, trading, native, _ = execution
    job, intent, deadline = expiring(execution)
    native.settle(intent["exchange_order_id"], quantity=1, terminal=False)
    reconcile(trading, intent["id"])
    native.clock = deadline
    strategies.tick()
    reconcile(trading, intent["id"])
    monkeypatch.setattr(runner, "signals", lambda frame, *args: pd.Series([-1] * len(frame)))
    finish_checks(strategies, native, 1)
    assert len(native.calls) == 1
    assert strategies.journal.job(job["id"])["execution_state"] == "waiting_cancellation"
    original = trading.preview

    def change_after_quote(*args, **kwargs):
        result = original(*args, **kwargs)
        if boundary_change == "fees":
            native.fills[0]["fees"][0]["cost"] = 0.2
            trading.reconciliation.sync(intent["id"], manual=True)
        elif boundary_change == "native_totals":
            fill(native, intent["exchange_order_id"], 0.5)
            trading.lifecycle.refresh(intent["id"])
        return result

    monkeypatch.setattr(trading, "preview", change_after_quote)
    finish_checks(strategies, native, 2)
    result = strategies.journal.job(job["id"])
    if boundary_change:
        assert len(native.calls) == 1
        assert result["status"] == "paused"
        assert "late native status checks" in result["error"]
    else:
        assert len(native.calls) == 2 and native.calls[-1][0] == "sell"
    assert len(native.cancels) == 1


def test_a_failed_history_transaction_cannot_leave_only_the_evidence_revision_changed(execution):
    strategies, trading, native, _ = execution
    job, intent = canceled_partial(execution)
    before = trading.reconciliation.detail(intent["id"])
    with pytest.raises(RuntimeError, match="rollback"):
        with strategies.store.db() as db:
            changed = json.loads(db.execute("SELECT payload FROM account_fills").fetchone()[0])
            changed["fees"][0]["cost"] = 1
            AccountLedger.upsert_fills(db, [changed], now_iso())
            raise RuntimeError("rollback")
    after = trading.reconciliation.detail(intent["id"])
    assert after["fill_revision"] == before["fill_revision"]
    assert after["reconciliation"]["fees"] == before["reconciliation"]["fees"]
    assert strategies.execution.closing.context(job["id"])["ready"]


@pytest.mark.parametrize("other", ["account", "pair"])
def test_same_native_order_id_on_another_account_or_pair_does_not_reopen_checks(execution, other):
    strategies, trading, native, _ = execution
    job, intent = canceled_partial(execution)
    row = {**native.fills[0]}
    metadata = {key: intent[key] for key in ("account", "exchange", "environment")}
    metadata.update(
        account_id="other-account" if other == "account" else intent["request"]["connection_id"],
        symbol="ETH/USDT" if other == "pair" else "BTC/USDT",
    )
    row["symbol"] = metadata["symbol"]
    with strategies.store.db() as db:
        AccountLedger.upsert_fills(db, [ledger_fill(row, metadata)], now_iso())
    assert strategies.execution.closing.context(job["id"])["ready"]
    assert not strategies.execution.cancellations.pending(job["id"])
