"""Real strategy lifecycle against a controlled venue, with no exchange credentials."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import ccxt
import pytest
from test_strategy_cancellation import approve_stop, retained
from test_strategy_closing import owned
from test_strategy_execution import execution as execution
from test_strategy_execution import reconcile

from sibyl.strategies import Strategies
from sibyl.strategies.execution.contracts import ClosePositionRequest, LiquidationRequest
from sibyl.strategies.execution.controls import RELEASE_CONFIRMATION, ControlAction


def review_plan(execution, **changes):
    strategies, _, _, _ = execution
    job, entry = owned(execution)
    policy = LiquidationRequest(**({"max_orders": 2, "max_order_base": 1} | changes))
    return job, entry, strategies.execution.liquidation.preview(job["id"], policy)


def approve(strategies, plan):
    return strategies.execution.liquidation.confirm(plan["job_id"], plan["id"], plan["confirmation"])


def current_order(strategies, trading, job_id):
    plan = strategies.execution.liquidation.view(job_id)
    return retained(trading, plan["orders"][-1]["id"])


def fill_child(strategies, trading, native, job_id, *, quantity=None, terminal=True):
    order = current_order(strategies, trading, job_id)
    native.settle(order["exchange_order_id"], quantity=quantity, terminal=terminal)
    reconcile(trading, order["id"])
    return order


def test_plan_is_read_only_until_worker_and_runs_two_capped_orders(execution):
    strategies, trading, native, _ = execution
    job, _, plan = review_plan(execution)
    assert len(native.calls) == 1 and len(trading.list_orders()) == 1
    assert plan["first_order_quantity"] == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: approve(strategies, plan), range(2)))
    assert all(result["status"] == "active" for result in results)
    assert len(native.calls) == 1
    strategies.tick()
    assert len(native.calls) == 2 and native.calls[-1][:3] == ("sell", 1, plan["minimum_price"])
    strategies.tick()
    assert len(native.calls) == 2

    order = fill_child(strategies, trading, native, job["id"], quantity=0.4, terminal=False)
    strategies.tick()
    assert len(native.calls) == 2
    native.orders[order["exchange_order_id"]]["status"] = "closed"
    trading.lifecycle.refresh(order["id"])
    reconcile(trading, order["id"])
    native.bid, native.ask = 110, 110.1
    strategies.tick()
    assert len(native.calls) == 3 and native.calls[-1][:3] == ("sell", 1, plan["minimum_price"])
    fill_child(strategies, trading, native, job["id"])
    strategies.tick()
    final = strategies.execution.liquidation.view(job["id"])
    assert final["status"] == "completed" and final["sold_quantity"] == 1.4
    assert strategies.journal.job(job["id"])["quantity"] == pytest.approx(job["quantity"] - 1.4)
    assert approve(strategies, plan)["status"] == "completed"
    assert len(native.calls) == 3
    journal = strategies.journal.events(job["id"], action="CLOSE_APPROVED")
    assert len(journal["items"]) == 2
    assert all(row["liquidation_id"] == plan["id"] for row in journal["items"])


def test_waits_for_cancellation_late_checks_before_another_sell(execution):
    strategies, trading, native, _ = execution
    job, _, plan = review_plan(execution)
    approve(strategies, plan)
    strategies.tick()
    intent = fill_child(strategies, trading, native, job["id"], quantity=0.4, terminal=False)
    with strategies.store.db() as db:
        retained_intent = trading.lifecycle.read(db, intent["id"])
        retained_intent["strategy_expires_at"] = "2000-01-01T00:00:00+00:00"
        trading.lifecycle.write(db, retained_intent)
    strategies.tick()
    reconcile(trading, intent["id"])
    assert native.cancels == [intent["exchange_order_id"]]
    assert len(native.calls) == 2
    for _ in range(2):
        native.clock += 300
        strategies.tick()
        assert len(native.calls) == 2
    native.clock += 300
    strategies.tick()
    assert len(native.calls) == 3


@pytest.mark.parametrize(
    "cause", ["bid", "correction", "halt", "withdrawn", "restart", "expiry", "credentials"]
)
def test_plan_cannot_send_more_after_its_authority_changes(execution, cause):
    strategies, trading, native, connection = execution
    job, entry, plan = review_plan(execution)
    approve(strategies, plan)
    strategies.tick()
    fill_child(strategies, trading, native, job["id"])
    if cause == "bid":
        native.bid, native.ask = 90, 90.05
    elif cause == "correction":
        native.fills[0]["fees"][0]["cost"] += 0.5
        reconcile(trading, entry["id"])
    elif cause == "halt":
        controls = strategies.execution.controls
        controls.change(ControlAction(action="halt", revision=0))
        controls.change(ControlAction(action="release", revision=1, confirmation=RELEASE_CONFIRMATION))
    elif cause == "withdrawn":
        strategies.execution.liquidation.stop(job["id"], plan["id"])
    elif cause == "restart":
        restarted = Strategies(strategies.market, strategies.store)
        restarted.attach_execution(trading)
        strategies = restarted
    elif cause == "expiry":
        with strategies.store.db() as db:
            current = strategies.execution.liquidation._read(db, plan["id"], job["id"])
            current["ends_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
            strategies.execution.liquidation._save(db, current)
    else:
        with strategies.store.db() as db:
            db.execute("UPDATE connections SET credentials=x'6162' WHERE id=?", (connection.id,))
    strategies.tick()
    final = strategies.execution.liquidation.view(job["id"])
    assert final["status"] != "active" and len(final["orders"]) == 1
    assert len(native.calls) == 2


def test_uncertain_submission_never_replays_or_advances(execution):
    strategies, trading, native, _ = execution
    job, _, plan = review_plan(execution)
    approve(strategies, plan)
    native.failure = ccxt.RequestTimeout("private transport response")
    strategies.tick()
    strategies.tick()
    record = strategies.execution.liquidation.view(job["id"])
    assert record["status"] in {"blocked", "interrupted"} and len(record["orders"]) == 1
    order = current_order(strategies, trading, job["id"])
    assert order["status"] == "unknown" and "response" not in record["message"]
    assert len(native.calls) == 2


def test_final_write_rechecks_order_evidence_and_child_cannot_be_confirmed_by_public_endpoint(
    execution, monkeypatch
):
    strategies, trading, native, _ = execution
    job, entry, plan = review_plan(execution)
    approve(strategies, plan)
    original = trading.preview

    def correct_after_prepare(*args, **kwargs):
        intent = original(*args, **kwargs)
        native.fills[0]["fees"][0]["cost"] += 0.1
        reconcile(trading, entry["id"])
        return intent

    monkeypatch.setattr(trading, "preview", correct_after_prepare)
    strategies.tick()
    assert len(native.calls) == 1
    assert strategies.execution.liquidation.view(job["id"])["status"] == "blocked"
    child = current_order(strategies, trading, job["id"])
    assert child["status"] == "preview" and child["strategy_abandoned"]
    with pytest.raises(ValueError, match="Only the worker"):
        strategies.execution.closing.confirm(child["strategy_close_review_id"], "yes")


def test_competing_standalone_confirmation_and_reviewed_stop_cancel(execution):
    strategies, _, native, _ = execution
    job, _ = owned(execution)
    close = strategies.execution.closing.preview(job["id"], ClosePositionRequest())
    plans = strategies.execution.liquidation
    plan = plans.preview(job["id"], LiquidationRequest(max_order_base=1))
    approve(strategies, plan)
    with pytest.raises(ValueError, match="Stop the active liquidation"):
        strategies.execution.closing.confirm(close["id"], close["confirmation"])
    strategies.tick()
    approve_stop(strategies, job["id"])
    assert plans.view(job["id"])["status"] == "stopped"
    strategies.tick()
    assert len(native.calls) == 2 and len(native.cancels) == 1


def test_http_plan_review_confirms_only_locally_and_stops_by_plan_id(manual_client, execution, monkeypatch):
    strategies, _, native, _ = execution
    job, _ = owned(execution)
    monkeypatch.setattr(manual_client.app.state.services, "strategies", strategies)
    path = f"/api/v1/strategies/exchange/jobs/{job['id']}/liquidation"
    assert manual_client.get(path).json() is None
    response = manual_client.post(path + "/preview", json={"max_order_base": 1, "max_orders": 2})
    assert response.status_code == 200, response.text
    plan = response.json()
    confirmed = manual_client.post(
        f"{path}/{plan['id']}/confirm", json={"confirmation": plan["confirmation"]}
    )
    assert confirmed.status_code == 200 and confirmed.headers["cache-control"] == "no-store"
    assert len(native.calls) == 1 and manual_client.get(path).json()["orders"] == []
    stopped = manual_client.post(f"{path}/{plan['id']}/stop")
    assert stopped.json()["status"] == "stopped"
    strategies.tick()
    assert len(native.calls) == 1
    events = manual_client.get(f"/api/v1/strategies/jobs/{job['id']}/events?action=LIQUIDATION").json()
    assert len(events["items"]) == 2 and events["items"][0]["liquidation_id"] == plan["id"]
    assert "credential_version" not in response.text + confirmed.text + json.dumps(events)


def test_fresh_stop_cancel_withdraws_plan_after_an_earlier_stop_review(execution):
    strategies, _, native, _ = execution
    job, _ = owned(execution)
    stop = strategies.execution.stop_reviews
    early = stop.preview(job["id"])
    stop.confirm(early["id"], early["confirmation"])
    plans = strategies.execution.liquidation
    plan = plans.preview(job["id"], LiquidationRequest(max_order_base=1))
    approve(strategies, plan)
    strategies.tick()
    stop.confirm(early["id"], early["confirmation"])
    assert plans.view(job["id"])["status"] == "active"
    fresh = stop.preview(job["id"])
    stop.confirm(fresh["id"], fresh["confirmation"])
    assert plans.view(job["id"])["status"] == "stopped"
    strategies.tick()
    assert len(native.calls) == 2 and len(native.cancels) == 1


def test_plan_requires_more_time_than_one_order_lifetime():
    with pytest.raises(ValueError, match="plan duration must exceed"):
        LiquidationRequest(duration_minutes=5, order_lifetime_seconds=300)
