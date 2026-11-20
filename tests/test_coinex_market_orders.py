"""Verify native CoinEx market-order sizing and lost-response recovery offline."""

import ccxt
import pytest
from test_coinex_activity import fill, order, response
from test_expanded_order_adapters import saved_account
from test_order_management import request as order_request

from sibyl.exchanges.coinex_activity import lookup_page, parse_order
from sibyl.services.trading.service import ExchangeTrading


def rules(**changes):
    return response(
        [
            {
                "market": "BTCUSDT",
                "base_ccy": "BTC",
                "quote_ccy": "USDT",
                "base_ccy_precision": 8,
                "min_amount": "0.0001",
                "status": "online",
                "is_api_trading_available": True,
                **changes,
            }
        ]
    )


@pytest.fixture
def coinex(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    owner.settings.allow_live_trading = True
    account, adapter = saved_account(owner, "coinex", "BTCUSDT")
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 10000, "BTC": 1}})
    monkeypatch.setattr(adapter, "fetch_ticker", lambda _: {"bid": 50000, "ask": 50000})
    return owner, account, adapter._exchange


def market_request(account, **changes):
    return order_request(account, order_type="market", limit_price=None, **changes)


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_native_order_and_restart_recovery_share_base_size(coinex, monkeypatch, side):
    owner, account, native = coinex
    reads, writes = [], []

    def transport(path, api, method, params, *args, **kwargs):
        if (path, method) == ("spot/market", "GET"):
            assert api == ["v2", "public"]
            reads.append(params.copy())
            return rules()
        assert (path, api, method) == ("spot/order", ["v2", "private"], "POST")
        writes.append(params.copy())
        raise ccxt.RequestTimeout("PRIVATE")

    monkeypatch.setattr(native, "fetch2", transport)
    review = owner.trading.preview(market_request(account, side=side))
    uncertain = owner.trading.execute(review["id"], review["confirmation"])
    assert uncertain["status"] == "unknown"
    assert owner.trading.execute(review["id"], review["confirmation"])["status"] == "unknown"
    assert reads == [{"market": "BTCUSDT"}] * 2
    assert writes == [
        {
            "market": "BTCUSDT",
            "market_type": "SPOT",
            "side": side,
            "type": "market",
            "ccy": "BTC",
            "amount": "0.01",
            "client_id": uncertain["client_order_id"],
        }
    ]
    observed_order = order(
        type="market",
        price="0",
        side=side,
        client_id=uncertain["client_order_id"],
        filled_amount="0.004",
        filled_value="200",
        unfilled_amount="0.006",
    )

    def pending(params):
        assert params["market"] == "BTCUSDT" and params["market_type"] == "SPOT"
        assert params["client_id"] == uncertain["client_order_id"]
        return response([])

    def finished(params):
        assert params["market"] == "BTCUSDT" and params["market_type"] == "SPOT"
        assert "client_id" not in params
        return response([observed_order], True) if params["page"] == 1 else response([])

    def exact_fills(params):
        assert params["order_id"] == str(observed_order["order_id"]) and params["market_type"] == "SPOT"
        return response([fill(side=side, amount="0.004")])

    monkeypatch.setattr(native, "v2PrivateGetSpotPendingOrder", pending)
    monkeypatch.setattr(native, "v2PrivateGetSpotFinishedOrder", finished)
    monkeypatch.setattr(native, "v2PrivateGetSpotOrderDeals", exact_fills)
    owner.settings.allow_live_trading = False
    assert owner.trading.recover(review["id"])["recovery"]["state"] == "searching"
    restarted = ExchangeTrading(owner.market, owner.store)
    assert restarted.recover(review["id"])["recovery"]["state"] == "searching"
    observed = restarted.recover(review["id"])
    assert observed["recovery"]["state"] == "found"
    assert observed["exchange_order_id"] == str(observed_order["order_id"])
    assert observed["status"] == "canceled" and observed["filled"] == 0.004
    assert observed["remaining"] == 0.006
    assert observed["reconciliation"]["status"] == "matched"
    assert observed["reconciliation"]["fees"] == [{"currency": "USDT", "cost": 0.2}]
    assert len(writes) == 1


@pytest.mark.parametrize(
    "change",
    [{}, {"ccy": "USDT"}, {"ccy": None}, {"amount": "0.02"}, {"order_id": None}, {"stop_id": "1"}],
)
def test_acknowledgment_requires_matching_original_terms_and_exact_identity(coinex, monkeypatch, change):
    owner, account, native = coinex
    monkeypatch.setattr(native, "v2PublicGetSpotMarket", lambda _: rules())

    def submit(params):
        assert params["amount"] == "0.00123456"
        row = order(
            type="market",
            price="0",
            **{"client_id": params["client_id"], "amount": params["amount"], **change},
        )
        return response({**row, "unfilled_amount": "0.00123456"})

    monkeypatch.setattr(native, "v2PrivatePostSpotOrder", submit)
    review = owner.trading.preview(market_request(account, quantity=0.00123456))
    result = owner.trading.execute(review["id"], review["confirmation"])
    if change:
        assert result["status"] == "unknown"
        assert not result.get("exchange_order_id")
    else:
        assert result["status"] == "submitted"
        assert result["exchange_order_id"] == str(2**60 + 18)


@pytest.mark.parametrize(
    "change, problem",
    [
        ({"base_ccy": "ETH"}, "different pair"),
        ({"is_api_trading_available": False}, "unavailable"),
        ({"base_ccy_precision": 1}, "base precision"),
        ({"min_amount": "0.02"}, "minimum base"),
        ({"min_amount": None}, "valid minimum"),
    ],
)
def test_preview_checks_current_pair_permission_and_base_size(coinex, monkeypatch, change, problem):
    owner, account, native = coinex
    monkeypatch.setattr(native, "v2PublicGetSpotMarket", lambda _: rules(**change))
    monkeypatch.setattr(native, "v2PrivatePostSpotOrder", lambda _: pytest.fail("Unexpected order"))
    with pytest.raises(ValueError, match=problem):
        owner.trading.preview(market_request(account))


@pytest.mark.parametrize("failure", ["offline", "public timeout"])
def test_confirmation_rechecks_permission_before_sending(coinex, monkeypatch, failure):
    owner, account, native = coinex
    monkeypatch.setattr(native, "v2PublicGetSpotMarket", lambda _: rules())
    review = owner.trading.preview(market_request(account))

    def changed(_):
        if failure == "public timeout":
            raise ccxt.RequestTimeout("PRIVATE")
        return rules(status="offline")

    monkeypatch.setattr(native, "v2PublicGetSpotMarket", changed)
    monkeypatch.setattr(native, "v2PrivatePostSpotOrder", lambda _: pytest.fail("Unexpected order"))
    result = owner.trading.execute(review["id"], review["confirmation"])
    assert result["status"] == "rejected" and not result.get("exchange_order_id")
    assert not result["tracking"]


@pytest.mark.parametrize("currency", ["USDT", None])
def test_recovery_requires_a_base_sized_request(coinex, monkeypatch, currency):
    _, _, native = coinex
    row = order(type="market", client_id="saved", ccy=currency)
    monkeypatch.setattr(native, "v2PrivateGetSpotPendingOrder", lambda _: response([row]))
    with pytest.raises(ValueError, match="original base currency"):
        lookup_page(native, "saved", "BTC/USDT", {})


@pytest.mark.parametrize(
    "currency, unfilled, state, amount",
    [("BTC", "0", "closed", 0.01), ("BTC", "0.005", "unknown", 0.01), ("USDT", "0", "unknown", None)],
)
def test_statusless_finished_market_rows_preserve_only_proven_units(
    coinex, currency, unfilled, state, amount
):
    _, _, native = coinex
    row = order(
        type="market", ccy=currency, unfilled_amount=unfilled, filled_amount="0.01", filled_value="500"
    )
    parsed = parse_order(native, row, native.market("BTC/USDT"), recent=True)
    assert parsed["status"] == state and parsed["amount"] == amount
    assert parsed["filled"] == 0.01 and parsed["cost"] == 500
    if currency == "USDT":
        assert parsed["remaining"] is None
