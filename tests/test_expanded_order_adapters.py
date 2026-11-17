"""Native-shaped offline transports for the additional order discovery and recovery adapters."""

import json
import time

import ccxt
import pytest
from test_extended_account_history import native as fill_row
from test_order_discovery import advance, job, spot_market
from test_order_management import submit
from test_order_recovery import gemini_order

from sibyl.exchanges.order_fills import fetch_order_fill_page
from sibyl.models import ConnectionCreate
from sibyl.services.trading.discovery import OrderDiscoveryRequest
from sibyl.services.trading.service import ExchangeTrading


def saved_account(owner, exchange, native_id, *, quote="USDT"):
    account = owner.store.add_connection(
        ConnectionCreate(exchange=exchange, label="Fixture", api_key="fake", secret="fake", passphrase="fake")
    )
    adapter = owner.market.client(account)
    adapter._exchange.set_markets(
        [{**spot_market(native_id), "quote": quote, "quoteId": quote, "symbol": f"BTC/{quote}"}]
    )
    return account, adapter


def gate_order(identity, **changes):
    stamp = str(int(time.time() * 1000) - 1000)
    return {
        "id": str(identity),
        "currency_pair": "BTC_USDT",
        "account": "spot",
        "type": "limit",
        "side": "buy",
        "time_in_force": "gtc",
        "amount": "0.01",
        "price": "50000",
        "create_time_ms": stamp,
        "update_time_ms": stamp,
        "status": "open",
        "left": "0.01",
        "filled_amount": "0",
        "filled_total": "0",
        **changes,
    }


def bitget_order(identity, **changes):
    return {
        "orderId": str(identity),
        "symbol": "btcusdt",
        "orderType": "limit",
        "side": "buy",
        "size": "0.01",
        "price": "50000",
        "baseVolume": "0",
        "quoteVolume": "0",
        "status": "live",
        "tpslType": "normal",
        "cTime": str(int(time.time() * 1000) - 1000),
        **changes,
    }


def test_gemini_discovers_open_regular_orders_only(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    account, adapter = saved_account(owner, "gemini", "btcusd", quote="USD")
    requests = []

    def read(params):
        requests.append(params)
        return [
            gemini_order(order_id=2**60 + 7),
            gemini_order(order_id=11, type="exchange stop limit"),
            gemini_order(order_id=12, symbol="btcusdperp"),
        ]

    monkeypatch.setattr(adapter._exchange, "privatePostV1Orders", read)
    service = owner.trading
    service.discovery.enqueue(OrderDiscoveryRequest(account_id=account.id))
    advance(service, account)
    saved = job(service, account)
    assert saved["complete"] and saved["skipped"] == 2 and requests == [{}]
    (order,) = service.monitor(account_id=account.id)["items"]
    assert order["read_only"] and order["exchange_order_id"] == str(2**60 + 7)
    assert not service.discovery.snapshot()["jobs"][0]["recent_enabled"]


def test_gate_discovery_restarts_middle_of_grouped_open_pages(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    account, adapter = saved_account(owner, "gate", "BTC_USDT")
    calls = []

    def opened(params):
        calls.append(("open", params))
        if params["page"] != 1:
            return []
        return [
            {
                "currency_pair": "BTC_USDT",
                "orders": [gate_order(2**60 + 8), gate_order(2**60 + 7, account="margin")],
            }
        ]

    def finished(params):
        calls.append(("recent", params))
        return (
            []
            if params["page"] != 1
            else [
                gate_order(
                    2**60 + 6,
                    type="market",
                    status="closed",
                    amount="550",
                    left="0",
                    filled_amount="0.01",
                    filled_total="500",
                    avg_deal_price="50000",
                ),
            ]
        )

    monkeypatch.setattr(adapter._exchange, "privateSpotGetOpenOrders", opened)
    monkeypatch.setattr(adapter._exchange, "privateSpotGetOrders", finished)
    service = owner.trading
    service.discovery.enqueue(OrderDiscoveryRequest(account_id=account.id, days=3))
    advance(service, account)
    init = job(service, account)
    assert init["cursor"]["page"] == 2 and init["skipped"] == 1
    resumed = ExchangeTrading(owner.market, owner.store)
    for _ in range(3):
        advance(resumed, account)
    assert job(resumed, account)["complete"]
    assert calls[0] == ("open", {"account": "spot", "page": 1, "limit": 20})
    assert calls[2] == (
        "recent",
        {
            "account": "spot",
            "status": "finished",
            "page": 1,
            "limit": 100,
            "from": init["start"] // 1000,
            "to": (init["end"] - 1) // 1000,
        },
    )
    monitor = resumed.monitor(account_id=account.id)
    assert monitor["total"] == 2 and all(order["read_only"] for order in monitor["items"])
    closed = next(order for order in monitor["items"] if order["status"] == "closed")
    assert closed["request"]["quantity"] is None and closed["remaining"] is None
    assert closed["cost"] == 500 and closed["filled"] == 0.01


def test_gate_lost_ack_recovers_finished_order_from_exact_pair_without_resending(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    owner.settings.allow_live_trading = True
    account, adapter = saved_account(owner, "gate", "BTC_USDT")
    native = adapter._exchange
    writes, lookups = [], []
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 10_000}})

    def lost_ack(symbol, kind, side, amount, price, *, params):
        assert (symbol, kind, side, amount, price) == ("BTC/USDT", "limit", "buy", 0.01, 50000)
        writes.append(params["clientOrderId"])
        raise ccxt.RequestTimeout("PRIVATE")

    def unavailable(params):
        lookups.append(("pending", params))
        raise ccxt.OrderNotFound("PRIVATE")

    def finished(params):
        lookups.append(("finished", params))
        assert params["currency_pair"] == "BTC_USDT" and params["status"] == "finished"
        return (
            []
            if params["page"] != 1
            else [
                gate_order(
                    2**60 + 4,
                    text=writes[0],
                    status="closed",
                    left="0",
                    filled_amount="0.01",
                    filled_total="500",
                ),
                gate_order(2**60 + 3, text="t-other", status="cancelled"),
            ]
        )

    monkeypatch.setattr(native, "create_order", lost_ack)
    monkeypatch.setattr(native, "privateSpotGetOrdersOrderId", unavailable)
    monkeypatch.setattr(native, "privateSpotGetOrders", finished)
    service = owner.trading
    placement = submit(service, account)
    assert placement["status"] == "unknown"
    owner.settings.allow_live_trading = False
    assert service.recover(placement["id"])["recovery"]["state"] == "searching"
    resumed = ExchangeTrading(owner.market, owner.store)
    assert resumed.recover(placement["id"])["recovery"]["state"] == "searching"
    result = resumed.recover(placement["id"])
    assert result["status"] == "closed" and result["recovery"]["state"] == "found"
    assert result["exchange_order_id"] == str(2**60 + 4)
    assert lookups[0] == ("pending", {"order_id": writes[0], "currency_pair": "BTC_USDT", "account": "spot"})
    assert all(lookups[1][1][key] == lookups[2][1][key] for key in ("from", "to"))
    assert (
        resumed.execute(placement["id"], placement["confirmation"])["exchange_order_id"]
        == result["exchange_order_id"]
    )
    assert writes == [placement["client_order_id"]]


def test_bitget_discovery_and_exact_fill_paging_share_the_history_ledger(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    account, adapter = saved_account(owner, "bitget", "BTCUSDT")
    native = adapter._exchange
    native_order = str(2**60 + 10)
    order_reads, fill_reads = [], []

    def read(recent, params):
        order_reads.append((recent, params))
        row = (
            bitget_order(
                native_order,
                status="filled",
                baseVolume="0.01",
                quoteVolume="500",
                priceAvg="50000",
                feeDetail="{}",
            )
            if recent
            else bitget_order(2**60 + 11, status="new")
        )
        rows = [row]
        if not recent:
            row.pop("price")
            row.update(priceAvg="50000", basePrice="0", feeDetail="")
            rows.append(bitget_order(2**60 + 9, orderSource="strategy_oco_limit"))
        return {"code": "00000", "data": [] if params.get("idLessThan") else rows}

    def read_fills(params):
        fill_reads.append(params)
        row = fill_row(
            "bitget",
            str(2**60 + 5),
            orderId=native_order,
            symbol="btcusdt",
            cTime=str(int(time.time() * 1000) - 1000),
            priceAvg="50000",
            amount="500",
        )
        return {"code": "00000", "data": [] if params.get("idLessThan") else [row]}

    monkeypatch.setattr(native, "privateSpotGetV2SpotTradeUnfilledOrders", lambda params: read(False, params))
    monkeypatch.setattr(native, "privateSpotGetV2SpotTradeHistoryOrders", lambda params: read(True, params))
    monkeypatch.setattr(native, "privateSpotGetV2SpotTradeFills", read_fills)
    service = owner.trading
    service.discovery.enqueue(OrderDiscoveryRequest(account_id=account.id))
    advance(service, account)
    resumed = ExchangeTrading(owner.market, owner.store)
    for _ in range(3):
        advance(resumed, account)
    records = resumed.monitor(account_id=account.id)["items"]
    (closed,) = [row for row in records if row["status"] == "closed"]
    saved = job(resumed, account)
    assert saved["complete"] and saved["skipped"] == 1 and len(records) == 2 and closed["read_only"]
    assert next(row for row in records if row["status"] == "open")["request"]["limit_price"] == 50000
    assert order_reads[0] == (False, {"tpslType": "normal", "limit": 100})
    assert order_reads[1][1]["idLessThan"] == str(2**60 + 9)
    assert order_reads[-1][1]["idLessThan"] == native_order
    first = resumed.reconciliation.sync(closed["id"], manual=True)
    second = resumed.reconciliation.sync(closed["id"], manual=True)
    assert first["reconciliation"]["status"] == "pending"
    assert second["reconciliation"]["status"] == "matched"
    assert second["reconciliation"]["fees"] == [{"currency": "USDT", "cost": 0.001}]
    assert all(row["orderId"] == native_order and row["symbol"] == "BTCUSDT" for row in fill_reads)
    owner.account_sync.enqueue(account, ["BTC/USDT"])
    owner.account_sync.tick()
    assert "orderId" not in fill_reads[-1]
    assert owner.account_sync.ledger.fills(account_id=account.id)["total"] == 1
    assert "PRIVATE" not in json.dumps(second)


def test_bitget_discounted_fill_does_not_invent_a_fee(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    _, adapter = saved_account(owner, "bitget", "BTCUSDT")
    native = adapter._exchange
    row = fill_row("bitget")
    row["feeDetail"].update(deduction="yes", feeCoin="BGB", totalDeductionFee="-0.001")
    monkeypatch.setattr(native, "privateSpotGetV2SpotTradeFills", lambda _: {"code": "00000", "data": [row]})
    page = fetch_order_fill_page(native, "bitget-id", "order-1", "BTC/USDT", {}, 100)
    assert len(page.items) == 1
    assert page.items[0]["fee"] == {"currency": None, "cost": None}
    assert page.items[0]["fees"] == [{"currency": None, "cost": None}]


@pytest.mark.parametrize("change", [{"orderId": "other"}, {"symbol": "ETHUSDT"}])
def test_bitget_exact_fills_reject_other_order_or_market(manual_client, monkeypatch, change):
    owner = manual_client.app.state.services
    _, adapter = saved_account(owner, "bitget", "BTCUSDT")
    native = adapter._exchange
    monkeypatch.setattr(
        native,
        "privateSpotGetV2SpotTradeFills",
        lambda _: {
            "code": "00000",
            "data": [fill_row("bitget", **change)],
        },
    )
    with pytest.raises(ccxt.ExchangeError, match="Unexpected market or order"):
        fetch_order_fill_page(native, "bitget-id", "order-1", "BTC/USDT", {}, 100)
