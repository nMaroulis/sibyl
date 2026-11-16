"""Repair local cost-basis receipts with real replay over controlled exchange fills."""

import json
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import pytest
from test_strategy_execution import execution as execution
from test_strategy_execution import reconcile, request
from test_strategy_fee_review import priced_candle
from test_strategy_ownership import handoff
from test_strategy_ownership import ownership as ownership

from sibyl.strategies import Strategies
from sibyl.strategies.execution import runner
from sibyl.strategies.execution.ownership import ledger
from sibyl.strategies.execution.risk.ledger import positions


def approve(repairs, review):
    return repairs.approve(review["job_id"], review["id"], review["confirmation"])


def executed_family(execution, ownership, monkeypatch):
    strategies, trading, native, connection = execution
    source, entry, _, middle = handoff(execution, ownership)
    monkeypatch.setattr(runner, "signals", lambda frame, *args: pd.Series([-1] * len(frame)))
    native.clock += 60
    strategies.tick()
    sell = strategies.execution._intent(strategies.journal.job(middle["id"]))
    native.settle(sell["exchange_order_id"], quantity=1.0)
    reconcile(trading, sell["id"])
    middle = strategies.status(middle["id"], "stopped")
    next_review = strategies.execution.preview(request(connection, handoff_from=middle["id"]))
    target = strategies.execution.start(next_review["id"], next_review["confirmation"])
    target = strategies.status(target["id"], "paused")
    return source, entry, middle, target


def test_replays_a_late_fee_correction_through_a_descendant_sale_and_second_handoff(
    execution, ownership, monkeypatch
):
    strategies, trading, native, _ = execution
    source, entry, middle, target = executed_family(execution, ownership, monkeypatch)
    ids = [job["id"] for job in (source, middle, target)]
    repairs = strategies.execution.ownership_repairs
    with strategies.store.db() as db:
        original = db.execute("SELECT payload FROM strategy_ownership_events ORDER BY sequence").fetchall()
        flows = [sum(event["reference_value"] for event in ledger.events(db, identity)) for identity in ids]

    native.fills[0]["fees"][0]["cost"] += 0.5
    reconcile(trading, entry["id"])
    assert all(ownership.state(identity)["stale"] for identity in ids)
    changes = repairs.preview(target["id"])
    assert len(changes["adjustments"]) == 4 and [row["job_id"] for row in changes["runs"]] == ids
    fraction_sold = 1 / source["quantity"]
    assert changes["runs"][1]["realized_pnl"] == pytest.approx(middle["realized_pnl"] - 0.5 * fraction_sold)
    assert changes["runs"][2]["entry_cost"] == pytest.approx(target["entry_cost"] + 0.5 * (1 - fraction_sold))
    assert all(ownership.state(identity)["stale"] for identity in ids)

    with ThreadPoolExecutor(2) as pool:
        receipts = list(pool.map(lambda _: approve(repairs, changes), range(2)))
    assert receipts[0] == receipts[1]
    restored = Strategies(strategies.market, strategies.store)
    restored.attach_execution(trading)
    for identity in ids:
        assert not restored.execution.ownership.state(identity)["stale"]
        assert restored.execution.ownership_repairs.receipt(identity, changes["id"]) == receipts[0]
        assert restored.journal.events(identity, action="OWNERSHIP_REPAIR")["matching_count"] == 1
    with strategies.store.db() as db:
        assert (
            db.execute("SELECT payload FROM strategy_ownership_events ORDER BY sequence").fetchall()
            == original
        )
        assert [sum(event["reference_value"] for event in ledger.events(db, i)) for i in ids] == flows
        assert len(positions(db, trading, "test")) == 3
    restored.tick()
    assert restored.journal.job(target["id"])["status"] == "paused"
    assert restored.journal.job(target["id"])["entry_cost"] == pytest.approx(changes["runs"][2]["entry_cost"])
    assert restored.journal.job(middle["id"])["realized_pnl"] == pytest.approx(
        changes["runs"][1]["realized_pnl"]
    )
    assert len(native.calls) == 2


def test_changed_handoff_units_keep_runs_blocked(execution, ownership):
    strategies, trading, native, _ = execution
    _, entry, _, target = handoff(execution, ownership)
    strategies.status(target["id"], "paused")
    native.fills[0]["fees"] = [{"currency": "BTC", "cost": 0.01}]
    reconcile(trading, entry["id"])
    with pytest.raises(ValueError, match="recorded quantity"):
        strategies.execution.ownership_repairs.preview(target["id"])
    assert ownership.state(target["id"])["stale"] and len(native.calls) == 1


def test_correction_after_preview_requires_a_new_review_and_running_runs_are_rejected(execution, ownership):
    strategies, trading, native, _ = execution
    _, entry, _, target = handoff(execution, ownership)
    repairs = strategies.execution.ownership_repairs
    native.fills[0]["fees"][0]["cost"] = 0.5
    reconcile(trading, entry["id"])
    with pytest.raises(ValueError, match="Pause all affected"):
        repairs.preview(target["id"])
    strategies.status(target["id"], "paused")
    first = repairs.preview(target["id"])
    native.fills[0]["fees"][0]["cost"] = 0.8
    reconcile(trading, entry["id"])
    with pytest.raises(ValueError, match="evidence or confirmation changed"):
        approve(repairs, first)
    assert ownership.state(target["id"])["stale"]
    current = repairs.preview(target["id"])
    approve(repairs, current)
    assert not ownership.state(target["id"])["stale"]
    assert len(native.calls) == 1


def test_a_repeated_native_fee_value_gets_a_distinct_repair_after_an_intermediate_revision(
    execution, ownership
):
    strategies, trading, native, _ = execution
    _, entry, _, target = handoff(execution, ownership)
    identity = target["id"]
    strategies.status(identity, "paused")
    repairs = strategies.execution.ownership_repairs
    reviewed = []
    for fee in (0.5, 0.1, 0.5):
        native.fills[0]["fees"][0]["cost"] = fee
        reconcile(trading, entry["id"])
        preview = repairs.preview(identity)
        reviewed.append(preview["id"])
        approve(repairs, preview)
        assert not ownership.state(identity)["stale"]
    assert len(set(reviewed)) == 3 and len(native.calls) == 1


def test_http_approval_and_receipt_are_scoped_to_affected_runs(
    manual_client, execution, ownership, monkeypatch
):
    strategies, trading, native, _ = execution
    source, entry, _, target = handoff(execution, ownership)
    strategies.status(target["id"], "paused")
    native.fills[0]["fees"][0]["cost"] += 0.5
    reconcile(trading, entry["id"])
    monkeypatch.setattr(manual_client.app.state.services, "strategies", strategies)
    prefix = "/api/v1/strategies/exchange/jobs/"
    route = f"{prefix}{target['id']}/ownership/repair"
    response = manual_client.get(route)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    review = response.json()
    invalid = manual_client.post(route, json={"review_id": review["id"], "confirmation": "yes"})
    assert invalid.status_code == 400
    approved = manual_client.post(
        route, json={"review_id": review["id"], "confirmation": review["confirmation"]}
    )
    assert approved.status_code == 200, approved.text
    receipt = manual_client.get(f"{prefix}{source['id']}/ownership/repairs/{review['id']}")
    assert receipt.status_code == 200 and receipt.json() == approved.json()
    unknown = manual_client.get(f"{prefix}other-run/ownership/repairs/{review['id']}")
    assert unknown.status_code == 404
    evidence = f"/api/v1/strategies/jobs/{target['id']}/events?action=OWNERSHIP_REPAIR"
    journal = manual_client.get(evidence).json()["items"]
    assert len(journal) == 1 and journal[0]["ownership_repair_id"] == review["id"]
    assert '"pins"' not in json.dumps(review) + receipt.text and "FAKE" not in response.text
    assert len(native.calls) == 1


def test_fee_prices_can_be_approved_before_an_ownership_repair(execution, ownership):
    strategies, trading, native, _ = execution
    source, entry, _, target = handoff(execution, ownership)
    strategies.status(target["id"], "paused")
    native.fills[0]["fees"] = [{"currency": "BNB", "cost": 0.01}]
    reconcile(trading, entry["id"])
    repairs = strategies.execution.ownership_repairs
    with pytest.raises(ValueError, match="Approve other-asset fee prices"):
        repairs.preview(target["id"])
    priced_candle(strategies, source, native)
    assert strategies.execution.performance.report(source["id"])["fee_review_pending"]
    fee_service = strategies.execution.fee_reviews
    review = fee_service.preview(source["id"])
    assert review["batch_quote"] == 5
    fee_service.approve(source["id"], review["review_id"])
    assert ownership.state(target["id"])["stale"]
    approve(repairs, repairs.preview(target["id"]))
    assert not ownership.state(target["id"])["stale"] and len(native.calls) == 1
