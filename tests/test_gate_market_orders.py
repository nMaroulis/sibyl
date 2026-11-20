"""Exercise Gate cash market-sell review, submission and recovery with offline transports."""

import ccxt
import pytest
from test_expanded_order_adapters import gate_order, saved_account
from test_order_management import request as order_request

from sibyl.exchanges.registry import provider_catalog
from sibyl.services.trading.service import ExchangeTrading

ORDER_ID = str(2**60 + 17)


@pytest.fixture
def gate(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    owner.settings.allow_live_trading = True
    account, adapter = saved_account(owner, "gate", "BTC_USDT")
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"BTC": 1, "USDT": 10000}})
    monkeypatch.setattr(adapter, "fetch_ticker", lambda _: {"bid": 50000, "ask": 50001})
    return owner, account, adapter


def rules(**changes):
    return {
        "id": "BTC_USDT",
        "base": "BTC",
        "quote": "USDT",
        "type": "normal",
        "trade_status": "sellable",
        "amount_precision": 8,
        "min_base_amount": "0.00001",
        "min_quote_amount": "1",
        "max_base_amount": "1",
        "market_order_max_stock": "0.5",
        **changes,
    }


def market_request(account, **changes):
    return order_request(account, **{"order_type": "market", "side": "sell", "limit_price": None, **changes})


def native_sell(**changes):
    return gate_order(
        ORDER_ID,
        **{
            "type": "market",
            "side": "sell",
            "price": "0",
            "time_in_force": "ioc",
            "status": "closed",
            "finish_as": "ioc",
            "left": "0.006",
            "filled_amount": "0.004",
            "filled_total": "200",
            "avg_deal_price": "50000",
            **changes,
        },
    )


def test_lost_response_recovers_market_sell_and_fees_after_restart(gate, monkeypatch):
    owner, account, adapter = gate
    native = adapter._exchange
    reads, writes = [], []

    def transport(path, api, method, params, *args, **kwargs):
        if (path, method) == ("currency_pairs/{currency_pair}", "GET"):
            assert api == ["public", "spot"]
            reads.append(params.copy())
            return rules()
        assert (path, api, method) == ("orders", ["private", "spot"], "POST")
        writes.append(params.copy())
        raise ccxt.RequestTimeout("private response")

    monkeypatch.setattr(native, "fetch2", transport)
    service = owner.trading
    review = service.preview(market_request(account))
    result = service.execute(review["id"], review["confirmation"])
    assert result["status"] == "unknown"
    assert service.execute(review["id"], review["confirmation"])["status"] == "unknown"
    assert reads == [{"currency_pair": "BTC_USDT"}] * 2
    assert writes == [
        {
            "currency_pair": "BTC_USDT",
            "account": "spot",
            "type": "market",
            "side": "sell",
            "amount": "0.01",
            "time_in_force": "ioc",
            "text": result["client_order_id"],
        }
    ]
    assert result["client_order_id"].startswith("t-")

    observed = native_sell(text=result["client_order_id"])

    def by_id(params):
        assert params["currency_pair"] == "BTC_USDT" and params["account"] == "spot"
        if params["order_id"] == result["client_order_id"]:
            raise ccxt.OrderNotFound("Gate requires the native ID for finished orders.")
        assert params["order_id"] == ORDER_ID
        return observed

    def finished(params):
        assert params["currency_pair"] == "BTC_USDT" and params["account"] == "spot"
        assert params["status"] == "finished"
        return [observed] if params["page"] == 1 else []

    def fills(params):
        assert params["currency_pair"] == "BTC_USDT" and params["order_id"] == ORDER_ID
        if params["page"] == 2:
            return []
        return [
            {
                "id": str(2**60 + 13),
                "order_id": ORDER_ID,
                "currency_pair": "BTC_USDT",
                "side": "sell",
                "price": "50000",
                "amount": "0.004",
                "create_time_ms": observed["create_time_ms"],
                "fee": "0.2",
                "fee_currency": "USDT",
                "gt_fee": "0",
                "point_fee": "0",
            }
        ]

    monkeypatch.setattr(native, "privateSpotGetOrdersOrderId", by_id)
    monkeypatch.setattr(native, "privateSpotGetOrders", finished)
    monkeypatch.setattr(native, "privateSpotGetMyTrades", fills)
    owner.settings.allow_live_trading = False
    assert service.recover(review["id"])["recovery"]["state"] == "searching"
    restarted = ExchangeTrading(owner.market, owner.store)
    assert restarted.recover(review["id"])["recovery"]["state"] == "searching"
    recovered = restarted.recover(review["id"])
    assert recovered["recovery"]["state"] == "found"
    assert recovered["exchange_order_id"] == ORDER_ID
    assert recovered["status"] == "canceled"
    assert recovered["filled"] == 0.004 and recovered["remaining"] == 0.006
    detail = restarted.reconciliation.sync(review["id"], manual=True)
    assert detail["reconciliation"]["status"] == "matched"
    assert detail["reconciliation"]["fees"] == [{"currency": "USDT", "cost": 0.2}]
    assert len(writes) == 1


@pytest.mark.parametrize(
    "change",
    [{}, {"side": "buy"}, {"account": "unified"}, {"time_in_force": "fok"}, {"amount": "0.02"}, {"id": None}],
)
def test_acknowledgment_requires_the_original_cash_ioc_sell(gate, monkeypatch, change):
    owner, account, adapter = gate
    native = adapter._exchange
    monkeypatch.setattr(native, "publicSpotGetCurrencyPairsCurrencyPair", lambda _: rules())

    def submit(params):
        assert params["amount"] == "0.01"
        return native_sell(
            text=params["text"],
            finish_as="filled",
            left="0",
            filled_amount="0.01",
            filled_total="500",
            **change,
        )

    monkeypatch.setattr(native, "privateSpotPostOrders", submit)
    review = owner.trading.preview(market_request(account))
    result = owner.trading.execute(review["id"], review["confirmation"])
    if change:
        assert result["status"] == "unknown" and not result.get("exchange_order_id")
    else:
        assert result["status"] == "closed" and result["exchange_order_id"] == ORDER_ID
        assert result["filled"] == 0.01 and result["remaining"] == 0


@pytest.mark.parametrize(
    "change, message",
    [
        ({"quote": "USDC"}, "different pair"),
        ({"trade_status": "buyable"}, "unavailable"),
        ({"type": "premarket"}, "unavailable"),
        ({"amount_precision": 1}, "base precision"),
        ({"min_base_amount": "0.02"}, "minimum base"),
        ({"market_order_max_stock": "0.001"}, "maximum base"),
        ({"min_quote_amount": "600"}, "minimum cost"),
        ({"max_base_amount": "bad"}, "invalid max_base_amount"),
    ],
)
def test_preview_checks_current_sell_permissions_and_published_limits(gate, monkeypatch, change, message):
    owner, account, adapter = gate
    monkeypatch.setattr(
        adapter._exchange, "publicSpotGetCurrencyPairsCurrencyPair", lambda _: rules(**change)
    )
    monkeypatch.setattr(adapter._exchange, "privateSpotPostOrders", lambda _: pytest.fail("Unexpected write"))
    with pytest.raises(ValueError, match=message):
        owner.trading.preview(market_request(account))


@pytest.mark.parametrize("failure", ["sell disabled", "public timeout"])
def test_confirmation_rechecks_sell_eligibility_before_any_write(gate, monkeypatch, failure):
    owner, account, adapter = gate
    native = adapter._exchange
    monkeypatch.setattr(native, "publicSpotGetCurrencyPairsCurrencyPair", lambda _: rules())
    review = owner.trading.preview(market_request(account))

    def changed(_):
        if failure == "public timeout":
            raise ccxt.RequestTimeout("private response")
        return rules(trade_status="buyable")

    monkeypatch.setattr(native, "publicSpotGetCurrencyPairsCurrencyPair", changed)
    monkeypatch.setattr(native, "privateSpotPostOrders", lambda _: pytest.fail("Unexpected write"))
    result = owner.trading.execute(review["id"], review["confirmation"])
    assert result["status"] == "rejected" and not result.get("exchange_order_id")
    assert not result["tracking"]


@pytest.mark.parametrize("change", [{"side": "buy"}, {"account": "margin"}, {"amend_text": "t-revised"}])
def test_recovery_refuses_native_evidence_from_other_order_paths(gate, monkeypatch, change):
    _, _, adapter = gate
    row = native_sell(text="t-saved", **change)
    monkeypatch.setattr(adapter._exchange, "privateSpotGetOrdersOrderId", lambda _: row)
    with pytest.raises(ValueError, match="differs"):
        adapter.fetch_order_lookup_page("t-saved", "BTC/USDT", {}, 1, 2)


def test_gate_buy_limit_remains_available_and_quote_budget_buys_fail_before_reading(gate, monkeypatch):
    owner, account, adapter = gate
    monkeypatch.setattr(adapter._exchange, "fetch2", lambda *args, **kwargs: pytest.fail("Unexpected I/O"))
    provider = next(row for row in provider_catalog()["items"] if row["id"] == "gate")
    assert provider["market_order_sides"] == ["sell"] and provider["limit_orders"]
    spot = next(group for group in provider["support"] if group["id"] == "spot")
    market = next(feature for feature in spot["features"] if feature["id"] == "market_orders")
    assert market["label"] == "Market sell · IOC" and "quote-currency budget" in market["detail"]
    with pytest.raises(ValueError, match="quote-currency budget"):
        owner.trading.preview(market_request(account, side="buy"))
    assert owner.trading.preview(order_request(account))["request"]["order_type"] == "limit"
