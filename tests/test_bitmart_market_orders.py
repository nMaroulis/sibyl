"""Exercise native BitMart spot market sell quantities and recovery offline."""

import json

import ccxt
import pytest
from test_bitmart_activity import bitmart as bitmart
from test_bitmart_activity import fill, order, response
from test_order_discovery import spot_market
from test_order_management import request as order_request

from sibyl.exchanges.bitmart_activity import lookup_order
from sibyl.services.trading.service import ExchangeTrading

ORDER_ID = str(2**60 + 29)


def rules(**changes):
    return response(
        {
            "symbols": [
                {
                    "symbol": "BTC_USDT",
                    "base_currency": "BTC",
                    "quote_currency": "USDT",
                    "quote_increment": "0.00001",
                    "base_min_size": "0.00002",
                    "base_max_size": "100",
                    "min_sell_amount": "5",
                    "min_buy_amount": "1000",
                    "trade_status": "trading",
                    "planned_down_time": None,
                    **changes,
                }
            ]
        }
    )


@pytest.fixture
def market_account(bitmart, monkeypatch):
    owner, account, adapter = bitmart
    owner.settings.allow_live_trading = True
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 10000, "BTC": 1}})
    monkeypatch.setattr(adapter, "fetch_ticker", lambda _: {"bid": 50000, "ask": 50001})
    return owner, account, adapter


def sell_request(account, **changes):
    return order_request(account, **{"side": "sell", "order_type": "market", "limit_price": None, **changes})


def market_order(**changes):
    return order(
        ORDER_ID,
        **{
            "side": "sell",
            "type": "market",
            "state": "partially_canceled",
            "price": "0",
            "priceAvg": "50000",
            "size": "0.003",
            "filledSize": "0.001",
            "filledNotional": "50",
            "stpMode": "none",
            **changes,
        },
    )


def test_live_increment_controls_order_and_recovery_preserves_partial_fills(market_account, monkeypatch):
    owner, account, adapter = market_account
    native = adapter._exchange
    market = spot_market("BTC_USDT")
    # The cached SDK reports the minimum as the increment. The native details define them separately.
    market["precision"]["amount"] = 0.002
    native.set_markets([market])
    reads, writes = [], []

    def transport(path, api, method, params, *args, **kwargs):
        if (path, method) == ("spot/v1/symbols/details", "GET"):
            assert api == "public"
            reads.append(params.copy())
            return rules(base_min_size="0.002", quote_increment="0.001")
        assert (path, api, method) == ("spot/v2/submit_order", "private", "POST")
        writes.append(params.copy())
        raise ccxt.RequestTimeout("private response")

    monkeypatch.setattr(native, "fetch2", transport)
    review = owner.trading.preview(sell_request(account, quantity=0.003))
    uncertain = owner.trading.execute(review["id"], review["confirmation"])
    assert uncertain["status"] == "unknown"
    assert owner.trading.execute(review["id"], review["confirmation"])["status"] == "unknown"
    assert reads == [{}, {}]
    assert writes == [
        {
            "symbol": "BTC_USDT",
            "side": "sell",
            "type": "market",
            "size": "0.003",
            "client_order_id": uncertain["client_order_id"],
        }
    ]

    def detail(params):
        assert params == {"clientOrderId": uncertain["client_order_id"]}
        return response(market_order(clientOrderId=uncertain["client_order_id"]))

    def trades(params):
        assert params == {"orderId": ORDER_ID}
        return response(
            [
                fill(
                    orderId=ORDER_ID,
                    type="market",
                    side="sell",
                    size="0.001",
                    notional="50",
                )
            ]
        )

    monkeypatch.setattr(native, "privatePostSpotV4QueryClientOrder", detail)
    monkeypatch.setattr(native, "privatePostSpotV4QueryOrderTrades", trades)
    owner.settings.allow_live_trading = False
    recovered = ExchangeTrading(owner.market, owner.store).recover(review["id"])
    assert recovered["recovery"]["state"] == "found" and recovered["exchange_order_id"] == ORDER_ID
    assert recovered["status"] == "canceled"
    assert recovered["filled"] == 0.001 and recovered["remaining"] == 0.002
    assert recovered["cost"] == 50 and recovered["average"] == 50000
    assert recovered["reconciliation"]["status"] == "matched"
    assert recovered["reconciliation"]["fees"] == [{"currency": "USDT", "cost": 0.2}]
    assert len(writes) == 1


@pytest.mark.parametrize("identity", [int(ORDER_ID), None, float(ORDER_ID)])
def test_ack_requires_an_exact_native_id(market_account, monkeypatch, identity):
    owner, account, adapter = market_account
    native = adapter._exchange
    monkeypatch.setattr(native, "publicGetSpotV1SymbolsDetails", lambda _: rules())

    def place(params):
        assert params["size"] == "0.00012"
        return response({"order_id": identity})

    monkeypatch.setattr(native, "privatePostSpotV2SubmitOrder", place)
    review = owner.trading.preview(sell_request(account, quantity=0.00012))
    result = owner.trading.execute(review["id"], review["confirmation"])
    if identity == int(ORDER_ID):
        assert result["status"] == "submitted" and result["exchange_order_id"] == ORDER_ID
        assert result.get("filled") is None
    else:
        assert result["status"] == "unknown" and not result.get("exchange_order_id")


@pytest.mark.parametrize("code, status", [(59002, "unknown"), (50042, "unknown"), (50020, "rejected")])
def test_native_server_and_duplicate_errors_remain_recoverable(market_account, monkeypatch, code, status):
    owner, account, adapter = market_account
    native = adapter._exchange
    monkeypatch.setattr(native, "publicGetSpotV1SymbolsDetails", lambda _: rules())
    writes = []

    def place(params):
        writes.append(params.copy())
        body = {"code": code, "message": "PRIVATE", "data": {}}
        native.handle_errors(
            500 if code == 59002 else 400, "", "", "POST", {}, json.dumps(body), body, {}, ""
        )

    monkeypatch.setattr(native, "privatePostSpotV2SubmitOrder", place)
    review = owner.trading.preview(sell_request(account))
    result = owner.trading.execute(review["id"], review["confirmation"])
    assert result["status"] == status and not result.get("exchange_order_id")
    assert owner.trading.execute(review["id"], review["confirmation"])["status"] == status
    assert len(writes) == 1 and "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"quote_currency": "USDC"}, "selected pair"),
        ({"trade_status": "pre-trade"}, "unavailable"),
        ({"planned_down_time": 1}, "unavailable"),
        ({"base_min_size": "0.02"}, "minimum base"),
        ({"base_max_size": "0.005"}, "maximum base"),
        ({"quote_increment": "0.003"}, "base increment"),
        ({"quote_increment": "0"}, "valid base"),
        ({"min_sell_amount": "600"}, "minimum cost"),
    ],
)
def test_current_pair_state_increment_and_sell_bounds_are_checked(
    market_account, monkeypatch, changes, message
):
    owner, account, adapter = market_account
    native = adapter._exchange
    monkeypatch.setattr(native, "publicGetSpotV1SymbolsDetails", lambda _: rules(**changes))
    monkeypatch.setattr(native, "privatePostSpotV2SubmitOrder", lambda _: pytest.fail("Unexpected write"))
    with pytest.raises(ValueError, match=message):
        owner.trading.preview(sell_request(account))


@pytest.mark.parametrize("failure", ["increment changed", "public timeout"])
def test_confirmation_reads_fresh_rules_before_sending(market_account, monkeypatch, failure):
    owner, account, adapter = market_account
    native = adapter._exchange
    monkeypatch.setattr(native, "publicGetSpotV1SymbolsDetails", lambda _: rules())
    review = owner.trading.preview(sell_request(account))

    def changed(_):
        if failure == "public timeout":
            raise ccxt.RequestTimeout("private response")
        return rules(quote_increment="0.003")

    monkeypatch.setattr(native, "publicGetSpotV1SymbolsDetails", changed)
    monkeypatch.setattr(native, "privatePostSpotV2SubmitOrder", lambda _: pytest.fail("Unexpected write"))
    result = owner.trading.execute(review["id"], review["confirmation"])
    assert result["status"] == "rejected" and not result.get("exchange_order_id")
    assert not result["tracking"]


@pytest.mark.parametrize(
    "change",
    [{"side": "buy", "notional": ""}, {"orderMode": "iso_margin"}, {"stpMode": "cancel_both"}, {"size": ""}],
)
def test_recovery_refuses_other_sizing_modes_and_unreviewed_terms(market_account, monkeypatch, change):
    _, _, adapter = market_account
    native = adapter._exchange
    row = market_order(**{"clientOrderId": "saved", **change})
    monkeypatch.setattr(native, "privatePostSpotV4QueryClientOrder", lambda _: response(row))
    with pytest.raises(ValueError, match="differs"):
        lookup_order(native, "saved", "BTC/USDT")


def test_market_buy_read_never_converts_quote_budget_to_requested_base(market_account, monkeypatch):
    _, _, adapter = market_account
    native = adapter._exchange
    row = market_order(side="buy", size="0.001", notional="60")
    monkeypatch.setattr(native, "privatePostSpotV4QueryOrder", lambda _: response(row))
    result = adapter.fetch_order(ORDER_ID, "BTC/USDT")
    assert result["amount"] is None and result["remaining"] is None
    assert result["filled"] == 0.001 and result["cost"] == 50 and result["quote_budget"] == 60


def test_base_sized_market_buy_is_rejected_before_io_and_gtc_buy_remains_available(
    market_account, monkeypatch
):
    owner, account, adapter = market_account
    monkeypatch.setattr(adapter._exchange, "fetch2", lambda *args, **kwargs: pytest.fail("Unexpected I/O"))
    with pytest.raises(ValueError, match="quote-currency budget"):
        owner.trading.preview(sell_request(account, side="buy"))
    assert owner.trading.preview(order_request(account))["request"]["order_type"] == "limit"
