"""Verify MEXC market submission and recovery through native-shaped offline responses."""

import ccxt
import pytest
from test_expanded_order_adapters import saved_account
from test_mexc_bitget_activity import mexc_fill, mexc_order
from test_order_management import request as order_request

from sibyl.exchanges.mexc_activity import lookup_order
from sibyl.services.trading.service import ExchangeTrading


def rules(**changes):
    return {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "baseAssetPrecision": 8,
                "status": "1",
                "isSpotTradingAllowed": True,
                "orderTypes": ["LIMIT", "MARKET"],
                "tradeSideType": 1,
                "baseSizePrecision": "0.0001",
                "quoteAmountPrecisionMarket": "10",
                "maxQuoteAmountMarket": "1000",
                **changes,
            }
        ]
    }


@pytest.fixture
def mexc(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    owner.settings.allow_live_trading = True
    account, adapter = saved_account(owner, "mexc", "BTCUSDT")
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 10000, "BTC": 1}})
    monkeypatch.setattr(adapter, "fetch_ticker", lambda _: {"bid": 50000, "ask": 50000})
    return owner, account, adapter


def market_request(account, **changes):
    return order_request(account, **{"order_type": "market", "limit_price": None, **changes})


@pytest.mark.parametrize("side, amount_key", [("buy", "Qty"), ("sell", "origQty")])
def test_market_wire_and_restart_recovery_use_the_same_original_base_size(
    mexc, monkeypatch, side, amount_key
):
    owner, account, adapter = mexc
    native = adapter._exchange
    reads, writes = [], []

    def transport(path, api, method, params, *args, **kwargs):
        if (path, api, method) == ("exchangeInfo", ["spot", "public"], "GET"):
            reads.append(params.copy())
            return rules(tradeSideType=2 if side == "buy" else 3)
        assert (path, api, method) == ("order", ["spot", "private"], "POST")
        writes.append(params.copy())
        raise ccxt.RequestTimeout("PRIVATE")

    monkeypatch.setattr(native, "fetch2", transport)
    review = owner.trading.preview(market_request(account, side=side))
    order = owner.trading.execute(review["id"], review["confirmation"])
    assert order["status"] == "unknown"
    assert reads == [{"symbol": "BTCUSDT"}] * 2
    assert writes == [
        {
            "symbol": "BTCUSDT",
            "type": "MARKET",
            "side": side.upper(),
            "quantity": "0.01",
            "newClientOrderId": order["client_order_id"],
        }
    ]

    native_order = mexc_order(
        "C02__market",
        clientOrderId=order["client_order_id"],
        type="MARKET",
        side=side.upper(),
        status="PARTIALLY_CANCELED",
        timeInForce="IOC",
        price="0",
        executedQty="0.004",
        cumulativeQuoteQty="200",
        origQuoteOrderQty="0.00",
    )
    native_order.pop("origQty")
    native_order[amount_key] = "0.01"

    def detail(params):
        assert params == {"symbol": "BTCUSDT", "origClientOrderId": order["client_order_id"]}
        return native_order

    monkeypatch.setattr(native, "spotPrivateGetOrder", detail)
    monkeypatch.setattr(
        native,
        "spotPrivateGetMyTrades",
        lambda _: [mexc_fill("C02__market", qty="0.004", quoteQty="200", isBuyer=side == "buy")],
    )
    owner.settings.allow_live_trading = False
    observed = ExchangeTrading(owner.market, owner.store).recover(review["id"])
    assert observed["recovery"]["state"] == "found"
    assert observed["exchange_order_id"] == "C02__market" and observed["status"] == "canceled"
    assert observed["filled"] == 0.004 and observed["remaining"] == 0.006
    assert observed["reconciliation"]["status"] == "matched"
    assert observed["reconciliation"]["fees"] == [{"currency": "USDT", "cost": 0.02}]
    assert len(writes) == 1


@pytest.mark.parametrize(
    "change, quantity, problem",
    [
        ({"symbol": "ETHUSDT"}, 0.01, "different pair"),
        ({"orderTypes": ["LIMIT"]}, 0.01, "unavailable"),
        ({"status": "2"}, 0.01, "unavailable"),
        ({"isSpotTradingAllowed": False}, 0.01, "unavailable"),
        ({"tradeSideType": 3}, 0.01, "unavailable"),
        ({"tradeSideType": None}, 0.01, "unavailable"),
        ({"baseAssetPrecision": 2}, 0.001, "base precision"),
        ({"baseSizePrecision": "0.02"}, 0.01, "minimum base"),
        ({"quoteAmountPrecisionMarket": "550"}, 0.01, "minimum cost"),
        ({"maxQuoteAmountMarket": "400"}, 0.01, "maximum cost"),
    ],
)
def test_preview_refuses_an_unsupported_pair_side_or_size(mexc, monkeypatch, change, quantity, problem):
    owner, account, adapter = mexc
    monkeypatch.setattr(adapter._exchange, "spotPublicGetExchangeInfo", lambda _: rules(**change))
    monkeypatch.setattr(adapter._exchange, "spotPrivatePostOrder", lambda _: pytest.fail("Unexpected write"))
    with pytest.raises(ValueError, match=problem):
        owner.trading.preview(market_request(account, quantity=quantity))


@pytest.mark.parametrize("failure", ["side closed", "public timeout"])
def test_confirmation_rechecks_rules_before_any_native_write(mexc, monkeypatch, failure):
    owner, account, adapter = mexc
    native = adapter._exchange
    monkeypatch.setattr(native, "spotPublicGetExchangeInfo", lambda _: rules())
    review = owner.trading.preview(market_request(account))

    def changed(_):
        if failure == "public timeout":
            raise ccxt.RequestTimeout("PRIVATE")
        return rules(tradeSideType=3)

    monkeypatch.setattr(native, "spotPublicGetExchangeInfo", changed)
    monkeypatch.setattr(native, "spotPrivatePostOrder", lambda _: pytest.fail("Unexpected write"))
    result = owner.trading.execute(review["id"], review["confirmation"])
    assert result["status"] == "rejected" and not result.get("exchange_order_id")
    assert not result["tracking"]


@pytest.mark.parametrize(
    "change",
    [
        {"origQuoteOrderQty": "500"},
        {"origQuoteOrderQty": None},
        {"origQty": None},
        {"Qty": "0.009"},
        {"stpMode": "cancel_maker"},
    ],
)
def test_market_recovery_refuses_quote_budget_and_missing_or_conflicting_original_terms(
    mexc, monkeypatch, change
):
    _, _, adapter = mexc
    native = adapter._exchange
    row = {
        **mexc_order(type="MARKET", timeInForce="IOC", origQuoteOrderQty="0", clientOrderId="saved"),
        **change,
    }
    monkeypatch.setattr(native, "spotPrivateGetOrder", lambda _: row)
    with pytest.raises(ValueError, match="differs"):
        lookup_order(native, "saved", "BTC/USDT")
