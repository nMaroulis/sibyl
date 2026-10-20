"""Dedicated test clients cannot select production routing or inflate real portfolio totals."""

from urllib.parse import urlparse

import pytest
from pydantic import ValidationError

from sibyl.config import Settings
from sibyl.exchanges import create_client
from sibyl.exchanges.catalog import TEST_ENVIRONMENTS
from sibyl.models import ConnectionCreate
from sibyl.services.market import Market
from sibyl.services.portfolio import Portfolio


@pytest.mark.parametrize("spec", TEST_ENVIRONMENTS, ids=lambda spec: spec.id)
def test_test_environment_is_forced_before_any_market_or_private_request(spec, store):
    request = ConnectionCreate(
        exchange=spec.id,
        label=spec.name,
        api_key="test-key",
        secret="test-secret",
        passphrase="test-passphrase" if spec.passphrase else "",
        sandbox=False,
    )
    assert request.sandbox is True
    connection = store.add_connection(request)
    assert connection.sandbox is True
    client = create_client(spec.id, credentials=store.credentials(connection.id), sandbox=False)
    # Inspect actual installed CCXT routing, without making any network request.
    for url in client._exchange.urls["api"].values():
        host = urlparse(url).hostname
        assert "testnet" in host or ".sandbox." in host
        assert host not in {"api.binance.com", "api.coinbase.com", "api.exchange.coinbase.com"}
    client.close()


def test_coinbase_sandbox_requires_exchange_passphrase_and_rejects_cdp_only_credentials():
    with pytest.raises(ValidationError, match="passphrase"):
        ConnectionCreate(exchange="coinbase-sandbox", label="missing", api_key="key", secret="secret")
    # Test-only identifiers are not eligible production reference exchanges.
    with pytest.raises(ValidationError):
        Settings(market_exchange="coinbase-sandbox", _env_file=None)


@pytest.mark.parametrize("identity", ["binance-testnet", "coinbase-sandbox"])
def test_sdk_market_request_keeps_base_size_and_id_without_transport(monkeypatch, identity):
    spec = next(item for item in TEST_ENVIRONMENTS if item.id == identity)
    client = create_client(
        identity,
        credentials={
            "apiKey": "test-key",
            "secret": "test-secret",
            **({"password": "test-passphrase"} if spec.passphrase else {}),
        },
    )
    raw = client._exchange
    symbol = "BTC/USD" if identity == "coinbase-sandbox" else "BTC/USDT"
    quote = symbol.split("/")[1]
    raw.set_markets(
        [
            {
                "id": "BTC-USD" if quote == "USD" else "BTCUSDT",
                "symbol": symbol,
                "base": "BTC",
                "quote": quote,
                "baseId": "BTC",
                "quoteId": quote,
                "spot": True,
                "type": "spot",
                "active": True,
                "contract": False,
                "linear": False,
                "inverse": False,
                "precision": {"amount": 0.00000001, "price": 0.01},
                "limits": {},
                "info": {"orderTypes": ["MARKET", "LIMIT"]},
            }
        ]
    )
    observed = []

    def submit(params):
        observed.append(params)
        return {"id": "test-order", "orderId": "test-order", "status": "open", "product_id": "BTC-USD"}

    if identity == "coinbase-sandbox":
        monkeypatch.setattr(raw, "privatePostOrders", submit)
    else:
        monkeypatch.setattr(raw, "privatePostOrder", submit)
    identifier = "2622afee-5c43-4e7e-b79f-0c4ed993f815"
    client.create_order(symbol, "market", "buy", 0.01, {"clientOrderId": identifier})
    assert len(observed) == 1
    request = observed[0]
    assert request.get("size", request.get("quantity")) == "0.01"
    assert request.get("client_oid", request.get("newClientOrderId")) == identifier
    assert "funds" not in request and "quoteOrderQty" not in request
    client.close()


def test_test_accounts_have_normal_apis_but_are_separate_from_real_totals(client, monkeypatch):
    payload = {
        "exchange": "coinbase-sandbox",
        "label": "Test funds",
        "api_key": "TEST-KEY-SENTINEL",
        "secret": "TEST-SECRET-SENTINEL",
        "passphrase": "TEST-PASS-SENTINEL",
        "sandbox": False,
    }
    saved = client.post("/api/v1/connections", json=payload)
    assert saved.status_code == 201
    account = saved.json()
    assert account["sandbox"] is True
    assert "SENTINEL" not in saved.text
    market = client.app.state.services.market
    portfolio = client.app.state.services.portfolio
    monkeypatch.setattr(
        market, "account_balances", lambda connection: [{"asset": "BTC", "total": 1, "free": 1, "used": 0}]
    )
    rows = client.get("/api/v1/portfolio/accounts").json()["accounts"]
    test = next(row for row in rows if row["id"] == account["id"])
    assert test["sandbox"] is True
    assert test["exchange"] == "coinbase-sandbox"
    assert all(connection.id != account["id"] for connection in portfolio.connections())
    market.settings.mode = "live"
    monkeypatch.setattr(market, "overview", lambda: {"items": []})
    assert portfolio.overview()["total"] == 0
    assert portfolio.overview()["venues"] == []
    assert any(row["sandbox"] for row in portfolio.accounts()["accounts"])


def test_existing_binance_sandbox_is_excluded_from_real_totals(settings, store):
    store.add_connection(
        ConnectionCreate(
            exchange="binance", label="Legacy testnet", api_key="key", secret="secret", sandbox=True
        )
    )
    real = store.add_connection(
        ConnectionCreate(exchange="kraken", label="Production", api_key="key", secret="secret")
    )
    settings.mode = "live"
    portfolio = Portfolio(Market(settings, store), store)
    assert [connection.id for connection in portfolio.connections()] == [real.id]
