"""A demo account follows normal connection APIs while keeping simulated money isolated."""

import pytest
from pydantic import ValidationError

from sibyl.config import Settings
from sibyl.exchanges import create_client
from sibyl.models import ConnectionCreate, ExchangeOrderRequest
from sibyl.services.market import Market
from sibyl.services.portfolio import Portfolio
from sibyl.services.trading import ExchangeTrading
from sibyl.storage import Store


def test_default_demo_is_persisted_once_without_credentials(store, settings):
    demo = store.connections()[0]
    assert demo.id == demo.exchange == "demo"
    assert demo.label == "Demo account"
    assert not demo.sandbox
    assert store.credentials(demo.id) == {}
    assert [item.model_dump() for item in Store(settings.data_dir).connections()] == [demo.model_dump()]
    existing = store.add_connection(ConnectionCreate(exchange="demo", label="Duplicate"))
    assert existing.id == demo.id
    assert len(store.connections()) == 1


def test_demo_uses_the_same_account_and_portfolio_api_without_a_vault_read(client, monkeypatch):
    service = client.app.state.services
    monkeypatch.setattr(
        service.store, "credentials", lambda _: pytest.fail("Demo must not decrypt credentials")
    )
    demo = next(item for item in client.get("/api/v1/connections").json() if item["exchange"] == "demo")
    balances = client.get(f"/api/v1/connections/{demo['id']}/balances").json()
    assert balances["source"] == "demo"
    assert balances["items"]
    overview = client.get("/api/v1/portfolio").json()
    accounts = client.get("/api/v1/portfolio/accounts").json()["accounts"]
    assert len(accounts) == 1
    assert accounts[0]["id"] == overview["venues"][0]["id"] == demo["id"]
    assert accounts[0]["name"] == demo["label"]
    assert accounts[0]["exchange"] == "demo"
    assert accounts[0]["status"] == overview["venues"][0]["status"] == "simulated"
    assert accounts[0]["total"] == pytest.approx(overview["total"])
    assert {item["asset"]: item["total"] for item in balances["items"]} == service.store.balances()
    check = client.post(f"/api/v1/connections/{demo['id']}/check").json()
    assert check["status"] == "connected"
    assert check["assets"] == len(balances["items"])
    assert client.get(f"/api/v1/connections/{demo['id']}/open-orders").json()["items"] == []


def test_paper_fill_updates_all_account_reads_and_survives_reconnection(client):
    store = client.app.state.services.store
    demo = next(item for item in client.get("/api/v1/connections").json() if item["exchange"] == "demo")
    route = f"/api/v1/connections/{demo['id']}/balances"
    before = {item["asset"]: item["total"] for item in client.get(route).json()["items"]}
    result = client.post(
        "/api/v1/orders",
        json={"symbol": "BTC/USDT", "side": "buy", "quantity": 0.001, "idempotency_key": "demo-account-flow"},
    )
    assert result.status_code == 201
    after = {item["asset"]: item["total"] for item in client.get(route).json()["items"]}
    assert after["BTC"] == pytest.approx(before["BTC"] + 0.001)
    assert after["USDT"] < before["USDT"]
    trades = client.get(f"/api/v1/connections/{demo['id']}/trades").json()["items"]
    assert trades[0]["id"] == result.json()["id"]
    assert client.delete(f"/api/v1/connections/{demo['id']}").status_code == 204
    assert client.get("/api/v1/portfolio").json()["total"] == 0
    assert client.get("/api/v1/portfolio/accounts").json()["accounts"] == []
    assert client.get(route).status_code == 404
    assert Store(store.path.parent).connections() == []  # Restart does not resurrect a disconnect.
    assert store.balances() == after
    restored = client.post("/api/v1/connections", json={"exchange": "demo", "label": "My demo wallet"})
    assert restored.status_code == 201
    assert restored.json()["id"] == demo["id"]
    assert client.get("/api/v1/portfolio/accounts").json()["accounts"][0]["name"] == "My demo wallet"
    assert {item["asset"]: item["total"] for item in client.get(route).json()["items"]} == after
    assert len(store.orders()) == 1


def test_live_portfolio_does_not_include_demo_and_demo_does_not_contact_real_accounts(
    settings, store, monkeypatch
):
    real = store.add_connection(
        ConnectionCreate(exchange="kraken", label="Real", api_key="key", secret="secret")
    )
    market = Market(settings, store)
    portfolio = Portfolio(market, store)
    observed = []

    def balance(connection):
        observed.append(connection.exchange)
        return {"BTC": 2} if connection.exchange == "kraken" else store.balances()

    monkeypatch.setattr(market, "balance", balance)
    monkeypatch.setattr(
        market, "overview", lambda: {"items": [{"asset": "BTC", "price": 100, "change": 0, "sparkline": []}]}
    )
    assert [item.exchange for item in portfolio.connections()] == ["demo"]
    portfolio.overview()
    assert observed == ["demo"]
    settings.mode = "live"
    assert [item.id for item in portfolio.connections()] == [real.id]
    live = portfolio.overview()
    assert live["total"] == 200
    assert observed == ["demo", "kraken"]
    assert all(venue["exchange"] != "demo" for venue in live["venues"])
    monkeypatch.setattr(
        market, "account_balances", lambda connection: [{"asset": "BTC", "total": 2, "free": 2, "used": 0}]
    )
    assert [account["exchange"] for account in portfolio.accounts()["accounts"]] == ["kraken"]


@pytest.mark.parametrize(
    "extra",
    [
        {"api_key": "secret"},
        {"secret": "secret"},
        {"passphrase": "secret"},
        {"uid": "secret"},
        {"sandbox": True},
    ],
)
def test_demo_rejects_real_credentials_and_sandbox(extra):
    with pytest.raises(ValidationError, match="Demo accounts"):
        ConnectionCreate(exchange="demo", label="Demo", **extra)
    with pytest.raises(ValidationError):
        Settings(market_exchange="demo", _env_file=None)


def test_real_accounts_still_require_secrets():
    with pytest.raises(ValidationError, match="API key and secret"):
        ConnectionCreate(exchange="binance", label="missing")


def test_demo_never_enters_live_order_flow(settings, store):
    settings.allow_live_trading = True
    trading = ExchangeTrading(Market(settings, store), store)
    with pytest.raises(ValueError, match="paper orders"):
        trading.preview(
            ExchangeOrderRequest(
                connection_id="demo", side="buy", quantity=0.01, idempotency_key="reject-demo-live"
            )
        )
    assert trading.list_orders() == []
    client = create_client("demo", store=store)
    assert client.fetch_balance()["total"] == store.balances()
