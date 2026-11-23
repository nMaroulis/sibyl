"""Offline OKX funding response contracts, restart and wallet reconciliation."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from time import time

import ccxt
import pytest

from sibyl.accounting.funding.rules import balance_effect
from sibyl.exchanges import create_client
from sibyl.exchanges.funding import DAY, fetch_funding_page
from sibyl.models import ConnectionCreate
from sibyl.services.funding.contracts import refresh_streams, scan_streams
from sibyl.services.funding.ledger import funding_event
from sibyl.services.funding.sync import FundingSync, FundingSyncRequest
from sibyl.services.transfers.reconciliation import eligible

FIRST_ID = 2**60 + 17


def envelope(*rows):
    return {"code": "0", "msg": "", "data": list(rows)}


def chain_row(stamp, native_id=FIRST_ID, **changes):
    return {
        "depId": str(native_id),
        "wdId": str(native_id),
        "ts": str(stamp),
        "state": "2",
        "chain": "BTC-Bitcoin",
        "ccy": "BTC",
        "amt": "0.2",
        "fee": "0.001",
        "feeCcy": "ETH",
        "txId": "PRIVATE_HASH",
        "from": "PRIVATE_ORIGIN",
        "to": "PRIVATE_RECIPIENT",
        **changes,
    }


def transfer_row(stamp, native_id=FIRST_ID, **changes):
    return {
        "billId": str(native_id),
        "ts": str(stamp),
        "type": "1",
        "subType": "11",
        "ccy": "USDT",
        "balChg": "99.8",
        "bal": "169.8",
        "fee": "-0.2",
        "from": "6",
        "to": "18",
        "mgnMode": "",
        "instType": "",
        "notes": "PRIVATE_ACCOUNT_NOTES",
        **changes,
    }


@pytest.fixture
def workspace(manual_client):
    owner = manual_client.app.state.services
    account = owner.store.add_connection(
        ConnectionCreate(
            exchange="okx", label="Fixture OKX", api_key="key", secret="secret", passphrase="pass"
        )
    )
    owner.store.activate_account(account.id, True)
    account = next(row for row in owner.store.connections() if row.id == account.id)
    return owner, account, owner.market.client(account)


def selected(stream, start, end):
    return FundingSyncRequest(
        streams=[stream],
        start=datetime.fromtimestamp(start / 1000, UTC),
        end=datetime.fromtimestamp(end / 1000, UTC),
    )


def test_deposit_http_contract_and_checkpoint_preserve_fifty_one_records(workspace, monkeypatch):
    owner, account, adapter = workspace
    native = adapter._exchange
    end = int(time() * 1000) - 60000
    start = end - 1000
    # Multiple records at the same timestamp survive full-page bisection.
    data = [
        chain_row(stamp, FIRST_ID + index, state="1" if index == 0 else "2")
        for index, stamp in enumerate([end - 900] * 25 + [end - 100] * 26)
    ]
    requests = []

    def read(path, api, method, params, *args, **kwargs):
        assert (path, api, method) == ("asset/deposit-history", "private", "GET")
        requests.append(params.copy())
        items = [row for row in data if int(params["before"]) < int(row["ts"]) < int(params["after"])]
        return envelope(*items[: int(params["limit"])])

    monkeypatch.setattr(native, "fetch2", read)
    owner.funding_sync.enqueue(account, selected("deposit", start, end))
    owner.funding_sync.tick()
    assert owner.funding_sync.ledger.events(account_id=account.id)["total"] == 0
    restarted = FundingSync(owner.market, owner.store)
    try:
        restarted.tick()
        restarted.tick()
        result = restarted.ledger.events(account_id=account.id, limit=100)
        assert result["total"] == 51
        assert len({row["native_id"] for row in result["items"]}) == 51
        restricted = next(row for row in result["items"] if row["native_id"] == str(FIRST_ID))
        assert restricted["status"] == "restricted"
        assert restricted["fee"] == {"currency": None, "cost": None}
        assert restarted.snapshot()["jobs"][0]["status"] == "caught_up"
        assert all(row["type"] == "4" and row["limit"] == "50" for row in requests)
        assert len(requests) == 3
        assert "PRIVATE" not in json.dumps(result)
        assert "cursor" not in json.dumps(restarted.snapshot())
    finally:
        restarted.close()


@pytest.mark.parametrize(
    "changes, error",
    [
        ({"type": "3"}, "on-chain scope"),
        ({"chain": ""}, "on-chain scope"),
        ({"fromWdId": "7"}, "on-chain scope"),
        ({"amt": True}, "funding amount"),
        ({"depId": 1e18}, "execution identity"),
    ],
)
def test_okx_deposit_rejects_ambiguous_scope_and_sizing(workspace, monkeypatch, changes, error):
    _, _, adapter = workspace
    now = int(time() * 1000) - 60000
    native = adapter._exchange
    monkeypatch.setattr(
        native, "privateGetAssetDepositHistory", lambda _: envelope(chain_row(now, **changes))
    )
    with pytest.raises(ccxt.ExchangeError, match=error):
        fetch_funding_page(native, "okx", "deposit", {"start": now - 100, "end": now + 100})


def test_saturated_millisecond_stops_instead_of_claiming_funding_coverage(workspace, monkeypatch):
    _, _, adapter = workspace
    native = adapter._exchange
    now = int(time() * 1000) - 60000
    monkeypatch.setattr(native, "privateGetAssetDepositHistory", lambda _: envelope(chain_row(now)))
    with pytest.raises(ccxt.NotSupported, match="single timestamp"):
        fetch_funding_page(native, "okx", "deposit", {"start": now, "end": now}, limit=1)


def test_withdrawal_keeps_reported_fee_asset_and_unknown_trading_effect(workspace, monkeypatch):
    owner, account, adapter = workspace
    now = int(time() * 1000) - 60000
    native = adapter._exchange
    observed = []

    def withdraw(path, api, method, params, *args, **kwargs):
        assert (path, api, method) == ("asset/withdrawal-history", "private", "GET")
        assert params["type"] == "4"
        observed.append(params)
        return envelope(chain_row(now))

    monkeypatch.setattr(native, "fetch2", withdraw)
    owner.funding_sync.enqueue(account, selected("withdrawal", now - 1000, now + 1000))
    owner.funding_sync.tick()
    (row,) = owner.funding_sync.ledger.events(account_id=account.id)["items"]
    assert row["fee"] == {"currency": "ETH", "cost": 0.001} and row["quantity"] == 0.2
    assert row["wallet_scope"] == "unknown" and row["posted_ms"] is None
    assert row["balance_effect"]["quantity"] is None
    assert "PRIVATE" not in json.dumps(row)
    assert len(observed) == 1


def test_posted_transfer_bill_drives_balance_check_without_counting_the_fee_twice(workspace, monkeypatch):
    owner, account, adapter = workspace
    now = int(time() * 1000) - 60000
    native = adapter._exchange
    calls = []
    outgoing = transfer_row(
        now - 1000, FIRST_ID, subType="12", balChg="-10.1", fee="-0.1", **{"from": "18", "to": "6"}
    )
    incoming = transfer_row(now, FIRST_ID + 1)
    query = {"type": "1", "begin": str(now - 2001), "end": str(now + 2001), "limit": "50"}

    def read(path, api, method, params, *args, **kwargs):
        assert (path, api, method) == ("account/bills-archive", "private", "GET")
        calls.append(params.copy())
        if params == query:
            return envelope(incoming)
        if params == {**query, "after": str(FIRST_ID + 1)}:
            return envelope(outgoing)
        assert params == {**query, "after": str(FIRST_ID)}
        return envelope()

    monkeypatch.setattr(native, "fetch2", read)
    service = owner.funding_sync
    service.enqueue(account, selected("transfer", now - 2000, now + 2000))
    service.tick()
    restarted = FundingSync(owner.market, owner.store)
    try:
        restarted.tick()
        restarted.tick()
        saved = restarted.ledger.events(account_id=account.id)
        assert saved["total"] == 2 and len(calls) == 3
        assert restarted.snapshot()["jobs"][0]["status"] == "caught_up"
        for row in saved["items"]:
            assert row["posted_ms"] == row["timestamp_ms"]
            assert not eligible(row, row["direction"])
            assert balance_effect(row)["rule"] == "okx-trading-bill-net-v1"
            assert balance_effect(row)["provenance"] == "provider"
        effects = {row["direction"]: Decimal(row["balance_effect"]["quantity"]) for row in saved["items"]}
        assert effects == {"in": Decimal("99.8"), "out": Decimal("-10.1")}
        assert "PRIVATE" not in json.dumps(saved)
    finally:
        restarted.close()


@pytest.mark.parametrize(
    "changes",
    [
        {"subType": "12"},
        {"balChg": "-1"},
        {"from": "99"},
        {"type": "2"},
        {"mgnMode": "cross"},
        {"instType": "FUTURES"},
    ],
)
def test_contradictory_trading_transfer_evidence_rejects_the_page(workspace, monkeypatch, changes):
    _, _, adapter = workspace
    now = int(time() * 1000) - 60000
    native = adapter._exchange
    monkeypatch.setattr(
        native, "privateGetAccountBillsArchive", lambda _: envelope(transfer_row(now, **changes))
    )
    with pytest.raises(ccxt.ExchangeError, match="wallet transfer"):
        adapter.fetch_funding_page("transfer", {"start": now - 2000, "end": now + 2000})


def test_old_transfer_window_and_repeating_native_id_are_explicit(workspace, monkeypatch):
    _, _, adapter = workspace
    now = int(time() * 1000) - 60000
    native = adapter._exchange
    monkeypatch.setattr(native, "privateGetAccountBillsArchive", lambda _: envelope(transfer_row(now)))
    with pytest.raises(ccxt.ExchangeError, match="did not advance"):
        adapter.fetch_funding_page("transfer", {"start": now - 100, "end": now, "after": str(FIRST_ID)})
    monkeypatch.setattr(
        native, "privateGetAccountBillsArchive", lambda _: pytest.fail("Out-of-retention read")
    )
    with pytest.raises(ccxt.NotSupported, match="89 days"):
        adapter.fetch_funding_page("transfer", {"start": now - 90 * DAY, "end": now})


def test_strict_balance_observation_reads_cash_and_keeps_existing_equity_display(workspace, monkeypatch):
    owner, account, adapter = workspace
    now = int(time() * 1000) - 60000
    native = adapter._exchange
    monkeypatch.setattr(
        native,
        "privateGetAccountBalance",
        lambda _: envelope(
            {"uTime": str(now), "details": [{"ccy": "USDT", "cashBal": "123.45", "eq": "234.56"}]}
        ),
    )
    monkeypatch.setattr(
        native, "fetch_balance", lambda **_: {"total": {"USDT": 234.56}, "free": {}, "used": {}}
    )
    assert adapter.fetch_balance()["total"]["USDT"] == 234.56
    assert adapter.fetch_balance_snapshot() == {
        "total": {"USDT": 123.45},
        "free": {},
        "used": {},
        "timestamp": now,
    }
    with owner.store.db() as db:
        latest = owner.balance_checks.journal.scope(db, account.id)
        monkeypatch.setattr(type(adapter), "balance_snapshot_revision", 1)
        assert owner.balance_checks.journal.scope(db, account.id) != latest


def test_okx_funding_policies_are_opt_in_and_production_only(workspace):
    _, account, _ = workspace
    assert refresh_streams(account) == ["deposit", "withdrawal"]
    assert scan_streams(account) == ["deposit", "withdrawal", "transfer"]
    test_account = account.model_copy(update={"sandbox": True})
    assert refresh_streams(test_account) == scan_streams(test_account) == []
    sandbox = create_client(
        "okx", credentials={"apiKey": "key", "secret": "secret", "password": "pass"}, sandbox=True
    )
    try:
        with pytest.raises(ccxt.NotSupported):
            sandbox.fetch_funding_page("deposit", {"start": 1, "end": 2})
    finally:
        sandbox.close()


def test_ledger_requires_verified_posting_even_for_normalized_okx_transfer():
    row = {
        "native_id": str(FIRST_ID),
        "asset": "USDT",
        "timestamp_ms": 2,
        "posted_ms": 3,
        "kind": "transfer",
        "direction": "in",
        "quantity": "10",
        "fee": {},
        "status": "completed",
        "internal": True,
        "amount_basis": "ledger_amount",
        "wallet_scope": "configured",
        "wallet_route": {"from": "FUNDING", "to": "TRADING"},
    }
    with pytest.raises(ValueError, match="wallet route"):
        funding_event(row, {"exchange": "okx", "stream": "transfer", "start_ms": 1, "end_ms": 5})
