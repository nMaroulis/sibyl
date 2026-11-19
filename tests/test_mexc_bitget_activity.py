"""Exercise supported native requests with controlled transports and saved workspaces."""

import time

import ccxt
import pytest
from test_expanded_order_adapters import bitget_order, saved_account
from test_order_discovery import advance, job
from test_order_management import submit

from sibyl.exchanges.order_fills import fetch_order_fill_page
from sibyl.exchanges.order_lookup import lookup_order_page
from sibyl.exchanges.registry import provider_catalog
from sibyl.services.accounts.sync import AccountSync
from sibyl.services.trading.discovery import OrderDiscoveryRequest
from sibyl.services.trading.service import ExchangeTrading


def mexc_order(identity="C02__open", **changes):
    return {
        "orderId": identity,
        "symbol": "BTCUSDT",
        "type": "LIMIT",
        "side": "BUY",
        "status": "NEW",
        "timeInForce": "GTC",
        "origQty": "0.01",
        "price": "50000",
        "executedQty": "0",
        "cumulativeQuoteQty": "0",
        "orderListId": -1,
        "time": int(time.time() * 1000) - 1000,
        **changes,
    }


def mexc_fill(order="C02__closed", **changes):
    return {
        "id": "fad2af9e942049b6adbda1a271f990c6",
        "orderId": order,
        "symbol": "BTCUSDT",
        "price": "50000",
        "qty": "0.01",
        "quoteQty": "500",
        "commission": "0.02",
        "commissionAsset": "USDT",
        "time": int(time.time() * 1000) - 1000,
        "isBuyer": True,
        **changes,
    }


@pytest.mark.parametrize("provider", ["mexc", "bitget"])
def test_recover_native_limit_after_lost_response_without_resubmitting(manual_client, monkeypatch, provider):
    owner = manual_client.app.state.services
    owner.settings.allow_live_trading = True
    account, adapter = saved_account(owner, provider, "BTCUSDT")
    native = adapter._exchange
    writes, reads = [], []
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 10_000}})

    def lost_ack(symbol, kind, side, amount, price, *, params):
        assert (symbol, kind, side, amount, price) == ("BTC/USDT", "limit", "buy", 0.01, 50000)
        writes.append(params["clientOrderId" if provider == "mexc" else "clientOid"])
        raise ccxt.RequestTimeout("private response")

    def details(params):
        reads.append(params)
        if provider == "mexc":
            assert params == {"symbol": "BTCUSDT", "origClientOrderId": writes[0]}
            row = mexc_order("C02__recovered", clientOrderId=writes[0], Qty="0.01")
            row.pop("origQty")
            return row
        assert params == {"clientOid": writes[0]}
        row = bitget_order(2**60 + 17, clientOid=writes[0], orderSource="normal", enterPointSource="API")
        return {"code": "00000", "data": [row]}

    monkeypatch.setattr(native, "create_order", lost_ack)
    monkeypatch.setattr(
        native, "spotPrivateGetOrder" if provider == "mexc" else "privateSpotGetV2SpotTradeOrderInfo", details
    )
    service = owner.trading
    uncertain = submit(service, account)
    assert uncertain["status"] == "unknown"
    owner.settings.allow_live_trading = False
    result = ExchangeTrading(owner.market, owner.store).recover(uncertain["id"])
    assert result["recovery"]["state"] == "found" and result["status"] == "open"
    assert result["exchange_order_id"] == ("C02__recovered" if provider == "mexc" else str(2**60 + 17))
    assert len(writes) == len(reads) == 1


def test_recovery_never_matches_special_orders_or_mexc_missing_records(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    _, bitget = saved_account(owner, "bitget", "BTCUSDT")
    _, mexc = saved_account(owner, "mexc", "BTCUSDT")
    client_id = "a" * 32
    row = bitget_order(123, clientOid=client_id, orderSource="normal", enterPointSource="API", force="ioc")
    monkeypatch.setattr(
        bitget._exchange, "privateSpotGetV2SpotTradeOrderInfo", lambda _: {"code": "00000", "data": [row]}
    )
    with pytest.raises(ValueError, match="differs"):
        lookup_order_page(bitget._exchange, "bitget", client_id, "BTC/USDT", {}, 1, 100)

    def missing(_):
        raise ccxt.BadRequest('mexc {"code":22222,"msg":"record does not exist"}')

    monkeypatch.setattr(mexc._exchange, "spotPrivateGetOrder", missing)
    page = lookup_order_page(mexc._exchange, "mexc", client_id, "BTC/USDT", {}, 1, 100)
    assert page.complete and page.candidates == []


def test_mexc_discovery_resumes_split_selected_pair_window(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    account, adapter = saved_account(owner, "mexc", "BTCUSDT")
    native = adapter._exchange
    reads = []
    closed = mexc_order("C02__closed", status="FILLED", executedQty="0.01", cumulativeQuoteQty="500")
    monkeypatch.setattr(
        native, "spotPrivateGetOpenOrders", lambda request: [mexc_order()] if request == {} else None
    )

    def history(params):
        reads.append(params)
        assert params["symbol"] == "BTCUSDT" and params["limit"] == 1000
        if len(reads) == 1:
            return [closed] * 1000  # The native cap cannot establish completeness.
        return [closed] if params["startTime"] <= closed["time"] <= params["endTime"] else []

    monkeypatch.setattr(native, "spotPrivateGetAllOrders", history)
    service = owner.trading
    service.discovery.enqueue(OrderDiscoveryRequest(account_id=account.id, symbols=["BTC/USDT"]))
    advance(service, account)
    advance(service, account)
    assert not job(service, account)["complete"] and len(job(service, account)["cursor"]["windows"]) == 2
    restarted = ExchangeTrading(owner.market, owner.store)
    advance(restarted, account)
    advance(restarted, account)
    snapshot = restarted.discovery.snapshot()
    assert snapshot["jobs"][0]["complete"] and snapshot["jobs"][0]["history_requires_symbols"]
    assert reads[1]["endTime"] + 1 == reads[2]["startTime"]
    orders = {
        order["exchange_order_id"]: order for order in restarted.monitor(account_id=account.id)["items"]
    }
    assert orders["C02__closed"]["cost"] == 500 and orders["C02__open"]["read_only"]


def test_mexc_history_and_exact_fills_share_native_ids_and_retain_both_self_trade_legs(
    manual_client, monkeypatch
):
    owner = manual_client.app.state.services
    account, adapter = saved_account(owner, "mexc", "BTCUSDT")
    native = adapter._exchange
    reads = []
    executed = mexc_fill(isSelfTrade=True)
    opposite = {**executed, "orderId": "C02__sell", "isBuyer": False}
    closed = mexc_order("C02__closed", status="FILLED", executedQty="0.01", cumulativeQuoteQty="500")
    monkeypatch.setattr(native, "spotPrivateGetOpenOrders", lambda _: [])
    monkeypatch.setattr(native, "spotPrivateGetAllOrders", lambda _: [closed])

    def fill_history(params):
        reads.append(params)
        if "orderId" in params:
            assert params["orderId"] == "C02__closed"
            return [executed]
        if len(reads) == 2:
            return [executed] * 100
        return [executed, opposite] if params["startTime"] <= executed["time"] <= params["endTime"] else []

    monkeypatch.setattr(native, "spotPrivateGetMyTrades", fill_history)
    service = owner.trading
    service.discovery.enqueue(OrderDiscoveryRequest(account_id=account.id, symbols=["BTC/USDT"]))
    advance(service, account)
    advance(service, account)
    (order,) = service.monitor(account_id=account.id)["items"]
    result = service.reconciliation.sync(order["id"], manual=True)
    assert result["reconciliation"]["status"] == "matched"
    assert result["reconciliation"]["fees"] == [{"currency": "USDT", "cost": 0.02}]
    owner.account_sync.enqueue(account, ["BTC/USDT"])
    owner.account_sync.tick()
    restarted = AccountSync(owner.market, owner.store)
    restarted.tick()
    restarted.tick()
    assert restarted.snapshot()["jobs"][0]["status"] == "caught_up"
    fills = restarted.ledger.fills(account_id=account.id)
    assert fills["total"] == 2
    assert {fill["order_id"] for fill in fills["items"]} == {"C02__closed", "C02__sell"}
    assert {fill["trade_id"] for fill in fills["items"]} == {executed["id"]}
    assert all(read["symbol"] == "BTCUSDT" for read in reads)


@pytest.mark.parametrize("fault", ["wrong order", "saturated millisecond"])
def test_mexc_fills_do_not_complete_with_conflicting_or_capped_evidence(manual_client, monkeypatch, fault):
    owner = manual_client.app.state.services
    _, adapter = saved_account(owner, "mexc", "BTCUSDT")
    row = mexc_fill("different" if fault == "wrong order" else "C02__closed")
    monkeypatch.setattr(
        adapter._exchange,
        "spotPrivateGetMyTrades",
        lambda _: [row] * (2 if fault == "saturated millisecond" else 1),
    )
    exc = ccxt.NotSupported if fault == "saturated millisecond" else ccxt.ExchangeError
    with pytest.raises(
        exc, match="page capacity" if fault == "saturated millisecond" else "Unexpected market"
    ):
        fetch_order_fill_page(
            adapter._exchange,
            "mexc-window",
            "C02__closed",
            "BTC/USDT",
            {"start": row["time"], "end": row["time"] + 1},
            2,
        )


def test_settings_reflect_manual_market_and_read_paths_with_automation_pending():
    catalog = {row["id"]: row for row in provider_catalog()["items"]}
    features = {
        feature["id"]: feature["status"]
        for group in catalog["mexc"]["support"]
        for feature in group["features"]
    }
    assert all(features[key] == "available" for key in ("history_import", "recovery", "fill_reconciliation"))
    assert features["automated"] == "pending"
    assert catalog["mexc"]["market_orders"] and features["market_orders"] == "available"
