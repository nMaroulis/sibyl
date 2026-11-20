"""Capture native cash-market requests and recover lost acknowledgements without a second write."""

from decimal import Decimal

import ccxt
import pytest
from test_bitfinex_activity import bitfinex as bitfinex
from test_bitfinex_activity import fill as bitfinex_fill
from test_bitfinex_activity import order as bitfinex_order
from test_cryptocom_activity import crypto as crypto
from test_cryptocom_activity import fill as crypto_fill
from test_cryptocom_activity import order as crypto_order
from test_cryptocom_activity import response
from test_exchange_spot_support import Captured
from test_exchange_spot_support import native_client as native_client
from test_order_management import request as order_request
from test_phemex_activity import fill as phemex_fill
from test_phemex_activity import order as phemex_order
from test_phemex_activity import phemex as phemex

from sibyl.exchanges.catalog import STRATEGY_EXECUTION_PROVIDERS
from sibyl.services.trading.service import ExchangeTrading

PROVIDERS = ["bitfinex", "phemex", "cryptocom"]


@pytest.fixture
def venue(request):
    return request.getfixturevalue("crypto" if request.param == "cryptocom" else request.param)


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("side", ["buy", "sell"])
def test_native_market_request_keeps_base_size_cash_scope_and_saved_identity(native_client, provider, side):
    adapter, requests = native_client(provider)
    native = adapter._exchange
    # Native Phemex products include settle=None for spot, unlike the generic fixture.
    if provider == "phemex":
        native.set_markets([{**native.market("BTC/USDT"), "settle": None}])
    client_id = adapter.format_client_order_id("135d8630-4dcc-4bfe-8918-41555302a029")
    with pytest.raises(Captured):
        adapter.create_order("BTC/USDT", "market", side, 0.001, {"clientOrderId": client_id})
    assert len(requests) == 1
    request = requests[0]
    params = request["params"]
    assert request["method"] == "POST"
    assert not any(
        name in params
        for name in ("price", "priceEp", "notional", "quoteQtyEv", "cost", "marginMode", "lev", "leverage")
    )
    if provider == "bitfinex":
        assert request["path"] == "auth/w/order/submit" and params["type"] == "EXCHANGE MARKET"
        assert type(params["cid"]) is int and str(params["cid"]) == client_id
        assert Decimal(params["amount"]) == Decimal("0.001" if side == "buy" else "-0.001")
        assert not params.get("flags")
    elif provider == "phemex":
        assert request["path"] == "spot/orders" and params["ordType"] == "Market"
        assert params["qtyType"] == "ByBase" and params["timeInForce"] == "ImmediateOrCancel"
        assert params["clOrdID"] == client_id and params["side"] == side.title()
        assert Decimal(str(params["baseQtyEv"])) == 100000
    else:
        assert request["path"] == "private/create-order" and params["type"] == "MARKET"
        assert params["side"] == side.upper() and params["quantity"] == "0.001"
        assert params["client_oid"] == client_id and params["spot_margin"] == "SPOT"
        assert params["time_in_force"] == "IMMEDIATE_OR_CANCEL" and not params.get("exec_inst")


def recovery_responses(monkeypatch, adapter, client_id, side, *, filled=True):
    """Install native terminal orders and individual fills, retaining real SDK normalization."""
    native = adapter._exchange
    if adapter.id == "bitfinex":
        parent = bitfinex_order(
            **{
                "2": int(client_id),
                "6": "0",
                "7": "0.01" if side == "buy" else "-0.01",
                "8": "EXCHANGE MARKET",
                "13": "EXECUTED @ 50000(0.01)",
                "16": "0",
                "17": "50000",
            }
        )
        execution = bitfinex_fill(**{"4": "0.01" if side == "buy" else "-0.01", "6": "EXCHANGE MARKET"})
        if not filled:
            parent[6], parent[13], parent[17] = parent[7], "CANCELED", "0"
        monkeypatch.setattr(native, "privatePostAuthROrdersSymbol", lambda _: [])
        monkeypatch.setattr(native, "privatePostAuthROrdersSymbolHist", lambda _: [parent])
        monkeypatch.setattr(
            native, "privatePostAuthROrderSymbolIdTrades", lambda _: [execution] if filled else []
        )
        return str(parent[0])
    if adapter.id == "phemex":
        parent = phemex_order(
            clOrdID=client_id,
            ordType="Market",
            side=side.title(),
            timeInForce="ImmediateOrCancel",
            priceEp=0,
            ordStatus="Filled",
            cumBaseQtyEv=1000000,
            cumQuoteQtyEv=50000000000,
            leavesBaseQtyEv=0,
            avgPriceEp=500000000,
        )
        execution = phemex_fill(ordType="Market", side=side.title())
        if not filled:
            parent.update(
                ordStatus="Canceled", cumBaseQtyEv=0, cumQuoteQtyEv=0, leavesBaseQtyEv=1000000, avgPriceEp=0
            )
        monkeypatch.setattr(native, "privateGetApiDataSpotsOrdersByOrderId", lambda _: [parent])
        monkeypatch.setattr(
            native, "privateGetApiDataSpotsTradesByOrderId", lambda _: [execution] if filled else []
        )
        return parent["orderID"]
    parent = crypto_order(
        client_oid=client_id,
        order_type="MARKET",
        side=side.upper(),
        time_in_force="IMMEDIATE_OR_CANCEL",
        limit_price="0",
        cumulative_quantity="0.01",
        cumulative_value="500",
        avg_price="50000",
        status="FILLED",
    )
    execution = crypto_fill(side=side.upper())
    if not filled:
        parent.update(status="CANCELED", cumulative_quantity="0", cumulative_value="0", avg_price="0")
    monkeypatch.setattr(native, "v1PrivatePostPrivateGetOrderDetail", lambda _: response(parent))
    monkeypatch.setattr(
        native, "v1PrivatePostPrivateGetTrades", lambda _: response({"data": [execution] if filled else []})
    )
    return parent["order_id"]


@pytest.mark.parametrize("venue", PROVIDERS, indirect=True)
@pytest.mark.parametrize("side", ["buy", "sell"])
def test_lost_market_ack_restarts_recovers_and_reconciles_without_resubmission(venue, monkeypatch, side):
    owner, account, adapter = venue
    owner.settings.allow_live_trading = True
    native, writes = adapter._exchange, []
    monkeypatch.setattr(adapter, "fetch_ticker", lambda _: {"ask": 50000, "bid": 50000})
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 100000, "BTC": 1}})

    def lost_ack(path, api="public", method="GET", params=None, *args, **kwargs):
        writes.append((path, params))
        raise ccxt.RequestTimeout("PRIVATE")

    monkeypatch.setattr(native, "fetch2", lost_ack)
    preview = owner.trading.preview(order_request(account, side=side, order_type="market", limit_price=None))
    placed = owner.trading.execute(preview["id"], preview["confirmation"])
    assert placed["status"] == "unknown" and len(writes) == 1
    owner.trading.execute(preview["id"], preview["confirmation"])
    assert len(writes) == 1
    expected_id = recovery_responses(monkeypatch, adapter, placed["client_order_id"], side)
    owner.settings.allow_live_trading = False
    restarted = ExchangeTrading(owner.market, owner.store)
    saved = restarted.recover(placed["id"])
    if adapter.id == "bitfinex":
        assert saved["recovery"]["state"] == "searching"
        saved = ExchangeTrading(owner.market, owner.store).recover(placed["id"])
    assert saved["recovery"]["state"] == "found" and saved["exchange_order_id"] == expected_id
    assert saved["status"] == "closed" and saved["filled"] == 0.01
    assert saved["reconciliation"]["status"] == "matched"
    assert saved["reconciliation"]["fill_count"] == 1 and saved["reconciliation"]["fees"]
    assert len(writes) == 1 and owner.account_sync.ledger.fills(account_id=account.id)["total"] == 1


@pytest.mark.parametrize("venue", PROVIDERS, indirect=True)
@pytest.mark.parametrize("block", ["server", "inactive"])
def test_manual_market_capability_keeps_server_and_account_controls(venue, monkeypatch, block):
    owner, account, adapter = venue
    owner.settings.allow_live_trading = block != "server"
    monkeypatch.setattr(
        adapter._exchange,
        "fetch2",
        lambda *args, **kwargs: pytest.fail("Blocked preview must not contact the provider"),
    )
    if block == "inactive":
        owner.store.activate_account(account.id, False)
    with pytest.raises(ValueError, match="disabled|Activate"):
        owner.trading.preview(order_request(account, order_type="market", limit_price=None))
    assert adapter.id not in STRATEGY_EXECUTION_PROVIDERS


@pytest.mark.parametrize("venue", PROVIDERS, indirect=True)
def test_recovery_cannot_attach_a_market_candidate_to_a_limit_intent(venue, monkeypatch):
    owner, account, adapter = venue
    owner.settings.allow_live_trading = True
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 100000}})
    monkeypatch.setattr(
        adapter._exchange,
        "create_order",
        lambda *args, **kwargs: (_ for _ in ()).throw(ccxt.RequestTimeout("PRIVATE")),
    )
    preview = owner.trading.preview(order_request(account))
    saved = owner.trading.execute(preview["id"], preview["confirmation"])
    recovery_responses(monkeypatch, adapter, saved["client_order_id"], "buy")
    result = owner.trading.recover(saved["id"])
    if adapter.id == "bitfinex":
        result = owner.trading.recover(saved["id"])
    assert result["recovery"]["state"] == "mismatch" and not result.get("exchange_order_id")


@pytest.mark.parametrize("venue", PROVIDERS, indirect=True)
def test_cancelled_unfilled_market_recovery_does_not_fabricate_executions(venue, monkeypatch):
    owner, account, adapter = venue
    owner.settings.allow_live_trading = True
    monkeypatch.setattr(adapter, "fetch_ticker", lambda _: {"ask": 50000})
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 100000}})
    writes = []

    def timeout(*args, **kwargs):
        writes.append(args)
        raise ccxt.RequestTimeout("PRIVATE")

    monkeypatch.setattr(adapter._exchange, "create_order", timeout)
    intent = owner.trading.preview(order_request(account, order_type="market", limit_price=None))
    saved = owner.trading.execute(intent["id"], intent["confirmation"])
    recovery_responses(monkeypatch, adapter, saved["client_order_id"], "buy", filled=False)
    recovered = owner.trading.recover(intent["id"])
    if adapter.id == "bitfinex":
        recovered = owner.trading.recover(intent["id"])
    assert recovered["recovery"]["state"] == "found" and recovered["status"] == "canceled"
    assert recovered["filled"] == 0 and recovered["reconciliation"]["fill_count"] == 0
    assert recovered["reconciliation"]["status"] == "matched"
    assert owner.account_sync.ledger.fills(account_id=account.id)["total"] == 0 and len(writes) == 1


@pytest.mark.parametrize("venue", ["phemex", "cryptocom"], indirect=True)
@pytest.mark.parametrize("missing_size", [False, True])
@pytest.mark.parametrize("native_price", [None, "50000"])
def test_market_recovery_requires_original_base_size_but_not_a_limit_price(
    venue, monkeypatch, missing_size, native_price
):
    _, _, adapter = venue
    native = adapter._exchange
    if adapter.id == "phemex":
        parent = phemex_order(
            clOrdID="saved",
            ordType="Market",
            timeInForce="ImmediateOrCancel",
            priceEp=None if native_price is None else 500000000,
            baseQtyEv=None if missing_size else 1000000,
            cumBaseQtyEv=1000000,
            leavesBaseQtyEv=0,
        )
        monkeypatch.setattr(native, "privateGetApiDataSpotsOrdersByOrderId", lambda _: [parent])
    else:
        parent = crypto_order(
            client_oid="saved",
            order_type="MARKET",
            time_in_force="IMMEDIATE_OR_CANCEL",
            limit_price=native_price,
            quantity=None if missing_size else "0.01",
            cumulative_quantity="0.01",
        )
        monkeypatch.setattr(native, "v1PrivatePostPrivateGetOrderDetail", lambda _: response(parent))
    if missing_size:
        with pytest.raises(ValueError, match="differs"):
            adapter.fetch_order_lookup_page("saved", "BTC/USDT", {}, 1, native.milliseconds())
    else:
        page = adapter.fetch_order_lookup_page("saved", "BTC/USDT", {}, 1, native.milliseconds())
        assert (
            page.complete and page.candidates[0]["type"] == "market" and page.candidates[0]["amount"] == 0.01
        )


@pytest.mark.parametrize("native_price", [None, "50000"])
def test_bitfinex_market_recovery_uses_original_size_without_a_limit_price_rule(
    bitfinex, monkeypatch, native_price
):
    _, _, adapter = bitfinex
    parent = bitfinex_order(**{"8": "EXCHANGE MARKET", "16": native_price})
    monkeypatch.setattr(adapter._exchange, "privatePostAuthROrdersSymbol", lambda _: [parent])
    page = adapter.fetch_order_lookup_page("1001", "BTC/USDT", {}, 1, adapter._exchange.milliseconds())
    assert page.candidates[0]["type"] == "market" and page.candidates[0]["amount"] == 0.01
    assert not page.complete  # The closed scan must still finish before unique attribution.
