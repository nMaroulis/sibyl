"""Fee conventions, versioned review, FIFO conservation and isolated examples."""

import json
from decimal import Decimal

import pytest
from test_transfer_basis import fill, row
from test_transfer_reconciliation import STAMP, change, save_event

from sibyl.services.transfer_allocation import TransferAllocation, allocate
from sibyl.services.transfer_reconciliation import TransferConfirm, TransferConflict


@pytest.fixture
def services(client):
    return client.app.state.services


def events(services, *, out_quantity=1, in_quantity=0.9, out_fee=0.1, in_fee=0, **kwargs):
    out = save_event(
        services.store,
        "fee-out",
        "north",
        quantity=out_quantity,
        fee={"currency": "BTC", "cost": out_fee},
        **kwargs,
    )
    inc = save_event(
        services.store,
        "fee-in",
        "daily",
        "in",
        quantity=in_quantity,
        timestamp_ms=STAMP + 60_000,
        fee={"currency": "BTC", "cost": in_fee},
    )
    return out, inc


def body(out, inc, allocation=None, note="Verified amount conventions and distinct fee charges."):
    from sibyl.services.transfer_reconciliation import fingerprint

    return TransferConfirm(
        outgoing_id=out["id"],
        incoming_id=inc["id"],
        outgoing_fingerprint=fingerprint(out),
        incoming_fingerprint=fingerprint(inc),
        allocation=allocation,
        note=note,
    )


def plan(**values):
    return TransferAllocation(outgoing_amount="total_debit", incoming_amount="net_credit", **values)


@pytest.mark.parametrize("out_mode", ["total_debit", "principal"])
@pytest.mark.parametrize("in_mode", ["net_credit", "gross_receipt"])
def test_all_four_amount_conventions_balance_without_inventing_fees(services, out_mode, in_mode):
    out, inc = events(
        services,
        out_quantity=1.1 if out_mode == "total_debit" else 1,
        in_quantity=0.95 if in_mode == "net_credit" else 1,
        out_fee=0.1,
        in_fee=0.05,
    )
    result = allocate(
        out,
        inc,
        TransferAllocation(outgoing_amount=out_mode, incoming_amount=in_mode, distinct_fees_confirmed=True),
    )
    assert Decimal(result["source_debit"]) == Decimal("1.1")
    assert Decimal(result["dispatch_quantity"]) == 1
    assert Decimal(result["destination_credit"]) == Decimal("0.95")
    assert result["fee_sources"] == {"outgoing": "reported", "incoming": "reported"}


def test_two_nonzero_fees_require_explicit_distinct_charge_acknowledgment(services):
    out, inc = events(services, in_quantity=0.8, out_fee=0.1, in_fee=0.1)
    with pytest.raises(ValueError, match="same fee reported twice"):
        allocate(out, inc, plan())
    assert allocate(out, inc, plan(distinct_fees_confirmed=True))["destination_credit"] == "0.8"


@pytest.mark.parametrize(
    "values,error",
    [
        ({"in_quantity": 0.95}, "does not balance"),
        ({"out_fee": -0.1}, "rebates"),
        ({"in_fee": -0.1}, "rebates"),
        ({"out_fee": 1}, "positive"),
    ],
)
def test_invalid_balances_rebates_and_zero_principal_do_not_save(services, values, error):
    out, inc = events(services, **values)
    with pytest.raises(ValueError, match=error):
        services.transfers.confirm(body(out, inc, plan()))
    assert services.transfers.report()["total"] == 0
    with services.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM transfer_members").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM transfer_audit").fetchone()[0] == 0


def test_missing_fee_is_an_explicit_assertion_and_never_defaults_to_zero(services):
    out, inc = events(services, in_fee=None)
    with pytest.raises(ValueError, match="explicit"):
        services.transfers.confirm(body(out, inc, plan()))
    saved = services.transfers.confirm(body(out, inc, plan(incoming_fee_quantity=0)))
    assert saved["allocation"]["fee_sources"]["incoming"] == "user_asserted"
    assert saved["reviewed"]["incoming"]["fee"]["cost"] is None
    assert saved["allocation"]["request"]["incoming_fee_quantity"] == "0"
    fill(services.performance, "north", 1, stamp=STAMP - 1000)
    assert row(services.performance)["known_open_cost"] == 90
    assert "user assertion" in " ".join(row(services.performance)["issues"])


def test_explicit_zero_missing_fee_can_resolve_coverage_without_zero_cost_basis(services):
    out, inc = events(services, out_fee=None, in_fee=None, in_quantity=1)
    saved = services.transfers.confirm(body(out, inc, plan(outgoing_fee_quantity=0, incoming_fee_quantity=0)))
    fill(services.performance, "north", 1, stamp=STAMP - 1000, price=125)
    result = row(services.performance)
    assert saved["allocation"]["fee_sources"] == {"outgoing": "user_asserted", "incoming": "user_asserted"}
    assert result["known_open_cost"] == 125
    assert result["net_matched_realized"] == 0


def test_reported_or_partially_reported_fees_cannot_be_overridden(services):
    out, inc = events(services)
    with pytest.raises(ValueError, match="cannot be overridden"):
        services.transfers.confirm(body(out, inc, plan(outgoing_fee_quantity=0)))
    out = change(services.store, out, fee_known=False, fee={"currency": None, "cost": 0.1})
    with pytest.raises(ValueError, match="partially reported"):
        allocate(out, inc, plan(outgoing_fee_quantity=0))


@pytest.mark.parametrize("cost", [None, 0.1, -0.1])
def test_foreign_fee_currency_cannot_be_asserted_away(services, cost):
    out, inc = events(services)
    out = change(services.store, out, fee_known=cost is not None, fee={"currency": "BNB", "cost": cost})
    with pytest.raises(ValueError, match="another currency"):
        services.transfers.confirm(body(out, inc, plan(outgoing_fee_quantity=0)))


@pytest.mark.parametrize("value", ["NaN", "Infinity", -0.1, "1e31"])
def test_fee_assertion_validation_is_finite_nonnegative_and_bounded(value):
    with pytest.raises(ValueError):
        plan(outgoing_fee_quantity=value)


def test_preview_is_version_checked_and_has_no_side_effects(services, client):
    out, inc = events(services)
    payload = body(out, inc, plan()).model_dump(mode="json")
    payload.pop("note")
    response = client.post("/api/v1/account-ledger/transfers/preview", json=payload)
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    assert response.json()["allocation"]["source_debit"] == "1.0"
    assert services.transfers.report()["total"] == 0
    change(services.store, out, reference="corrected")
    assert client.post("/api/v1/account-ledger/transfers/preview", json=payload).status_code == 409
    assert (
        client.post("/api/v1/account-ledger/transfers", json={**payload, "note": "Reviewed"}).status_code
        == 409
    )


def test_allocated_review_requires_note_and_cannot_accept_derived_amounts(services, client):
    out, inc = events(services)
    with pytest.raises(ValueError, match="review note"):
        services.transfers.confirm(body(out, inc, plan(), note=""))
    request = body(out, inc, plan()).model_dump(mode="json")
    request["allocation"]["source_debit"] = "0.5"
    assert client.post("/api/v1/account-ledger/transfers", json=request).status_code == 422


def test_changing_or_removing_allocation_is_audited_and_idempotent(services):
    out, inc = events(services)
    request = body(out, inc, plan())
    saved = services.transfers.confirm(request)
    assert services.transfers.confirm(request)["id"] == saved["id"]
    assert len(services.transfers.detail(saved["id"])["audit"]) == 1
    services.transfers.confirm(body(out, inc), saved["id"])
    assert services.transfers.detail(saved["id"])["allocation"] is None
    services.transfers.confirm(request, saved["id"])
    assert len(services.transfers.detail(saved["id"])["audit"]) == 3
    assert (
        services.transfers.detail(saved["id"])["audit"][0]["after"]["reviewed"]["allocation"]["source_debit"]
        == "1.0"
    )


def test_fee_units_are_separate_from_received_basis_and_trading_pnl(services):
    fill(services.performance, "north", 1, stamp=STAMP - 1000, quantity=2)
    out, inc = events(services)
    saved = services.transfers.confirm(body(out, inc, plan()))
    sender, receiver = row(services.performance, "north"), row(services.performance)
    assert sender["known_open_cost"] == 100
    assert sender["transfer_fee_quantity"] == 0.1
    assert sender["transfer_fee_known_inventory_cost"] == 10
    assert receiver["known_open_cost"] == 90
    assert receiver["open_quantity"] == 0.9
    assert sender["disposal_count"] == receiver["disposal_count"] == 0
    assert sender["realized_before_other_fees"] == receiver["realized_before_other_fees"] == 0
    assert sender["net_matched_realized"] is receiver["net_matched_realized"] is None
    assert receiver["basis_transfers"][0]["link_id"] == saved["id"]
    fill(services.performance, "daily", 1, stamp=STAMP + 120_000, quantity=0.9, side="sell", price=200)
    assert row(services.performance)["realized_before_other_fees"] == 90
    assert row(services.performance)["disposal_count"] == 1


def test_principal_excludes_fee_debits_additional_fee_units(services):
    fill(services.performance, "north", 1, stamp=STAMP - 1000, quantity=2)
    out, inc = events(services, in_quantity=1)
    allocation = TransferAllocation(outgoing_amount="principal", incoming_amount="net_credit")
    services.transfers.confirm(body(out, inc, allocation))
    assert row(services.performance, "north")["open_quantity"] == 0.9
    assert row(services.performance)["known_open_cost"] == 100


def test_both_fee_sides_split_lots_in_the_reviewed_order_and_conserve_cost(services):
    fill(services.performance, "north", 1, stamp=STAMP - 2000, quantity=1, price=100)
    fill(services.performance, "north", 2, stamp=STAMP - 1000, quantity=1, price=200)
    out, inc = events(services, out_quantity=1.5, in_quantity=1.3, out_fee=0.2, in_fee=0.3)
    allocation = TransferAllocation(
        outgoing_amount="total_debit", incoming_amount="gross_receipt", distinct_fees_confirmed=True
    )
    services.transfers.confirm(body(out, inc, allocation))
    sender, receiver = row(services.performance, "north"), row(services.performance)
    assert sender["known_open_cost"] == 100
    assert sender["transfer_fee_known_inventory_cost"] == 40
    assert receiver["transfer_fee_known_inventory_cost"] == 60
    assert receiver["known_open_cost"] == 100
    assert receiver["open_quantity"] == 1
    evidence = receiver["basis_transfers"][0]
    assert (
        evidence["outgoing_fee_evidence"]["lots"][0]["origin_id"]
        == evidence["incoming_fee_evidence"]["lots"][0]["origin_id"]
    )
    assert (
        sum(
            item["known_open_cost"] + item["transfer_fee_known_inventory_cost"]
            for item in services.performance.report()["items"]
        )
        == 300
    )


def test_unknown_fee_unit_cost_is_not_silently_zero(services):
    fill(services.performance, "north", 1, stamp=STAMP - 1000, quantity=0.2)
    out, inc = events(services)
    services.transfers.confirm(body(out, inc, plan()))
    sender, receiver = row(services.performance, "north"), row(services.performance)
    assert sender["transfer_fee_unknown_quantity"] == 0.1
    assert sender["transfer_fee_known_inventory_cost"] == 0
    assert receiver["unknown_open_quantity"] == 0.7
    assert receiver["known_open_cost"] == 20
    assert receiver["basis_transfers"][0]["outgoing_fee_evidence"]["lots"][0]["cost"] is None


def test_fee_inventory_basis_does_not_block_a_later_valid_transfer(services):
    fill(services.performance, "north", 1, stamp=STAMP - 1000, quantity=2)
    out, inc = events(services)
    first = services.transfers.confirm(body(out, inc, plan()))
    out2 = save_event(services.store, "second-out", "daily", quantity=0.5, timestamp_ms=STAMP + 120_000)
    inc2 = save_event(
        services.store, "second-in", "reserve", "in", quantity=0.5, timestamp_ms=STAMP + 180_000
    )
    services.transfers.confirm(body(out2, inc2))
    result = row(services.performance, "reserve")
    assert result["known_open_cost"] == 50
    assert result["open_quantity"] == 0.5
    services.transfers.remove(first["id"])
    missing = services.performance.report(account_id="reserve")
    assert missing["items"] == [] and missing["transfer_summary"]["unapplied"] == 1
    services.transfers.confirm(body(out, inc, plan()), first["id"])
    assert row(services.performance, "reserve")["known_open_cost"] == 50


def test_source_changes_invalidate_allocations_and_stale_reviews(services):
    fill(services.performance, "north", 1, stamp=STAMP - 1000, quantity=2)
    out, inc = events(services)
    old = body(out, inc, plan())
    saved = services.transfers.confirm(old)
    changed = change(services.store, out, quantity=1.1, fee={"currency": "BTC", "cost": 0.2})
    assert row(services.performance)["known_open_cost"] == 0
    assert services.transfers.detail(saved["id"])["status"] == "needs_review"
    with pytest.raises(TransferConflict):
        services.transfers.confirm(old, saved["id"])
    services.transfers.confirm(body(changed, inc, plan()), saved["id"])
    assert row(services.performance)["known_open_cost"] == 90
    assert row(services.performance, "north")["transfer_fee_known_inventory_cost"] == 20


def test_failed_audit_rolls_back_allocation_and_memberships(services):
    out, inc = events(services)
    with services.store.db() as db:
        db.execute(
            "CREATE TRIGGER fail_fee_review BEFORE INSERT ON transfer_audit BEGIN SELECT RAISE(ABORT,'failure'); END"
        )
    with pytest.raises(Exception, match="failure"):
        services.transfers.confirm(body(out, inc, plan()))
    assert services.transfers.report()["total"] == 0
    with services.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM transfer_members").fetchone()[0] == 0


def test_isolated_allocation_preview_never_reads_or_writes_real_records(services, client):
    sample = services.transfers.example()
    pair = next(item for item in sample["candidates"] if item["asset"] == "BTC")
    payload = body(pair["outgoing"], pair["incoming"], plan(incoming_fee_quantity=0)).model_dump(mode="json")
    payload.pop("note")
    result = client.post("/api/v1/account-ledger/transfers/example/preview", json=payload)
    assert result.status_code == 200 and result.headers["Cache-Control"] == "no-store"
    assert result.json()["allocation"]["destination_credit"] == "0.0499"
    assert services.transfers.report()["total"] == 0
    assert client.get("/api/v1/account-ledger/funding").json()["total"] == 0
    payload["outgoing_id"] = "a" * 64
    assert client.post("/api/v1/account-ledger/transfers/example/preview", json=payload).status_code == 404


def test_fee_performance_fixture_and_agent_agree_without_account_side_effects(services, client):
    data = client.get("/api/v1/account-ledger/performance/example?transfers=true&fees=true").json()
    assert data["example_kind"] == "transfer_fees"
    assert data["totals"][0]["matched_realized"] == 2481
    assert data["totals"][0]["net_matched_realized"] is None
    assert sum(item["known_open_cost"] for item in data["items"]) == 6450
    assert sum(item["transfer_fee_known_inventory_cost"] for item in data["items"]) == 40
    evidence = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "accountant",
            "message": "Explain fee units and missing valuation.",
            "context": {
                "performance_view": True,
                "performance_example": True,
                "performance_transfer_example": True,
                "performance_fee_example": True,
            },
        },
    ).json()["evidence"]
    assert evidence["totals"] == data["totals"]
    assert evidence["transfer_evidence"][0]["outgoing_fee_evidence"]["known_cost"] == 40
    assert services.performance.report()["items"] == []
    assert services.transfers.report()["total"] == 0
    assert services.store.orders() == []
    json.dumps(data, allow_nan=False)


def test_extreme_fractional_assertions_cannot_round_a_fee_out_of_the_equation(services):
    out, inc = events(services, out_fee=None, in_quantity=1)
    for value in (Decimal("1e-1000000"), Decimal("1e-31")):
        with pytest.raises(ValueError, match="precision"):
            allocate(out, inc, plan(outgoing_fee_quantity=value))


def test_api_roundtrip_saved_allocation_with_zero_assertion_is_stable(services, client):
    out, inc = events(services, in_fee=None)
    payload = body(out, inc, plan(incoming_fee_quantity=0)).model_dump(mode="json")
    saved = client.post("/api/v1/account-ledger/transfers", json=payload)
    assert saved.status_code == 200
    identity = saved.json()["id"]
    again = client.post(f"/api/v1/account-ledger/transfers/{identity}/review", json=payload)
    assert again.status_code == 200
    detail = client.get(f"/api/v1/account-ledger/transfers/{identity}").json()
    assert len(detail["audit"]) == 1
    assert detail["allocation"]["request"]["incoming_fee_quantity"] == "0"
