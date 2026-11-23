"""Capture real SDK request generation; no credentials, network calls or orders."""

from copy import deepcopy
from decimal import Decimal

import ccxt
import pytest

from sibyl.exchanges import create_client
from sibyl.exchanges.catalog import CATALOG
from sibyl.exchanges.registry import provider_catalog


class Captured(Exception):
    """Abort at the transport boundary after inspecting native request parameters."""


MARKET = {
    "id": "BTCUSDT",
    "symbol": "BTC/USDT",
    "base": "BTC",
    "quote": "USDT",
    "baseId": "BTC",
    "quoteId": "USDT",
    "spot": True,
    "type": "spot",
    "active": True,
    "contract": False,
    "swap": False,
    "future": False,
    "option": False,
    "linear": False,
    "inverse": False,
    "precision": {"amount": 0.00000001, "price": 0.01},
    "limits": {},
    "info": {"orderTypes": ["MARKET", "LIMIT"]},
}
NEW_MARKET = ["binanceus", "okx", "bybit", "kucoin", "bitstamp"]
NEW_LIMIT = [*NEW_MARKET, "gemini"]
ADDITIONAL_LIMIT = [
    "gate",
    "bitget",
    "mexc",
    "htx",
    "cryptocom",
    "bitfinex",
    "coinex",
    "bitmart",
    "phemex",
    "poloniex",
    "upbit",
]


@pytest.fixture
def native_client(monkeypatch):
    clients = []

    def make(identity):
        client = create_client(
            identity,
            credentials={
                "apiKey": "test-key",
                "secret": "test-secret",
                **({"password": "test-pass"} if CATALOG[identity].passphrase else {}),
                **({"uid": "test-memo"} if CATALOG[identity].uid else {}),
            },
        )
        clients.append(client)
        market = deepcopy(MARKET)
        market["id"] = {
            "okx": "BTC-USDT",
            "kucoin": "BTC-USDT",
            "bitstamp": "btcusdt",
            "gemini": "btcusdt",
            "gate": "BTC_USDT",
            "bitmart": "BTC_USDT",
            "poloniex": "BTC_USDT",
            "htx": "btcusdt",
            "cryptocom": "BTC_USDT",
            "bitfinex": "tBTCUST",
            "phemex": "sBTCUSDT",
            "upbit": "USDT-BTC",
        }.get(identity, "BTCUSDT")
        if identity == "bitfinex":
            market["precision"] = {"amount": 8, "price": 5}  # Native significant-digit precision.
        if identity == "phemex":
            market.update(valueScale=8, priceScale=4, ratioScale=8)
        client._exchange.set_markets([market])
        if identity == "htx":
            client._exchange.accounts = [
                {"id": "1234", "type": "spot"},
                {"id": "unrelated-margin", "type": "margin"},
            ]
        requests = []

        def capture(path, api="public", method="GET", params=None, *args, **kwargs):
            requests.append({"path": path, "api": api, "method": method, "params": params})
            raise Captured

        monkeypatch.setattr(client._exchange, "fetch2", capture)
        return client, requests

    yield make
    for client in clients:
        client.close()


@pytest.mark.parametrize("identity", NEW_MARKET)
@pytest.mark.parametrize("side", ["buy", "sell"])
def test_market_request_preserves_base_quantity_and_native_id(native_client, identity, side):
    client, requests = native_client(identity)
    identity_value = client.format_client_order_id("135d8630-4dcc-4bfe-8918-41555302a029")
    with pytest.raises(Captured):
        client.create_order("BTC/USDT", "market", side, 0.001, {"clientOrderId": identity_value})
    assert len(requests) == 1
    request = requests[0]
    assert request["method"] == "POST"
    params = request["params"]
    size, id_field = {
        "binanceus": ("quantity", "newClientOrderId"),
        "okx": ("sz", "clOrdId"),
        "bybit": ("qty", "orderLinkId"),
        "kucoin": ("size", "clientOid"),
        "bitstamp": ("amount", "client_order_id"),
    }[identity]
    if identity == "okx":
        params = params[0]
        assert params["tdMode"] == "cash"
        assert params["tgtCcy"] == "base_ccy"
        assert identity_value.isalnum() and len(identity_value) == 32
    if identity == "bybit":
        assert params["marketUnit"] == "baseCoin"
        assert params["category"] == "spot" and params["isLeverage"] == 0
    assert params[size] == "0.001"
    assert params[id_field] == identity_value
    assert not any(key in params for key in ["quoteOrderQty", "funds", "cost"])


@pytest.mark.parametrize("identity", NEW_LIMIT)
@pytest.mark.parametrize("side", ["buy", "sell"])
def test_gtc_limit_request_preserves_quantity_price_id(native_client, identity, side):
    client, requests = native_client(identity)
    identity_value = client.format_client_order_id("135d8630-4dcc-4bfe-8918-41555302a029")
    with pytest.raises(Captured):
        client.create_order("BTC/USDT", "limit", side, 0.001, {"clientOrderId": identity_value}, price=50000)
    assert len(requests) == 1
    params = requests[0]["params"]
    if identity == "okx":
        params = params[0]
        assert params["tdMode"] == "cash" and params["ordType"] == "limit"
    size, price, id_field = {
        "binanceus": ("quantity", "price", "newClientOrderId"),
        "okx": ("sz", "px", "clOrdId"),
        "bybit": ("qty", "price", "orderLinkId"),
        "kucoin": ("size", "price", "clientOid"),
        "bitstamp": ("amount", "price", "client_order_id"),
        "gemini": ("amount", "price", "client_order_id"),
    }[identity]
    assert params[size] == "0.001" and params[price] == "50000"
    assert params[id_field] == identity_value
    assert params.get("timeInForce", "GTC") == "GTC"
    if identity == "gemini":
        assert params["type"] == "exchange limit"
        assert not params.get("options")


@pytest.mark.parametrize("identity", NEW_LIMIT)
def test_cancellation_uses_only_known_order_and_spot_symbol(native_client, identity):
    client, requests = native_client(identity)
    with pytest.raises(Captured):
        client.cancel_order("123456", "BTC/USDT")
    assert len(requests) == 1
    assert requests[0]["method"] in {"POST", "DELETE"}
    assert "123456" in str(requests[0]["params"])


def test_gemini_market_remains_disabled(native_client):
    client, requests = native_client("gemini")
    with pytest.raises(ccxt.NotSupported):
        client.create_order("BTC/USDT", "market", "buy", 1, {"clientOrderId": "test"})
    assert not requests


def test_support_matrix_is_app_scoped_and_lists_gaps():
    catalog = provider_catalog()
    assert "locally and encrypted" in catalog["key_storage"]
    for provider in catalog["items"]:
        assert len(provider["support"]) == 5
        features = {f["id"]: f for group in provider["support"] for f in group["features"]}
        assert features["automated"]["status"] == (
            "available"
            if provider["id"]
            in {
                "binance",
                "binanceus",
                "binance-testnet",
                "coinbase",
                "coinbase-sandbox",
                "kraken",
                "okx",
                "bybit",
                "kucoin",
            }
            else "pending"
        )
        assert features["withdrawals"]["status"] == "unavailable"
        assert (
            features["limit_orders"]["status"] in {"available", "simulated"}
            if provider["limit_orders"]
            else features["limit_orders"]["status"] == "pending"
        )
        if provider["id"] == "okx":
            assert features["market_orders"]["status"] == "available"
            assert features["history_import"]["status"] == "available"
            assert features["fill_reconciliation"]["status"] == "available"
        if provider["id"] == "upbit":
            assert features["trade_history"]["status"] == "unavailable"
        if provider["id"] == "gemini":
            assert features["market_orders"]["status"] == "unavailable"


@pytest.mark.parametrize("identity", NEW_LIMIT)
def test_known_order_status_reaches_native_read(native_client, identity):
    client, requests = native_client(identity)
    with pytest.raises(Captured):
        client.fetch_order("123456", "BTC/USDT")
    assert len(requests) == 1
    assert "123456" in str(requests[0]["params"])
    assert not any(word in requests[0]["path"].lower() for word in ["create", "cancel"])


def test_okx_preview_persists_native_id_before_ambiguous_submission(
    settings, store, native_client, monkeypatch
):
    from sibyl.models import ConnectionCreate, ExchangeOrderRequest
    from sibyl.services.markets.service import Market
    from sibyl.services.trading.service import ExchangeTrading

    settings.allow_live_trading = True
    connection = store.add_connection(
        ConnectionCreate(exchange="okx", label="test", api_key="test", secret="test", passphrase="test")
    )
    client, requests = native_client("okx")
    monkeypatch.setattr(client, "fetch_ticker", lambda symbol: {"ask": 50000})
    monkeypatch.setattr(client, "fetch_balance", lambda: {"free": {"USDT": 100000}})
    market = Market(settings, store)
    market._clients[connection.id] = client
    service = ExchangeTrading(market, store)
    intent = service.preview(
        ExchangeOrderRequest(
            connection_id=connection.id, side="buy", quantity=0.001, idempotency_key="okx-preview"
        )
    )
    assert intent["client_order_id"].isalnum() and len(intent["client_order_id"]) == 32
    observed = []

    def timeout(request):
        observed.append(request)
        raise ccxt.RequestTimeout("ambiguous")

    monkeypatch.setattr(client._exchange, "privatePostTradeBatchOrders", timeout)
    result = service.execute(intent["id"], intent["confirmation"])
    assert result["status"] == "unknown"
    assert observed[0][0]["clOrdId"] == intent["client_order_id"]
    service.execute(intent["id"], intent["confirmation"])
    assert len(observed) == 1


@pytest.mark.parametrize("identity", ADDITIONAL_LIMIT)
@pytest.mark.parametrize("side", ["buy", "sell"])
def test_additional_native_limits_preserve_spot_quantity_price_and_the_saved_client_id(
    native_client, identity, side
):
    client, requests = native_client(identity)
    cid = client.format_client_order_id("135d8630-4dcc-4bfe-8918-41555302a029")
    with pytest.raises(Captured):
        client.create_order("BTC/USDT", "limit", side, 0.001, {"clientOrderId": cid}, price=50000)
    assert len(requests) == 1
    request, params = requests[0], requests[0]["params"]
    assert request["method"] == "POST"
    quantity, price, identity_field = {
        "gate": ("amount", "price", "text"),
        "bitget": ("size", "price", "clientOid"),
        "mexc": ("quantity", "price", "newClientOrderId"),
        "htx": ("amount", "price", "client-order-id"),
        "cryptocom": ("quantity", "price", "client_oid"),
        "bitfinex": ("amount", "price", "cid"),
        "coinex": ("amount", "price", "client_id"),
        "bitmart": ("size", "price", "client_order_id"),
        "phemex": ("baseQtyEv", "priceEp", "clOrdID"),
        "poloniex": ("quantity", "price", "clientOrderId"),
        "upbit": ("volume", "price", "identifier"),
    }[identity]
    expected_quantity = Decimal("-0.001") if identity == "bitfinex" and side == "sell" else Decimal("0.001")
    if identity == "phemex":
        assert Decimal(str(params[quantity])) == expected_quantity * 100_000_000
        assert Decimal(str(params[price])) == 50000 * 10000
        assert params["qtyType"] == "ByBase" and params["timeInForce"] == "GoodTillCancel"
        assert "quoteQtyEv" not in params
    else:
        assert Decimal(str(params[quantity])) == expected_quantity
        assert Decimal(str(params[price])) == 50000
    assert str(params[identity_field]) == cid
    if identity == "gate":
        assert cid.startswith("t-") and len(cid) <= 28
        assert params["account"] == "spot" and params["time_in_force"] == "gtc"
    elif identity == "bitget":
        assert request["path"] == "v2/spot/trade/place-order"
        assert params["force"] == "gtc" and "timeInForce" not in params
    elif identity == "cryptocom":
        assert params["time_in_force"] == "GOOD_TILL_CANCEL" and params["spot_margin"] == "SPOT"
    elif identity == "bitfinex":
        assert isinstance(params["cid"], int) and 0 < params["cid"] < 2**45
        assert params["type"] == "EXCHANGE LIMIT" and "lev" not in params
    elif identity == "coinex":
        assert params["market_type"] == "SPOT" and "clientOrderId" not in params
    elif identity == "htx":
        assert params["account-id"] == "1234" and params["source"] == "spot-api"
        assert params["type"] == side + "-limit"
    elif identity == "poloniex":
        assert params["timeInForce"] == "GTC" and not params.get("allowBorrow", False)
    elif identity == "upbit":
        assert params["ord_type"] == "limit" and "time_in_force" not in params
    assert not any(key in params for key in ("quoteOrderQty", "notional", "funds", "cost", "reduceOnly"))


@pytest.mark.parametrize("identity", ADDITIONAL_LIMIT)
def test_additional_native_limit_cancellation_is_one_known_order_request(native_client, identity):
    client, requests = native_client(identity)
    with pytest.raises(Captured):
        client.cancel_order("123456", "BTC/USDT")
    assert len(requests) == 1
    assert requests[0]["method"] in {"POST", "DELETE"}
    assert "123456" in str(requests[0]["params"])


def test_htx_does_not_fall_back_to_an_unrelated_wallet(native_client):
    client, requests = native_client("htx")
    client._exchange.accounts = [{"id": "margin-only", "type": "margin"}]
    with pytest.raises(ValueError, match="unambiguous spot"):
        client.create_order("BTC/USDT", "limit", "buy", 0.001, {"clientOrderId": "safe-id"}, price=50000)
    with pytest.raises(ValueError, match="unambiguous spot"):
        client.fetch_balance()
    assert requests == []
