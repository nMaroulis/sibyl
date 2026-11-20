"""A reconciled buy can supply basis, while the user's availability assertion stays explicit."""

import json

import pytest
from test_strategy_execution import execution as execution
from test_strategy_ownership import ownership as ownership
from test_strategy_sale_funding import OPTIONS, approve, shortfall

from sibyl.services.trading.discovery import normalized_order
from sibyl.strategies.execution.ownership.acquisitions import Acquisitions
from sibyl.strategies.execution.ownership.sale_funding import active_funding


def imported_buy(execution, *, earlier=True, fee_currency="BTC"):
    strategies, trading, native, connection = execution
    instant = native.fills[-1]["timestamp"] + (-30_000 if earlier else 0)
    order = normalized_order(
        {
            "id": "external-order",
            "clientOrderId": "opaque-native-label",
            "symbol": "BTC/USDT",
            "side": "buy",
            "status": "closed",
            "filled": 0.7,
            "cost": 63,
            "timestamp": instant,
        }
    )
    with strategies.store.db() as db:
        assert trading.discovery._upsert(db, connection, order) == "imported"
        order_id = db.execute(
            "SELECT id FROM exchange_orders WHERE json_extract(payload,'$.exchange_order_id')=?",
            (order["id"],),
        ).fetchone()[0]
    native.fills.append(
        {
            "id": "external-buy",
            "order": order["id"],
            "symbol": "BTC/USDT",
            "side": "buy",
            "timestamp": instant,
            "amount": 0.7,
            "price": 90,
            "cost": 63,
            "fees": [{"currency": fee_currency, "cost": 0.1}],
        }
    )
    result = trading.reconciliation.sync(order_id, manual=True)
    assert result["reconciliation"]["status"] == "matched", result["reconciliation"]
    with strategies.store.db() as db:
        local_id = db.execute("SELECT id FROM account_fills WHERE trade_id='external-buy'").fetchone()[0]
    return local_id, order_id


def link(sale, buy_id):
    return {
        "fill_id": sale["fill_id"],
        "acquisition_fill_id": buy_id,
        "note": "Held as unmanaged units from before the sale",
    }


def test_reconciled_venue_discovered_buy_derives_basis_and_revalidates_after_source_edit(
    execution, ownership, monkeypatch
):
    strategies, trading, native, _ = execution
    _, _, middle, target = shortfall(execution, ownership, monkeypatch)
    buy_id, intent_id = imported_buy(execution)
    repairs = strategies.execution.ownership_repairs
    (sale,) = repairs.preview(target["id"], **OPTIONS)["funding_requirements"]
    (buy,) = sale["acquisition_candidates"]
    assert buy["fill_id"] == buy_id and buy["origin"] == "venue_discovered"
    # 0.7 gross - 0.1 base fee leaves 0.6; the sale consumes 0.5 of that acquisition.
    assert buy["estimated_basis"] == pytest.approx(52.5)
    inputs = [link(sale, buy_id)]
    draft = repairs.preview(target["id"], **OPTIONS, sale_funding=inputs)
    data = draft["funding_changes"][0]
    assert data["cost_basis"] == pytest.approx(52.5) and data["acquisition"]["trade_id"] == "external-buy"
    assert "proof" not in json.dumps(data)
    saved = approve(repairs, draft, inputs)
    assert not ownership.state(middle["id"])["stale"]
    assert ownership.state(middle["id"])["funded_sales"][0]["linked_buy"]
    assert len(native.calls) == 2

    # A correction to the external buy must invalidate funding even though the linked sale is unchanged.
    native.fills[-1]["fees"][0]["cost"] = 0.05
    trading.reconciliation.sync(intent_id, manual=True)
    assert ownership.state(middle["id"])["stale"]
    replacement = repairs.preview(target["id"], **OPTIONS, sale_funding=inputs)
    assert replacement["id"] != saved["id"]
    assert replacement["funding_changes"][0]["cost_basis"] == pytest.approx(63 * 0.5 / 0.65)
    approve(repairs, replacement, inputs)
    assert not ownership.state(middle["id"])["stale"] and len(native.calls) == 2


@pytest.mark.parametrize("condition", ["same_time", "foreign_fee", "unreconciled"])
def test_buy_ineligible_for_native_basis_cannot_be_selected(execution, ownership, monkeypatch, condition):
    strategies, trading, _, _ = execution
    _, _, _, target = shortfall(execution, ownership, monkeypatch)
    buy_id, order_id = imported_buy(
        execution,
        earlier=condition != "same_time",
        fee_currency="BNB" if condition == "foreign_fee" else "BTC",
    )
    if condition == "unreconciled":
        with strategies.store.db() as db:
            checkpoint = trading.reconciliation._read(db, order_id)
            checkpoint["caught_up"] = False
            trading.reconciliation._write(db, order_id, checkpoint)
    repairs = strategies.execution.ownership_repairs
    (sale,) = repairs.preview(target["id"], **OPTIONS)["funding_requirements"]
    assert sale["acquisition_candidates"] == []
    with pytest.raises(ValueError, match="earlier reconciled non-strategy buy"):
        repairs.preview(target["id"], **OPTIONS, sale_funding=[link(sale, buy_id)])


def test_existing_reservations_count_against_the_buy_but_can_be_reallocated_in_one_review(
    execution, ownership, monkeypatch
):
    strategies, _, _, _ = execution
    _, _, middle, target = shortfall(execution, ownership, monkeypatch)
    buy_id, _ = imported_buy(execution)
    repairs = strategies.execution.ownership_repairs
    (sale,) = repairs.preview(target["id"], **OPTIONS)["funding_requirements"]
    inputs = [link(sale, buy_id)]
    draft = repairs.preview(target["id"], **OPTIONS, sale_funding=inputs)
    approve(repairs, draft, inputs)
    with strategies.store.db() as db:
        _, existing = active_funding(db, middle["id"])
        extra = {**existing[sale["fill_id"]], "quantity": 0.2}
        with pytest.raises(ValueError, match="already reserved"):
            Acquisitions(db).check_repair([({}, {"second_sale": extra})])
        Acquisitions(db).check_repair([(existing, {}), ({}, {"second_sale": extra})])


def test_api_rejects_supplying_both_asserted_and_derived_basis(
    manual_client, execution, ownership, monkeypatch
):
    strategies, _, _, _ = execution
    _, _, _, target = shortfall(execution, ownership, monkeypatch)
    buy_id, _ = imported_buy(execution)
    monkeypatch.setattr(manual_client.app.state.services, "strategies", strategies)
    path = f"/api/v1/strategies/exchange/jobs/{target['id']}/ownership"
    (sale,) = manual_client.get(f"{path}/repair", params=OPTIONS).json()["funding_requirements"]
    response = manual_client.post(
        f"{path}/repair-preview",
        json={**OPTIONS, "sale_funding": [{**link(sale, buy_id), "cost_basis": 0}]},
    )
    assert response.status_code == 400
    valid = manual_client.post(
        f"{path}/repair-preview",
        json={**OPTIONS, "sale_funding": [link(sale, buy_id)]},
    )
    assert valid.status_code == 200, valid.text


def test_quote_fee_is_included_in_proportional_basis(execution, ownership, monkeypatch):
    strategies, _, _, _ = execution
    _, _, _, target = shortfall(execution, ownership, monkeypatch)
    imported_buy(execution, fee_currency="USDT")
    (sale,) = strategies.execution.ownership_repairs.preview(target["id"], **OPTIONS)["funding_requirements"]
    assert sale["acquisition_candidates"][0]["estimated_basis"] == pytest.approx(63.1 * 0.5 / 0.7)
