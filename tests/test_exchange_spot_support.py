"""Capture real SDK request generation; no credentials, network calls or orders."""

from copy import deepcopy

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
            },
        )
        clients.append(client)
        market = deepcopy(MARKET)
        market["id"] = {
            "okx": "BTC-USDT",
            "kucoin": "BTC-USDT",
            "bitstamp": "btcusdt",
            "gemini": "btcusdt",
        }.get(identity, "BTCUSDT")
        client._exchange.set_markets([market])
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
        assert features["automated"]["status"] == "pending"
        assert features["withdrawals"]["status"] == "unavailable"
        assert (
            features["limit_orders"]["status"] in {"available", "simulated"}
            if provider["limit_orders"]
            else features["limit_orders"]["status"] == "pending"
        )
        if provider["id"] == "okx":
            assert features["market_orders"]["status"] == "available"
            assert features["history_import"]["status"] == "pending"
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
    from sibyl.services.market import Market
    from sibyl.services.trading import ExchangeTrading

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
