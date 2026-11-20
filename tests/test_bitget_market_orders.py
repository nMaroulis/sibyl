"""Exercise Bitget Classic market-sell sizing and recovery against native response shapes."""

import ccxt
import pytest
from test_expanded_order_adapters import bitget_order, saved_account
from test_extended_account_history import native as fill_row
from test_order_management import request as order_request

from sibyl.exchanges.bitget_orders import parse_order
from sibyl.exchanges.registry import provider_catalog
from sibyl.services.trading.service import ExchangeTrading

ORDER_ID = str(2**60 + 17)


def response(data):
    return {"code": "00000", "data": data}


def rules(**changes):
    return response(
        [
            {
                "symbol": "BTCUSDT",
                "baseCoin": "BTC",
                "quoteCoin": "USDT",
                "quantityPrecision": "8",
                "status": "online",
                "minTradeUSDT": "1",
                "maxMarketOrderValue": "1000",
                **changes,
            }
        ]
    )


@pytest.fixture
def bitget(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    owner.settings.allow_live_trading = True
    account, adapter = saved_account(owner, "bitget", "BTCUSDT")
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 10000, "BTC": 1}})
    monkeypatch.setattr(adapter, "fetch_ticker", lambda _: {"bid": 50000, "ask": 50001})
    return owner, account, adapter


def market_request(account, **changes):
    return order_request(account, **{"side": "sell", "order_type": "market", "limit_price": None, **changes})


def market_order(**changes):
    return bitget_order(
        ORDER_ID,
        **{
            "side": "sell",
            "orderType": "market",
            "orderSource": "market",
            "enterPointSource": "API",
            "executionType": "exchange",
            "baseCoin": "BTC",
            "quoteCoin": "USDT",
            "price": "0",
            "priceAvg": "50000",
            "status": "cancelled",
            "baseVolume": "0.004",
            "quoteVolume": "200",
            "feeDetail": "native fee evidence belongs to exact fills",
            **changes,
        },
    )


def test_native_sell_recovers_after_restart_and_preserves_reported_fees(bitget, monkeypatch):
    owner, account, adapter = bitget
    native = adapter._exchange
    reads, writes = [], []

    def transport(path, api, method, params, *args, **kwargs):
        if (path, method) == ("v2/spot/public/symbols", "GET"):
            assert api == ["public", "spot"]
            reads.append(params.copy())
            return rules()
        assert (path, api, method) == ("v2/spot/trade/place-order", ["private", "spot"], "POST")
        writes.append(params.copy())
        raise ccxt.RequestTimeout("uncertain response")

    monkeypatch.setattr(native, "fetch2", transport)
    review = owner.trading.preview(market_request(account))
    uncertain = owner.trading.execute(review["id"], review["confirmation"])
    assert uncertain["status"] == "unknown"
    assert owner.trading.execute(review["id"], review["confirmation"])["status"] == "unknown"
    assert reads == [{"symbol": "BTCUSDT"}] * 2
    assert writes == [
        {
            "symbol": "BTCUSDT",
            "side": "sell",
            "orderType": "market",
            "force": "gtc",
            "size": "0.01",
            "clientOid": uncertain["client_order_id"],
            "tpslType": "normal",
        }
    ]

    observed = market_order(clientOid=uncertain["client_order_id"])

    def exact_order(params):
        assert params in ({"clientOid": uncertain["client_order_id"]}, {"orderId": ORDER_ID})
        return response([observed])

    def exact_fills(params):
        assert params["orderId"] == ORDER_ID and params["symbol"] == "BTCUSDT"
        if params.get("idLessThan"):
            return response([])
        return response(
            [
                fill_row(
                    "bitget",
                    str(2**60 + 5),
                    side="sell",
                    orderId=ORDER_ID,
                    size="0.004",
                    amount="200",
                    priceAvg="50000",
                    cTime=observed["cTime"],
                )
            ]
        )

    monkeypatch.setattr(native, "privateSpotGetV2SpotTradeOrderInfo", exact_order)
    monkeypatch.setattr(native, "privateSpotGetV2SpotTradeFills", exact_fills)
    owner.settings.allow_live_trading = False
    restarted = ExchangeTrading(owner.market, owner.store)
    result = restarted.recover(review["id"])
    assert result["recovery"]["state"] == "found" and result["exchange_order_id"] == ORDER_ID
    assert result["status"] == "canceled" and result["filled"] == 0.004 and result["remaining"] == 0.006
    detail = restarted.reconciliation.sync(review["id"], manual=True)
    assert detail["reconciliation"]["status"] == "matched"
    assert detail["reconciliation"]["fees"] == [{"currency": "USDT", "cost": 0.001}]
    assert adapter.fetch_order(ORDER_ID, "BTC/USDT")["amount"] == 0.01
    assert len(writes) == 1


@pytest.mark.parametrize("change", [{}, {"clientOid": "wrong"}, {"orderId": None}, {"orderId": 1.2}])
def test_ack_tracks_only_the_exact_returned_identity_without_inventing_fills(bitget, monkeypatch, change):
    owner, account, adapter = bitget
    native = adapter._exchange
    monkeypatch.setattr(native, "publicSpotGetV2SpotPublicSymbols", lambda _: rules())

    def place(params):
        assert params["size"] == "0.00123456"
        return response({"clientOid": params["clientOid"], "orderId": ORDER_ID, **change})

    monkeypatch.setattr(native, "privateSpotPostV2SpotTradePlaceOrder", place)
    review = owner.trading.preview(market_request(account, quantity=0.00123456))
    result = owner.trading.execute(review["id"], review["confirmation"])
    if change:
        assert result["status"] == "unknown" and not result.get("exchange_order_id")
    else:
        assert result["status"] == "submitted" and result["exchange_order_id"] == ORDER_ID
        assert result.get("filled") is None


@pytest.mark.parametrize(
    "change, message",
    [
        ({"baseCoin": "ETH"}, "different pair"),
        ({"status": "halt"}, "unavailable"),
        ({"quantityPrecision": "bad"}, "valid base"),
        ({"quantityPrecision": "1"}, "base precision"),
        ({"minTradeUSDT": "600"}, "minimum cost"),
        ({"maxMarketOrderValue": "400"}, "maximum cost"),
    ],
)
def test_preview_checks_current_market_rules(bitget, monkeypatch, change, message):
    owner, account, adapter = bitget
    monkeypatch.setattr(adapter._exchange, "publicSpotGetV2SpotPublicSymbols", lambda _: rules(**change))
    monkeypatch.setattr(
        adapter._exchange, "privateSpotPostV2SpotTradePlaceOrder", lambda _: pytest.fail("Write")
    )
    with pytest.raises(ValueError, match=message):
        owner.trading.preview(market_request(account))


def test_native_usdt_bounds_are_never_compared_to_other_quote_units(bitget, monkeypatch):
    owner, _, _ = bitget
    account, adapter = saved_account(owner, "bitget", "BTCETH", quote="ETH")
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"BTC": 1}})
    monkeypatch.setattr(adapter, "fetch_ticker", lambda _: {"bid": 20})
    monkeypatch.setattr(
        adapter._exchange,
        "publicSpotGetV2SpotPublicSymbols",
        lambda _: rules(symbol="BTCETH", quoteCoin="ETH"),
    )
    preview = owner.trading.preview(market_request(account, symbol="BTC/ETH"))
    assert preview["notional"] == 0.2 and preview["status"] == "preview"


@pytest.mark.parametrize("fault", ["halt", "timeout"])
def test_confirmation_revalidates_pair_before_any_write(bitget, monkeypatch, fault):
    owner, account, adapter = bitget
    native = adapter._exchange
    monkeypatch.setattr(native, "publicSpotGetV2SpotPublicSymbols", lambda _: rules())
    review = owner.trading.preview(market_request(account))

    def changed(_):
        if fault == "timeout":
            raise ccxt.RequestTimeout("private response")
        return rules(status="halt")

    monkeypatch.setattr(native, "publicSpotGetV2SpotPublicSymbols", changed)
    monkeypatch.setattr(native, "privateSpotPostV2SpotTradePlaceOrder", lambda _: pytest.fail("Write"))
    result = owner.trading.execute(review["id"], review["confirmation"])
    assert result["status"] == "rejected" and not result["tracking"]
    assert not result.get("exchange_order_id")


@pytest.mark.parametrize(
    "change",
    [{"side": "buy"}, {"orderSource": "spot_trader_sell"}, {"quoteCoin": "USDC"}, {"clientOid": "wrong"}],
)
def test_recovery_refuses_other_order_types_origin_units_or_identity(bitget, monkeypatch, change):
    _, _, adapter = bitget
    row = market_order(**{"clientOid": "saved", **change})
    monkeypatch.setattr(adapter._exchange, "privateSpotGetV2SpotTradeOrderInfo", lambda _: response([row]))
    with pytest.raises(ValueError, match="differs"):
        adapter.fetch_order_lookup_page("saved", "BTC/USDT", {}, 1, 2)


def test_only_exact_sell_details_establish_base_quantity(bitget):
    _, _, adapter = bitget
    native = adapter._exchange
    market = native.market("BTC/USDT")
    listed = parse_order(native, market_order(size="500"), market)
    bought = parse_order(native, market_order(side="buy", size="500"), market, detail=True)
    for order in (listed, bought):
        assert order["amount"] is None and order["remaining"] is None
        assert order["filled"] == 0.004 and order["cost"] == 200
    with pytest.raises(ccxt.ExchangeError, match="Conflicting"):
        parse_order(native, market_order(status="filled", baseVolume="0.004"), market, detail=True)


def test_catalog_offers_market_sells_and_rejects_quote_budget_buys_before_io(bitget, monkeypatch):
    owner, account, adapter = bitget
    monkeypatch.setattr(adapter._exchange, "fetch2", lambda *args, **kwargs: pytest.fail("Unexpected I/O"))
    provider = next(row for row in provider_catalog()["items"] if row["id"] == "bitget")
    assert provider["market_order_sides"] == ["sell"] and provider["limit_orders"]
    with pytest.raises(ValueError, match="quote-currency budget"):
        owner.trading.preview(market_request(account, side="buy"))
    assert owner.trading.preview(order_request(account))["request"]["order_type"] == "limit"
