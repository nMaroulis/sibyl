"""Explicit activation, multi-exchange views, and isolated Demo/test funds."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from sibyl.api.app import create_app
from sibyl.config import Settings
from sibyl.models import ConnectionCreate, OrderRequest
from sibyl.services.accounts import Accounts
from sibyl.storage import Store


def connect(client, exchange="binance", label="Main"):
    response = client.post(
        "/api/v1/connections",
        json={
            "exchange": exchange,
            "label": label,
            "api_key": "TEST-KEY",
            "secret": "TEST-SECRET",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_fresh_workspace_has_no_connections_or_implicit_demo(tmp_path):
    settings = Settings(data_dir=tmp_path, _env_file=None)
    store = Store(tmp_path)
    store.save_data_profile("market", {"source": "demo", "profiles": {}})
    assert store.connections() == []
    assert Accounts(store).public()["mode"] == "none"
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/connections").json() == []
        assert client.get("/api/v1/accounts").json()["active_ids"] == []
        assert client.get("/api/v1/system").json()["accounts"]["mode"] == "none"
        portfolio = client.get("/api/v1/portfolio").json()
        assert not portfolio["active"] and portfolio["history"] == []
        assert client.get("/api/v1/portfolio/accounts").json()["accounts"] == []
        assert client.get("/api/v1/paper/balances").status_code == 400
        assert (
            client.post(
                "/api/v1/orders/preview",
                json={
                    "symbol": "BTC/USDT",
                    "side": "buy",
                    "quantity": 0.001,
                    "idempotency_key": "no-demo-account",
                },
            ).status_code
            == 400
        )
        assert client.get("/api/v1/markets/symbols").status_code == 200  # Public tools remain independent.
        assert client.post("/api/v1/accounts/demo").json()["mode"] == "demo"
        assert client.get("/api/v1/paper/balances").status_code == 200
    assert Accounts(Store(tmp_path)).public()["mode"] == "demo"


def test_real_activation_disables_demo_and_last_deactivation_stays_empty(client):
    assert client.get("/api/v1/accounts").json()["mode"] == "demo"
    first = connect(client)
    state = client.get("/api/v1/accounts").json()
    assert state["active_ids"] == [first["id"]]
    assert state["mode"] == "live"
    assert not state["demo_available"]
    assert not next(row for row in state["accounts"] if row["exchange"] == "demo")["active"]
    assert client.post("/api/v1/accounts/demo").status_code == 400
    assert client.post("/api/v1/connections/demo/activation", json={"active": True}).status_code == 400
    assert client.get("/api/v1/paper/balances").status_code == 400
    result = client.post(f"/api/v1/connections/{first['id']}/activation", json={"active": False})
    assert result.json()["mode"] == "none"
    assert client.app.state.services.store.credentials(first["id"])["apiKey"] == "TEST-KEY"
    assert client.post("/api/v1/accounts/demo").json()["mode"] == "demo"


def test_combined_exchange_and_account_scopes_sum_the_same_native_balances(client, monkeypatch):
    first, second, third = (
        connect(client, label="Binance 1"),
        connect(client, label="Binance 2"),
        connect(client, "kraken", "Kraken"),
    )
    market = client.app.state.services.market
    quantities = {
        first["id"]: {"BTC": 1, "USDT": 10},
        second["id"]: {"BTC": 2, "USDT": 20},
        third["id"]: {"BTC": 3, "USDT": 30},
    }
    calls = []

    def balance(connection):
        calls.append(connection.id)
        return quantities[connection.id]

    monkeypatch.setattr(market, "balance", balance)
    monkeypatch.setattr(
        market, "symbols", lambda: {"items": [{"symbol": "BTC/USDT", "base": "BTC", "quote": "USDT"}]}
    )
    monkeypatch.setattr(market, "valuation_ticker", lambda symbol: {"price": 100, "change": 1})
    monkeypatch.setattr(market, "candles", lambda *args: [])
    combined = client.get("/api/v1/portfolio").json()
    assert combined["total"] == 660
    assert combined["mode"] == "live"
    assert len(next(row for row in combined["holdings"] if row["asset"] == "BTC")["accounts"]) == 3
    assert sum(row["total"] for row in combined["venues"]) == 660
    assert all(row["exchange"] != "demo" for row in combined["venues"])
    exchange = client.get("/api/v1/portfolio?scope=exchange:binance").json()
    assert exchange["total"] == 330
    assert {row["id"] for row in exchange["venues"]} == {first["id"], second["id"]}
    single = client.get(f"/api/v1/portfolio?scope=account:{third['id']}").json()
    assert single["total"] == 330 and len(single["venues"]) == 1
    state = client.get("/api/v1/accounts").json()
    assert next(row for row in state["scopes"] if row["id"] == "exchange:binance")["count"] == 2
    client.post(f"/api/v1/connections/{second['id']}/activation", json={"active": False})
    calls.clear()
    assert client.get("/api/v1/portfolio").json()["total"] == 440
    assert second["id"] not in calls
    calls.clear()
    assert client.get(f"/api/v1/portfolio?scope=account:{second['id']}").status_code == 400
    assert not calls


def test_no_active_accounts_do_not_resolve_even_an_unavailable_feed(client, monkeypatch):
    services = client.app.state.services
    client.post("/api/v1/connections/demo/activation", json={"active": False})
    monkeypatch.setattr(
        services.market, "snapshot", lambda *args: pytest.fail("Inactive workspace requested market data")
    )
    assert client.get("/api/v1/portfolio").json()["mode"] == "none"
    assert client.get("/api/v1/portfolio/accounts").json()["accounts"] == []
    with services.store.db() as db:
        assert db.execute("SELECT count(*) FROM source_snapshots").fetchone()[0] == 0


def test_sandbox_never_joins_production_totals_and_has_an_explicit_scope(client):
    sandbox = connect(client, "binance-testnet", "Test")
    state = client.get("/api/v1/accounts").json()
    assert state["mode"] == "test"
    real = connect(client)
    selection = client.app.state.services.accounts
    assert [row.id for row in selection.resolve()] == [real["id"]]
    assert selection.mode(selection.resolve(f"account:{sandbox['id']}")) == "test"
    assert any(row["sandbox"] for row in selection.public()["scopes"] if row["kind"] == "account")


def test_selection_survives_restart_without_reactivating_saved_accounts(client):
    store = client.app.state.services.store
    real = connect(client)
    client.post(f"/api/v1/connections/{real['id']}/activation", json={"active": False})
    reopened = Store(store.path.parent)
    assert Accounts(reopened).public()["mode"] == "none"
    assert len(reopened.connections()) == 2
    reopened.activate_account(real["id"], True)
    assert Accounts(Store(store.path.parent)).public()["active_ids"] == [real["id"]]
    reopened.delete_connection(real["id"])
    assert Accounts(reopened).public()["mode"] == "none"


def test_activation_preserves_concurrent_other_accounts_and_demo_exclusion(store):
    first = store.add_connection(
        ConnectionCreate(exchange="binance", label="One", api_key="key", secret="secret"), activate=False
    )
    second = store.add_connection(
        ConnectionCreate(exchange="kraken", label="Two", api_key="key", secret="secret"), activate=False
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda identity: store.activate_account(identity, True), [first.id, second.id]))
    assert set(Accounts(store).public()["active_ids"]) == {first.id, second.id}
    with pytest.raises(ValueError, match="Deactivate"):
        store.activate_account("demo", True)
    assert set(Accounts(store).public()["active_ids"]) == {first.id, second.id}


def test_deactivation_pauses_imports_without_deleting_retained_data(client):
    services = client.app.state.services
    queued = client.post("/api/v1/connections/demo/sync", json={"symbols": ["BTC/USDT"]})
    assert queued.status_code == 202
    client.post("/api/v1/connections/demo/activation", json={"active": False})
    assert all(row["status"] == "paused" for row in services.account_sync.snapshot()["jobs"])
    assert client.post("/api/v1/connections/demo/sync", json={"symbols": ["BTC/USDT"]}).status_code == 400
    assert client.get("/api/v1/account-ledger/fills").status_code == 200


def test_demo_write_rechecks_activation_in_the_ledger_transaction(store):
    before = store.balances()
    store.activate_account("demo", False)
    with pytest.raises(ValueError, match="no longer active"):
        store.execute_paper(
            OrderRequest(side="buy", quantity=0.001, idempotency_key="inactive-demo-write"),
            100,
            require_demo=True,
        )
    assert store.balances() == before
    assert store.orders() == []


def test_inactive_connected_market_feed_is_not_used_as_a_fallback(client):
    account = connect(client)
    assert (
        client.post("/api/v1/settings/market", json={"source": f"connection:{account['id']}"}).status_code
        == 200
    )
    client.post(f"/api/v1/connections/{account['id']}/activation", json={"active": False})
    catalog = client.get("/api/v1/settings/market").json()
    assert not catalog["active"]["available"]
    assert client.get("/api/v1/markets/symbols").status_code == 400
    assert client.get("/api/v1/portfolio").json()["active"] is False


def test_accountant_uses_the_selected_account_scope(client, monkeypatch):
    first, second = connect(client, label="One"), connect(client, "kraken", "Two")
    market = client.app.state.services.market
    monkeypatch.setattr(
        market, "balance", lambda connection: {"USDT": 10 if connection.id == first["id"] else 30}
    )
    reply = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "accountant",
            "message": "Explain this account.",
            "context": {"portfolio_scope": f"account:{first['id']}"},
        },
    )
    assert reply.status_code == 200
    assert reply.json()["evidence"]["total"] == 10
    assert [row["id"] for row in reply.json()["evidence"]["venues"]] == [first["id"]]
    assert second["id"] not in str(reply.json()["evidence"])
