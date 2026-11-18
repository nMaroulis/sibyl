"""Bitfinex cash-wallet workflows use native arrays and real parsing without network writes."""

import json
import time

import ccxt
import pytest
from test_expanded_order_adapters import saved_account
from test_order_discovery import advance, job
from test_order_management import submit

from sibyl.exchanges.bitfinex_orders import discover_page, lookup_page
from sibyl.exchanges.registry import provider_catalog
from sibyl.services.accounts.sync import AccountSync
from sibyl.services.trading.discovery import OrderDiscoveryRequest
from sibyl.services.trading.service import ExchangeTrading

ORDER_ID = 2**60 + 7
TRADE_ID = 2**60 + 101


def order(identity=ORDER_ID, **changes):
    stamp = int(time.time() * 1000) - 1000
    fields = {
        0: identity,
        1: None,
        2: 1001,
        3: "tBTCUST",
        4: stamp,
        5: stamp + 500,
        6: "0.01",
        7: "0.01",
        8: "EXCHANGE LIMIT",
        9: None,
        10: None,
        12: 0,
        13: "ACTIVE",
        16: "50000",
        17: "0",
        18: "0",
        19: "0",
        23: 0,
        24: 0,
        25: None,
        28: "API>BFX",
        31: {"private": "PRIVATE"},
    }
    fields.update({int(key): value for key, value in changes.items()})
    return [fields.get(index) for index in range(32)]


def fill(identity=TRADE_ID, **changes):
    fields = {
        0: identity,
        1: "tBTCUST",
        2: int(time.time() * 1000) - 1000,
        3: ORDER_ID,
        4: "0.01",
        5: "50000",
        6: "EXCHANGE LIMIT",
        7: "50000",
        8: 1,
        9: "-0.2",
        10: "UST",
        11: 1001,
    }
    fields.update({int(key): value for key, value in changes.items()})
    return [fields.get(index) for index in range(12)]


@pytest.fixture
def bitfinex(manual_client):
    owner = manual_client.app.state.services
    account, adapter = saved_account(owner, "bitfinex", "tBTCUST")
    adapter._exchange.markets["BTC/USDT"]["precision"] = {"amount": 8, "price": 5}
    return owner, account, adapter


def test_open_cash_discovery_and_recent_splits_preserve_resume_and_creation_time(bitfinex, monkeypatch):
    owner, account, adapter = bitfinex
    native, reads = adapter._exchange, []
    older = order(**{"4": int(time.time() * 1000) - 30 * 86400000})
    finished = order(ORDER_ID + 1, **{"6": "0.006", "13": "PARTIALLY FILLED @ 50000(0.004)", "17": "50000"})
    monkeypatch.setattr(
        native,
        "privatePostAuthROrders",
        lambda _: [
            older,
            order(11, **{"8": "LIMIT"}),
            order(12, **{"12": 4096}),
            order(13, **{"3": "tOLDUST"}),
        ],
    )

    def history(params):
        reads.append(params.copy())
        if len(reads) == 1:
            return [finished] * 100
        return [finished] if params["start"] <= finished[4] <= params["end"] else []

    monkeypatch.setattr(native, "privatePostAuthROrdersHist", history)
    owner.trading.discovery.enqueue(OrderDiscoveryRequest(account_id=account.id, days=3))
    advance(owner.trading, account)
    advance(owner.trading, account)
    assert len(job(owner.trading, account)["cursor"]["windows"]) == 2
    restarted = ExchangeTrading(owner.market, owner.store)
    advance(restarted, account)
    advance(restarted, account)
    assert job(restarted, account)["complete"] and job(restarted, account)["skipped"] == 3
    monitor = restarted.monitor(account_id=account.id)
    assert monitor["total"] == 2 and all(row["read_only"] for row in monitor["items"])
    saved = next(row for row in monitor["items"] if row["exchange_order_id"] == str(finished[0]))
    assert saved["status"] == "canceled" and saved["filled"] == pytest.approx(0.004)
    assert saved["cost"] is None and "PRIVATE" not in json.dumps(monitor)
    assert reads[1]["end"] + 1 == reads[2]["start"]


def test_lost_ack_checks_both_open_and_closed_matches_before_recovery(bitfinex, monkeypatch):
    owner, account, adapter = bitfinex
    owner.settings.allow_live_trading = True
    native, writes, reads = adapter._exchange, [], []
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 10000}})

    def lost_ack(symbol, kind, side, quantity, price, *, params):
        assert (symbol, kind, side, quantity, price) == ("BTC/USDT", "limit", "buy", 0.01, 50000)
        writes.append(params["cid"])
        raise ccxt.RequestTimeout("PRIVATE")

    def active(params):
        reads.append(("open", params.copy()))
        return [
            order(**{"2": writes[0], "6": "0.006", "13": "PARTIALLY FILLED @ 50000(0.004)", "17": "50000"})
        ]

    def history(params):
        reads.append(("recent", params.copy()))
        return []

    monkeypatch.setattr(native, "create_order", lost_ack)
    monkeypatch.setattr(native, "privatePostAuthROrdersSymbol", active)
    monkeypatch.setattr(native, "privatePostAuthROrdersSymbolHist", history)
    monkeypatch.setattr(native, "privatePostAuthROrderSymbolIdTrades", lambda _: [])
    uncertain = submit(owner.trading, account)
    assert uncertain["status"] == "unknown" and isinstance(writes[0], int) and 0 < writes[0] < 2**45
    owner.settings.allow_live_trading = False
    checked = owner.trading.recover(uncertain["id"])
    assert checked["status"] == "unknown" and checked["recovery"]["state"] == "searching"
    recovered = ExchangeTrading(owner.market, owner.store).recover(uncertain["id"])
    assert recovered["recovery"]["state"] == "found" and recovered["filled"] == pytest.approx(0.004)
    assert recovered["exchange_order_id"] == str(ORDER_ID)
    assert len(writes) == 1 and [stream for stream, _ in reads] == ["open", "recent"]
    assert reads[0][1] == {"symbol": "tBTCUST"} and "PRIVATE" not in json.dumps(recovered)


def test_terminal_order_status_falls_back_to_exact_native_closed_read(bitfinex, monkeypatch):
    _, _, adapter = bitfinex
    native, reads = adapter._exchange, []
    finished = order(**{"13": "PARTIALLY FILLED @ 50000(0.004)", "6": "0.006", "17": "50000"})
    monkeypatch.setattr(
        native, "privatePostAuthROrdersSymbol", lambda params: reads.append(params.copy()) or []
    )
    monkeypatch.setattr(
        native, "privatePostAuthROrdersSymbolHist", lambda params: reads.append(params.copy()) or [finished]
    )
    saved = adapter.fetch_order(str(ORDER_ID), "BTC/USDT")
    assert (
        saved["status"] == "canceled"
        and saved["timestamp"] == finished[4]
        and saved["timestamp"] != finished[5]
    )
    assert reads == [
        {"symbol": "tBTCUST", "id": [ORDER_ID]},
        {"symbol": "tBTCUST", "id": [ORDER_ID], "limit": 1},
    ]


def test_exact_fills_and_split_history_share_native_ids_and_fee_corrections(bitfinex, monkeypatch):
    owner, account, adapter = bitfinex
    native, reads = adapter._exchange, []
    finished = order(**{"13": "EXECUTED @ 50000(0.01)", "6": "0", "17": "50000"})
    execution = fill()
    monkeypatch.setattr(native, "privatePostAuthROrders", lambda _: [])
    monkeypatch.setattr(native, "privatePostAuthROrdersHist", lambda _: [finished])
    monkeypatch.setattr(
        native,
        "privatePostAuthROrderSymbolIdTrades",
        lambda params: [execution] if params == {"symbol": "tBTCUST", "id": ORDER_ID} else None,
    )

    def history(params):
        reads.append(params.copy())
        if len(reads) == 1:
            return [execution] * 100
        return [execution] if params["start"] <= execution[2] <= params["end"] else []

    monkeypatch.setattr(native, "privatePostAuthRTradesSymbolHist", history)
    owner.trading.discovery.enqueue(OrderDiscoveryRequest(account_id=account.id))
    advance(owner.trading, account)
    advance(owner.trading, account)
    (saved,) = owner.trading.monitor(account_id=account.id)["items"]
    checked = owner.trading.reconciliation.sync(saved["id"], manual=True)
    assert checked["reconciliation"]["status"] == "matched"
    assert checked["reconciliation"]["fees"] == [{"currency": "USDT", "cost": 0.2}]
    owner.account_sync.enqueue(account, ["BTC/USDT"])
    owner.account_sync.tick()
    restarted = AccountSync(owner.market, owner.store)
    restarted.tick()
    restarted.tick()
    assert restarted.snapshot()["jobs"][0]["status"] == "caught_up"
    assert restarted.ledger.fills(account_id=account.id)["total"] == 1
    execution[9] = "0.25"  # Native positive wallet effects are fee rebates.
    owner.account_sync.enqueue(account, ["BTC/USDT"])
    owner.account_sync.tick()
    corrected = owner.trading.reconciliation.detail(saved["id"])
    assert corrected["reconciliation"]["fees"] == [{"currency": "USDT", "cost": -0.25}]
    assert "PRIVATE" not in json.dumps(corrected)


def test_cash_history_excludes_margin_fills_and_keeps_unknown_fees(bitfinex, monkeypatch):
    _, _, adapter = bitfinex
    cash, margin = fill(**{"10": None, "9": None}), fill(TRADE_ID + 1, **{"6": "LIMIT"})
    monkeypatch.setattr(adapter._exchange, "privatePostAuthRTradesSymbolHist", lambda _: [cash, margin])
    page = adapter.fetch_trade_page("BTC/USDT", {})
    assert page.caught_up and len(page.items) == 1
    assert page.items[0]["fee"] == {"currency": None, "cost": None}


def test_exact_execution_snapshot_pages_by_large_native_ids(bitfinex, monkeypatch):
    _, _, adapter = bitfinex
    rows = [fill(TRADE_ID + value) for value in range(103)]
    monkeypatch.setattr(
        adapter._exchange, "privatePostAuthROrderSymbolIdTrades", lambda _: list(reversed(rows))
    )
    first = adapter.fetch_order_fill_page(str(ORDER_ID), "BTC/USDT", {})
    last = adapter.fetch_order_fill_page(str(ORDER_ID), "BTC/USDT", first.cursor)
    assert len(first.items) == 100 and not first.caught_up and len(last.items) == 3 and last.caught_up
    assert last.items[-1]["id"] == str(TRADE_ID + 102)


@pytest.mark.parametrize(
    "change",
    [
        {"8": "LIMIT"},
        {"8": "EXCHANGE STOP"},
        {"12": 4096},
        {"25": 111},
        {"10": 1234},
        {"24": 1},
        {"28": "BFX"},
        {"31": {"$F7": 1}},
        {"9": "EXCHANGE LIMIT"},
    ],
)
def test_recovery_rejects_changed_cash_instructions(bitfinex, monkeypatch, change):
    _, _, adapter = bitfinex
    monkeypatch.setattr(adapter._exchange, "privatePostAuthROrdersSymbol", lambda _: [order(**change)])
    end = int(time.time() * 1000)
    with pytest.raises(ValueError, match="differs"):
        lookup_page(adapter._exchange, "1001", "BTC/USDT", {}, end - 10000, end)


def test_reused_cid_can_reveal_a_second_native_order_before_adoption(bitfinex, monkeypatch):
    _, _, adapter = bitfinex
    native = adapter._exchange
    opened = order()
    closed = order(ORDER_ID + 1, **{"13": "CANCELED"})
    monkeypatch.setattr(native, "privatePostAuthROrdersSymbol", lambda _: [opened])
    monkeypatch.setattr(native, "privatePostAuthROrdersSymbolHist", lambda _: [closed])
    end = int(time.time() * 1000)
    first = adapter.fetch_order_lookup_page("1001", "BTC/USDT", {}, end - 10000, end)
    second = adapter.fetch_order_lookup_page("1001", "BTC/USDT", first.cursor, end - 10000, end)
    assert not first.complete and second.complete
    assert {row["id"] for row in first.candidates + second.candidates} == {str(ORDER_ID), str(ORDER_ID + 1)}


@pytest.mark.parametrize(
    "change", [{"3": ORDER_ID + 1}, {"1": "tETHUST"}, {"6": "LIMIT"}, {"0": float(TRADE_ID)}]
)
def test_exact_fills_reject_wrong_identity_market_or_wallet(bitfinex, monkeypatch, change):
    _, _, adapter = bitfinex
    monkeypatch.setattr(adapter._exchange, "privatePostAuthROrderSymbolIdTrades", lambda _: [fill(**change)])
    with pytest.raises(ccxt.ExchangeError):
        adapter.fetch_order_fill_page(str(ORDER_ID), "BTC/USDT", {})


def test_missing_legacy_cash_type_requires_review(bitfinex, monkeypatch):
    _, _, adapter = bitfinex
    monkeypatch.setattr(
        adapter._exchange, "privatePostAuthRTradesSymbolHist", lambda _: [fill(**{"6": None})]
    )
    with pytest.raises(ccxt.ExchangeError, match="cash execution"):
        adapter.fetch_trade_page("BTC/USDT", {})


def test_saturated_creation_timestamp_stops_without_skip(bitfinex, monkeypatch):
    _, _, adapter = bitfinex
    end = int(time.time() * 1000)
    raw = order(**{"4": end - 1, "13": "CANCELED"})
    monkeypatch.setattr(adapter._exchange, "privatePostAuthROrdersHist", lambda _: [raw] * 100)
    with pytest.raises(ccxt.NotSupported, match="timestamp"):
        discover_page(adapter._exchange, "recent", {}, end - 1, end)


def test_missing_terminal_order_stays_unconfirmed(bitfinex, monkeypatch):
    _, _, adapter = bitfinex
    monkeypatch.setattr(adapter._exchange, "privatePostAuthROrdersSymbol", lambda _: [])
    monkeypatch.setattr(adapter._exchange, "privatePostAuthROrdersSymbolHist", lambda _: [])
    with pytest.raises(ccxt.OrderNotFound):
        adapter.fetch_order(str(ORDER_ID), "BTC/USDT")


def test_settings_enable_reviewed_cash_reads_only():
    (provider,) = [row for row in provider_catalog()["items"] if row["id"] == "bitfinex"]
    features = {feature["id"]: feature for group in provider["support"] for feature in group["features"]}
    for name in ("discovery", "recovery", "history_import", "fill_reconciliation"):
        assert features[name]["status"] == "available"
    assert features["automated"]["status"] == "pending" and provider["market_orders"]
