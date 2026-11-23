"""Concentration, sampled rolling loss and modeled size against isolated venues."""

from datetime import timedelta

import pytest
from pydantic import ValidationError
from test_portfolio_limits import enable, state
from test_portfolio_limits import shared as shared
from test_strategy_execution import execution as execution
from test_strategy_execution import reconcile, request, submit

from sibyl.strategies.execution.contracts import ExchangeStrategyRequest, ExecutionGuard
from sibyl.strategies.execution.risk.contracts import RELEASE_CONFIRMATION, ReleaseLossLock
from sibyl.strategies.execution.risk.ledger import concentration_refusal, totals
from sibyl.strategies.execution.venue import order_size


@pytest.mark.parametrize("cap", ["max_account_exposure", "max_asset_exposure"])
def test_concentration_cap_is_enforced_before_the_native_write(execution, shared, cap):
    strategies, _, native, _ = execution
    limits, _, _ = shared
    enable(limits, **{cap: 200})
    submit(execution)
    assert native.calls == []
    assert any("exposure cap" in job["error"] for job in strategies.execution.jobs())
    sample = state(limits)["sample"]
    assert sample["accounts"][0]["exposure"] == 0
    assert sample["assets"][0]["exposure"] == 0


def test_concentration_groups_same_asset_across_accounts_and_pairs():
    rows = [
        dict(
            id=str(i),
            account="Account " + account,
            connection_id=account,
            symbol=symbol,
            status="running",
            capital=1000,
            cash=800,
            quantity=1,
            retained=True,
            pending_buys=[dict(quantity=1, price=100)],
        )
        for i, (account, symbol) in enumerate([("one", "BTC/USD"), ("one", "ETH/USD"), ("two", "BTC/USDT")])
    ]
    result = totals(rows, {a: {"price": p} for a, p in [("BTC", 100), ("ETH", 50), ("USD", 1), ("USDT", 1)]})
    assert result["accounts"] == [
        dict(id="one", label="Account one", exposure=350),
        dict(id="two", label="Account two", exposure=200),
    ]
    assert result["assets"] == [dict(asset="BTC", exposure=400), dict(asset="ETH", exposure=150)]
    assert "account exposure cap" in concentration_refusal(result, {"max_account_exposure": 300})
    assert "asset exposure cap" in concentration_refusal(result, {"max_asset_exposure": 399})
    assert concentration_refusal(result, {"max_asset_exposure": 400}) is None


def test_rolling_loss_latches_survives_policy_change_and_requires_window_expiry(execution, shared):
    _, trading, native, _ = execution
    limits, clock, values = shared
    enable(limits, max_daily_loss=10000, max_window_loss=30, loss_window_hours=1)
    _, intent = submit(execution)
    native.settle(intent["exchange_order_id"], fee=0)
    reconcile(trading, intent["id"])
    clock[0] += timedelta(minutes=1)
    values["BTC"] = 80
    limits.check("test")
    current = state(limits)
    assert current["locked"] and current["sample"]["window_loss"] > 90
    assert current["history"][0]["action"] == "window_loss_locked"
    enable(limits, max_daily_loss=10000, max_window_loss=1000, loss_window_hours=1)
    with pytest.raises(ExecutionGuard, match="recorded window expires"):
        limits.release(
            "test", ReleaseLossLock(revision=state(limits)["revision"], confirmation=RELEASE_CONFIRMATION)
        )
    clock[0] += timedelta(hours=1, minutes=1)
    limits.release(
        "test", ReleaseLossLock(revision=state(limits)["revision"], confirmation=RELEASE_CONFIRMATION)
    )
    assert not state(limits)["locked"]
    assert state(limits)["sample"]["window_loss"] == 0


def test_observation_gap_carries_preceding_boundary_instead_of_erasing_loss(execution, shared):
    _, trading, native, _ = execution
    limits, clock, values = shared
    enable(limits, max_daily_loss=10000, max_window_loss=10000, loss_window_hours=1)
    _, intent = submit(execution)
    native.settle(intent["exchange_order_id"], fee=0)
    reconcile(trading, intent["id"])
    limits.check("test")
    baseline = state(limits)["sample"]["as_of"]
    clock[0] += timedelta(hours=3)
    values["BTC"] = 80
    limits.check("test")
    sample = state(limits)["sample"]
    assert sample["window_started_at"] == baseline
    assert sample["window_loss"] > 90
    assert len(native.calls) == 1 and native.cancels == []


def test_window_marks_do_not_overwrite_the_first_mark_per_minute(execution, shared):
    _, _, _, _ = execution
    limits, clock, _ = shared
    enable(limits, max_window_loss=10000)
    limits.check("test")
    with limits.store.db() as db:
        first = db.execute("SELECT payload FROM strategy_loss_marks").fetchone()[0]
    limits.check("test")
    with limits.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM strategy_loss_marks").fetchone()[0] == 1
        assert db.execute("SELECT payload FROM strategy_loss_marks").fetchone()[0] == first
    clock[0] -= timedelta(minutes=1)
    with pytest.raises(ExecutionGuard, match="backwards|newer shared assessment"):
        limits.check("test")


def test_entry_sizing_requires_stop_distance_and_reduces_only_entries(execution):
    _, _, native, connection = execution
    original = request(connection).model_dump()
    original["risk"]["risk_per_entry_pct"] = 1.0
    with pytest.raises(ValidationError, match="stop-loss distance"):
        ExchangeStrategyRequest(**original)
    original["parameters"]["stop_loss_pct"] = 5
    approved = ExchangeStrategyRequest(**original)
    job = dict(
        parameters=approved.parameters.model_dump(), risk=approved.risk.model_dump(), cash=1000, quantity=2
    )
    observed = dict(bid=99.9, ask=100.1, price=100)
    amount, price = order_size(native, job, observed, "buy")
    assert amount * price < 1200 * 1 / (5 + 2)  # fee reserve lowers modeled budget too
    job["risk"]["risk_per_entry_pct"] = None
    larger, _ = order_size(native, job, observed, "buy")
    assert larger > amount
    first, _ = order_size(native, job, observed, "sell")
    job["risk"]["risk_per_entry_pct"] = 0.01
    second, _ = order_size(native, job, observed, "sell")
    assert first == second
