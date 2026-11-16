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
    return repairs.approve(
        review["job_id"],
        review["id"],
        review["confirmation"],
        allow_quantity_changes=review.get("allow_quantity_changes", False),
    )


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


@pytest.mark.parametrize("base_fee", [0.01, -0.01])
def test_quantity_repair_replays_an_executed_sale_and_both_handoffs(
    execution, ownership, monkeypatch, base_fee
):
    strategies, trading, native, _ = execution
    source, entry, middle, target = executed_family(execution, ownership, monkeypatch)
    identities = [row["id"] for row in (source, middle, target)]
    with strategies.store.db() as db:
        original = db.execute("SELECT payload FROM strategy_ownership_events ORDER BY sequence").fetchall()
        marks = {
            event["id"]: event["reference_value"] / event["quantity"]
            for identity in identities
            for event in ledger.events(db, identity)
        }
    native.fills[0]["fees"] = [{"currency": "BTC", "cost": base_fee}]
    reconcile(trading, entry["id"])
    repairs = strategies.execution.ownership_repairs
    with pytest.raises(ValueError, match="recorded quantity"):
        repairs.preview(target["id"])
    review = repairs.preview(target["id"], allow_quantity_changes=True)
    assert review["runs"][2]["quantity"] == pytest.approx(target["quantity"] - base_fee)
    assert review["runs"][1]["realized_pnl"] == pytest.approx(
        99.9 - source["quantity"] * 100 / (source["quantity"] - base_fee)
    )
    assert all(ownership.state(identity)["stale"] for identity in identities)
    with pytest.raises(ValueError, match="recorded quantity"):
        repairs.approve(target["id"], review["id"], review["confirmation"])
    result = approve(repairs, review)
    assert result["allow_quantity_changes"]
    assert approve(repairs, review) == result
    with strategies.store.db() as db:
        assert (
            db.execute("SELECT payload FROM strategy_ownership_events ORDER BY sequence").fetchall()
            == original
        )
        rows = [event for identity in identities for event in ledger.events(db, identity)]
        assert sum(row["quantity"] for row in rows) == pytest.approx(0)
        assert sum(row["reference_value"] for row in rows) == pytest.approx(0)
        assert all(
            row["reference_value"] == pytest.approx(marks[row["id"]] * row["quantity"]) for row in rows
        )
        assert len(positions(db, trading, "test")) == 3
    restarted = Strategies(strategies.market, strategies.store)
    restarted.attach_execution(trading)
    assert restarted.execution.ownership.state(target["id"])["quantity"] == pytest.approx(
        target["quantity"] - base_fee
    )
    assert not any(ownership.state(identity)["stale"] for identity in identities)
    assert len(native.calls) == 2


def test_reflow_refuses_if_a_descendant_sale_exceeds_corrected_units(execution, ownership, monkeypatch):
    strategies, trading, native, _ = execution
    source, entry, middle, target = executed_family(execution, ownership, monkeypatch)
    native.fills[0]["fees"] = [{"currency": "BTC", "cost": source["quantity"] - 0.5}]
    reconcile(trading, entry["id"])
    with pytest.raises(ValueError, match="exceed the strategy-owned position"):
        strategies.execution.ownership_repairs.preview(target["id"], allow_quantity_changes=True)
    assert all(ownership.state(row["id"])["stale"] for row in (source, middle, target))
    with strategies.store.db() as db:
        assert not db.execute("SELECT 1 FROM strategy_ownership_adjustments").fetchall()
    assert len(native.calls) == 2


def test_zero_handoff_can_be_repaired_again_using_its_original_reference_price(
    execution, ownership, monkeypatch
):
    strategies, trading, native, _ = execution
    source, entry, _, target = executed_family(execution, ownership, monkeypatch)
    repairs = strategies.execution.ownership_repairs
    with strategies.store.db() as db:
        incoming = ledger.events(db, target["id"])[0]
    native.fills[0]["fees"] = [{"currency": "BTC", "cost": source["quantity"] - 1.0}]
    reconcile(trading, entry["id"])
    zero = approve(repairs, repairs.preview(target["id"], allow_quantity_changes=True))
    with strategies.store.db() as db:
        corrected = ledger.events(db, target["id"])[0]
        assert corrected["quantity"] == corrected["cost_basis"] == corrected["reference_value"] == 0
    native.fills[0]["fees"] = [{"currency": "USDT", "cost": 0.1}]
    reconcile(trading, entry["id"])
    restored = approve(repairs, repairs.preview(target["id"], allow_quantity_changes=True))
    assert restored["id"] != zero["id"]
    with strategies.store.db() as db:
        row = ledger.events(db, target["id"])[0]
        assert row["quantity"] == incoming["quantity"]
        assert row["reference_value"] == pytest.approx(incoming["reference_value"])
        assert row["cost_basis"] == pytest.approx(incoming["cost_basis"])
    assert len(native.calls) == 2


def test_http_quantity_switch_must_match_the_exact_preview(manual_client, execution, ownership, monkeypatch):
    strategies, trading, native, _ = execution
    _, entry, _, target = handoff(execution, ownership)
    strategies.status(target["id"], "paused")
    native.fills[0]["fees"] = [{"currency": "BTC", "cost": 0.01}]
    reconcile(trading, entry["id"])
    monkeypatch.setattr(manual_client.app.state.services, "strategies", strategies)
    route = f"/api/v1/strategies/exchange/jobs/{target['id']}/ownership/repair"
    assert manual_client.get(route).status_code == 400
    response = manual_client.get(route, params={"allow_quantity_changes": True})
    assert response.status_code == 200, response.text
    review = response.json()
    body = {"review_id": review["id"], "confirmation": review["confirmation"]}
    assert manual_client.post(route, json=body).status_code == 400
    saved = manual_client.post(route, json={**body, "allow_quantity_changes": True})
    assert saved.status_code == 200, saved.text
    assert saved.json()["allow_quantity_changes"]
    assert manual_client.post(route, json=body).status_code == 400
