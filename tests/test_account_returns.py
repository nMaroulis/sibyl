"""Measured returns: cash-flow arithmetic, current reviews, coverage and immutable boundaries."""

import copy
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from sibyl.models import ConnectionCreate
from sibyl.services.portfolio.returns.calculation import dietz
from sibyl.services.portfolio.returns.contracts import CoverageReview, ManualFlow, PeriodRevision, StartPeriod


def test_dietz_distinguishes_contributions_withdrawals_and_investment_gain():
    result = dietz(1000, 1600, 0, 100, [{"timestamp_ms": 50, "value": 500}])
    assert result["gain"] == 100 and result["return_pct"] == 8
    assert dietz(1000, 800, 0, 100, [{"timestamp_ms": 50, "value": -300}])["gain"] == 100
    assert dietz(0, 100, 0, 100, [{"timestamp_ms": 100, "value": 100}])["return_pct"] is None
    with pytest.raises(ValueError):
        dietz(1000, 1000, 0, 100, [{"timestamp_ms": -1, "value": 10}])


def test_actual_demo_capture_is_explicit_fresh_and_private(client):
    response = client.post("/api/v1/account-returns", json={"label": "Measured Demo", "scope": "all"})
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["environment"] == "demo" and row["closing"] is None and row["result"] is None
    assert row["opening"]["demo"]["complete"]
    assert response.headers["Cache-Control"] == "no-store"
    assert "credentials" not in response.text and "vault" not in response.text
    assert client.get("/api/v1/account-returns/" + row["id"]).json()["opening"] == row["opening"]


@pytest.fixture
def measured(client, monkeypatch):
    service = client.app.state.services.performance.returns
    store = service.store
    accounts = [
        store.add_connection(
            ConnectionCreate(exchange="binance", label="Alpha", api_key="TEST", secret="TEST")
        ),
        store.add_connection(
            ConnectionCreate(exchange="kraken", label="Beta", api_key="TEST", secret="TEST")
        ),
    ]
    ids = sorted(a.id for a in accounts)
    names = {a.id: a.label for a in accounts}
    start = datetime.now(UTC) - timedelta(days=30)
    finish = start + timedelta(days=20)
    sequence = [(start, {ids[0]: 1000, ids[1]: 2000}), (finish, {ids[0]: 1600, ids[1]: 2100})]

    def capture(identities, source):
        at, values = sequence.pop(0)
        with store.db() as db:
            guard = service.observations._guard(db, identities, source)
        samples = {
            i: dict(
                total=values[i],
                currency="USDT",
                environment="production",
                source=source,
                complete=True,
                accounts=[{"id": i, "label": names[i]}],
                holdings=[],
                started_at=at.isoformat(),
                as_of=(at + timedelta(seconds=1)).isoformat(),
            )
            for i in identities
        }
        return samples, guard

    monkeypatch.setattr(service, "capture", capture)
    monkeypatch.setattr(service.observations, "fresh", lambda sample: None)
    row = service.start(StartPeriod())
    row = service.close(row["id"], PeriodRevision(revision=row["revision"]))
    return service, row, ids, start, finish


def attest(service, row, confirmed=True):
    return service.attest(
        row["id"],
        CoverageReview(
            revision=row["revision"],
            evidence_fingerprint=row["evidence_fingerprint"],
            confirmed=confirmed,
            note="Checked full wallet statements, no missing or duplicate movements.",
        ),
    )


def test_reviewed_manual_principal_yields_combined_and_per_account_returns(measured):
    service, row, ids, start, end = measured
    assert row["result"] is None and row["blockers"]
    row = service.manual(
        row["id"],
        ManualFlow(
            revision=row["revision"],
            account_id=ids[0],
            direction="in",
            value=Decimal(500),
            occurred_at=start + timedelta(days=10),
            note="Missing fiat funding in exchange statement.",
        ),
    )
    assert row["flows"][0]["event"]["provenance"] == "user_assertion"
    row = attest(service, row)
    assert row["result"]["gain"] == 200
    assert row["result"]["net_external_flow"] == 500
    assert row["result"]["return_pct"] == pytest.approx(200 / 3250 * 100, rel=1e-6)
    assert sorted(a["gain"] for a in row["account_results"]) == [100, 100]
    assert any(a["action"] == "manual_external_flow" for a in row["audit"])
    original = copy.deepcopy(row["closing"])
    with pytest.raises(ValueError, match="frozen"):
        service.close(row["id"], PeriodRevision(revision=row["revision"]))
    assert service.detail(row["id"])["closing"] == original


def test_stale_reviews_manual_removal_and_coverage_withdrawal_block_returns(measured):
    service, row, ids, start, end = measured
    row = service.manual(
        row["id"],
        ManualFlow(
            revision=row["revision"],
            account_id=ids[0],
            direction="in",
            value=500,
            occurred_at=start + timedelta(days=10),
            note="Statement",
        ),
    )
    old = row
    row = attest(service, row)
    assert row["result"]
    with pytest.raises(ValueError, match="changed"):
        service.attest(
            row["id"],
            CoverageReview(
                revision=old["revision"],
                evidence_fingerprint=old["evidence_fingerprint"],
                confirmed=True,
                note="stale",
            ),
        )
    row = service.remove_manual(
        row["id"], row["flows"][0]["event"]["id"], PeriodRevision(revision=row["revision"])
    )
    assert (
        row["result"] is None
        and row["coverage"] is None
        and row["audit"][0]["action"] == "remove_manual_flow"
    )
    row = attest(service, row)
    assert row["result"]["gain"] == 700
    row = attest(service, row, False)
    assert row["result"] is None


def test_manual_scope_timing_and_duplicate_guards(measured):
    service, row, ids, start, end = measured
    with pytest.raises(ValueError, match="strictly inside"):
        service.manual(
            row["id"],
            ManualFlow(
                revision=row["revision"],
                account_id=ids[0],
                direction="in",
                value=5,
                occurred_at=end,
                note="boundary",
            ),
        )
    request = ManualFlow(
        revision=row["revision"],
        account_id=ids[0],
        direction="out",
        value=50,
        occurred_at=start + timedelta(days=5),
        note="Withdrawal principal",
    )
    row = service.manual(row["id"], request)
    with pytest.raises(ValueError, match="already present"):
        service.manual(row["id"], request.model_copy(update={"revision": row["revision"]}))


def test_late_import_invalidates_coverage_even_when_no_previous_flows(measured):
    from sibyl.services.funding.ledger import funding_event, write_event

    service, row, ids, start, end = measured
    row = attest(service, row)
    assert row["result"]
    event = funding_event(
        {
            "native_id": "late-deposit",
            "asset": "USDT",
            "timestamp_ms": (start + timedelta(days=5)).timestamp() * 1000,
            "quantity": 50,
            "direction": "in",
            "status": "completed",
            "fee": {"currency": "USDT", "cost": 0},
            "kind": "deposit",
            "internal": False,
            "amount_basis": "provider_reported",
            "wallet_scope": "configured",
        },
        {
            "account_id": ids[0],
            "account": "Alpha",
            "exchange": "binance",
            "environment": "production",
            "stream": "deposit",
            "start_ms": 0,
            "end_ms": datetime.now(UTC).timestamp() * 1000,
        },
    )
    with service.store.db() as db:
        write_event(db, event, datetime.now(UTC).isoformat())
    changed = service.detail(row["id"])
    assert changed["result"] is None and changed["evidence_fingerprint"] != row["evidence_fingerprint"]
    assert changed["flows"][0]["review_current"] is False
    from sibyl.services.portfolio.returns.contracts import FlowReview

    f = changed["flows"][0]
    changed = service.review(
        row["id"],
        event["id"],
        FlowReview(
            revision=changed["revision"],
            source_version=f["source_version"],
            classification="external",
            value=50,
            occurred_at=start + timedelta(days=5),
            note="Reviewed statement",
        ),
    )
    changed = attest(service, changed)
    assert changed["result"]["gain"] == 650
    event["quantity"] = 75
    with service.store.db() as db:
        write_event(db, event, datetime.now(UTC).isoformat())
    assert service.detail(row["id"])["result"] is None


def test_confirmed_internal_transfer_cancels_combined_flow_but_not_individual_flows(measured):
    from sibyl.services.funding.ledger import funding_event, write_event
    from sibyl.services.portfolio.returns.contracts import FlowReview
    from sibyl.services.transfers.reconciliation import TransferConfirm, TransferPair, TransferReconciliation

    service, row, ids, start, end = measured
    events = []
    for index, (identity, kind, direction) in enumerate(
        [(ids[0], "withdrawal", "out"), (ids[1], "deposit", "in")]
    ):
        at = start + timedelta(days=5, hours=index)
        event = funding_event(
            dict(
                native_id=str(index),
                asset="USDT",
                timestamp_ms=at.timestamp() * 1000,
                quantity=100,
                direction=direction,
                status="completed",
                fee=dict(currency="USDT", cost=0),
                kind=kind,
                internal=False,
                amount_basis="provider_reported",
                wallet_scope="configured",
            ),
            dict(
                account_id=identity,
                account=identity,
                exchange="binance",
                environment="production",
                stream=kind,
                start_ms=0,
                end_ms=datetime.now(UTC).timestamp() * 1000,
            ),
        )
        events.append(event)
        with service.store.db() as db:
            write_event(db, event, datetime.now(UTC).isoformat())
    transfers = TransferReconciliation(service.store)
    preview = transfers.preview(TransferPair(outgoing_id=events[0]["id"], incoming_id=events[1]["id"]))
    transfers.confirm(
        TransferConfirm(
            outgoing_id=events[0]["id"],
            incoming_id=events[1]["id"],
            outgoing_fingerprint=preview["outgoing"]["fingerprint"],
            incoming_fingerprint=preview["incoming"]["fingerprint"],
            note="Both owned wallets",
        )
    )
    row = service.detail(row["id"])
    for event in events:
        flow = next(f for f in row["flows"] if f["event"]["id"] == event["id"])
        row = service.review(
            row["id"],
            event["id"],
            FlowReview(
                revision=row["revision"],
                source_version=flow["source_version"],
                classification="own_transfer",
                value=100,
                occurred_at=datetime.fromtimestamp(event["timestamp_ms"] / 1000, UTC),
                note="Reviewed both owned wallets",
            ),
        )
    row = attest(service, row)
    assert row["result"]["net_external_flow"] == 0
    assert row["result"]["gain"] == 700
    assert sorted(r["net_external_flow"] for r in row["account_results"]) == [-100, 100]


def test_native_accountant_reads_selected_period_without_revaluing(measured, client, monkeypatch):
    service, row, ids, start, end = measured
    monkeypatch.setattr(service, "capture", lambda *args: pytest.fail("Read-only agent captured balances"))
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "accountant",
            "message": "Explain this measured period",
            "context": {"return_period_id": row["id"]},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["tool"] == "investment_returns"
    assert response.json()["evidence"]["id"] == row["id"]
    assert "unavailable" in response.json()["answer"].lower()


def test_remove_period_clears_only_local_measurements(measured):
    service, row, ids, start, end = measured
    with pytest.raises(ValueError):
        service.remove(row["id"], PeriodRevision(revision=1))
    service.remove(row["id"], PeriodRevision(revision=row["revision"]))
    with pytest.raises(LookupError):
        service.detail(row["id"])
    assert all(identity in {a.id for a in service.store.connections()} for identity in ids)


def test_extreme_percentage_does_not_return_infinity():
    result = dietz(1e-320, 1e24, 0, 100, [])
    assert result["return_pct"] is None and "numerical range" in result["return_note"]
