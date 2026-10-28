"""Native fee rules and explicit local assertions never rewrite funding observations."""

import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

from sibyl.accounting.balance_checks.journal import CheckJournal
from sibyl.accounting.balance_checks.movements import compare
from sibyl.accounting.funding import FundingReviews, balance_effect
from sibyl.accounting.funding.reviews import FundingReviewConflict, ReviewFunding, ReviewVersion
from sibyl.accounting.funding.rules import fingerprint
from sibyl.exchanges.funding import _binance_row
from sibyl.services.funding_ledger import FundingLedger


def event(**changes):
    return {
        "id": "a" * 64,
        "native_id": "native",
        "reference": None,
        "account_id": "retained",
        "account": "Retained account",
        "exchange": "binance",
        "environment": "production",
        "kind": "withdrawal",
        "asset": "BTC",
        "timestamp_ms": 150_000,
        "posted_ms": 150_000,
        "created_at": "1970-01-01T00:02:30+00:00",
        "direction": "out",
        "quantity": 1,
        "status": "completed",
        "internal": False,
        "fee": {"currency": "BTC", "cost": 0.1},
        "fee_known": True,
        "amount_basis": "provider_reported",
        "wallet_scope": "configured",
        **changes,
    }


def persist(store, row):
    FundingLedger(store)
    with store.db() as db:
        db.execute(
            "INSERT INTO funding_events VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
            (
                row["id"],
                row["account_id"],
                row["kind"],
                row["native_id"],
                row["asset"],
                row["timestamp_ms"],
                row["status"],
                json.dumps(row),
                "first",
                "last",
            ),
        )
    return row


def request(row, **changes):
    return ReviewFunding(
        source_version=fingerprint(row),
        wallet_scope="configured",
        amount_convention="principal",
        note="Checked exchange wallet statement.",
        **changes,
    )


@pytest.mark.parametrize(
    "direction,amount,fee,expected",
    [
        ("out", 1, 0.1, "-1.1"),
        ("in", 1, 0.1, "0.9"),
        ("out", 1, -0.1, "-0.9"),
        ("in", 1, -0.1, "1.1"),
        ("in", 0, 0.1, "-0.1"),
        ("in", 0, -0.1, "0.1"),
    ],
)
def test_kraken_posted_ledger_subtracts_signed_same_asset_fee(direction, amount, fee, expected):
    result = balance_effect(
        event(
            exchange="kraken",
            amount_basis="ledger_amount",
            direction=direction,
            quantity=amount,
            fee={"currency": "BTC", "cost": fee},
        )
    )
    assert Decimal(result["quantity"]) == Decimal(expected)
    assert result["provenance"] == "provider" and result["rule"] == "kraken-ledger-v1"
    assert result["source_url"].startswith("https://support.kraken.com/")
    assert not result["reviewable"]


@pytest.mark.parametrize(
    "changes",
    [
        {"wallet_scope": "unknown"},
        {"fee_known": False},
        {"fee": {"currency": "ETH", "cost": 0.1}},
        {"status": "pending"},
    ],
)
def test_kraken_rule_requires_completed_same_wallet_known_same_asset_facts(changes):
    result = balance_effect(event(exchange="kraken", amount_basis="ledger_amount", **changes))
    assert result["quantity"] is None
    assert not result["reviewable"]


@pytest.mark.parametrize(
    "wallet,expected",
    [
        (0, "configured"),
        (1, "outside"),
        (None, "unknown"),
        (2, "unknown"),
        (True, "unknown"),
        ("0", "unknown"),
    ],
)
def test_binance_wallet_type_is_preserved_without_defaulting_missing_values(wallet, expected):
    row = _binance_row(
        {"coin": "BTC", "id": "x", "insertTime": 1000, "status": 1, "walletType": wallet}, "deposit"
    )
    assert row["wallet_scope"] == expected


@pytest.mark.parametrize("provider", ["binance", "bybit"])
def test_amount_and_fee_fields_alone_do_not_define_debit(provider):
    result = balance_effect(event(exchange=provider))
    assert result["quantity"] is None and result["reviewable"]


def test_zero_fee_still_requires_known_wallet_scope():
    assert (
        balance_effect(event(wallet_scope="unknown", fee={"currency": "BTC", "cost": 0}))["quantity"] is None
    )
    assert balance_effect(event(fee={"currency": "BTC", "cost": 0}))["quantity"] == "-1"
    result = balance_effect(event(wallet_scope="outside"))
    assert result["quantity"] == "0" and result["provenance"] == "provider"


@pytest.mark.parametrize(
    "direction,convention,expected",
    [
        ("out", "total_debit", "-1"),
        ("out", "principal", "-1.1"),
        ("in", "net_credit", "1"),
        ("in", "gross_receipt", "0.9"),
    ],
)
def test_user_conventions_have_distinct_signed_changes_and_preserve_native_facts(
    store, direction, convention, expected
):
    row = persist(store, event(direction=direction))
    reviews = FundingReviews(store)
    body = request(row).model_copy(update={"amount_convention": convention})
    result = reviews.save(row["id"], body)
    assert result["event"] == row
    assert result["balance_effect"]["quantity"] == expected
    assert result["balance_effect"]["provenance"] == "user_review"
    assert result["history"][0]["decision"]["fee_quantity"] is None
    assert FundingReviews(store).state(row["id"]) == result


def test_unknown_fee_requires_explicit_assertion_and_remains_unknown_in_provider_record(store):
    row = persist(store, event(fee_known=False, fee={"currency": None, "cost": None}))
    reviews = FundingReviews(store)
    with pytest.raises(ValueError, match="missing same-asset fee"):
        reviews.save(row["id"], request(row))
    result = reviews.save(row["id"], request(row, fee_quantity=Decimal("0")))
    assert result["balance_effect"]["quantity"] == "-1"
    assert not result["event"]["fee_known"] and result["event"]["fee"]["cost"] is None
    assert result["history"][0]["decision"]["fee_quantity"] == "0"


def test_unknown_wallet_can_be_explicitly_excluded_without_assuming_fees(store):
    row = persist(store, event(wallet_scope="unknown", fee_known=False, fee={"currency": None, "cost": None}))
    body = request(row).model_copy(update={"wallet_scope": "outside", "amount_convention": None})
    state = FundingReviews(store).save(row["id"], body)
    assert state["balance_effect"]["quantity"] == "0"
    assert state["balance_effect"]["provenance"] == "user_review"
    assert state["event"]["wallet_scope"] == "unknown"


@pytest.mark.parametrize(
    "changes",
    [
        {"wallet_scope": "outside", "amount_convention": None},
        {"amount_convention": "net_credit"},
        {"fee_quantity": Decimal("0.2")},
        {"note": "   "},
    ],
)
def test_invalid_or_contradictory_review_is_atomic(store, changes):
    row = persist(store, event())
    reviews = FundingReviews(store)
    with pytest.raises(ValueError):
        reviews.save(row["id"], request(row).model_copy(update=changes))
    assert reviews.state(row["id"])["history"] == []


@pytest.mark.parametrize(
    "changes",
    [
        {"status": "pending"},
        {"status": "failed"},
        {"wallet_scope": "outside"},
        {"exchange": "kraken", "amount_basis": "ledger_amount"},
        {"fee": {"currency": "ETH", "cost": 0.1}},
        {"fee": {"currency": "BTC", "cost": -0.1}},
    ],
)
def test_manual_decision_cannot_override_ineligible_or_provider_defined_records(store, changes):
    row = persist(store, event(**changes))
    with pytest.raises(ValueError, match="not eligible"):
        FundingReviews(store).save(row["id"], request(row))


def test_source_correction_invalidates_review_and_old_form_but_preserves_audit(store):
    row = persist(store, event())
    reviews = FundingReviews(store)
    saved = reviews.save(row["id"], request(row))
    corrected = persist(store, {**row, "fee": {"currency": "BTC", "cost": 0.2}})
    state = reviews.state(row["id"])
    assert state["balance_effect"]["review_status"] == "stale"
    assert state["balance_effect"]["quantity"] is None
    assert state["history"] == saved["history"]
    with pytest.raises(FundingReviewConflict):
        reviews.save(row["id"], request(row, replace_id=saved["history"][0]["id"]))
    latest = reviews.save(row["id"], request(corrected, replace_id=saved["history"][0]["id"]))
    assert latest["balance_effect"]["quantity"] == "-1.2"
    assert len(latest["history"]) == 2


def test_label_changes_do_not_invalidate_review(store):
    row = persist(store, event())
    reviews = FundingReviews(store)
    reviews.save(row["id"], request(row))
    persist(store, {**row, "account": "Renamed account"})
    assert reviews.state(row["id"])["balance_effect"]["review_status"] == "current"


def test_concurrent_review_cannot_overwrite_another_decision(store):
    row = persist(store, event())
    reviews = FundingReviews(store)

    def save():
        try:
            reviews.save(row["id"], request(row))
            return "saved"
        except FundingReviewConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: save(), range(2)))
    assert sorted(outcomes) == ["conflict", "saved"]
    assert len(reviews.state(row["id"])["history"]) == 1


def test_withdraw_is_versioned_and_retains_source_and_history(store):
    row = persist(store, event())
    reviews = FundingReviews(store)
    saved = reviews.save(row["id"], request(row))
    revision = saved["history"][0]["id"]
    result = reviews.save(
        row["id"], ReviewVersion(source_version=fingerprint(row), replace_id=revision), withdraw=True
    )
    assert result["event"] == row and len(result["history"]) == 2
    assert result["balance_effect"]["quantity"] is None
    assert result["balance_effect"]["review_status"] == "withdrawn"
    with pytest.raises(FundingReviewConflict):
        reviews.save(row["id"], request(row, replace_id=revision))


def test_ledger_and_checkpoints_read_same_effects_without_modifying_native_payload(client):
    store = client.app.state.services.store
    row = persist(store, event())
    reviews = FundingReviews(store)
    reviews.save(row["id"], request(row))
    retained = client.get("/api/v1/account-ledger/funding").json()["items"][0]
    with store.db() as db:
        observed = CheckJournal.inputs(db, row["account_id"])["funding"][0]
        assert (
            json.loads(
                db.execute("SELECT payload FROM funding_events WHERE id=?", (row["id"],)).fetchone()[0]
            )
            == row
        )
    assert retained["balance_effect"] == observed["balance_effect"]
    opening = {"started_ms": 100_000, "ended_ms": 101_000, "balances": {"BTC": 2}, "fills": [], "funding": []}
    current = {
        **opening,
        "started_ms": 200_000,
        "ended_ms": 201_000,
        "balances": {"BTC": 0.9},
        "funding": [observed],
        "imports": [{"kind": "fills", "status": "caught_up", "caught_up": True}],
    }
    report = compare(opening, current)
    assert report["status"] == "observed_match"
    assert report["funding_effect_counts"] == {"user_review": 1}
    assert report["rows"][0]["funding_change"] == -1.1
    assert report["calculation_version"] == 2
    reviews.save(
        row["id"],
        ReviewVersion(source_version=fingerprint(row), replace_id=retained["balance_effect"]["review_id"]),
        withdraw=True,
    )
    assert observed["balance_effect"]["quantity"] == "-1.1"  # Frozen observation remains evidence.
    assert report["status"] == "observed_match"  # A saved calculation is never mutated.


def test_api_source_conflict_auth_and_unknown_record(client, monkeypatch):
    services = client.app.state.services
    row = persist(services.store, event())

    def forbidden(*_args, **_kwargs):
        pytest.fail("A local funding review must not access credentials or call a provider.")

    monkeypatch.setattr(services.store, "credentials", forbidden)
    monkeypatch.setattr(services.market, "client", forbidden)
    endpoint = f"/api/v1/account-ledger/funding/{row['id']}/review"
    response = client.get(endpoint)
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    body = request(row).model_dump(mode="json")
    assert client.post(endpoint, json=body).status_code == 200
    assert client.post(endpoint, json=body).status_code == 409
    assert client.get("/api/v1/account-ledger/funding/missing/review").status_code == 404
    assert client.post(endpoint, json={**body, "fee_quantity": "NaN"}).status_code == 422
    assert client.post(endpoint, json={**body, "api_key": "PRIVATE"}).status_code == 422
    assert "PRIVATE" not in client.post(endpoint, json={**body, "api_key": "PRIVATE"}).text


def test_binance_completion_time_is_distinct_from_creation_time():
    row = _binance_row(
        {
            "id": "x",
            "coin": "BTC",
            "amount": "1",
            "status": 6,
            "applyTime": "2024-01-01 00:00:00",
            "completeTime": "2024-01-02 00:00:00",
            "transactionFee": "0.1",
            "walletType": 0,
        },
        "withdrawal",
    )
    assert row["posted_ms"] - row["timestamp_ms"] == 86_400_000
    assert _binance_row({"id": "x", "status": 1, "insertTime": 1000}, "deposit")["posted_ms"] is None


def compare_movement(row, before=None):
    opening = {
        "started_ms": 100_000,
        "ended_ms": 101_000,
        "balances": {"BTC": 2},
        "fills": [],
        "funding": [before] if before else [],
    }
    current = {
        **opening,
        "started_ms": 200_000,
        "ended_ms": 201_000,
        "funding": [row],
        "imports": [{"kind": "fills", "status": "caught_up", "caught_up": True}],
    }
    return compare(opening, current)


def test_balance_check_uses_posting_time_not_funding_creation_time():
    row = event(exchange="kraken", amount_basis="ledger_amount", timestamp_ms=90_000, posted_ms=150_000)
    result = compare_movement(row)
    assert result["rows"][0]["funding_change"] == -1.1
    assert result["rows"][0]["expected"] == 0.9


@pytest.mark.parametrize("posted", [None, 100_500, 199_500, 201_000])
def test_missing_or_boundary_posting_time_prevents_application(posted):
    row = event(exchange="kraken", amount_basis="ledger_amount", posted_ms=posted)
    result = compare_movement(row)
    assert result["rows"][0]["expected"] is None
    assert result["activity"]["funding"] == 0


def test_review_change_on_record_already_in_checkpoint_cannot_replay_a_movement(store):
    row = persist(store, event(posted_ms=50_000))
    reviews = FundingReviews(store)
    before = {**row, "balance_effect": balance_effect(row)}
    reviewed = reviews.save(row["id"], request(row))
    after = {**row, "balance_effect": reviewed["balance_effect"]}
    result = compare_movement(after, before=before)
    assert result["status"] == "incomplete" and result["activity"]["funding"] == 0
    assert any("after the checkpoint" in issue for issue in result["rows"][0]["issues"])


def test_audit_limit_does_not_delete_decisions(store):
    row = persist(store, event())
    reviews = FundingReviews(store)
    revision = None
    for _ in range(22):
        state = reviews.save(row["id"], request(row, replace_id=revision))
        revision = state["balance_effect"]["review_id"]
    assert len(state["history"]) == 20
    with store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM funding_reviews").fetchone()[0] == 22


def test_native_accountant_reads_provenance_without_review_notes_or_provider_access(client, monkeypatch):
    from protolink import Task

    services = client.app.state.services
    row = persist(services.store, event())
    services.funding_sync.ledger.reviews.save(
        row["id"], request(row).model_copy(update={"note": "PRIVATE_REVIEW_NOTE"})
    )

    def forbidden(*_args, **_kwargs):
        pytest.fail("Reading retained funding through AgentClient must not contact a provider.")

    monkeypatch.setattr(services.store, "credentials", forbidden)
    monkeypatch.setattr(services.market, "client", forbidden)
    network = services.agents.network
    task = Task.create_tool_call(
        "accountant_snapshot", {"funding_view": True, "account_id": row["account_id"]}
    )
    response = client.portal.call(network.client.send_task, network.cards["accountant"].url, task)
    response.raise_for_status()
    evidence = response.get_last_item().parts[-1].as_tool_output().result
    assert evidence["items"][0]["balance_effect"]["provenance"] == "user_review"
    assert evidence["items"][0]["balance_effect"]["quantity"] == "-1.1"
    assert "PRIVATE_REVIEW_NOTE" not in json.dumps(evidence)
