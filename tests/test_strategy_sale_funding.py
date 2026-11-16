"""Historical funding is explicit, bounded to the native sale and reversible on new evidence."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from test_strategy_execution import execution as execution
from test_strategy_execution import reconcile
from test_strategy_ownership import ownership as ownership
from test_strategy_ownership_repair import executed_family

from sibyl.strategies import Strategies
from sibyl.strategies.execution.accounting import project
from sibyl.strategies.execution.ownership.sale_funding import active_funding
from sibyl.strategies.execution.risk.ledger import positions

OPTIONS = {"allow_quantity_changes": True, "review_sale_funding": True}


def shortfall(execution, ownership, monkeypatch):
    strategies, trading, native, _ = execution
    source, entry, middle, target = executed_family(execution, ownership, monkeypatch)
    native.fills[0]["fees"] = [{"currency": "BTC", "cost": source["quantity"] - 0.5}]
    reconcile(trading, entry["id"])
    return source, entry, middle, target


def assertion(required, basis=24):
    return {
        "fill_id": required["fill_id"],
        "cost_basis": basis,
        "note": "Unmanaged units from account records",
    }


def approve(repairs, draft, assertions=()):
    return repairs.approve(
        draft["job_id"],
        draft["id"],
        draft["confirmation"],
        **OPTIONS,
        sale_funding=assertions,
    )


def test_funded_historical_sale_replays_without_creating_spendable_units_or_editing_fills(
    execution, ownership, monkeypatch
):
    strategies, trading, native, _ = execution
    source, _, middle, target = shortfall(execution, ownership, monkeypatch)
    repairs = strategies.execution.ownership_repairs
    identity = target["id"]
    missing = repairs.preview(identity, **OPTIONS)
    (required,) = missing["funding_requirements"]
    assert required["job_id"] == middle["id"] and required["quantity"] == 0.5
    assert required["reference_value"] == 50 and required["missing_basis"]
    assert missing["id"] is missing["confirmation"] is None
    assert missing["runs"] == [] and missing["funding_changes"] == []
    with pytest.raises(ValueError, match="evidence or confirmation changed"):
        approve(repairs, missing)
    with strategies.store.db() as db:
        originals = db.execute("SELECT payload FROM account_fills ORDER BY id").fetchall()
    user_assertions = [assertion(required)]
    draft = repairs.preview(identity, **OPTIONS, sale_funding=user_assertions)
    assert draft["runs"][1]["realized_pnl"] == pytest.approx(99.9 - source["quantity"] * 100 - 24)
    assert draft["runs"][1]["quantity"] == draft["runs"][2]["quantity"] == 0
    with pytest.raises(ValueError, match="evidence or confirmation changed"):
        approve(repairs, draft, [assertion(required, 23)])
    with ThreadPoolExecutor(2) as pool:
        result, duplicate = pool.map(lambda _: approve(repairs, draft, user_assertions), range(2))
    assert result == duplicate
    with strategies.store.db() as db:
        assert db.execute("SELECT payload FROM account_fills ORDER BY id").fetchall() == originals
        version, active = active_funding(db, middle["id"])
        assert version == draft["id"] and active[required["fill_id"]]["cost_basis"] == 24
        assert len(positions(db, trading, "test")) == 3

    restarted = Strategies(strategies.market, strategies.store)
    restarted.attach_execution(trading)
    mid = project(middle, trading)
    assert mid["cash"] == middle["cash"] and mid["quantity"] == mid["entry_cost"] == 0
    assert not mid["ownership_stale"] and not restarted.execution.ownership.state(identity)["stale"]
    report = restarted.execution.performance.report(middle["id"])
    assert any(
        flow["action"] == "historical sale funding" and flow["value"] == 50 for flow in report["flows"]
    )
    assert len(native.calls) == 2


def test_native_fee_revision_invalidates_funding_and_requires_a_fresh_assertion(
    execution, ownership, monkeypatch
):
    strategies, trading, native, _ = execution
    _, _, middle, target = shortfall(execution, ownership, monkeypatch)
    repairs = strategies.execution.ownership_repairs
    missing = repairs.preview(target["id"], **OPTIONS)
    inputs = [assertion(missing["funding_requirements"][0])]
    first = repairs.preview(target["id"], **OPTIONS, sale_funding=inputs)
    approve(repairs, first, inputs)
    closed_sale = next(
        order for order in mid_orders(strategies, middle) if order["request"]["side"] == "sell"
    )
    native.fills[-1]["fees"][0]["cost"] = 0.2
    reconcile(trading, closed_sale["id"])
    assert ownership.state(middle["id"])["stale"]
    discovery = repairs.preview(target["id"], **OPTIONS)
    assert discovery["id"] is None and discovery["funding_requirements"][0]["missing_basis"]
    second = repairs.preview(target["id"], **OPTIONS, sale_funding=inputs)
    assert second["id"] != first["id"]
    approve(repairs, second, inputs)
    assert not ownership.state(middle["id"])["stale"]
    assert len(native.calls) == 2


def mid_orders(strategies, job):
    return project(job, strategies.execution.trading)["orders"]


def test_restored_units_retire_the_historical_funding_explicitly(execution, ownership, monkeypatch):
    strategies, trading, native, _ = execution
    _, entry, middle, target = shortfall(execution, ownership, monkeypatch)
    repairs = strategies.execution.ownership_repairs
    identity = target["id"]
    missing = repairs.preview(identity, **OPTIONS)
    inputs = [assertion(missing["funding_requirements"][0])]
    first = repairs.preview(identity, **OPTIONS, sale_funding=inputs)
    paid = approve(repairs, first, inputs)
    native.fills[0]["fees"] = [{"currency": "USDT", "cost": 0.1}]
    reconcile(trading, entry["id"])
    with pytest.raises(ValueError, match="Enable Review sale funding"):
        repairs.preview(identity, allow_quantity_changes=True)
    retirement = repairs.preview(identity, **OPTIONS)
    assert (
        retirement["funding_requirements"] == [] and retirement["funding_changes"][0]["status"] == "retired"
    )
    approve(repairs, retirement)
    with strategies.store.db() as db:
        assert active_funding(db, middle["id"]) == (retirement["id"], {})
    assert repairs.receipt(middle["id"], paid["id"])["funding_changes"][0]["status"] == "approved"
    assert not any(
        row["action"] == "historical sale funding"
        for row in strategies.execution.performance.report(middle["id"])["flows"]
    )
    assert len(native.calls) == 2


def test_api_discovery_and_assertions_are_private_and_read_only_until_approval(
    manual_client, execution, ownership, monkeypatch
):
    strategies, _, native, _ = execution
    _, _, _, target = shortfall(execution, ownership, monkeypatch)
    monkeypatch.setattr(manual_client.app.state.services, "strategies", strategies)
    prefix = f"/api/v1/strategies/exchange/jobs/{target['id']}/ownership"
    discovery = manual_client.get(f"{prefix}/repair", params=OPTIONS)
    assert discovery.status_code == 200 and discovery.headers["cache-control"] == "no-store"
    required = discovery.json()["funding_requirements"][0]
    assert "proof" not in required
    options = {**OPTIONS, "sale_funding": [assertion(required)]}
    response = manual_client.post(f"{prefix}/repair-preview", json=options)
    assert response.status_code == 200, response.text
    draft = response.json()
    assert ownership.state(target["id"])["stale"]
    assert (
        manual_client.post(
            f"{prefix}/repair",
            json={**OPTIONS, "review_id": draft["id"], "confirmation": draft["confirmation"]},
        ).status_code
        == 400
    )
    result = manual_client.post(
        f"{prefix}/repair",
        json={**options, "review_id": draft["id"], "confirmation": draft["confirmation"]},
    )
    assert result.status_code == 200, result.text
    assert "proof" not in result.json()["funding_changes"][0]
    assert "funding_updates" not in result.json()
    assert not ownership.state(target["id"])["stale"] and len(native.calls) == 2
