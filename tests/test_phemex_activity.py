"""Native-shaped Phemex spot reads validate scaling, discovery, recovery and ledger sharing."""

import time
from uuid import UUID

import ccxt
import pytest
from test_expanded_order_adapters import saved_account
from test_order_discovery import advance, job
from test_order_management import submit

from sibyl.exchanges.phemex_activity import discover_page, lookup_order
from sibyl.exchanges.registry import provider_catalog
from sibyl.services.accounts.sync import AccountSync
from sibyl.services.trading.discovery import OrderDiscoveryRequest
from sibyl.services.trading.service import ExchangeTrading


def order(identity=1, **changes):
    return {
        "orderID": str(UUID(int=identity)),
        "clOrdID": "external",
        "symbol": "sBTCUSDT",
        "side": "Buy",
        "ordType": "Limit",
        "ordStatus": "New",
        "qtyType": "ByBase",
        "timeInForce": "GoodTillCancel",
        "priceEp": 500000000,
        "baseQtyEv": 1000000,
        "quoteQtyEv": 50000000000,
        "cumBaseQtyEv": 0,
        "cumQuoteQtyEv": 0,
        "leavesBaseQtyEv": 1000000,
        "stopDirection": "UNSPECIFIED",
        "stopPxEp": 0,
        "avgPriceEp": 0,
        "createTimeNs": (time.time_ns() // 1000000 - 1000) * 1000000 + 123456,
        **changes,
    }


def fill(identity=100, **changes):
    return {
        "execId": str(UUID(int=identity)),
        "orderID": str(UUID(int=1)),
        "symbol": "sBTCUSDT",
        "side": "Buy",
        "ordType": "Limit",
        "tradeType": "Trade",
        "execStatus": "MakerFill",
        "execPriceEp": 500000000,
        "execBaseQtyEv": 1000000,
        "execQuoteQtyEv": 50000000000,
        "execFeeEv": 20000000,
        "feeCurrency": "USDT",
        "baseCurrency": "BTC",
        "quoteCurrency": "USDT",
        "transactTimeNs": (time.time_ns() // 1000000 - 1000) * 1000000 + 987654,
        **changes,
    }


@pytest.fixture
def phemex(manual_client):
    owner = manual_client.app.state.services
    account, adapter = saved_account(owner, "phemex", "sBTCUSDT")
    native = adapter._exchange
    native.set_markets(
        [
            {
                **native.markets["BTC/USDT"],
                "priceScale": 4,
                "valueScale": 8,
                "ratioScale": 8,
                "settle": None,
                "swap": False,
            }
        ]
    )
    native.currencies = {code: {"id": code, "code": code, "valueScale": 8} for code in ("BTC", "USDT")}
    return owner, account, adapter


def test_pair_selection_is_required_before_queuing_discovery(phemex):
    owner, account, _ = phemex
    with pytest.raises(ValueError, match="exact pairs"):
        owner.trading.discovery.enqueue(OrderDiscoveryRequest(account_id=account.id))
    assert owner.trading.discovery.snapshot()["jobs"] == []
    source = next(row for row in owner.trading.discovery.snapshot()["accounts"] if row["id"] == account.id)
    assert source["open_requires_symbols"] and source["history_requires_symbols"]


def test_selected_pair_open_and_recent_reads_checkpoint_native_offsets(phemex, monkeypatch):
    owner, account, adapter = phemex
    native, reads = adapter._exchange, []
    closed = order(
        2,
        ordStatus="Filled",
        cumBaseQtyEv=1000000,
        cumQuoteQtyEv=50000000000,
        leavesBaseQtyEv=0,
        avgPriceEp=500000000,
    )
    monkeypatch.setattr(
        native,
        "privateGetSpotOrders",
        lambda params: (
            {"code": 0, "data": [order(createTimeNs=1), order(3, ordType="StopLimit", stopPxEp=300000000)]}
            if params == {"symbol": "sBTCUSDT"}
            else None
        ),
    )

    def history(params):
        reads.append(params.copy())
        return {"code": 0, "data": [closed]} if params["offset"] == 0 else []

    monkeypatch.setattr(native, "privateGetApiDataSpotsOrders", history)
    owner.trading.discovery.enqueue(OrderDiscoveryRequest(account_id=account.id, symbols=["BTC/USDT"]))
    advance(owner.trading, account)
    restarted = ExchangeTrading(owner.market, owner.store)
    advance(restarted, account)
    assert job(restarted, account)["complete"] and job(restarted, account)["skipped"] == 1
    rows = restarted.monitor(account_id=account.id)["items"]
    assert len(rows) == 2 and all(row["read_only"] for row in rows)
    saved = next(row for row in rows if row["exchange_order_id"] == closed["orderID"])
    assert saved["cost"] == 500 and saved["filled"] == 0.01 and saved["remaining"] == 0
    assert reads[0]["offset"] == 0 and reads[0]["symbol"] == "sBTCUSDT"


def test_uncertain_submission_recovers_by_exact_client_read_without_second_write(phemex, monkeypatch):
    owner, account, adapter = phemex
    owner.settings.allow_live_trading = True
    native, writes = adapter._exchange, []
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 10000}})

    def lost_ack(*args, params):
        writes.append(params["clientOrderId"])
        raise ccxt.RequestTimeout("PRIVATE")

    def lookup(params):
        assert params == {"symbol": "sBTCUSDT", "clOrdID": writes[0]}
        return [order(clOrdID=writes[0])]

    monkeypatch.setattr(native, "create_order", lost_ack)
    monkeypatch.setattr(native, "privateGetApiDataSpotsOrdersByOrderId", lookup)
    monkeypatch.setattr(native, "privateGetApiDataSpotsTradesByOrderId", lambda _: [])
    intent = submit(owner.trading, account)
    assert intent["status"] == "unknown"
    owner.settings.allow_live_trading = False
    result = ExchangeTrading(owner.market, owner.store).recover(intent["id"])
    assert result["recovery"]["state"] == "found" and len(writes) == 1


def test_exact_fills_and_resumed_history_share_fees_and_native_uuid(phemex, monkeypatch):
    owner, account, adapter = phemex
    native, reads = adapter._exchange, []
    execution = fill()
    closed = order(
        ordStatus="Filled",
        cumBaseQtyEv=1000000,
        cumQuoteQtyEv=50000000000,
        leavesBaseQtyEv=0,
        avgPriceEp=500000000,
    )
    monkeypatch.setattr(native, "privateGetSpotOrders", lambda _: [])
    monkeypatch.setattr(native, "privateGetApiDataSpotsOrders", lambda _: [closed])
    monkeypatch.setattr(
        native,
        "privateGetApiDataSpotsTradesByOrderId",
        lambda params: (
            [execution] if params == {"symbol": "sBTCUSDT", "orderID": closed["orderID"]} else None
        ),
    )
    monkeypatch.setattr(
        native, "privateGetApiDataSpotsTrades", lambda params: reads.append(params.copy()) or [execution]
    )
    owner.trading.discovery.enqueue(OrderDiscoveryRequest(account_id=account.id, symbols=["BTC/USDT"]))
    advance(owner.trading, account)
    advance(owner.trading, account)
    (saved,) = owner.trading.monitor(account_id=account.id)["items"]
    checked = owner.trading.reconciliation.sync(saved["id"], manual=True)
    assert checked["reconciliation"]["status"] == "matched"
    owner.account_sync.enqueue(account, ["BTC/USDT"])
    AccountSync(owner.market, owner.store).tick()
    assert owner.account_sync.ledger.fills(account_id=account.id)["total"] == 1
    execution["execFeeEv"] = -25000000
    owner.account_sync.enqueue(account, ["BTC/USDT"])
    owner.account_sync.tick()
    assert owner.trading.reconciliation.detail(saved["id"])["reconciliation"]["fees"] == [
        {"currency": "USDT", "cost": -0.25}
    ]


def test_quote_budget_does_not_become_native_base_quantity_or_cost(phemex, monkeypatch):
    _, _, adapter = phemex
    native = order(
        qtyType="ByQuote", baseQtyEv=0, cumQuoteQtyEv=None, quoteQtyEv=50000000000, ordType="Market"
    )
    monkeypatch.setattr(
        adapter._exchange,
        "fetch_order",
        lambda *_: adapter._exchange.parse_order(native, adapter._exchange.market("BTC/USDT")),
    )
    saved = adapter.fetch_order(native["orderID"], "BTC/USDT")
    assert saved["amount"] is None and saved["remaining"] is None and saved["cost"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"qtyType": "ByQuote"},
        {"timeInForce": "PostOnly"},
        {"ordType": "StopLimit"},
        {"clOrdID": "other"},
        {"symbol": "BTCUSDT"},
    ],
)
def test_recovery_rejects_native_term_or_account_mismatches(phemex, monkeypatch, change):
    _, _, adapter = phemex
    monkeypatch.setattr(
        adapter._exchange,
        "privateGetApiDataSpotsOrdersByOrderId",
        lambda _: [order(**{"clOrdID": "saved", **change})],
    )
    with pytest.raises(ValueError, match="differs"):
        lookup_order(adapter._exchange, "saved", "BTC/USDT")


def test_repeated_recent_offset_page_requires_attention(phemex, monkeypatch):
    _, _, adapter = phemex
    raw = [order(index + 1) for index in range(100)]
    monkeypatch.setattr(adapter._exchange, "privateGetApiDataSpotsOrders", lambda _: raw)
    end = adapter._exchange.milliseconds()
    first = discover_page(adapter._exchange, "recent", {}, end - 10000, end, ["BTC/USDT"])
    with pytest.raises(ccxt.ExchangeError, match="repeated"):
        discover_page(adapter._exchange, "recent", first[1], end - 10000, end, ["BTC/USDT"])


def test_unknown_currency_scale_keeps_fee_cost_unknown(phemex, monkeypatch):
    _, _, adapter = phemex
    monkeypatch.setattr(
        adapter._exchange, "privateGetApiDataSpotsTradesByOrderId", lambda _: [fill(feeCurrency="OTHER")]
    )
    page = adapter.fetch_order_fill_page(order()["orderID"], "BTC/USDT", {})
    assert page.items[0]["fee"] == {"currency": "OTHER", "cost": None}


def test_settings_expose_only_implemented_phemex_workflows():
    (provider,) = [row for row in provider_catalog()["items"] if row["id"] == "phemex"]
    features = {f["id"]: f for group in provider["support"] for f in group["features"]}
    assert all(
        features[name]["status"] == "available"
        for name in ("discovery", "recovery", "history_import", "fill_reconciliation")
    )
    assert features["automated"]["status"] == "pending" and provider["market_orders"]


def test_discount_token_fee_is_not_presented_as_zero_quote_fee(phemex, monkeypatch):
    _, _, adapter = phemex
    monkeypatch.setattr(
        adapter._exchange,
        "privateGetApiDataSpotsTradesByOrderId",
        lambda _: [fill(execFeeEv=0, ptFeeRv="0.2")],
    )
    page = adapter.fetch_order_fill_page(order()["orderID"], "BTC/USDT", {})
    assert page.items[0]["fee"] == {"currency": None, "cost": None}


def test_invalid_success_envelope_cannot_complete_history(phemex, monkeypatch):
    _, _, adapter = phemex
    monkeypatch.setattr(
        adapter._exchange, "privateGetApiDataSpotsTrades", lambda _: {"code": False, "data": []}
    )
    with pytest.raises(ccxt.ExchangeError, match="response"):
        adapter.fetch_trade_page("BTC/USDT", {})
