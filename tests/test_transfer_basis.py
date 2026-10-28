"""Offline conservation, chronology, invalidation and dependency-scope contracts."""

import json

import pytest
from test_account_performance import execution, retained
from test_transfer_reconciliation import STAMP, change, request, save_event

from sibyl.services.funding_ledger import FundingLedger
from sibyl.services.performance import AccountPerformance, OpeningInventory
from sibyl.services.transfer_reconciliation import TransferReconciliation


@pytest.fixture
def basis(client):
    return client.app.state.services.performance


def fill(basis, account, identity, *, stamp, **values):
    row = execution(identity, account_id=account, environment="production", timestamp=stamp, **values)
    retained(basis, row)
    return row


def link(basis, source="north", destination="daily", *, stamp=STAMP, quantity=1, **values):
    service = TransferReconciliation(basis.store)
    out = save_event(
        basis.store, f"out-{source}-{destination}-{stamp}", source, quantity=quantity, timestamp_ms=stamp
    )
    inc = save_event(
        basis.store,
        f"in-{source}-{destination}-{stamp}",
        destination,
        "in",
        quantity=quantity,
        timestamp_ms=stamp + 60_000,
        **values,
    )
    saved = service.confirm(request(service, out, inc, "Reviewed own-account movement."))
    return saved, out, inc


def row(basis, account="daily", **filters):
    return basis.report(account_id=account, **filters)["items"][0]


def test_carryover_conserves_quantity_cost_and_has_no_disposal_or_writes(basis):
    buy = fill(basis, "north", 1, stamp=STAMP - 2000, quantity=2, price=100)
    saved, _, _ = link(basis)
    before = FundingLedger(basis.store).events()
    result = basis.report()
    sender, receiver = row(basis, "north"), row(basis)
    assert sender["open_quantity"] == receiver["open_quantity"] == 1
    assert sender["known_open_cost"] == receiver["known_open_cost"] == 100
    assert sender["disposal_count"] == receiver["disposal_count"] == 0
    assert sender["net_matched_realized"] == receiver["net_matched_realized"] == 0
    assert sender["unresolved_funding_count"] == receiver["unresolved_funding_count"] == 0
    assert sender["transfer_out_count"] == receiver["transfer_in_count"] == 1
    evidence = receiver["basis_transfers"][0]
    assert evidence["link_id"] == saved["id"] and evidence["status"] == "applied"
    assert evidence["lots"][0]["origin_id"] == buy["id"]
    assert evidence["lots"][0]["acquired_at_ms"] == buy["timestamp_ms"]
    assert result["transfer_summary"]["applied"] == 1
    assert before == FundingLedger(basis.store).events()
    with basis.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM account_fills").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM transfer_audit").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_destination_uses_original_age_before_newer_local_lots_and_splits_cost(basis):
    fill(basis, "north", 1, stamp=STAMP - 4000, quantity=2, price=100)
    fill(basis, "daily", 1, stamp=STAMP - 3000, quantity=1, price=200)
    link(basis)
    fill(basis, "daily", 2, stamp=STAMP + 120_000, side="sell", quantity=1.5, price=300)
    result = row(basis)
    assert result["net_matched_realized"] == 250  # 450 - 100 carried - 100 local
    assert result["known_open_cost"] == 100
    assert result["open_quantity"] == 0.5
    assert row(basis, "north")["known_open_cost"] == 100


def test_chain_and_round_trip_carry_original_provenance_once(basis):
    buy = fill(basis, "north", 1, stamp=STAMP - 1000, quantity=2, price=100)
    link(basis)
    link(basis, "daily", "reserve", stamp=STAMP + 120_000)
    link(basis, "reserve", "north", stamp=STAMP + 240_000)
    report = basis.report(account_id="north", symbol="BTC/USDT", environment="production")
    result = report["items"][0]
    assert result["open_quantity"] == 2 and result["known_open_cost"] == 200
    assert result["transfer_in_count"] == result["transfer_out_count"] == 1
    assert result["basis_transfers"][-1]["lots"][0]["origin_id"] == buy["id"]
    assert row(basis, "daily")["open_quantity"] == row(basis, "reserve")["open_quantity"] == 0
    assert report["dependency_account_count"] == 3
    assert all(item["net_matched_realized"] == 0 for item in basis.report()["items"])


def test_account_and_pair_filters_load_donor_and_intermediate_history_first(basis):
    fill(basis, "north", 1, stamp=STAMP - 1000, quantity=2, price=100)
    link(basis)
    link(basis, "daily", "reserve", stamp=STAMP + 120_000)
    fill(basis, "reserve", 1, stamp=STAMP + 240_000, side="sell", price=150)
    result = basis.report(account_id="reserve", symbol="BTC/USDT", environment="production")
    assert len(result["items"]) == 1 and result["fill_count"] == 1
    assert result["dependency_fill_count"] == 2
    assert result["items"][0]["net_matched_realized"] == 50
    assert basis.report(account_id="reserve", environment="demo")["items"] == []


def test_source_correction_removal_restoration_recompute_without_materialized_lots(basis):
    buy = fill(basis, "north", 1, stamp=STAMP - 1000, price=100)
    saved, out, inc = link(basis)
    service = TransferReconciliation(basis.store)
    assert row(basis)["known_open_cost"] == 100
    changed = change(basis.store, inc, reference="updated")
    assert row(basis)["known_open_cost"] == 0
    assert row(basis)["net_matched_realized"] is None
    assert "changed" in row(basis)["basis_transfers"][0]["reason"]
    service.confirm(request(service, out, changed), saved["id"])
    assert row(basis)["known_open_cost"] == 100
    retained(basis, {**buy, "notional": 130, "price": 130})
    assert row(basis)["known_open_cost"] == 130  # Source execution corrections also replay.
    service.remove(saved["id"])
    assert basis.report(account_id="daily")["items"] == []
    assert row(basis, "north")["known_open_cost"] == 130
    assert row(basis, "north")["net_matched_realized"] is None
    service.confirm(request(service, out, changed), saved["id"])
    assert row(basis)["known_open_cost"] == 130
    restarted = AccountPerformance(basis.market, basis.store)
    assert restarted.report(account_id="daily")["items"][0]["known_open_cost"] == 130


@pytest.mark.parametrize(
    "values,reason",
    [
        ({"quantity": 0.99}, "amounts differ"),
        ({"fee": {"currency": "BTC", "cost": None}}, "zero fees"),
        ({"fee": {"currency": "BTC", "cost": 0.01}}, "zero fees"),
        ({"fee": {"currency": "BNB", "cost": -0.01}}, "zero fees"),
    ],
)
def test_unsupported_amounts_or_fees_never_infer_cost(basis, values, reason):
    fill(basis, "north", 1, stamp=STAMP - 1000, price=100)
    service = TransferReconciliation(basis.store)
    out = save_event(basis.store, "out")
    inc = save_event(basis.store, "in", "daily", "in", timestamp_ms=STAMP + 60_000, **values)
    service.confirm(request(service, out, inc, "Manual review of native fees."))
    result = row(basis)
    assert result["known_open_cost"] == result["open_quantity"] == 0
    assert result["net_matched_realized"] is None
    assert reason in result["basis_transfers"][0]["reason"]
    assert row(basis, "north")["open_quantity"] == 1


@pytest.mark.parametrize("symbol", ["BTC/USD", "ETH/BTC"])
def test_quote_mismatch_and_cross_market_are_not_converted_or_combined(basis, symbol):
    fill(basis, "north", 1, stamp=STAMP - 1000)
    fill(basis, "daily", 1, stamp=STAMP - 2000, symbol=symbol)
    saved, _, _ = link(basis)
    result = basis.report(symbol="BTC/USDT")
    assert result["transfer_summary"]["unapplied"] == 1
    assert result["items"][0]["net_matched_realized"] is None
    assert result["items"][0]["basis_transfers"][0]["link_id"] == saved["id"]
    assert "denomination" in result["items"][0]["basis_transfers"][0]["reason"]


@pytest.mark.parametrize("unreliable", ["funding", "missing_fee", "third_fee", "notional", "fill_tie"])
def test_unreliable_source_never_exports_known_basis(basis, unreliable):
    values = {}
    if unreliable == "missing_fee":
        values["fees"] = []
    elif unreliable == "third_fee":
        values["fees"] = [{"currency": "BNB", "cost": 0.1}]
    elif unreliable == "notional":
        values["cost"] = None
    fill(basis, "north", 1, stamp=STAMP - 2000, **values)
    if unreliable == "funding":
        save_event(basis.store, "earlier", "north", "in", timestamp_ms=STAMP - 1000)
    if unreliable == "fill_tie":
        fill(basis, "north", 2, stamp=STAMP - 2000)
    link(basis)
    result = row(basis)
    assert result["known_open_cost"] == 0 and result["net_matched_realized"] is None
    assert "Source inventory" in result["basis_transfers"][0]["reason"]


def test_later_unresolved_funding_does_not_rewrite_previously_carried_known_basis(basis):
    fill(basis, "north", 1, stamp=STAMP - 1000, quantity=2)
    link(basis)
    save_event(basis.store, "later", "north", "in", timestamp_ms=STAMP + 120_000)
    assert row(basis)["known_open_cost"] == 100
    assert row(basis, "north")["net_matched_realized"] is None


def test_unknown_source_shortfall_never_becomes_zero_cost_or_newer_known_basis(basis):
    fill(basis, "north", 1, stamp=STAMP - 2000, quantity=0.4)
    fill(basis, "daily", 1, stamp=STAMP - 1000, quantity=1, price=200)
    link(basis)
    fill(basis, "daily", 2, stamp=STAMP + 120_000, side="sell", quantity=0.5, price=300)
    result = row(basis)
    assert result["unknown_sold_quantity"] == 0.5
    assert result["realized_before_other_fees"] == 0
    assert result["unknown_open_quantity"] == pytest.approx(0.1)
    evidence = result["basis_transfers"][0]
    assert evidence["shortfall_quantity"] == pytest.approx(0.6)
    assert evidence["unknown_quantity"] == pytest.approx(0.6)
    assert evidence["lots"][-1]["cost"] is None
    assert evidence["lots"][-1]["acquired_at_ms"] is None
    assert result["net_matched_realized"] is None


def test_unknown_cost_opening_with_known_date_carries_through_chain(basis):
    # Opening assertions are allowed on saved accounts; use the existing saved Demo
    # ID but matching normalized demo facts for this fixture.
    basis.save_opening("demo", OpeningInventory(symbol="BTC/USDT", quantity=2, as_of="2023-01-01T00:00:00Z"))
    service = TransferReconciliation(basis.store)
    out = save_event(basis.store, "out", "demo", environment="demo")
    inc = save_event(basis.store, "in", "daily", "in", environment="demo", timestamp_ms=STAMP + 60_000)
    service.confirm(request(service, out, inc))
    result = row(basis)
    assert result["open_quantity"] == result["unknown_open_quantity"] == 1
    assert result["known_open_cost"] == 0
    assert result["basis_transfers"][0]["unknown_quantity"] == 1


def test_missing_source_invalidates_downstream_basis_even_when_event_row_is_gone(basis):
    fill(basis, "north", 1, stamp=STAMP - 1000)
    _, out, _ = link(basis)
    link(basis, "daily", "reserve", stamp=STAMP + 120_000)
    with basis.store.db() as db:
        db.execute("DELETE FROM funding_events WHERE id=?", (out["id"],))
    assert row(basis, "north")["net_matched_realized"] is None
    assert row(basis, "reserve")["known_open_cost"] == 0
    assert row(basis, "reserve")["net_matched_realized"] is None


@pytest.mark.parametrize("offset", [0, -1000])
def test_equal_or_reversed_receipt_is_not_reordered_to_make_basis(offset, basis):
    fill(basis, "north", 1, stamp=STAMP - 3000)
    service = TransferReconciliation(basis.store)
    out = save_event(basis.store, "out")
    inc = save_event(basis.store, "in", "daily", "in", timestamp_ms=STAMP + offset)
    service.confirm(request(service, out, inc))
    assert "ordering" in row(basis)["basis_transfers"][0]["reason"]
    assert row(basis)["known_open_cost"] == 0


def test_fill_at_dispatch_time_and_equal_origin_ages_are_provisional(basis):
    fill(basis, "north", 1, stamp=STAMP)
    saved, _, _ = link(basis)
    assert "share a timestamp" in row(basis)["basis_transfers"][0]["reason"]
    TransferReconciliation(basis.store).remove(saved["id"])
    # Two distinct lots acquired at the same time on separate accounts have no
    # cross-account native ordering, even though the transfer itself is later.
    fill(basis, "older", 1, stamp=STAMP)
    fill(basis, "newer", 1, stamp=STAMP)
    link(basis, "older", "newer", stamp=STAMP + 120_000)
    result = row(basis, "newer")
    assert result["transfer_in_count"] == 1 and result["net_matched_realized"] is None
    assert "acquisition timestamp" in " ".join(result["issues"])


def test_deposit_before_first_fill_is_included_in_coverage(basis):
    fill(basis, "north", 1, stamp=STAMP + 1000)
    save_event(basis.store, "early", "north", "in", timestamp_ms=STAMP)
    result = row(basis, "north")
    assert result["funding_event_count"] == result["unresolved_funding_count"] == 1
    assert result["net_matched_realized"] is None


def test_transfer_and_dependency_budgets_reject_instead_of_truncating(basis, monkeypatch):
    fill(basis, "north", 1, stamp=STAMP - 1000)
    link(basis)
    monkeypatch.setattr("sibyl.services.performance.MAX_FILLS", 0)
    with pytest.raises(ValueError, match="dependencies"):
        basis.report(account_id="daily")
    monkeypatch.setattr("sibyl.services.performance.MAX_FILLS", 20_000)
    monkeypatch.setattr("sibyl.services.transfer_basis.MAX_LINKS", 0)
    with pytest.raises(ValueError, match="dependency budget"):
        basis.report()
    monkeypatch.setattr("sibyl.services.transfer_basis.MAX_LINKS", 2000)
    monkeypatch.setattr("sibyl.services.transfer_basis.MAX_FUNDING", 0)
    with pytest.raises(ValueError, match="Funding dependency"):
        basis.report()


def test_report_survives_disconnected_source_and_never_reads_providers(basis, monkeypatch):
    fill(basis, "north", 1, stamp=STAMP - 1000)
    link(basis)
    monkeypatch.setattr(basis.market, "account_balances", lambda *_: pytest.fail("private read"))
    monkeypatch.setattr(basis.market, "metadata", lambda *_: pytest.fail("price read"))
    assert row(basis)["known_open_cost"] == 100
    json.dumps(basis.report(), allow_nan=False)


def test_multiple_lot_slices_and_explicit_zero_cost_are_preserved(basis):
    fill(basis, "north", 1, stamp=STAMP - 3000, quantity=1, price=1, fees=[{"currency": "USDT", "cost": -1}])
    fill(basis, "north", 2, stamp=STAMP - 2000, quantity=1, price=120)
    link(basis, quantity=1.5)
    fill(basis, "daily", 1, stamp=STAMP + 120_000, quantity=1.5, side="sell", price=200)
    result = row(basis)
    assert result["net_matched_realized"] == 240
    assert result["basis_transfers"][0]["carried_cost"] == 60
    assert result["basis_transfers"][0]["lots"][0]["cost"] == 0
    assert row(basis, "north")["known_open_cost"] == 60


def test_base_buy_fee_is_already_in_lot_quantity_and_quote_fees_carry_with_cost(basis):
    fill(
        basis,
        "north",
        1,
        stamp=STAMP - 3000,
        quantity=1,
        price=100,
        fees=[{"currency": "BTC", "cost": 0.1}, {"currency": "USDT", "cost": 2}],
    )
    link(basis, quantity=0.45)
    fill(
        basis,
        "daily",
        1,
        stamp=STAMP + 120_000,
        quantity=0.45,
        side="sell",
        price=200,
        fees=[{"currency": "USDT", "cost": 1}],
    )
    assert row(basis)["net_matched_realized"] == 38  # 90 - 1 - half of 102
    assert row(basis, "north")["known_open_cost"] == 51


def test_opening_boundary_prevents_double_counting_a_previous_receipt(basis):
    basis.save_opening(
        "demo", OpeningInventory(symbol="BTC/USDT", quantity=2, total_cost=200, as_of="2024-01-05T00:00:00Z")
    )
    fill(basis, "north", 1, stamp=STAMP - 3000)
    service = TransferReconciliation(basis.store)
    out = save_event(basis.store, "out", "north", environment="demo")
    inc = save_event(basis.store, "in", "demo", "in", environment="demo", timestamp_ms=STAMP + 60_000)
    service.confirm(request(service, out, inc))
    result = row(basis, "demo")
    assert result["open_quantity"] == 2 and result["known_open_cost"] == 200
    assert result["transfer_in_count"] == result["funding_event_count"] == 0
    assert basis.report()["transfer_summary"]["applied"] == 0


def test_multiple_funding_events_at_same_time_do_not_choose_an_arbitrary_order(basis):
    fill(basis, "north", 1, stamp=STAMP - 2000, quantity=2)
    link(basis)
    link(basis, "north", "reserve", stamp=STAMP)
    assert "Multiple funding" in row(basis)["basis_transfers"][0]["reason"]
    assert row(basis)["known_open_cost"] == 0


def test_retained_market_environment_cannot_supply_another_environments_basis(basis):
    retained(basis, execution(1, account_id="north", environment="test", timestamp=STAMP - 1000))
    link(basis)
    result = row(basis)
    assert result["known_open_cost"] == 0 and result["net_matched_realized"] is None
    assert "environments differ" in result["basis_transfers"][0]["reason"]
    # Filtering production cannot import test lots: a source shortfall stays unknown.
    filtered = row(basis, environment="production")
    assert filtered["known_open_cost"] == 0
    assert filtered["unknown_open_quantity"] == 1


def test_transfer_only_recipient_can_get_balance_checked_mark(client, monkeypatch):
    from sibyl.models import ConnectionCreate

    service = client.app.state.services
    destination = service.store.add_connection(
        ConnectionCreate(exchange="binance", label="Destination", api_key="fake", secret="fake")
    )
    service.store.activate_account(destination.id, True)
    fill(service.performance, "north", 1, stamp=STAMP - 1000)
    link(service.performance, destination=destination.id)
    monkeypatch.setattr(service.market, "metadata", lambda: {"source": "binance"})
    monkeypatch.setattr(service.market, "account_balances", lambda *_: [{"asset": "BTC", "total": 1}])
    monkeypatch.setattr(
        "sibyl.services.performance.Valuation.price",
        lambda _, asset: {"price": 150 if asset == "BTC" else 1, "status": "fresh", "route": []},
    )
    result = row(service.performance, destination.id, mark=True)
    assert result["unrealized"] == 50 and result["mark_status"] == "fresh"
    assert result["fill_count"] == 0
    service.store.delete_connection(destination.id)
    assert row(service.performance, destination.id)["known_open_cost"] == 100


def test_transfer_example_and_agent_are_isolated_and_use_same_snapshot(client, monkeypatch):
    before = client.get("/api/v1/account-ledger/fills").json()
    sample = client.get("/api/v1/account-ledger/performance/example?transfers=true")
    assert sample.status_code == 200 and sample.headers["Cache-Control"] == "no-store"
    data = sample.json()
    assert data["example_kind"] == "transfers"
    assert data["transfer_summary"]["applied"] == 1
    assert data["totals"][0]["net_matched_realized"] == 2491
    assert sum(item["known_open_cost"] for item in data["items"]) == 6500
    monkeypatch.setattr(
        client.app.state.services.market, "account_balances", lambda *_: pytest.fail("private read")
    )
    answer = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "accountant",
            "message": "Explain the transferred lots.",
            "context": {
                "performance_view": True,
                "performance_example": True,
                "performance_transfer_example": True,
            },
        },
    )
    assert answer.status_code == 200
    evidence = answer.json()["evidence"]
    assert evidence["example_kind"] == "transfers" and evidence["totals"] == data["totals"]
    assert evidence["evidence_lot_limit"] == 5
    assert client.get("/api/v1/account-ledger/fills").json() == before
    assert client.get("/api/v1/account-ledger/transfers").json()["total"] == 0
    assert client.get("/api/v1/account-ledger/performance").json()["items"] == []


def test_agent_reports_applied_and_unapplied_basis_with_evidence_limits(client):
    basis = client.app.state.services.performance
    fill(basis, "north", 1, stamp=STAMP - 1000)
    link(basis)
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "accountant",
            "message": "Explain this basis.",
            "context": {"performance_view": True, "performance_account_id": "daily", "symbol": "BTC/USDT"},
        },
    )
    assert response.status_code == 200
    evidence = response.json()["evidence"]
    assert evidence["transfer_summary"]["applied"] == 1
    assert evidence["items"][0]["known_open_cost"] == 100
    assert evidence["transfer_evidence"][0]["status"] == "applied"
    assert evidence["evidence_transfer_per_market_limit"] == 3


def test_unapplied_btc_link_does_not_taint_an_unrelated_eth_market(basis):
    fill(basis, "north", 1, stamp=STAMP - 3000)
    fill(basis, "north", 2, stamp=STAMP - 2000, symbol="ETH/USDT")
    fill(basis, "daily", 1, stamp=STAMP - 1000, symbol="BTC/USD")
    link(basis)
    result = basis.report(account_id="north")
    eth = next(item for item in result["items"] if item["base"] == "ETH")
    assert eth["net_matched_realized"] == 0
    assert eth["basis_transfers"] == []


def test_same_account_mixed_environment_fills_are_never_totaled_together(basis):
    fill(basis, "north", 1, stamp=STAMP - 3000)
    retained(basis, execution(2, account_id="north", environment="test", timestamp=STAMP - 2000))
    with pytest.raises(ValueError, match="never combined across environments"):
        basis.report()
    assert row(basis, "north", environment="production")["open_quantity"] == 1


def test_receiving_only_disconnected_account_is_available_in_filter_choices(client):
    basis = client.app.state.services.performance
    fill(basis, "north", 1, stamp=STAMP - 1000)
    link(basis)
    response = client.get("/api/v1/account-ledger/performance/markets")
    assert response.headers["Cache-Control"] == "no-store"
    assert {item["id"] for item in response.json()["accounts"]} == {"north", "daily"}
    assert response.json()["symbols"] == ["BTC/USDT"]
