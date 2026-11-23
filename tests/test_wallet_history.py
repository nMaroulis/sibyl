"""Gate/HTX resumable imports preserve the same verified parent and execution evidence."""

import time

import ccxt
import pytest
from test_expanded_order_adapters import gate_order, saved_account
from test_gate_htx_orders import htx_fill, htx_order, save_htx

from sibyl.services.accounts.sync import AccountSync


def gate_fill(**changes):
    return {
        "id": str(2**60 + 11),
        "order_id": str(2**60 + 7),
        "currency_pair": "BTC_USDT",
        "side": "buy",
        "price": "50000",
        "amount": "0.01",
        "fee": "0.2",
        "fee_currency": "USDT",
        "create_time": str(int(time.time()) - 1),
        "create_time_ms": str(int(time.time() * 1000) - 1000),
        **changes,
    }


def test_gate_history_resumes_native_pages_and_rechecks_cash_parent(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    account, adapter = saved_account(owner, "gate", "BTC_USDT")
    native, reads, parents = adapter._exchange, [], []
    row = gate_fill()
    parent = gate_order(row["order_id"])
    monkeypatch.setattr(
        native, "privateSpotGetOrdersOrderId", lambda params: parents.append(params.copy()) or parent
    )
    monkeypatch.setattr(
        native,
        "privateSpotGetMyTrades",
        lambda params: reads.append(params.copy()) or ([row] if params["page"] == 1 else []),
    )
    owner.account_sync.enqueue(account, ["BTC/USDT"])
    owner.account_sync.tick()
    restarted = AccountSync(owner.market, owner.store)
    restarted.tick()
    assert restarted.snapshot()["jobs"][0]["status"] == "caught_up"
    assert reads[0]["from"] == reads[1]["from"] and reads[0]["to"] == reads[1]["to"]
    assert reads[1]["page"] == 2 and len(parents) == 1
    saved = restarted.ledger.fills(account_id=account.id)
    assert saved["total"] == 1 and saved["items"][0]["trade_id"] == row["id"]
    row["fee"] = "-0.1"
    owner.account_sync.enqueue(account, ["BTC/USDT"])
    owner.account_sync.tick()
    assert owner.account_sync.ledger.fills(account_id=account.id)["items"][0]["fees"] == [
        {"currency": "USDT", "cost": -0.1}
    ]


def test_gate_history_rejects_unverified_wallet_or_fee_instructions(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    _, adapter = saved_account(owner, "gate", "BTC_USDT")
    monkeypatch.setattr(adapter._exchange, "privateSpotGetMyTrades", lambda _: [gate_fill()])
    monkeypatch.setattr(
        adapter._exchange,
        "privateSpotGetOrdersOrderId",
        lambda _: gate_order(str(2**60 + 7), account="margin"),
    )
    with pytest.raises(ccxt.NotSupported, match="wallet-scope"):
        adapter.fetch_trade_page("BTC/USDT", {})


def test_htx_history_retains_wallet_and_48_hour_checkpoints(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    account, adapter = save_htx(owner)
    native, reads = adapter._exchange, []
    execution = htx_fill()
    monkeypatch.setattr(
        native, "spotPrivateGetV1OrderOrdersOrderId", lambda _: {"status": "ok", "data": htx_order()}
    )

    def history(params):
        reads.append(params.copy())
        assert params["end-time"] - params["start-time"] < 2 * 86400000
        return {
            "status": "ok",
            "data": [execution]
            if params["start-time"] <= execution["created-at"] <= params["end-time"]
            else [],
        }

    monkeypatch.setattr(native, "spotPrivateGetV1OrderMatchresults", history)
    owner.account_sync.enqueue(account, ["BTC/USDT"])
    owner.account_sync.tick()
    restarted = AccountSync(owner.market, owner.store)
    for _ in range(3):
        restarted.tick()
    saved = restarted.ledger.fills(account_id=account.id)
    assert saved["total"] == 1 and saved["items"][0]["trade_id"] == str(execution["id"])
    assert restarted.snapshot()["jobs"][0]["status"] == "caught_up" and len(reads) == 4


def test_htx_wallet_change_during_history_requires_review(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    _, adapter = save_htx(owner)
    with pytest.raises(ValueError, match="wallet changed"):
        adapter.fetch_trade_page("BTC/USDT", {"account": "different"})
