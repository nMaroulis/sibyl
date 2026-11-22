"""Exercise native sizing and durable recovery for the reviewed market order adapters."""

from decimal import Decimal

import ccxt
import pytest
from test_bitget_market_orders import market_order as bitget_order
from test_bitget_market_orders import response
from test_bitget_market_orders import rules as bitget_rules
from test_bitmart_market_orders import bitmart as bitmart
from test_bitmart_market_orders import market_account as market_account
from test_bitmart_market_orders import market_order as bitmart_market
from test_bitmart_market_orders import response as bitmart_response
from test_bitmart_market_orders import rules as bitmart_rules
from test_expanded_order_adapters import saved_account
from test_gate_market_orders import gate as gate
from test_gate_market_orders import native_sell as gate_sell
from test_gate_market_orders import rules as gate_rules
from test_htx_market_orders import htx as htx
from test_htx_market_orders import response as htx_response
from test_htx_market_orders import rules as htx_rules
from test_htx_market_orders import sell as htx_sell
from test_order_management import request as order_request
from test_poloniex_orders import FIRST_ID
from test_poloniex_orders import order as poloniex_order
from test_upbit_orders import order as upbit_order

from sibyl.exchanges.history import TradePage
from sibyl.services.trading.reconciliation import summarize
from sibyl.services.trading.reporting import trading_report
from sibyl.services.trading.service import ExchangeTrading


@pytest.fixture(params=["poloniex", "upbit", "bitget"])
def venue(request, manual_client, monkeypatch):
    owner = manual_client.app.state.services
    owner.settings.allow_live_trading = True
    name = request.param
    native_symbol = {"poloniex": "BTC_USDT", "upbit": "USDT-BTC", "bitget": "BTCUSDT"}[name]
    account, adapter = saved_account(owner, name, native_symbol)
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"BTC": 2, "USDT": 1000}})
    monkeypatch.setattr(adapter, "fetch_ticker", lambda _: {"ask": 1, "bid": 1})
    native = adapter._exchange
    if name == "poloniex":
        monkeypatch.setattr(
            native,
            "publicGetMarketsSymbol",
            lambda _: {
                "symbol": native_symbol,
                "state": "NORMAL",
                "baseCurrencyName": "BTC",
                "quoteCurrencyName": "USDT",
                "symbolTradeLimit": {
                    "quantityScale": 8,
                    "amountScale": 2,
                    "minAmount": "0.001",
                    "maxAmount": "100",
                    "minQuantity": "0.001",
                    "maxQuantity": "10",
                },
            },
        )
    elif name == "upbit":
        monkeypatch.setattr(
            native,
            "privateGetOrdersChance",
            lambda _: {
                "market": {
                    "id": native_symbol,
                    "state": "active",
                    "order_sides": ["bid", "ask"],
                    "bid_types": ["price"],
                    "ask_types": ["market"],
                    "bid": {"currency": "USDT", "min_total": "0.001"},
                    "ask": {"currency": "BTC", "min_total": "0.001"},
                    "max_total": "100",
                }
            },
        )
    else:
        monkeypatch.setattr(
            native, "publicSpotGetV2SpotPublicSymbols", lambda _: bitget_rules(quotePrecision="2")
        )
    return name, owner, account, adapter


def market_request(account, side, value):
    return order_request(
        account,
        side=side,
        order_type="market",
        limit_price=None,
        quantity=None if side == "buy" else value,
        quote_budget=value if side == "buy" else None,
    )


def placement(name, side, client_id):
    if name == "poloniex":
        return "privatePostOrders", {
            "side": side.upper(),
            "symbol": "BTC_USDT",
            "type": "MARKET",
            "timeInForce": "IOC",
            "accountType": "SPOT",
            "allowBorrow": False,
            "clientOrderId": client_id,
            "amount" if side == "buy" else "quantity": "2",
        }
    if name == "upbit":
        return "privatePostOrders", {
            "side": "bid" if side == "buy" else "ask",
            "market": "USDT-BTC",
            "identifier": client_id,
            "ord_type": "price" if side == "buy" else "market",
            "price" if side == "buy" else "volume": "2",
        }
    return "privateSpotPostV2SpotTradePlaceOrder", {
        "symbol": "BTCUSDT",
        "side": side,
        "orderType": "market",
        "size": "2",
        "force": "gtc",
        "clientOid": client_id,
        "tpslType": "normal",
    }


def recovered_row(name, side, client_id, *, original="2", cost="1"):
    # A quote budget of 2 can buy 3 base units. A sell of 2 can fill at most 2.
    quantity = "3" if side == "buy" else "1"
    if name == "poloniex":
        row = poloniex_order(
            clientOrderId=client_id,
            side=side.upper(),
            type="MARKET",
            timeInForce="IOC",
            quantity="0" if side == "buy" else original,
            price="0",
            amount=original if side == "buy" else "0",
            filledAmount=cost,
            filledQuantity=quantity,
            state="PARTIALLY_FILLED",
        )
        return "privateGetOrdersId", {"id": f"cid:{client_id}"}, row, str(FIRST_ID)
    if name == "upbit":
        row = upbit_order(
            identifier=client_id,
            side="bid" if side == "buy" else "ask",
            ord_type="price" if side == "buy" else "market",
            price=original if side == "buy" else None,
            volume=None if side == "buy" else original,
            remaining_volume=None if side == "buy" else "1",
            executed_funds=cost,
            executed_volume=quantity,
        )
        return "privateGetOrder", {"identifier": client_id}, row, row["uuid"]
    row = bitget_order(
        clientOid=client_id,
        side=side,
        size=original,
        baseVolume=quantity,
        quoteVolume=cost,
        status="partially_filled",
    )
    return "privateSpotGetV2SpotTradeOrderInfo", {"clientOid": client_id}, response([row]), row["orderId"]


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_exact_native_size_and_recovery_after_lost_response(venue, monkeypatch, side):
    name, owner, account, adapter = venue
    native = adapter._exchange
    request = market_request(account, side, 2)
    review = owner.trading.preview(request)
    path, expected = placement(name, side, review["client_order_id"])
    writes = []

    def lost(params):
        writes.append(params)
        raise ccxt.RequestTimeout("unknown response")

    monkeypatch.setattr(native, path, lost)
    result = owner.trading.execute(review["id"], review["confirmation"])
    assert result["status"] == "unknown"
    assert owner.trading.execute(review["id"], review["confirmation"])["status"] == "unknown"
    assert writes == [expected]
    lookup, query, payload, native_id = recovered_row(name, side, review["client_order_id"])

    def detail(params):
        assert params == query
        return payload

    monkeypatch.setattr(native, lookup, detail)
    monkeypatch.setattr(adapter, "fetch_order_fill_page", lambda *args, **kwargs: TradePage([], {}, True))
    owner.settings.allow_live_trading = False
    restarted = ExchangeTrading(owner.market, owner.store)
    persisted = restarted.recover(review["id"])
    assert persisted["recovery"]["state"] == "found" and persisted["exchange_order_id"] == native_id
    assert persisted["filled"] == (3 if side == "buy" else 1) and persisted["cost"] == 1
    assert len(writes) == 1
    if side == "buy":
        assert persisted["request"]["quote_budget"] == 2 and persisted["request"]["quantity"] is None
        assert persisted.get("remaining") is None
        row = next(
            row for row in trading_report(owner.store, restarted)["items"] if row["id"] == review["id"]
        )
        assert row["notional"] == 2 and row["notional_kind"] == "Quote budget" and row["quantity"] is None


@pytest.mark.parametrize("original, cost", [("2.01", "1"), ("2", "2.01")])
def test_recovery_rejects_wrong_budget_or_overspend(venue, monkeypatch, original, cost):
    name, owner, account, adapter = venue
    review = owner.trading.preview(market_request(account, "buy", 2))
    path, _ = placement(name, "buy", review["client_order_id"])

    def lost(_):
        raise ccxt.RequestTimeout("unknown response")

    monkeypatch.setattr(adapter._exchange, path, lost)
    assert owner.trading.execute(review["id"], review["confirmation"])["status"] == "unknown"
    lookup, _, row, _ = recovered_row(name, "buy", review["client_order_id"], original=original, cost=cost)
    monkeypatch.setattr(adapter._exchange, lookup, lambda _: row)
    result = owner.trading.recover(review["id"])
    assert result["status"] == "unknown" and not result.get("exchange_order_id")


def test_budget_preview_is_idempotent_and_requires_quote_funds(venue, monkeypatch):
    _, owner, account, adapter = venue
    request = market_request(account, "buy", 2)
    review = owner.trading.preview(request)
    assert review["notional"] == 2 and owner.trading.preview(request)["id"] == review["id"]
    with pytest.raises(ValueError, match="different exchange order"):
        owner.trading.preview(market_request(account, "buy", 3))
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"BTC": 1000, "USDT": 1}})
    with pytest.raises(ValueError, match="Insufficient available USDT"):
        owner.trading.preview(
            market_request(account, "buy", 2).model_copy(update={"idempotency_key": "new-key-123"})
        )


def test_budget_and_base_units_cannot_share_one_request():
    with pytest.raises(ValueError, match="either"):
        order_request(quantity=2, quote_budget=5, limit_price=None, order_type="market")
    with pytest.raises(ValueError, match="only to a market buy"):
        order_request(quantity=None, quote_budget=5, limit_price=None, order_type="market", side="sell")


def test_valid_native_acknowledgment_tracks_budget_without_invented_fills(venue, monkeypatch):
    name, owner, account, adapter = venue
    native = adapter._exchange
    review = owner.trading.preview(market_request(account, "buy", 2))
    client_id = review["client_order_id"]
    path, expected = placement(name, "buy", client_id)
    _, _, _, native_id = recovered_row(name, "buy", client_id)
    if name == "poloniex":
        acknowledgment = {"id": native_id, "clientOrderId": client_id}
    elif name == "upbit":
        acknowledgment = {**expected, "uuid": native_id}
    else:
        acknowledgment = response({"orderId": native_id, "clientOid": client_id})

    def place(params):
        assert params == expected
        return acknowledgment

    monkeypatch.setattr(native, path, place)
    result = owner.trading.execute(review["id"], review["confirmation"])
    assert result["status"] == "submitted" and result["exchange_order_id"] == native_id
    assert result["request"]["quote_budget"] == 2 and result.get("filled") is None


def test_native_budget_limits_are_checked_before_review(venue):
    _, owner, account, _ = venue
    with pytest.raises(ValueError, match="market limits"):
        owner.trading.preview(market_request(account, "buy", 1001))


@pytest.mark.parametrize(
    ("fill_cost", "native_cost", "expected_status"),
    [(None, None, "unverified"), (None, 1, "matched"), (1, None, "matched"), (3, None, "mismatch")],
)
def test_budget_reconciliation_requires_reported_execution_cost(fill_cost, native_cost, expected_status):
    intent = {
        "request": {"quote_budget": 2, "side": "buy"},
        "filled": 3,
        "cost": native_cost,
        "status": "closed",
        "environment": "live",
        "exchange": "poloniex",
    }
    fill = {
        "quantity": 3,
        "notional": fill_cost,
        "side": "buy",
        "environment": "live",
        "exchange": "poloniex",
        "fees_known": True,
        "fees": [],
    }
    assert summarize(intent, [fill], None)["status"] == expected_status


@pytest.mark.parametrize("name", ["gate", "htx", "bitmart"])
@pytest.mark.parametrize("fault", [None, "budget mismatch", "cost exceeds budget"])
def test_additional_venue_buys_recover_exact_budget_and_native_fills(request, monkeypatch, name, fault):
    owner, account, adapter = request.getfixturevalue(
        {"gate": "gate", "htx": "htx", "bitmart": "market_account"}[name]
    )
    native = adapter._exchange
    budget = Decimal("1250.25")
    terms = order_request(
        account, side="buy", order_type="market", limit_price=None, quantity=None, quote_budget=float(budget)
    )
    _enable_budget_rules(native, monkeypatch, name)
    confirmed_id = str(2**60 + 17)
    writes = []

    if name == "gate":
        submit_path = "privateSpotPostOrders"
        details_path = "privateSpotGetOrdersOrderId"
        expected = {
            "currency_pair": "BTC_USDT",
            "account": "spot",
            "type": "market",
            "side": "buy",
            "amount": str(budget),
            "time_in_force": "ioc",
        }
        client_field = "text"
    elif name == "htx":
        submit_path = "spotPrivatePostV1OrderOrdersPlace"
        details_path = "spotPrivateGetV1OrderOrdersGetClientOrder"
        expected = {
            "account-id": "1234",
            "symbol": "btcusdt",
            "type": "buy-market",
            "source": "spot-api",
            "amount": str(budget),
        }
        client_field = "client-order-id"
    else:
        submit_path = "privatePostSpotV2SubmitOrder"
        details_path = "privatePostSpotV4QueryClientOrder"
        expected = {"symbol": "BTC_USDT", "side": "buy", "type": "market", "notional": str(budget)}
        client_field = "client_order_id"

    def timeout(payload):
        writes.append(payload.copy())
        raise ccxt.RequestTimeout("Order response timed out")

    monkeypatch.setattr(native, submit_path, timeout)

    review = owner.trading.preview(terms)
    client_id = review["client_order_id"]
    assert owner.trading.execute(review["id"], review["confirmation"])["status"] == "unknown"
    assert writes == [{**expected, client_field: client_id}]

    original = str(budget + 1 if fault == "budget mismatch" else budget)
    cost = str(budget + 1 if fault == "cost exceeds budget" else Decimal("1150"))
    if name == "gate":
        row = gate_sell(
            id=confirmed_id,
            text=client_id,
            side="buy",
            amount=original,
            filled_amount="0.023",
            filled_total=cost,
            left="100.25",
        )
    elif name == "htx":
        row = htx_response(
            htx_sell(
                id=confirmed_id,
                **{
                    "client-order-id": client_id,
                    "type": "buy-market",
                    "amount": original,
                    "field-amount": "0.023",
                    "field-cash-amount": cost,
                },
            )
        )
    else:
        row = bitmart_response(
            bitmart_market(
                orderId=confirmed_id,
                side="buy",
                clientOrderId=client_id,
                notional=original,
                size="",
                filledSize="0.023",
                filledNotional=cost,
            )
        )
    monkeypatch.setattr(native, details_path, lambda _: row)
    owner.settings.allow_live_trading = False
    restored = ExchangeTrading(owner.market, owner.store).recover(review["id"])
    if fault:
        assert restored["status"] == "unknown" and not restored.get("exchange_order_id")
    else:
        assert restored["recovery"]["state"] == "found"
        assert restored["exchange_order_id"] == confirmed_id and restored["status"] == "canceled"
        assert restored["request"]["quantity"] is None and restored["request"]["quote_budget"] == float(
            budget
        )
        assert restored["filled"] == 0.023 and restored["cost"] == 1150
    assert len(writes) == 1


def _enable_budget_rules(native, monkeypatch, name):
    """Provide valid native rules for each quote-sized fixture."""
    if name == "gate":
        monkeypatch.setattr(
            native,
            "publicSpotGetCurrencyPairsCurrencyPair",
            lambda _: gate_rules(trade_status="buyable", market_order_max_money="1300"),
        )
    elif name == "htx":
        monkeypatch.setattr(
            native,
            "spotPublicGetV1SettingsCommonMarketSymbols",
            lambda _: htx_rules(vp=2, minov="1", bmmaxov="1300"),
        )
    else:
        monkeypatch.setattr(native, "publicGetSpotV1SymbolsDetails", lambda _: bitmart_rules())


@pytest.mark.parametrize(
    ("name", "budget", "message"),
    [
        ("gate", 1301, "maximum quote"),
        ("htx", 1250.251, "value precision"),
        ("bitmart", 999, "minimum quote"),
    ],
)
def test_additional_venue_budget_review_rejects_native_limit_violations(
    request, monkeypatch, name, budget, message
):
    owner, account, adapter = request.getfixturevalue(
        {"gate": "gate", "htx": "htx", "bitmart": "market_account"}[name]
    )
    _enable_budget_rules(adapter._exchange, monkeypatch, name)
    terms = order_request(
        account, side="buy", order_type="market", limit_price=None, quantity=None, quote_budget=budget
    )
    with pytest.raises(ValueError, match=message):
        owner.trading.preview(terms)
