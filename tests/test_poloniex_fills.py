"""Cash-parent validation, exact fills and native pageId history are tested offline."""

import json
import time

import ccxt
import pytest
from test_order_discovery import advance
from test_poloniex_orders import FIRST_ID, order
from test_poloniex_orders import poloniex as poloniex

from sibyl.services.accounts.sync import AccountSync
from sibyl.services.trading.discovery import OrderDiscoveryRequest


def fill(identity=2**60 + 3, **changes):
    return {
        "id": str(identity),
        "pageId": str(identity + 1000),
        "orderId": str(FIRST_ID),
        "symbol": "BTC_USDT",
        "accountType": "SPOT",
        "side": "BUY",
        "type": "LIMIT",
        "matchRole": "MAKER",
        "price": "50000",
        "quantity": "0.01",
        "amount": "500",
        "feeCurrency": "USDT",
        "feeAmount": "0.2",
        "createTime": int(time.time() * 1000) - 1000,
        **changes,
    }


def test_exact_fills_and_resumed_history_share_ids_and_fee_corrections(poloniex, monkeypatch):
    owner, account, adapter = poloniex
    native, reads = adapter._exchange, []
    execution = fill()
    parent = order(state="FILLED", filledQuantity="0.01", filledAmount="500", avgPrice="50000")
    monkeypatch.setattr(native, "privateGetOrders", lambda _: [])
    monkeypatch.setattr(
        native, "privateGetOrdersHistory", lambda params: [parent] if params["from"] == "0" else []
    )
    monkeypatch.setattr(
        native, "privateGetOrdersId", lambda params: parent if params == {"id": parent["id"]} else None
    )
    monkeypatch.setattr(
        native,
        "privateGetOrdersIdTrades",
        lambda params: [execution] if params == {"id": parent["id"]} else None,
    )

    def history(params):
        reads.append(params.copy())
        assert params["symbols"] == "BTC_USDT" and params["direction"] == "NEXT"
        return [execution]

    monkeypatch.setattr(native, "privateGetTrades", history)
    owner.trading.discovery.enqueue(OrderDiscoveryRequest(account_id=account.id))
    for _ in range(3):
        advance(owner.trading, account)
    (saved,) = owner.trading.monitor(account_id=account.id)["items"]
    checked = owner.trading.reconciliation.sync(saved["id"], manual=True)
    assert checked["reconciliation"]["status"] == "matched"
    owner.account_sync.enqueue(account, ["BTC/USDT"])
    owner.account_sync.tick()
    restarted = AccountSync(owner.market, owner.store)
    restarted.tick()
    assert restarted.snapshot()["jobs"][0]["status"] == "caught_up"
    assert reads[0]["startTime"] == reads[1]["startTime"] and reads[0]["endTime"] == reads[1]["endTime"]
    assert reads[1]["from"] == execution["pageId"] and reads[1]["from"] != execution["id"]
    assert restarted.ledger.fills(account_id=account.id)["total"] == 1
    execution["feeAmount"] = "-0.25"
    owner.account_sync.enqueue(account, ["BTC/USDT"])
    owner.account_sync.tick()
    corrected = owner.trading.reconciliation.detail(saved["id"])
    assert corrected["reconciliation"]["fees"] == [{"currency": "USDT", "cost": -0.25}]
    assert "info" not in json.dumps(corrected)


def test_large_order_snapshot_pages_by_exact_trade_id_and_keeps_unknown_fee_currency(poloniex, monkeypatch):
    _, _, adapter = poloniex
    native = adapter._exchange
    monkeypatch.setattr(native, "privateGetOrdersId", lambda _: order())
    rows = [fill(2**60 + i) for i in range(103)]
    rows[-1].pop("feeCurrency")
    monkeypatch.setattr(native, "privateGetOrdersIdTrades", lambda _: list(reversed(rows)))
    first = adapter.fetch_order_fill_page(str(FIRST_ID), "BTC/USDT", {}, 100)
    last = adapter.fetch_order_fill_page(str(FIRST_ID), "BTC/USDT", first.cursor, 100)
    assert len(first.items) == 100 and not first.caught_up and len(last.items) == 3 and last.caught_up
    assert last.items[-1]["id"] == rows[-1]["id"] and last.items[-1]["fee"] == {"currency": None, "cost": 0.2}


def test_small_history_pages_tolerate_inclusive_boundaries_and_do_not_skip_extra_row(poloniex, monkeypatch):
    _, _, adapter = poloniex
    native, parents = adapter._exchange, []
    rows = [fill(2**60 + i) for i in range(3)]

    def parent(params):
        parents.append(params)
        return order()

    def history(params):
        return [row for row in rows if int(row["pageId"]) >= int(params["from"])][: params["limit"]]

    monkeypatch.setattr(native, "privateGetOrdersId", parent)
    monkeypatch.setattr(native, "privateGetTrades", history)
    cursor, ids = {}, []
    for _ in range(4):
        page = adapter.fetch_trade_page("BTC/USDT", cursor, 1)
        ids.extend(row["id"] for row in page.items)
        cursor = page.cursor
    assert ids == [row["id"] for row in rows] and page.caught_up and len(parents) == 3


@pytest.mark.parametrize("change", [{"loan": True}, {"loan": None}, {"symbol": "ETH_USDT"}, {"id": "123"}])
def test_borrowed_or_mismatched_parent_cannot_admit_fills(poloniex, monkeypatch, change):
    _, _, adapter = poloniex
    monkeypatch.setattr(adapter._exchange, "privateGetOrdersId", lambda _: order(**change))
    with pytest.raises(ccxt.ExchangeError, match="parent"):
        adapter.fetch_order_fill_page(str(FIRST_ID), "BTC/USDT", {})


@pytest.mark.parametrize(
    "change",
    [
        {"accountType": "MARGIN"},
        {"side": "SELL"},
        {"orderId": "123"},
        {"symbol": "ETH_USDT"},
        {"id": float(2**60)},
    ],
)
def test_incompatible_execution_is_rejected(poloniex, monkeypatch, change):
    _, _, adapter = poloniex
    monkeypatch.setattr(adapter._exchange, "privateGetOrdersId", lambda _: order())
    monkeypatch.setattr(adapter._exchange, "privateGetOrdersIdTrades", lambda _: [fill(**change)])
    with pytest.raises(ccxt.ExchangeError):
        adapter.fetch_order_fill_page(str(FIRST_ID), "BTC/USDT", {})


def test_expired_parent_leaves_coverage_unconfirmed(poloniex, monkeypatch):
    _, _, adapter = poloniex

    def missing(_):
        raise ccxt.OrderNotFound("PRIVATE")

    monkeypatch.setattr(adapter._exchange, "privateGetTrades", lambda _: [fill()])
    monkeypatch.setattr(adapter._exchange, "privateGetOrdersId", missing)
    with pytest.raises(ccxt.NotSupported, match="parent is unavailable"):
        adapter.fetch_trade_page("BTC/USDT", {})


def test_history_freezes_window_bounds_and_reuses_parent_within_page(poloniex, monkeypatch):
    _, _, adapter = poloniex
    native, parents, requests = adapter._exchange, [], []
    rows = [fill(2**60 + i) for i in range(21)]

    def parent(params):
        parents.append(params)
        return order()

    def history(params):
        requests.append(params.copy())
        return [row for row in rows if int(row["pageId"]) >= int(params["from"])][: params["limit"]]

    monkeypatch.setattr(native, "privateGetOrdersId", parent)
    monkeypatch.setattr(native, "privateGetTrades", history)
    first = adapter.fetch_trade_page("BTC/USDT", {})
    second = adapter.fetch_trade_page("BTC/USDT", first.cursor)
    assert len(first.items) == 20 and len(second.items) == 1 and len(parents) == 2
    assert first.cursor["start"] == second.cursor["start"] and first.cursor["end"] == second.cursor["end"]
    assert requests[0]["limit"] == 21


def test_matching_trade_ids_on_different_orders_remain_separate_ledger_legs(poloniex, monkeypatch):
    owner, account, adapter = poloniex
    native = adapter._exchange
    bought = fill()
    sold = fill(orderId=str(FIRST_ID + 1), side="SELL", pageId=str(int(bought["pageId"]) + 1))
    rows = [bought, sold]

    def parent(params):
        return order(identity=int(params["id"]), side="BUY" if params["id"] == bought["orderId"] else "SELL")

    monkeypatch.setattr(native, "privateGetOrdersId", parent)
    monkeypatch.setattr(
        native,
        "privateGetTrades",
        lambda params: [row for row in rows if int(row["pageId"]) >= int(params["from"])],
    )
    owner.account_sync.enqueue(account, ["BTC/USDT"])
    owner.account_sync.tick()
    owner.account_sync.tick()
    saved = owner.account_sync.ledger.fills(account_id=account.id)
    assert saved["total"] == 2
    assert {row["trade_id"] for row in saved["items"]} == {bought["id"]}
    assert {row["order_id"] for row in saved["items"]} == {bought["orderId"], sold["orderId"]}
    assert {row["side"] for row in saved["items"]} == {"buy", "sell"}
