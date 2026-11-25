"""Verify actual-funds execution logic with a fake exchange, never a real account."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import ccxt
import pytest
from fastapi.testclient import TestClient

from sibyl.api.app import create_app
from sibyl.models import ConnectionCreate, ExchangeOrderRequest
from sibyl.services.markets.service import Market
from sibyl.services.trading.service import ExchangeTrading


class FakeExchange:
    """A deterministic CCXT-shaped provider for validation and retry tests."""

    def __init__(self):
        self.markets = {
            "BTC/USDT": {
                "spot": True,
                "active": True,
                "limits": {"amount": {"min": 0.001, "max": 10}, "cost": {"min": 10, "max": 1_000_000}},
            }
        }
        self.calls = 0
        self.failure = None
        self.free = {"USDT": 100000, "BTC": 2}

    def close(self):
        pass

    def format_client_order_id(self, identity):
        return identity

    def load_markets(self):
        return self.markets

    def market(self, symbol):
        return self.markets[symbol]

    def amount_to_precision(self, symbol, amount):
        return f"{amount:.4f}"

    def fetch_ticker(self, symbol):
        return {"ask": 50000, "bid": 49999, "last": 50000}

    def fetch_balance(self):
        return {"free": self.free, "total": self.free}

    def create_order(self, *args, **kwargs):
        self.calls += 1
        if self.failure:
            raise self.failure
        return {"id": "exchange-order-123", "status": "closed", "filled": args[3], "average": 50000}


@pytest.fixture
def trading(settings, store):
    settings.allow_live_trading = True
    market = Market(settings, store)
    connection = store.add_connection(
        ConnectionCreate(
            exchange="binance", label="Test sandbox", api_key="fake-key", secret="fake-secret", sandbox=True
        )
    )
    adapter = FakeExchange()
    market._clients[connection.id] = adapter
    return ExchangeTrading(market, store), adapter, connection


def request(connection, **changes):
    return ExchangeOrderRequest(
        **{
            "connection_id": connection.id,
            "side": "buy",
            "quantity": 0.01,
            "idempotency_key": "exchange-intent-test",
            **changes,
        }
    )


def test_workspace_manual_switch_persists_and_rechecks_existing_review(settings, store):
    settings.allow_strategy_execution = True
    connection = store.add_connection(
        ConnectionCreate(
            exchange="binance", label="Local test", api_key="fake-key", secret="fake-secret", sandbox=True
        )
    )
    venue = FakeExchange()
    endpoint = "/api/v1/workspace/manual-spot-trading"
    payload = request(connection).model_dump(mode="json")
    with TestClient(create_app(settings)) as client:
        services = client.app.state.services
        services.market._clients[connection.id] = venue
        assert client.post("/api/v1/exchange-orders/preview", json=payload).status_code == 400
        assert client.post(endpoint, json={"enabled": "true"}).status_code == 422
        enabled = client.post(endpoint, json={"enabled": True})
        assert enabled.json() == {"enabled": True, "locked": False}
        assert enabled.headers["Cache-Control"] == "no-store"
        state = client.get("/api/v1/system").json()
        assert state["manual_spot_trading"]["enabled"]
        assert not state["allow_live_trading"]
        review = client.post("/api/v1/exchange-orders/preview", json=payload)
        assert review.status_code == 200, review.text
        assert client.post(endpoint, json={"enabled": False}).json()["enabled"] is False
        intent = review.json()
        denied = client.post(
            f"/api/v1/exchange-orders/{intent['id']}/confirm",
            json={"confirmation": intent["confirmation"]},
        )
        assert denied.status_code == 400 and "Settings" in denied.json()["detail"]
        assert venue.calls == 0

    # A saved off overrides even an enabled environment default after restart.
    settings.allow_live_trading = True
    with TestClient(create_app(settings)) as client:
        assert not client.get("/api/v1/system").json()["manual_spot_trading"]["enabled"]
        assert client.post("/api/v1/exchange-orders/preview", json=payload).status_code == 400
        client.post(endpoint, json={"enabled": True}).raise_for_status()

    settings.allow_live_trading = False
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/system").json()["manual_spot_trading"]["enabled"]


def test_preview_validates_without_sending(trading):
    service, adapter, connection = trading
    intent = service.preview(request(connection))
    assert intent["notional"] == 500
    assert intent["sandbox"] is True
    assert intent["confirmation"] == "BUY BTC"
    assert adapter.calls == 0


def test_wrong_confirmation_and_expiry_do_not_send(trading):
    service, adapter, connection = trading
    intent = service.preview(request(connection))
    with pytest.raises(ValueError, match="Type BUY BTC"):
        service.execute(intent["id"], "SELL BTC")
    intent["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    with service.store.db() as db:
        db.execute("UPDATE exchange_orders SET payload = ? WHERE id = ?", (json.dumps(intent), intent["id"]))
    with pytest.raises(ValueError, match="expired"):
        service.execute(intent["id"], "BUY BTC")
    assert adapter.calls == 0


def test_concurrent_confirm_submits_once(trading):
    service, adapter, connection = trading
    intent = service.preview(request(connection))
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda _: service.execute(intent["id"], "BUY BTC"), range(8)))
    assert adapter.calls == 1
    assert service.list_orders()[0]["status"] == "closed"


def test_ambiguous_network_failure_never_retries(trading):
    service, adapter, connection = trading
    adapter.failure = ccxt.RequestTimeout("sensitive provider request detail")
    intent = service.preview(request(connection))
    first = service.execute(intent["id"], "BUY BTC")
    second = service.execute(intent["id"], "BUY BTC")
    assert first["status"] == second["status"] == "unknown"
    assert adapter.calls == 1
    assert "sensitive" not in json.dumps(first)
    assert "Do not resubmit" in first["message"]


def test_exchange_rejection_is_sanitized(trading):
    service, adapter, connection = trading
    adapter.failure = ccxt.InsufficientFunds("secret provider content")
    intent = service.preview(request(connection))
    result = service.execute(intent["id"], "BUY BTC")
    assert result["status"] == "rejected"
    assert "secret" not in json.dumps(result)


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"quantity": 0.0001}, "minimum"),
        ({"quantity": 0.0100001}, "precision"),
        ({"symbol": "ETH/USDT"}, "unavailable"),
        ({"quantity": 11}, "maximum"),
    ],
)
def test_preview_rejects_invalid_exchange_orders(trading, changes, message):
    service, adapter, connection = trading
    with pytest.raises(ValueError, match=message):
        service.preview(request(connection, **changes))
    assert adapter.calls == 0


def test_preview_checks_free_funds_and_idempotency(trading):
    service, adapter, connection = trading
    adapter.free["USDT"] = 500
    with pytest.raises(ValueError, match="1%"):
        service.preview(request(connection))
    adapter.free["USDT"] = 100000
    first = service.preview(request(connection))
    assert service.preview(request(connection))["id"] == first["id"]
    with pytest.raises(ValueError, match="different exchange order"):
        service.preview(request(connection, quantity=0.02))


def test_sandbox_adapter_configuration_happens_before_requests(settings, store, monkeypatch):
    events = []

    class ConfiguredExchange:
        def __init__(self, options):
            events.append(("init", options))

        def set_sandbox_mode(self, enabled):
            events.append(("sandbox", enabled))

    monkeypatch.setattr(ccxt, "binance", ConfiguredExchange)
    connection = store.add_connection(
        ConnectionCreate(
            exchange="binance", label="sandbox", api_key="test-key", secret="test-secret", sandbox=True
        )
    )
    market = Market(settings, store)
    client = market.client(connection)
    assert events[0][1]["enableRateLimit"] is True
    assert events[0][1]["apiKey"] == "test-key"
    assert events[1] == ("sandbox", True)
    market.forget(connection.id)
    assert market.client(connection) is not client


def test_status_refresh_is_read_only_even_when_execution_disabled(trading, monkeypatch):
    service, adapter, connection = trading
    intent = service.preview(request(connection))
    service.execute(intent["id"], "BUY BTC")
    observed = []

    def fetch_order(identity, symbol):
        observed.append((identity, symbol))
        return {"status": "closed", "filled": 0.01, "average": 49998}

    monkeypatch.setattr(adapter, "fetch_order", fetch_order, raising=False)
    service.market.settings.allow_live_trading = False
    refreshed = service.refresh(intent["id"])
    assert refreshed["average"] == 49998
    assert refreshed["refreshed_at"]
    assert observed == [("exchange-order-123", "BTC/USDT")]
    assert adapter.calls == 1


def test_status_refresh_never_resubmits_unknown_outcome(trading):
    service, adapter, connection = trading
    intent = service.preview(request(connection))
    adapter.failure = TimeoutError()
    service.execute(intent["id"], "BUY BTC")
    with pytest.raises(ValueError, match="No exchange order ID"):
        service.refresh(intent["id"])
    assert adapter.calls == 1


def test_deactivated_account_cannot_confirm_an_existing_preview(trading):
    service, adapter, connection = trading
    intent = service.preview(request(connection))
    service.store.activate_account(connection.id, False)
    with pytest.raises(ValueError, match="inactive"):
        service.execute(intent["id"], "BUY BTC")
    with pytest.raises(ValueError, match="Activate"):
        service.preview(request(connection, idempotency_key="inactive-preview"))
    assert adapter.calls == 0
    assert service.list_orders()[0]["status"] == "preview"


def test_native_id_collision_is_rejected_before_submitting_or_persisting_another_review(trading, monkeypatch):
    service, adapter, connection = trading
    monkeypatch.setattr(adapter, "format_client_order_id", lambda _identity: "same-native-id")
    service.preview(request(connection))
    with pytest.raises(ValueError, match="collision"):
        service.preview(request(connection, idempotency_key="different-native-intent"))
    assert len(service.list_orders()) == 1
    assert adapter.calls == 0
