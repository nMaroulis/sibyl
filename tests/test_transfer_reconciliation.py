"""Local transfer assertions: bounded suggestions, source versions, exclusivity and reversible audit."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from sibyl.services.funding_ledger import FundingLedger, funding_event
from sibyl.services.transfer_reconciliation import (
    TransferConfirm,
    TransferConflict,
    TransferPair,
    TransferReconciliation,
    fingerprint,
)

STAMP = 1_704_153_600_000


def save_event(store, identity, account="north", direction="out", **values):
    """Insert normalized observed facts without an exchange client, wallet mutation or order."""
    kind = values.pop("kind", "withdrawal" if direction == "out" else "deposit")
    row = funding_event(
        {
            "native_id": identity,
            "reference": None,
            "asset": "BTC",
            "timestamp_ms": STAMP,
            "kind": kind,
            "direction": direction,
            "quantity": 1,
            "status": "completed",
            "internal": False,
            "amount_basis": "provider_reported",
            "fee": {"currency": "BTC", "cost": 0},
            **values,
        },
        {
            "account_id": account,
            "account": account,
            "exchange": "binance",
            "environment": values.get("environment", "production"),
            "stream": kind,
            "start_ms": 1,
            "end_ms": 1_800_000_000_000,
        },
    )
    with store.db() as db:
        db.execute(
            "INSERT INTO funding_events VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET asset=excluded.asset,timestamp_ms=excluded.timestamp_ms,status=excluded.status,payload=excluded.payload",
            (
                row["id"],
                account,
                kind,
                identity,
                row["asset"],
                row["timestamp_ms"],
                row["status"],
                json.dumps(row),
                "first",
                "last",
            ),
        )
    return row


@pytest.fixture
def transfers(store):
    FundingLedger(store)
    return TransferReconciliation(store)


def pair(transfers, store, **incoming_values):
    outgoing = save_event(store, "out")
    incoming = save_event(store, "in", "daily", "in", timestamp_ms=STAMP + 60_000, **incoming_values)
    return outgoing, incoming


def request(transfers, outgoing, incoming, note=""):
    review = transfers.preview(TransferPair(outgoing_id=outgoing["id"], incoming_id=incoming["id"]))
    return TransferConfirm(
        outgoing_id=outgoing["id"],
        incoming_id=incoming["id"],
        outgoing_fingerprint=review["outgoing"]["fingerprint"],
        incoming_fingerprint=review["incoming"]["fingerprint"],
        note=note,
    )


def change(store, event, **values):
    event = {**event, **values}
    with store.db() as db:
        db.execute(
            "UPDATE funding_events SET payload=?,status=?,asset=?,timestamp_ms=? WHERE id=?",
            (json.dumps(event), event["status"], event["asset"], event["timestamp_ms"], event["id"]),
        )
    return event


def test_preview_and_candidates_have_no_side_effects(transfers, store):
    outgoing, incoming = pair(transfers, store)
    report = transfers.report()
    assert report["total"] == 0 and len(report["candidates"]) == 1
    assert report["candidates"][0]["equal_amounts"] and report["candidates"][0]["valid"]
    assert transfers.preview(TransferPair(outgoing_id=outgoing["id"], incoming_id=incoming["id"]))["valid"]
    with store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM transfer_links").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM transfer_audit").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0


def test_confirm_persists_source_snapshots_and_is_idempotent(transfers, store):
    outgoing, incoming = pair(transfers, store)
    body = request(transfers, outgoing, incoming)
    saved = transfers.confirm(body)
    assert transfers.confirm(body)["id"] == saved["id"]
    assert saved["status"] == "confirmed" and not saved["cost_basis_applied"]
    assert saved["reviewed"]["outgoing"]["native_id"] == "out"
    assert transfers.report()["candidates"] == []
    assert TransferReconciliation(store).detail(saved["id"])["audit"][0]["action"] == "confirm"
    assert len(transfers.detail(saved["id"])["audit"]) == 1
    assert FundingLedger(store).events()["items"][0]["reconciliation"]["status"] == "confirmed"


@pytest.mark.parametrize(
    "values",
    [
        {"quantity": 0.9},
        {"status": "pending"},
        {"asset": "ETH"},
        {"fee": {"currency": "BTC", "cost": 0.001}},
        {"reference": "new"},
        {"timestamp_ms": STAMP + 5000},
        {"internal": True},
        {"amount_basis": "ledger_amount"},
    ],
)
def test_material_source_corrections_require_review_and_keep_reservations(transfers, store, values):
    outgoing, incoming = pair(transfers, store)
    saved = transfers.confirm(request(transfers, outgoing, incoming))
    change(store, incoming, **values)
    current = transfers.detail(saved["id"])
    assert current["status"] == "needs_review" and current["changed_sides"] == ["incoming"]
    assert current["reviewed"]["incoming"]["quantity"] == 1
    assert transfers.report()["candidates"] == []
    assert FundingLedger(store).events()["items"][0]["reconciliation"]["status"] == "needs_review"
    with store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM transfer_members").fetchone()[0] == 2


def test_display_label_or_last_observation_changes_do_not_invalidate_confirmation(transfers, store):
    outgoing, incoming = pair(transfers, store)
    body = request(transfers, outgoing, incoming)
    saved = transfers.confirm(body)
    change(store, incoming, account="New display label", last_seen_at="later")
    assert transfers.detail(saved["id"])["status"] == "confirmed"
    assert transfers.confirm(body)["id"] == saved["id"]
    assert len(transfers.detail(saved["id"])["audit"]) == 1


def test_confirm_rejects_a_stale_preview_and_creates_nothing(transfers, store):
    outgoing, incoming = pair(transfers, store)
    body = request(transfers, outgoing, incoming)
    change(store, incoming, quantity=0.99)
    with pytest.raises(TransferConflict, match="changed"):
        transfers.confirm(body)
    assert transfers.report()["total"] == 0


def test_difference_requires_note_and_does_not_become_a_fee_or_adjust_source_amounts(transfers, store):
    outgoing, incoming = pair(transfers, store, quantity=0.999)
    with pytest.raises(ValueError, match="review note"):
        transfers.confirm(request(transfers, outgoing, incoming))
    saved = transfers.confirm(
        request(
            transfers, outgoing, incoming, "Reviewed source amount difference; inclusion of fees is unknown."
        )
    )
    assert saved["reviewed"]["amount_difference"] == pytest.approx(0.001)
    assert not saved["reviewed"]["difference_matches_outgoing_fee"]
    assert saved["current"]["incoming"]["quantity"] == 0.999
    assert saved["current"]["outgoing"]["quantity"] == 1


def test_fee_compatible_suggestion_is_still_explicit_and_ambiguous(transfers, store):
    outgoing = save_event(store, "out", fee={"currency": "BTC", "cost": 0.1})
    save_event(store, "in", "daily", "in", quantity=0.9)
    save_event(store, "other-in", "reserve", "in", quantity=0.9)
    candidates = transfers.report()["candidates"]
    assert len(candidates) == 2 and all(row["alternatives"] == 2 for row in candidates)
    assert all(row["difference_matches_outgoing_fee"] and row["note_required"] for row in candidates)
    assert not transfers.report()["items"]
    assert outgoing["quantity"] == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "pending"),
        ("status", "restricted"),
        ("asset", "ETH"),
        ("direction", "out"),
        ("kind", "withdrawal"),
    ],
)
def test_invalid_pairs_cannot_be_saved(transfers, store, field, value):
    outgoing, incoming = pair(transfers, store)
    incoming = change(store, incoming, **{field: value})
    review = transfers.preview(TransferPair(outgoing_id=outgoing["id"], incoming_id=incoming["id"]))
    assert not review["valid"]
    with pytest.raises(ValueError):
        transfers.confirm(request(transfers, outgoing, incoming))


def test_environments_and_same_account_are_never_merged(transfers, store):
    outgoing = save_event(store, "out")
    test = save_event(store, "test-in", "test", "in", environment="test")
    same = save_event(store, "same-in", "north", "in")
    for incoming in [test, same, outgoing]:
        with pytest.raises(ValueError):
            transfers.confirm(request(transfers, outgoing, incoming))
    assert transfers.report()["candidates"] == []


def test_manual_review_supports_older_and_non_heuristic_pairs_with_note(transfers, store):
    outgoing, incoming = pair(transfers, store, quantity=0.5)
    incoming = change(store, incoming, timestamp_ms=STAMP + 30 * 86400000)
    assert transfers.report()["candidates"] == []
    assert transfers.events("in", q="in")["items"][0]["id"] == incoming["id"]
    assert (
        transfers.confirm(
            request(
                transfers, outgoing, incoming, "Checked older records and reviewed both dates and quantities."
            )
        )["status"]
        == "confirmed"
    )


def test_soft_remove_retains_audit_and_restores_after_fresh_review(transfers, store):
    outgoing, incoming = pair(transfers, store)
    saved = transfers.confirm(request(transfers, outgoing, incoming))
    transfers.remove(saved["id"])
    transfers.remove(saved["id"])
    assert (
        transfers.report()["total"] == 0
        and transfers.report(include_removed=True)["items"][0]["status"] == "removed"
    )
    assert len(transfers.report()["candidates"]) == 1
    assert FundingLedger(store).events()["items"][0]["reconciliation"] is None
    restored = transfers.confirm(request(transfers, outgoing, incoming), saved["id"])
    assert restored["status"] == "confirmed"
    assert [row["action"] for row in transfers.detail(saved["id"])["audit"]] == [
        "restore",
        "remove",
        "confirm",
    ]


def test_restoration_cannot_steal_an_observation_linked_elsewhere(transfers, store):
    outgoing, incoming = pair(transfers, store)
    old = transfers.confirm(request(transfers, outgoing, incoming))
    transfers.remove(old["id"])
    other = save_event(store, "other", "reserve", "in")
    transfers.confirm(request(transfers, outgoing, other))
    with pytest.raises(TransferConflict, match="another link"):
        transfers.confirm(request(transfers, outgoing, incoming), old["id"])


def test_reconfirmation_records_updated_versions_and_note(transfers, store):
    outgoing, incoming = pair(transfers, store)
    saved = transfers.confirm(request(transfers, outgoing, incoming))
    incoming = change(store, incoming, quantity=0.99)
    updated = transfers.confirm(
        request(transfers, outgoing, incoming, "Reviewed corrected incoming quantity."), saved["id"]
    )
    assert updated["status"] == "confirmed" and updated["reviewed"]["incoming"]["quantity"] == 0.99
    assert transfers.detail(saved["id"])["audit"][0]["action"] == "reconfirm"


def test_reconfirmation_cannot_silently_swap_a_counterpart(transfers, store):
    outgoing, incoming = pair(transfers, store)
    saved = transfers.confirm(request(transfers, outgoing, incoming))
    other = save_event(store, "other", "reserve", "in")
    with pytest.raises(ValueError, match="original pair"):
        transfers.confirm(request(transfers, outgoing, other), saved["id"])


def test_concurrent_confirmation_claims_an_event_only_once(transfers, store):
    outgoing, incoming = pair(transfers, store)
    other = save_event(store, "other", "reserve", "in")
    bodies = [request(transfers, outgoing, incoming), request(transfers, outgoing, other)]

    def save(body):
        try:
            return transfers.confirm(body)["status"]
        except TransferConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(save, bodies)) == ["confirmed", "conflict"]
    with store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM transfer_members").fetchone()[0] == 2
        assert db.execute("SELECT COUNT(*) FROM transfer_audit").fetchone()[0] == 1


def test_audit_failure_rolls_back_link_and_both_reservations(transfers, store, monkeypatch):
    outgoing, incoming = pair(transfers, store)

    def failed(*_):
        raise RuntimeError("interrupted audit")

    monkeypatch.setattr(transfers, "_audit", failed)
    with pytest.raises(RuntimeError):
        transfers.confirm(request(transfers, outgoing, incoming))
    assert transfers.report()["total"] == 0
    with store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM transfer_members").fetchone()[0] == 0


def test_scans_are_bounded_and_manual_search_is_independent(transfers, store, monkeypatch):
    outgoing, incoming = pair(transfers, store)
    monkeypatch.setattr("sibyl.services.transfer_reconciliation.MAX_EVENTS", 1)
    report = transfers.report()
    assert report["scan_limited"] and report["scanned_events"] == 1 and report["candidates"] == []
    assert transfers.events("out", q=outgoing["native_id"])["items"][0]["id"] == outgoing["id"]
    assert transfers.events("in", q=incoming["id"])["total"] == 1
    assert transfers.events("in", q="%")["total"] == 0


def test_filters_match_either_account_keep_other_environments_and_assets_out(transfers, store):
    outgoing, incoming = pair(transfers, store)
    saved = transfers.confirm(request(transfers, outgoing, incoming))
    assert transfers.report(account_id="daily")["items"][0]["id"] == saved["id"]
    assert transfers.report(account_id="north")["total"] == 1
    assert transfers.report(account_id="missing")["total"] == 0
    assert transfers.report(environment="test")["total"] == 0
    assert transfers.report(asset="ETH")["total"] == 0


def test_missing_source_requires_review_and_can_still_be_unlinked(transfers, store):
    outgoing, incoming = pair(transfers, store)
    saved = transfers.confirm(request(transfers, outgoing, incoming))
    with store.db() as db:
        db.execute("DELETE FROM funding_events WHERE id=?", (incoming["id"],))
    assert transfers.detail(saved["id"])["status"] == "needs_review"
    assert transfers.detail(saved["id"])["current"] is None
    transfers.remove(saved["id"])
    assert transfers.detail(saved["id"])["status"] == "removed"


def test_confirmation_without_active_saved_accounts_is_local_annotation_only(transfers, store):
    outgoing, incoming = pair(transfers, store)
    store.activate_account("demo", False)
    assert transfers.confirm(request(transfers, outgoing, incoming))["status"] == "confirmed"
    assert store.orders() == []


def test_api_preview_confirm_stale_reconfirm_and_history(client):
    service = client.app.state.services.transfers
    outgoing, incoming = pair(service, service.store)
    root = "/api/v1/account-ledger/transfers"
    body = request(service, outgoing, incoming).model_dump()
    assert (
        client.post(
            root + "/preview", json={"outgoing_id": outgoing["id"], "incoming_id": incoming["id"]}
        ).headers["Cache-Control"]
        == "no-store"
    )
    response = client.post(root, json=body)
    assert response.status_code == 200
    identity = response.json()["id"]
    other = save_event(service.store, "other", "reserve", "in")
    assert client.post(root, json=request(service, outgoing, other).model_dump()).status_code == 409
    incoming = change(service.store, incoming, quantity=0.99)
    assert client.post(root + f"/{identity}/review", json=body).status_code == 409
    assert client.get(root + f"/{identity}").json()["status"] == "needs_review"
    assert (
        client.post(
            root + f"/{identity}/review",
            json=request(service, outgoing, incoming, "Reviewed corrected incoming amount.").model_dump(),
        ).status_code
        == 200
    )
    assert client.delete(root + f"/{identity}").status_code == 204
    assert client.get(root + "?include_removed=true").json()["total"] == 1
    assert client.get(root + "/events?direction=in&q=in").json()["total"] == 1
    assert client.get(root + "/events?direction=sideways").status_code == 422
    assert client.get(root + "/missing").status_code == 404
    assert client.post(root, json={**body, "note": "x" * 1001}).status_code == 422
    assert (
        client.post(root + "/preview", json={"outgoing_id": "0" * 64, "incoming_id": "1" * 64}).status_code
        == 404
    )


def test_example_is_isolated_and_contains_ambiguous_candidates(client):
    data = client.get("/api/v1/account-ledger/transfers/example").json()
    assert data["example"] and len(data["candidates"]) == 3
    assert any(row["alternatives"] > 1 for row in data["candidates"])
    assert data["items"][0]["status"] == "confirmed"
    assert client.get("/api/v1/account-ledger/transfers").json()["total"] == 0
    assert client.get("/api/v1/account-ledger/funding").json()["total"] == 0
    assert client.app.state.services.store.orders() == []
    assert fingerprint(data["candidates"][0]["outgoing"]) == data["candidates"][0]["outgoing"]["fingerprint"]


def test_confirm_does_not_rewrite_source_facts_or_wallet(transfers, store):
    outgoing, incoming = pair(transfers, store)
    with store.db() as db:
        before = [tuple(row) for row in db.execute("SELECT id,payload FROM funding_events ORDER BY id")]
    balances = store.balances()
    transfers.confirm(request(transfers, outgoing, incoming))
    with store.db() as db:
        assert [
            tuple(row) for row in db.execute("SELECT id,payload FROM funding_events ORDER BY id")
        ] == before
    assert store.balances() == balances and store.orders() == []


def test_failed_remove_audit_preserves_link_and_reservations(transfers, store, monkeypatch):
    outgoing, incoming = pair(transfers, store)
    saved = transfers.confirm(request(transfers, outgoing, incoming))

    def failed(*_):
        raise RuntimeError("interrupted removal")

    monkeypatch.setattr(transfers, "_audit", failed)
    with pytest.raises(RuntimeError):
        transfers.remove(saved["id"])
    assert transfers.detail(saved["id"])["status"] == "confirmed"
    with store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM transfer_members").fetchone()[0] == 2


@pytest.mark.parametrize("gap_minutes,expected", [(-4, 1), (-6, 0), (73 * 60, 0)])
def test_clock_skew_and_suggestion_window_are_explicit(transfers, store, gap_minutes, expected):
    outgoing, incoming = pair(transfers, store)
    change(store, incoming, timestamp_ms=STAMP + gap_minutes * 60_000)
    assert len(transfers.report()["candidates"]) == expected


def test_accountant_transfer_evidence_is_read_only_and_scoped(client, monkeypatch):
    service = client.app.state.services
    monkeypatch.setattr(
        service.market,
        "account_balances",
        lambda *_: pytest.fail("Transfer review must not read private balances"),
    )
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "accountant",
            "message": "Explain these possible transfers.",
            "context": {"transfer_view": True, "transfer_example": True},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["engine"] == "ProtoLink" and data["evidence"]["view"] == "transfers"
    assert data["evidence"]["example"] and len(data["evidence"]["candidates"]) == 3
    assert "not automatically external cash flows" in data["answer"]
    assert service.transfers.report()["total"] == 0


def test_transfer_inference_cannot_change_selection_or_confirm_links(client, monkeypatch):
    from protolink import create_llm

    registry = client.app.state.services.agents
    registry.settings.llm_provider = "ollama"
    registry.settings.llm_model = "fixture-model"
    monkeypatch.setattr(
        "sibyl.agents.registry.create_llm",
        lambda *a, **kw: create_llm(
            "mock",
            sequential_responses=[
                {
                    "type": "tool_call",
                    "tool": "accountant_snapshot",
                    "args": {"transfer_view": False, "account_id": "another-account", "example": False},
                },
                "The review remains an explicit user action.",
            ],
        ),
    )
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "accountant",
            "message": "Review transfer suggestions.",
            "context": {"transfer_view": True, "transfer_example": True},
        },
    )
    assert response.status_code == 200 and response.json()["mode"] == "llm"
    assert response.json()["evidence"]["view"] == "transfers" and response.json()["evidence"]["example"]
    assert set(registry.agents["accountant"].tools) == {
        "accountant_snapshot",
        "account_history",
        "risk_alerts",
        "page_help",
        "read_context_artifact",
    }
    assert client.app.state.services.transfers.report()["total"] == 0
