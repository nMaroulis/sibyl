"""BitMart v4 native-shaped reads verify discovery, recovery and shared execution imports offline."""

import json
import time

import ccxt
import pytest
from test_order_discovery import advance, job, spot_market
from test_order_management import submit

from sibyl.exchanges.bitmart_activity import discover_page, fetch_fill_page, lookup_order
from sibyl.exchanges.registry import provider_catalog
from sibyl.models import ConnectionCreate
from sibyl.services.accounts.sync import AccountSync
from sibyl.services.trading.discovery import OrderDiscoveryRequest
from sibyl.services.trading.service import ExchangeTrading


def response(rows):
    return {"code": 1000, "message": "PRIVATE", "data": rows, "trace": "PRIVATE"}


def order(identity="118100034543076010", **changes):
    return {
        "orderId": identity,
        "clientOrderId": "external",
        "symbol": "BTC_USDT",
        "side": "buy",
        "orderMode": "spot",
        "type": "limit",
        "state": "new",
        "price": "50000",
        "priceAvg": "0",
        "size": "0.01",
        "filledSize": "0",
        "notional": "500",
        "filledNotional": "0",
        "createTime": int(time.time() * 1000) - 1000,
        **changes,
    }


def fill(identity="122177405911172002", **changes):
    return {
        "tradeId": identity,
        "orderId": "118100034543076010",
        "symbol": "BTC_USDT",
        "side": "buy",
        "orderMode": "spot",
        "type": "limit",
        "price": "50000",
        "size": "0.01",
        "notional": "500",
        "fee": "0.2",
        "feeCoinName": "USDT",
        "tradeRole": "maker",
        "createTime": int(time.time() * 1000) - 1000,
        **changes,
    }


@pytest.fixture
def bitmart(manual_client):
    owner = manual_client.app.state.services
    account = owner.store.add_connection(
        ConnectionCreate(exchange="bitmart", label="Fixture", api_key="fake", secret="fake", uid="fake-memo")
    )
    adapter = owner.market.client(account)
    adapter._exchange.set_markets([spot_market("BTC_USDT")])
    return owner, account, adapter


def test_open_and_recent_discovery_resume_split_ranges_and_include_older_open_orders(bitmart, monkeypatch):
    owner, account, adapter = bitmart
    native, reads = adapter._exchange, []
    older = order("old-opaque-order", createTime=int(time.time() * 1000) - 20 * 86400000)
    closed = order(state="filled", filledSize="0.01", filledNotional="500", priceAvg="50000")

    def opened(params):
        reads.append(("open", params.copy()))
        assert params["orderMode"] == "spot" and params["startTime"] == 1
        return response([older])

    def finished(params):
        reads.append(("recent", params.copy()))
        assert params["orderMode"] == "spot"
        if len(reads) == 2:
            return response([closed] * 200)
        return (
            response([closed])
            if params["startTime"] <= closed["createTime"] <= params["endTime"]
            else response([])
        )

    monkeypatch.setattr(native, "privatePostSpotV4QueryOpenOrders", opened)
    monkeypatch.setattr(native, "privatePostSpotV4QueryHistoryOrders", finished)
    service = owner.trading
    service.discovery.enqueue(OrderDiscoveryRequest(account_id=account.id, days=3))
    advance(service, account)
    advance(service, account)
    assert len(job(service, account)["cursor"]["windows"]) == 2
    restarted = ExchangeTrading(owner.market, owner.store)
    advance(restarted, account)
    advance(restarted, account)
    assert job(restarted, account)["complete"]
    monitor = restarted.monitor(account_id=account.id)
    assert monitor["total"] == 2 and all(row["read_only"] for row in monitor["items"])
    assert {row["exchange_order_id"] for row in monitor["items"]} == {older["orderId"], closed["orderId"]}
    assert reads[2][1]["endTime"] - 1 == reads[3][1]["startTime"]


def test_recovery_after_lost_ack_uses_only_exact_client_read(bitmart, monkeypatch):
    owner, account, adapter = bitmart
    owner.settings.allow_live_trading = True
    native, writes, reads = adapter._exchange, [], []
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 10_000}})

    def lost_ack(symbol, kind, side, quantity, price, *, params):
        assert (symbol, kind, side, quantity, price) == ("BTC/USDT", "limit", "buy", 0.01, 50000)
        writes.append(params["clientOrderId"])
        raise ccxt.RequestTimeout("PRIVATE")

    def lookup(params):
        reads.append(params)
        assert params == {"clientOrderId": writes[0]}
        return response(
            order(
                clientOrderId=writes[0],
                state="partially_filled",
                filledSize="0.004",
                filledNotional="200",
                priceAvg="50000",
            )
        )

    monkeypatch.setattr(native, "create_order", lost_ack)
    monkeypatch.setattr(native, "privatePostSpotV4QueryClientOrder", lookup)
    uncertain = submit(owner.trading, account)
    assert uncertain["status"] == "unknown"
    owner.settings.allow_live_trading = False
    restarted = ExchangeTrading(owner.market, owner.store)
    recovered = restarted.recover(uncertain["id"])
    assert recovered["recovery"]["state"] == "found" and recovered["filled"] == 0.004
    assert recovered["exchange_order_id"] == "118100034543076010"
    assert len(writes) == len(reads) == 1 and "PRIVATE" not in json.dumps(recovered)


@pytest.mark.parametrize(
    "change",
    [
        {"orderMode": "iso_margin"},
        {"type": "limit_maker"},
        {"symbol": "ETH_USDT"},
        {"clientOrderId": "other"},
    ],
)
def test_recovery_rejects_incompatible_original_terms(bitmart, monkeypatch, change):
    _, _, adapter = bitmart
    monkeypatch.setattr(
        adapter._exchange,
        "privatePostSpotV4QueryClientOrder",
        lambda _: response(order(**{"clientOrderId": "a" * 32, **change})),
    )
    with pytest.raises(ValueError, match="differs"):
        lookup_order(adapter._exchange, "a" * 32, "BTC/USDT")


def test_exact_fills_and_split_account_history_share_ids_and_fee_corrections(bitmart, monkeypatch):
    owner, account, adapter = bitmart
    native, reads = adapter._exchange, []
    execution = fill()
    closed = order(state="filled", filledSize="0.01", filledNotional="500", priceAvg="50000")
    monkeypatch.setattr(native, "privatePostSpotV4QueryOpenOrders", lambda _: response([]))
    monkeypatch.setattr(native, "privatePostSpotV4QueryHistoryOrders", lambda _: response([closed]))
    monkeypatch.setattr(
        native,
        "privatePostSpotV4QueryOrderTrades",
        lambda params: response([execution]) if params == {"orderId": closed["orderId"]} else None,
    )

    def history(params):
        reads.append(params.copy())
        assert params["symbol"] == "BTC_USDT" and params["orderMode"] == "spot"
        if len(reads) == 1:
            return response([execution] * 100)
        return (
            response([execution])
            if params["startTime"] <= execution["createTime"] <= params["endTime"]
            else response([])
        )

    monkeypatch.setattr(native, "privatePostSpotV4QueryTrades", history)
    service = owner.trading
    service.discovery.enqueue(OrderDiscoveryRequest(account_id=account.id))
    advance(service, account)
    advance(service, account)
    (saved,) = service.monitor(account_id=account.id)["items"]
    initial = service.reconciliation.sync(saved["id"], manual=True)
    assert initial["reconciliation"]["status"] == "matched"
    owner.account_sync.enqueue(account, ["BTC/USDT"])
    owner.account_sync.tick()
    sync = AccountSync(owner.market, owner.store)
    sync.tick()
    sync.tick()
    assert sync.snapshot()["jobs"][0]["status"] == "caught_up"
    assert sync.ledger.fills(account_id=account.id)["total"] == 1
    execution["fee"] = "0.25"
    owner.account_sync.enqueue(account, ["BTC/USDT"])
    owner.account_sync.tick()
    corrected = service.reconciliation.detail(saved["id"])
    assert corrected["reconciliation"]["fees"] == [{"currency": "USDT", "cost": 0.25}]
    assert "PRIVATE" not in json.dumps(corrected)


def test_full_timestamp_windows_and_inclusive_boundaries_do_not_skip_records(bitmart, monkeypatch):
    _, _, adapter = bitmart
    native = adapter._exchange
    end = int(time.time() * 1000)
    inside = order(createTime=end - 1, state="filled", filledSize="0.01", filledNotional="500")
    boundary = order("other", createTime=end, state="filled", filledSize="0.01", filledNotional="500")
    monkeypatch.setattr(native, "privatePostSpotV4QueryHistoryOrders", lambda _: response([inside, boundary]))
    page = discover_page(native, "recent", {}, end - 10, end)
    assert page[2] and len(page[0]) == 1 and page[0][0]["id"] == inside["orderId"]
    monkeypatch.setattr(native, "privatePostSpotV4QueryHistoryOrders", lambda _: response([inside] * 200))
    with pytest.raises(ccxt.NotSupported, match="timestamp"):
        discover_page(native, "recent", {}, end - 1, end)


def test_exact_fill_snapshot_pages_by_native_id_and_preserves_unknown_fee_currency(bitmart, monkeypatch):
    _, _, adapter = bitmart
    native = adapter._exchange
    rows = [fill(str(2**60 + value)) for value in range(101)]
    rows[-1].pop("feeCoinName")
    monkeypatch.setattr(native, "privatePostSpotV4QueryOrderTrades", lambda _: response(rows))
    first = adapter.fetch_order_fill_page(rows[0]["orderId"], "BTC/USDT", {})
    final = adapter.fetch_order_fill_page(rows[0]["orderId"], "BTC/USDT", first.cursor)
    assert len(first.items) == 100 and not first.caught_up and len(final.items) == 1 and final.caught_up
    assert final.items[0]["id"] == str(2**60 + 100)
    assert final.items[0]["fee"] == {"currency": None, "cost": 0.2}


@pytest.mark.parametrize(
    "change", [{"orderMode": "iso_margin"}, {"orderId": "different"}, {"symbol": "ETH_USDT"}]
)
def test_execution_scope_must_match_the_selected_native_order(bitmart, monkeypatch, change):
    _, _, adapter = bitmart
    monkeypatch.setattr(
        adapter._exchange, "privatePostSpotV4QueryOrderTrades", lambda _: response([fill(**change)])
    )
    with pytest.raises(ccxt.ExchangeError):
        fetch_fill_page(adapter._exchange, "BTC/USDT", {}, 100, order_id="118100034543076010")


def test_expired_or_missing_client_record_keeps_an_empty_lookup(bitmart, monkeypatch):
    _, _, adapter = bitmart

    def missing(_):
        raise ccxt.OrderNotFound("PRIVATE")

    monkeypatch.setattr(adapter._exchange, "privatePostSpotV4QueryClientOrder", missing)
    assert lookup_order(adapter._exchange, "a" * 32, "BTC/USDT") == []


def test_settings_are_derived_from_the_implemented_read_paths():
    (provider,) = [row for row in provider_catalog()["items"] if row["id"] == "bitmart"]
    features = {feature["id"]: feature for group in provider["support"] for feature in group["features"]}
    for name in ("recovery", "discovery", "history_import", "fill_reconciliation"):
        assert features[name]["status"] == "available"
    assert features["automated"]["status"] == "pending"
    assert provider["market_order_sides"] == ["buy", "sell"]
    assert features["market_orders"]["status"] == "available"
