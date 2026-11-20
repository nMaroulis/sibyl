"""Verify reviewed HTX spot market sells with native-shaped offline transports."""

import ccxt
import pytest
from test_gate_htx_orders import htx_fill, htx_order, save_htx
from test_order_management import request as order_request

from sibyl.exchanges.registry import provider_catalog
from sibyl.services.trading.service import ExchangeTrading

ORDER_ID = str(2**60 + 20)


def response(data):
    return {"status": "ok", "data": data}


def rules(**changes):
    return response(
        [
            {
                "symbol": "btcusdt",
                "bc": "btc",
                "qc": "usdt",
                "state": "online",
                "at": "enabled",
                "ap": 8,
                "smminoa": 0.001,
                "smmaxoa": 1,
                "minov": 5000,
                "bmmaxov": 1,
                **changes,
            }
        ]
    )


@pytest.fixture
def htx(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    owner.settings.allow_live_trading = True
    account, adapter = save_htx(owner)
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 10000, "BTC": 1}})
    monkeypatch.setattr(adapter, "fetch_ticker", lambda _: {"bid": 50000, "ask": 50001})
    return owner, account, adapter


def market_request(account, **changes):
    return order_request(account, **{"side": "sell", "order_type": "market", "limit_price": None, **changes})


def sell(**changes):
    row = htx_order()
    del row["filled-amount"], row["filled-cash-amount"]
    return {
        **row,
        "type": "sell-market",
        "price": "0",
        "state": "partial-canceled",
        "field-amount": "0.004",
        "field-cash-amount": "200",
        **changes,
    }


def test_lost_ack_recovers_exact_spot_sale_and_fees_after_restart(htx, monkeypatch):
    owner, account, adapter = htx
    native = adapter._exchange
    reads, writes = [], []

    def transport(path, api, method, params, *args, **kwargs):
        if (path, method) == ("v1/settings/common/market-symbols", "GET"):
            assert api == ["spot", "public"]
            reads.append(params.copy())
            return rules()
        assert (path, api, method) == ("v1/order/orders/place", ["spot", "private"], "POST")
        writes.append(params.copy())
        raise ccxt.RequestTimeout("uncertain response")

    monkeypatch.setattr(native, "fetch2", transport)
    review = owner.trading.preview(market_request(account))
    uncertain = owner.trading.execute(review["id"], review["confirmation"])
    assert uncertain["status"] == "unknown"
    assert owner.trading.execute(review["id"], review["confirmation"])["status"] == "unknown"
    assert reads == [{"symbols": "btcusdt"}] * 2
    assert writes == [
        {
            "account-id": "1234",
            "symbol": "btcusdt",
            "type": "sell-market",
            "source": "spot-api",
            "amount": "0.01",
            "client-order-id": uncertain["client_order_id"],
        }
    ]
    observed = sell(**{"client-order-id": uncertain["client_order_id"]})

    def client_detail(params):
        assert params == {"clientOrderId": uncertain["client_order_id"]}
        return response(observed)

    def exact_detail(params):
        assert params == {"order-id": ORDER_ID}
        return response(observed)

    def exact_fills(params):
        assert params == {"order-id": ORDER_ID}
        return response(
            [
                htx_fill(
                    **{
                        "type": "sell-market",
                        "filled-amount": "0.004",
                        "created-at": observed["created-at"],
                    }
                )
            ]
        )

    monkeypatch.setattr(native, "spotPrivateGetV1OrderOrdersGetClientOrder", client_detail)
    monkeypatch.setattr(native, "spotPrivateGetV1OrderOrdersOrderId", exact_detail)
    monkeypatch.setattr(native, "spotPrivateGetV1OrderOrdersOrderIdMatchresults", exact_fills)
    owner.settings.allow_live_trading = False
    restarted = ExchangeTrading(owner.market, owner.store)
    result = restarted.recover(review["id"])
    assert result["recovery"]["state"] == "found" and result["exchange_order_id"] == ORDER_ID
    assert result["status"] == "canceled" and result["filled"] == 0.004 and result["remaining"] == 0.006
    assert result["cost"] == 200 and result["average"] == 50000
    assert result["reconciliation"]["status"] == "matched"
    assert result["reconciliation"]["fees"] == [{"currency": "USDT", "cost": 0.2}]
    assert len(writes) == 1


@pytest.mark.parametrize("order_id", [ORDER_ID, None, float(2**60 + 20), "0"])
def test_acknowledgment_only_records_an_exact_order_id(htx, monkeypatch, order_id):
    owner, account, adapter = htx
    native = adapter._exchange
    monkeypatch.setattr(native, "spotPublicGetV1SettingsCommonMarketSymbols", lambda _: rules())
    monkeypatch.setattr(native, "spotPrivatePostV1OrderOrdersPlace", lambda _: response(order_id))
    review = owner.trading.preview(market_request(account))
    result = owner.trading.execute(review["id"], review["confirmation"])
    if order_id == ORDER_ID:
        assert result["status"] == "submitted" and result["exchange_order_id"] == ORDER_ID
        assert result.get("filled") is None
    else:
        assert result["status"] == "unknown" and not result.get("exchange_order_id")


@pytest.mark.parametrize(
    "change, message",
    [
        ({"qc": "usdc"}, "selected pair"),
        ({"at": "disabled"}, "unavailable"),
        ({"state": "suspend"}, "unavailable"),
        ({"ap": 1}, "base precision"),
        ({"smminoa": 0.02}, "minimum base"),
        ({"smmaxoa": 0.005}, "maximum base"),
        ({"smmaxoa": None}, "valid market sell bounds"),
    ],
)
def test_review_applies_market_sell_bounds_and_current_pair_permissions(htx, monkeypatch, change, message):
    owner, account, adapter = htx
    monkeypatch.setattr(
        adapter._exchange, "spotPublicGetV1SettingsCommonMarketSymbols", lambda _: rules(**change)
    )
    monkeypatch.setattr(
        adapter._exchange, "spotPrivatePostV1OrderOrdersPlace", lambda _: pytest.fail("Write")
    )
    with pytest.raises(ValueError, match=message):
        owner.trading.preview(market_request(account))


@pytest.mark.parametrize("fault", ["two spot wallets", "disabled", "timeout"])
def test_confirmation_requires_wallet_and_current_sell_rules_before_writing(htx, monkeypatch, fault):
    owner, account, adapter = htx
    native = adapter._exchange
    monkeypatch.setattr(native, "spotPublicGetV1SettingsCommonMarketSymbols", lambda _: rules())
    review = owner.trading.preview(market_request(account))

    def changed(_):
        if fault == "timeout":
            raise ccxt.RequestTimeout("private response")
        return rules(at="disabled")

    if fault == "two spot wallets":
        native.accounts = [{"id": "1234", "type": "spot"}, {"id": "3210", "type": "spot"}]
    else:
        monkeypatch.setattr(native, "spotPublicGetV1SettingsCommonMarketSymbols", changed)
    monkeypatch.setattr(native, "spotPrivatePostV1OrderOrdersPlace", lambda _: pytest.fail("Write"))
    result = owner.trading.execute(review["id"], review["confirmation"])
    assert result["status"] == "rejected" and not result.get("exchange_order_id")
    assert not result["tracking"]


@pytest.mark.parametrize(
    "changes, error",
    [
        ({"account-id": 4321}, ccxt.ExchangeError),
        ({"symbol": "ethusdt"}, ccxt.ExchangeError),
        ({"source": "super-margin-api"}, ValueError),
        ({"type": "buy-market"}, ValueError),
        ({"stop-price": "13.2"}, ValueError),
    ],
)
def test_recovery_refuses_wrong_wallet_pair_or_native_terms(htx, monkeypatch, changes, error):
    _, _, adapter = htx
    native = adapter._exchange
    row = sell(**{"client-order-id": "saved", **changes})
    monkeypatch.setattr(native, "spotPrivateGetV1OrderOrdersGetClientOrder", lambda _: response(row))
    with pytest.raises(error):
        adapter.fetch_order_lookup_page("saved", "BTC/USDT", {}, 1, 2)


def test_known_market_buys_keep_their_execution_but_hide_quote_sizing(htx, monkeypatch):
    _, _, adapter = htx
    native = adapter._exchange
    row = htx_order(
        **{
            "type": "buy-market",
            "amount": "510",
            "price": "0",
            "state": "filled",
            "filled-amount": "0.01",
            "filled-cash-amount": "500",
        }
    )
    monkeypatch.setattr(native, "spotPrivateGetV1OrderOrdersOrderId", lambda _: response(row))
    result = adapter.fetch_order(ORDER_ID, "BTC/USDT")
    assert result["amount"] is None and result["remaining"] is None
    assert result["filled"] == 0.01 and result["cost"] == 500 and result["average"] == 50000


def test_catalog_offers_market_sells_and_rejects_quote_budget_buys_before_io(htx, monkeypatch):
    owner, account, adapter = htx
    monkeypatch.setattr(adapter._exchange, "fetch2", lambda *args, **kwargs: pytest.fail("Unexpected I/O"))
    provider = next(row for row in provider_catalog()["items"] if row["id"] == "htx")
    assert provider["market_order_sides"] == ["sell"] and provider["limit_orders"]
    with pytest.raises(ValueError, match="quote-currency budget"):
        owner.trading.preview(market_request(account, side="buy"))
    assert owner.trading.preview(order_request(account))["request"]["order_type"] == "limit"
