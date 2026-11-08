"""Real Decimal split/merge carryover and atomic reviews over retained funding facts."""

import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from pydantic import ValidationError
from test_transfer_reconciliation import change, save_event
from test_transfer_reconciliation import request as pair_request

from sibyl.accounting.executions.books import replay
from sibyl.accounting.funding.reviews import FundingReviews
from sibyl.services.funding.ledger import FundingLedger
from sibyl.services.transfers.groups.contracts import GroupConfirm, GroupPreview
from sibyl.services.transfers.groups.planning import source_version
from sibyl.services.transfers.reconciliation import TransferConflict, TransferReconciliation


@pytest.fixture
def transfers(store):
    FundingLedger(store)
    return TransferReconciliation(store)


STAMP = 1_704_153_600_000


class IdentityPrices:
    def rate(self, asset, currency, timestamp):
        return (Decimal(1), []) if asset == currency else None


def setup(store, *, merge=False, fees=False):
    if merge:
        out = [
            save_event(store, "o1", quantity=1, wallet_scope="configured"),
            save_event(store, "o2", account="reserve", quantity=2, wallet_scope="configured"),
        ]
        inc = [
            save_event(
                store, "i", "daily", "in", quantity=3, timestamp_ms=STAMP + 1000, wallet_scope="configured"
            )
        ]
        quantities = [(0, 0, "1"), (1, 0, "2")]
    else:
        out = [
            save_event(
                store, "o", quantity=3.2 if fees else 3, fee={"currency": "BTC", "cost": 0.2 if fees else 0}
            )
        ]
        inc = [
            save_event(store, "i1", "daily", "in", quantity=1, timestamp_ms=STAMP + 1000),
            save_event(
                store,
                "i2",
                "reserve",
                "in",
                quantity=1.9 if fees else 2,
                fee={"currency": "BTC", "cost": 0.1 if fees else 0},
                timestamp_ms=STAMP + 2000,
            ),
        ]
        quantities = [(0, 0, "1"), (0, 1, "2")]
    with store.db() as db:
        enriched = FundingReviews.enrich(db, out + inc)
    facts = {row["id"]: row for row in enriched}
    body = GroupPreview(
        outgoing=[
            {
                "event_id": row["id"],
                "source_version": source_version(facts[row["id"]]),
                "amount": "total_debit",
            }
            for row in out
        ],
        incoming=[
            {
                "event_id": row["id"],
                "source_version": source_version(facts[row["id"]]),
                "amount": "net_credit",
            }
            for row in inc
        ],
        edges=[
            {"outgoing_id": out[o]["id"], "incoming_id": inc[i]["id"], "quantity": q}
            for o, i, q in quantities
        ],
        distinct_fees_confirmed=fees,
    )
    return body, out, inc


def confirmation(transfers, body, **overrides):
    preview = transfers.groups.preview(body)
    return GroupConfirm(
        **{
            **body.model_dump(),
            "review_fingerprint": preview["review_fingerprint"],
            "note": "Reviewed wallet statements and independent fee charges.",
            "own_accounts_confirmed": True,
            "configured_wallets_confirmed": True,
            **overrides,
        }
    )


def calculated(transfers, store, saved, openings):
    current = transfers.groups.detail(saved["id"])["current"]
    funding = [leg["event"] for side in ("outgoing", "incoming") for leg in current[side]]
    return replay(
        "USDT",
        IdentityPrices(),
        [],
        funding,
        openings,
        [{"id": saved["id"], "kind": "group", "plan": current}],
    )


def opening(account, quantity, cost, identity="one", timestamp=STAMP - 1000):
    return {
        "id": identity,
        "account_id": account,
        "asset": "BTC",
        "quantity": str(quantity),
        "total_cost": str(cost) if cost is not None else None,
        "timestamp_ms": timestamp,
    }


def test_split_conserves_basis_and_native_fees_without_making_up_market_value(transfers, store):
    body, out, inc = setup(store, fees=True)
    preview = transfers.groups.preview(body)
    assert preview["source_debit"] == "3.2" and preview["destination_credit"] == "2.9"
    assert preview["fee_quantity"] == "0.3" and preview["warnings"]
    with store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM transfer_members").fetchone()[0] == 0
    saved = transfers.groups.confirm(confirmation(transfers, body))
    result = calculated(transfers, store, saved, [opening("north", "3.2", "320")])
    rows = {row["account_id"]: row for row in result["items"]}
    assert rows["north"]["quantity"] == 0
    assert rows["daily"]["known_open_cost"] == 100
    assert rows["reserve"]["known_open_cost"] == 190
    assert sum(row["known_open_cost"] for row in rows.values()) == 290
    assert all(row["matched_realized"] == 0 for row in rows.values())
    assert any("fee value" in issue for row in rows.values() for issue in row["issues"])
    assert result["transfer_count"] == 2
    assert result["transfers"][1]["fee_lots"]["known_cost"] == 10
    assert result["transfers"][0]["credit_lots"]["lots"][0]["origin_account"] == "north"
    assert out[0]["quantity"] == 3.2  # Source facts were not rewritten.


def test_merge_preserves_origins_and_acquisition_order(transfers, store):
    body, out, inc = setup(store, merge=True)
    saved = transfers.groups.confirm(confirmation(transfers, body))
    result = calculated(
        transfers, store, saved, [opening("north", 1, 100), opening("reserve", 2, 500, "two", STAMP - 2000)]
    )
    row = next(row for row in result["items"] if row["account_id"] == "daily")
    assert row["quantity"] == 3 and row["known_open_cost"] == 600
    lots = result["transfers"][0]["credit_lots"]["lots"]
    assert [lot["origin_account"] for lot in lots] == ["reserve", "north"]


def test_unknown_shortfall_and_cost_stay_unknown_in_merge(transfers, store):
    body, _, _ = setup(store, merge=True)
    saved = transfers.groups.confirm(confirmation(transfers, body))
    result = calculated(transfers, store, saved, [opening("north", 1, 100)])
    row = next(row for row in result["items"] if row["account_id"] == "daily")
    assert row["quantity"] == 3 and row["unknown_open_quantity"] == 2
    assert row["known_open_cost"] == 100
    assert any(lot["acquired_at_ms"] is None for lot in result["transfers"][0]["credit_lots"]["lots"])


def test_matrix_must_balance_every_row_and_column_and_fees_are_distinct(transfers, store):
    body, _, _ = setup(store, fees=True)
    bad = body.model_copy(deep=True)
    bad.edges[0].quantity = Decimal("0.9")
    with pytest.raises(ValueError, match="row and column"):
        transfers.groups.preview(bad)
    with pytest.raises(ValueError, match="distinct"):
        transfers.groups.preview(body.model_copy(update={"distinct_fees_confirmed": False}))
    with pytest.raises(ValidationError):
        confirmation(transfers, body, configured_wallets_confirmed=False)


def test_pair_and_group_share_one_atomic_member_reservation(transfers, store):
    body, out, inc = setup(store)
    group_request = confirmation(transfers, body)
    saved = transfers.groups.confirm(group_request)
    assert transfers.groups.confirm(group_request)["id"] == saved["id"]
    with pytest.raises(TransferConflict, match="linked"):
        transfers.confirm(pair_request(transfers, out[0], inc[0], "Known split source record"))
    events = transfers.events("in")
    assert all(row["reconciliation"]["group"] for row in events["items"])
    assert transfers.report()["candidates"] == []
    with store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM transfer_group_audit").fetchone()[0] == 1
    with pytest.raises(TransferConflict):
        transfers.groups.remove(saved["id"], 99)
    transfers.groups.remove(saved["id"], saved["revision"])
    assert transfers.groups.detail(saved["id"])["status"] == "removed"
    restored = transfers.groups.confirm(confirmation(transfers, body, revision=2), saved["id"])
    assert restored["revision"] == 3
    assert [row["action"] for row in transfers.groups.detail(saved["id"])["audit"]] == [
        "restore",
        "remove",
        "confirm",
    ]


def test_group_cannot_steal_a_pair_record_and_concurrent_groups_only_commit_once(transfers, store):
    body, out, inc = setup(store)
    request = confirmation(transfers, body)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: transfers.groups.confirm(request), range(2)))
    assert responses[0]["id"] == responses[1]["id"]
    transfers.groups.remove(responses[0]["id"], 1)
    transfers.confirm(pair_request(transfers, out[0], inc[0], "Explicit different amounts assertion"))
    with pytest.raises(TransferConflict, match="another pair"):
        transfers.groups.confirm(confirmation(transfers, body, revision=2), responses[0]["id"])


@pytest.mark.parametrize(
    "changed",
    [{"quantity": 3.1}, {"posted_ms": STAMP + 3000}, {"wallet_scope": "outside"}, {"status": "pending"}],
)
def test_source_correction_invalidates_entire_group_and_stale_confirmation(transfers, store, changed):
    body, out, inc = setup(store)
    request = confirmation(transfers, body)
    saved = transfers.groups.confirm(request)
    change(store, out[0], **changed)
    detail = transfers.groups.detail(saved["id"])
    assert detail["status"] == "needs_review" and detail["current"] is None
    assert detail["changed_members"] == [out[0]["id"]]
    with pytest.raises(TransferConflict, match="changed"):
        transfers.groups.confirm(request, saved["id"])
    assert transfers.events("in")["items"][0]["reconciliation"]["status"] == "needs_review"


@pytest.mark.parametrize(
    "changed,message",
    [
        ({"environment": "test"}, "environment"),
        ({"account_id": "north"}, "disjoint"),
        ({"timestamp_ms": STAMP - 1000}, "precede"),
        ({"wallet_scope": "outside"}, "outside-wallet"),
    ],
)
def test_incompatible_legs_are_never_accepted(transfers, store, changed, message):
    body, out, inc = setup(store)
    updated = change(store, inc[0], **changed)
    with store.db() as db:
        enriched = FundingReviews.enrich(db, [updated])[0]
    body.incoming[0].source_version = source_version(enriched)
    with pytest.raises(ValueError, match=message):
        transfers.groups.preview(body)


def test_known_funding_convention_cannot_be_overridden(transfers, store):
    body, out, inc = setup(store, merge=True)
    body.outgoing[0].fee_quantity = Decimal(1)
    with pytest.raises(ValueError, match="known reported fee"):
        transfers.groups.preview(body)
    # A configured zero-fee leg has a documented amount effect, independent of the group.
    body.outgoing[0].fee_quantity = None
    row = change(
        store, out[0], exchange="kraken", amount_basis="ledger_amount", fee={"currency": "BTC", "cost": 0.1}
    )
    with store.db() as db:
        body.outgoing[0].source_version = source_version(FundingReviews.enrich(db, [row])[0])
    with pytest.raises(ValueError, match="balance effect"):
        transfers.groups.preview(body)


def test_precision_and_nonfinite_requests_fail_before_any_reservation(transfers, store):
    body, _, _ = setup(store)
    bad = body.model_copy(deep=True)
    bad.edges[0].quantity = Decimal("1.0000000000000000000000000000001")
    with pytest.raises(ValueError, match="arithmetic budget"):
        transfers.groups.preview(bad)
    with pytest.raises(ValidationError):
        GroupPreview.model_validate(
            {
                **body.model_dump(),
                "edges": [{**body.edges[0].model_dump(), "quantity": "NaN"}, body.edges[1].model_dump()],
            }
        )


def test_http_books_group_filter_audit_removal_and_opening_overlap(client):
    services = client.app.state.services
    body, out, inc = setup(services.store)
    base = "/api/v1/account-ledger/transfer-groups"
    preview = client.post(base + "/preview", json=body.model_dump(mode="json"))
    assert preview.status_code == 200 and preview.headers["cache-control"] == "no-store"
    saved = client.post(base, json=confirmation(services.transfers, body).model_dump(mode="json"))
    assert saved.status_code == 200, saved.text
    identity = saved.json()["id"]
    assert client.get(base + "?account_id=daily").json()["total"] == 1
    assert client.get(base + "?account_id=unrelated").json()["total"] == 0
    assert client.get(base + "/" + identity).json()["audit"][0]["action"] == "confirm"
    # Direct fixture opening; the public save path independently requires an existing connection.
    row = {**opening("north", 3, 300, timestamp=STAMP - 100), "currency": "USDT", "environment": "production"}
    with services.store.db() as db:
        db.execute(
            "INSERT INTO asset_openings VALUES(?,?,?,?,?,?)",
            ("one", "north", "production", "BTC", "USDT", json.dumps(row)),
        )
    result = client.get("/api/v1/account-books?environment=production&source=demo").json()
    assert not result["unapplied_transfers"]
    daily = next(row for row in result["reports"][0]["items"] if row["account_id"] == "daily")
    assert daily["known_open_cost"] == 100
    with services.store.db() as db:
        row["timestamp_ms"] = STAMP + 1
        db.execute("UPDATE asset_openings SET payload=?", (json.dumps(row),))
    result = client.get("/api/v1/account-books?environment=production&source=demo").json()
    assert result["unapplied_transfers"][0]["id"] == identity
    assert result["reports"][0]["transfer_count"] == 0
    assert client.delete(base + "/" + identity + "?revision=1").status_code == 200
    assert client.get(base).json()["total"] == 0
    assert client.get(base + "?include_removed=true").json()["total"] == 1


def test_many_to_many_ordered_matrix_slices_cost_once(transfers, store):
    body, outs, inc = setup(store, merge=True)
    second = save_event(
        store, "i2", "daily", "in", quantity=1.5, timestamp_ms=STAMP + 2000, wallet_scope="configured"
    )
    first = change(store, inc[0], quantity=1.5)
    with store.db() as db:
        facts = {row["id"]: row for row in FundingReviews.enrich(db, [first, second])}
    values = body.model_dump()
    values["incoming"] = [
        {"event_id": row["id"], "source_version": source_version(facts[row["id"]]), "amount": "net_credit"}
        for row in [first, second]
    ]
    values["edges"] = [
        {"outgoing_id": outs[o]["id"], "incoming_id": row["id"], "quantity": quantity}
        for o, row, quantity in [(0, first, "1"), (1, first, "0.5"), (1, second, "1.5")]
    ]
    body = GroupPreview.model_validate(values)
    saved = transfers.groups.confirm(confirmation(transfers, body))
    result = calculated(
        transfers, store, saved, [opening("north", 1, 100), opening("reserve", 2, 500, "two", STAMP - 2000)]
    )
    daily = next(row for row in result["items"] if row["account_id"] == "daily")
    assert daily["known_open_cost"] == 600 and daily["quantity"] == 3
    assert [row["known_cost"] for row in result["transfers"]] == [225, 375]


def test_funding_review_revision_invalidates_group_even_with_unchanged_native_amount(transfers, store):
    from sibyl.accounting.funding.reviews import ReviewFunding

    body, out, inc = setup(store)
    saved = transfers.groups.confirm(confirmation(transfers, body))
    reviews = FundingReviews(store)
    state = reviews.state(out[0]["id"])
    reviews.save(
        out[0]["id"],
        ReviewFunding(
            source_version=state["balance_effect"]["source_version"],
            wallet_scope="configured",
            amount_convention="total_debit",
            note="Reviewed configured wallet movement.",
        ),
    )
    assert transfers.groups.detail(saved["id"])["status"] == "needs_review"
    rows = transfers.groups.detail(saved["id"])["current_members"]
    versions = {row["id"]: row["group_fingerprint"] for row in rows}
    for leg in [*body.outgoing, *body.incoming]:
        leg.source_version = versions[leg.event_id]
    reviewed = transfers.groups.confirm(confirmation(transfers, body, revision=1), saved["id"])
    assert reviewed["revision"] == 2 and reviewed["status"] == "confirmed"


def test_native_accountant_reports_groups_without_private_provider_reads(client, monkeypatch):
    from test_agent_guidance import forbid_reads, tool_call

    services = client.app.state.services
    body, _, _ = setup(services.store)
    saved = services.transfers.groups.confirm(confirmation(services.transfers, body))
    forbid_reads(client, monkeypatch)
    result = tool_call(client, "accountant", "accountant_snapshot", transfer_view=True)
    assert result["groups"][0]["id"] == saved["id"]
    detail = tool_call(client, "accountant", "accountant_snapshot", group_id=saved["id"])
    assert len(detail["reviewed"]["edges"]) == 2
    assert detail["status"] == "confirmed" and "audit" not in detail
