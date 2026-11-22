"""Upbit Korea native order contracts run offline against the real CCXT parser."""

import json
import time
from uuid import UUID

import ccxt
import pytest
from test_expanded_order_adapters import saved_account
from test_order_discovery import advance, job
from test_order_management import submit

from sibyl.exchanges.registry import provider_catalog
from sibyl.exchanges.upbit_orders import discover_page, lookup_order
from sibyl.services.trading.discovery import OrderDiscoveryRequest
from sibyl.services.trading.service import ExchangeTrading


def order(identity=1, **changes):
    return {
        "uuid": str(UUID(int=identity)),
        "identifier": "external",
        "market": "USDT-BTC",
        "side": "bid",
        "ord_type": "limit",
        "price": "50000",
        "state": "wait",
        "created_at": ccxt.Exchange.iso8601(int(time.time() * 1000) - 1000),
        "volume": "0.01",
        "remaining_volume": "0.01",
        "executed_volume": "0",
        "paid_fee": "0",
        "trades_count": 0,
        **changes,
    }


@pytest.fixture
def upbit(manual_client):
    owner = manual_client.app.state.services
    account, adapter = saved_account(owner, "upbit", "USDT-BTC")
    return owner, account, adapter


def test_open_pages_and_split_recent_windows_resume_after_restart(upbit, monkeypatch):
    owner, account, adapter = upbit
    native, calls = adapter._exchange, []
    old = native.iso8601(int(time.time() * 1000) - 30 * 86400000)
    finished = order(
        101, state="cancel", executed_volume="0.004", remaining_volume="0.006", executed_funds="200"
    )
    stamp = native.parse8601(finished["created_at"])

    def opened(params):
        calls.append(("open", params.copy()))
        assert params["state"] == "wait" and params["order_by"] == "asc"
        return [order(i, created_at=old) for i in range(1, 101)] if params["page"] == 1 else []

    def closed(params):
        calls.append(("recent", params.copy()))
        assert "page" not in params and "state" not in params
        if sum(stream == "recent" for stream, _ in calls) == 1:
            return [finished] * 100
        return [finished] if int(params["start_time"]) <= stamp <= int(params["end_time"]) else []

    monkeypatch.setattr(native, "privateGetOrdersOpen", opened)
    monkeypatch.setattr(native, "privateGetOrdersClosed", closed)
    service = owner.trading
    service.discovery.enqueue(OrderDiscoveryRequest(account_id=account.id, days=3))
    advance(service, account)
    assert job(service, account)["cursor"]["page"] == 2
    restarted = ExchangeTrading(owner.market, owner.store)
    for _ in range(4):
        advance(restarted, account)
    assert job(restarted, account)["complete"]
    monitor = restarted.monitor(account_id=account.id)
    assert monitor["total"] == 101 and all(row["read_only"] for row in monitor["items"])
    saved = next(row for row in monitor["items"] if row["exchange_order_id"] == finished["uuid"])
    assert saved["status"] == "canceled" and saved["cost"] == 200 and saved["filled"] == 0.004
    recent = [params for stream, params in calls if stream == "recent"]
    assert int(recent[1]["end_time"]) + 1 == int(recent[2]["start_time"])


def test_lost_ack_recovery_uses_only_saved_identifier(upbit, monkeypatch):
    owner, account, adapter = upbit
    owner.settings.allow_live_trading = True
    native, writes, reads = adapter._exchange, [], []
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 10000}})

    def lost_ack(symbol, kind, side, quantity, price, *, params):
        assert (symbol, kind, side, quantity, price) == ("BTC/USDT", "limit", "buy", 0.01, 50000)
        writes.append(params["clientOrderId"])
        raise ccxt.RequestTimeout("PRIVATE")

    def lookup(params):
        reads.append(params.copy())
        if "uuid" in params:
            return order(trades_count=0, trades=[])
        assert params == {"identifier": writes[0]}
        return order(
            identifier=writes[0], executed_volume="0.004", remaining_volume="0.006", executed_funds="200"
        )

    monkeypatch.setattr(native, "create_order", lost_ack)
    monkeypatch.setattr(native, "privateGetOrder", lookup)
    uncertain = submit(owner.trading, account)
    assert uncertain["status"] == "unknown"
    owner.settings.allow_live_trading = False
    recovered = ExchangeTrading(owner.market, owner.store).recover(uncertain["id"])
    assert recovered["recovery"]["state"] == "found" and recovered["filled"] == 0.004
    assert recovered["exchange_order_id"] == order()["uuid"] and recovered["cost"] == 200
    assert len(writes) == 1 and reads == [{"identifier": writes[0]}, {"uuid": order()["uuid"]}]
    assert "PRIVATE" not in json.dumps(recovered)


@pytest.mark.parametrize("budget,executed", [("500", None), ("500", "450")])
def test_market_buy_quote_budget_is_never_executed_cost(upbit, monkeypatch, budget, executed):
    _, _, adapter = upbit
    raw = order(
        ord_type="price",
        price=budget,
        state="cancel",
        volume=None,
        remaining_volume=None,
        executed_volume="0.009",
    )
    if executed is not None:
        raw["executed_funds"] = executed
    monkeypatch.setattr(adapter._exchange, "fetch_order", lambda *_: adapter._exchange.parse_order(raw))
    saved = adapter.fetch_order(raw["uuid"], "BTC/USDT")
    assert saved["amount"] is None and saved["remaining"] is None and saved["filled"] == 0.009
    assert saved["cost"] == (float(executed) if executed else None)


def test_trade_funds_can_establish_actual_cost_but_limit_price_cannot(upbit, monkeypatch):
    _, _, adapter = upbit
    raw = order(executed_volume="0.004", remaining_volume="0.006")
    monkeypatch.setattr(adapter._exchange, "fetch_order", lambda *_: adapter._exchange.parse_order(raw))
    assert adapter.fetch_order(raw["uuid"], "BTC/USDT")["cost"] is None
    raw["trades"] = [
        {
            "market": "USDT-BTC",
            "uuid": str(UUID(int=99)),
            "price": "49000",
            "volume": "0.004",
            "funds": "196",
            "created_at": raw["created_at"],
            "side": "bid",
        }
    ]
    saved = adapter.fetch_order(raw["uuid"], "BTC/USDT")
    assert saved["cost"] == 196 and saved["average"] == 49000


def test_reserved_and_unknown_market_orders_are_excluded(upbit, monkeypatch):
    _, _, adapter = upbit
    monkeypatch.setattr(
        adapter._exchange,
        "privateGetOrdersOpen",
        lambda _: [order(), order(2, state="watch"), order(3, market="USDT-OLD")],
    )
    end = int(time.time() * 1000)
    page = adapter.fetch_account_order_page("open", {}, end - 10000, end, [])
    assert page.complete and page.skipped == 2 and len(page.items) == 1


def test_saturated_single_timestamp_stops_without_losing_orders(upbit, monkeypatch):
    _, _, adapter = upbit
    end = int(time.time() * 1000)
    raw = order(state="done", created_at=adapter._exchange.iso8601(end - 1))
    monkeypatch.setattr(adapter._exchange, "privateGetOrdersClosed", lambda _: [raw] * 100)
    with pytest.raises(ccxt.NotSupported, match="timestamp"):
        discover_page(adapter._exchange, "recent", {}, end - 1, end)


def test_repeated_open_page_is_rejected(upbit, monkeypatch):
    _, _, adapter = upbit
    monkeypatch.setattr(
        adapter._exchange, "privateGetOrdersOpen", lambda _: [order(i) for i in range(1, 101)]
    )
    end = int(time.time() * 1000)
    first = discover_page(adapter._exchange, "open", {}, end - 1000, end)
    with pytest.raises(ccxt.ExchangeError, match="repeated"):
        discover_page(adapter._exchange, "open", first[1], end - 1000, end)


@pytest.mark.parametrize(
    "change",
    [
        {"identifier": "other"},
        {"market": "KRW-BTC"},
        {"ord_type": "price"},
        {"time_in_force": "ioc"},
        {"time_in_force": "post_only"},
        {"state": "watch"},
        {"smp_type": "cancel_maker"},
        {"prevented_volume": "0.001"},
        {"trigger_price": "40000"},
    ],
)
def test_recovery_rejects_different_native_instructions(upbit, monkeypatch, change):
    _, _, adapter = upbit
    monkeypatch.setattr(
        adapter._exchange, "privateGetOrder", lambda _: order(**{"identifier": "a" * 32, **change})
    )
    with pytest.raises(ValueError, match="differs"):
        lookup_order(adapter._exchange, "a" * 32, "BTC/USDT")


def test_missing_identifier_does_not_establish_an_order(upbit, monkeypatch):
    _, _, adapter = upbit

    def missing(_):
        raise ccxt.OrderNotFound("PRIVATE")

    monkeypatch.setattr(adapter._exchange, "privateGetOrder", missing)
    assert lookup_order(adapter._exchange, "a" * 32, "BTC/USDT") == []


def test_settings_only_enable_implemented_upbit_reads():
    (provider,) = [row for row in provider_catalog()["items"] if row["id"] == "upbit"]
    features = {feature["id"]: feature for group in provider["support"] for feature in group["features"]}
    assert features["discovery"]["status"] == features["recovery"]["status"] == "available"
    for name in ("automated",):
        assert features[name]["status"] == "pending"
    assert features["history_import"]["status"] == features["fill_reconciliation"]["status"] == "available"
    assert provider["market_order_sides"] == ["buy", "sell"]
    assert provider["market_buy_budget"]
