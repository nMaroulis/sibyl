"""Exchange contracts use controlled transports and isolated paper wallets, never real funds."""

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime

import ccxt
import pytest
from pydantic import ValidationError

from sibyl.config import Settings
from sibyl.exchanges import ExchangeClient, create_client
from sibyl.exchanges.catalog import CATALOG, EXCHANGES, TEST_ENVIRONMENTS
from sibyl.exchanges.demo import DemoClient
from sibyl.exchanges.providers import CLIENTS
from sibyl.exchanges.registry import provider_catalog
from sibyl.models import ConnectionCreate, ExchangeOrderRequest
from sibyl.services.market import Market
from sibyl.services.trading import ExchangeTrading


class Transport:
    """Unified provider responses containing deliberately sensitive discarded metadata."""

    def __init__(self, options):
        self.options = options
        self.has = dict.fromkeys(
            [
                "fetchTicker",
                "fetchOHLCV",
                "fetchOrderBook",
                "fetchBalance",
                "fetchOrder",
                "fetchOpenOrders",
                "fetchMyTrades",
                "createOrder",
            ],
            True,
        )
        self.timeframes = {"1d": "1d", "1h": "1h"}
        self.events = [("init", deepcopy(options))]
        self.session = self
        self.calls = 0
        self.failure = None
        self.closed = False

    def close(self):
        self.closed = True

    def set_sandbox_mode(self, enabled):
        self.events.append(("sandbox", enabled))

    def load_markets(self):
        self.events.append(("markets",))
        return {
            "BTC/USDT": {
                "base": "BTC",
                "quote": "USDT",
                "spot": True,
                "active": True,
                "precision": {"amount": 0.0001},
                "limits": {"amount": {"min": 0.001}},
                "info": "PRIVATE-SENTINEL",
            },
            "BTC/USDT:USDT": {"base": "BTC", "quote": "USDT", "spot": False},
            "OLD/USDT": {"base": "OLD", "quote": "USDT", "spot": True, "active": False},
        }

    def fetch_ticker(self, symbol):
        return {
            "symbol": symbol,
            "last": "100",
            "bid": 99,
            "ask": 101,
            "percentage": float("nan"),
            "info": "PRIVATE-SENTINEL",
        }

    def fetch_ohlcv(self, symbol, timeframe, limit):
        return [[3000, 100, 102, 98, 101, 20], [1000, 100, 101, 98, 99, 10], [1000, 100, 101, 98, 100, 11]]

    def fetch_order_book(self, symbol, limit):
        self.events.append(("book", limit))
        return {
            "bids": [[98, 2], [99, 1], [float("nan"), 1], [97, -1]],
            "asks": [[102, 2], [101, 1]],
            "info": "PRIVATE-SENTINEL",
        }

    def fetch_balance(self, params):
        self.events.append(("balance", params))
        if self.failure:
            raise self.failure
        return {
            "total": {"BTC": "2", "BAD": float("inf")},
            "free": {"BTC": "1.5"},
            "used": {"BTC": 0.5},
            "info": "PRIVATE-SENTINEL",
        }

    def amount_to_precision(self, symbol, amount):
        return f"{amount:.4f}"

    def fetch_order(self, identity, symbol):
        return {
            "id": identity,
            "symbol": symbol,
            "status": "open",
            "filled": "0.1",
            "info": "PRIVATE-SENTINEL",
        }

    def fetch_open_orders(self, symbol):
        return [self.fetch_order("order-1", symbol)]

    def fetch_my_trades(self, symbol, since, limit):
        self.events.append(("trades", since, limit))
        return [
            {
                "id": "fill-1",
                "symbol": symbol,
                "amount": "1",
                "price": 100,
                "cost": 100,
                "fee": {"cost": "0.1", "currency": "USDT", "info": "PRIVATE-SENTINEL"},
                "info": "PRIVATE-SENTINEL",
            }
        ]

    def create_order(self, symbol, type, side, amount, params):
        self.calls += 1
        if self.failure:
            raise self.failure
        return {"id": "submitted", "symbol": symbol, "filled": amount, "info": "PRIVATE-SENTINEL"}


def credentials(identity):
    return {
        "apiKey": "PRIVATE-KEY",
        "secret": "PRIVATE-SECRET",
        **({"password": "PRIVATE-PASS"} if CATALOG[identity].passphrase else {}),
        **({"uid": "PRIVATE-MEMO"} if CATALOG[identity].uid else {}),
    }


def fake_client(monkeypatch, identity="binance", private=True, sandbox=False):
    monkeypatch.setattr(ccxt, CATALOG[identity].ccxt_id or identity, Transport)
    return create_client(identity, credentials=credentials(identity) if private else None, sandbox=sandbox)


@pytest.mark.parametrize("identity", CLIENTS)
def test_all_provider_classes_implement_normalized_read_contract(monkeypatch, identity):
    client = fake_client(monkeypatch, identity)
    assert isinstance(client, ExchangeClient)
    assert client.id == identity
    expected = [("init", client._exchange.options)]
    if CATALOG[identity].test_environment:
        expected.append(("sandbox", True))
    assert client._exchange.events == expected  # no eager network I/O
    markets = client.load_markets()
    assert list(markets) == ["BTC/USDT"]
    markets["BTC/USDT"]["limits"]["amount"]["min"] = 99
    assert client.market("BTC/USDT")["limits"]["amount"]["min"] == 0.001
    ticker = client.fetch_ticker("BTC/USDT")
    assert ticker["last"] == 100
    assert ticker["percentage"] is None
    assert client.fetch_ohlcv("BTC/USDT", limit=2) == [
        [1000, 100, 101, 98, 100, 11],
        [3000, 100, 102, 98, 101, 20],
    ]
    book = client.fetch_order_book("BTC/USDT", limit=1)
    assert book["bids"] == [[99, 1]] and book["asks"] == [[101, 1]]
    balances = client.fetch_balance()
    assert balances == {"total": {"BTC": 2}, "free": {"BTC": 1.5}, "used": {"BTC": 0.5}}
    assert ("balance", client.balance_params) in client._exchange.events
    status = client.fetch_order("order-1", "BTC/USDT")
    orders = client.fetch_open_orders("BTC/USDT")
    trades = client.fetch_my_trades("BTC/USDT", since=123, limit=25)
    assert trades[0]["fee"] == {"cost": 0.1, "currency": "USDT"}
    assert ("trades", 123, 25) in client._exchange.events
    assert "PRIVATE" not in json.dumps(
        [markets, ticker, book, balances, status, orders, trades], allow_nan=False
    )
    assert client.amount_to_precision("BTC/USDT", 0.12345) == "0.1235"
    transport = client._exchange
    client.close()
    assert transport.closed
    assert transport.secret == transport.apiKey == transport.password == transport.uid == ""
    with pytest.raises(ccxt.AuthenticationError):
        client.fetch_balance()


@pytest.mark.parametrize("spec", (*EXCHANGES, *TEST_ENVIRONMENTS), ids=lambda spec: spec.id)
def test_installed_ccxt_configuration_matches_catalog_without_network(spec):
    client = create_client(spec.id, credentials=credentials(spec.id), sandbox=spec.sandbox)
    assert client._exchange.options["defaultType"] == "spot"
    assert client._exchange.enableRateLimit is True
    assert client._exchange.timeout == 12000
    required = [key for key, value in client._exchange.requiredCredentials.items() if value]
    assert all(credentials(spec.id).get(key) for key in required)
    client.close()


@pytest.mark.parametrize("identity", [spec.id for spec in EXCHANGES if spec.sandbox])
def test_sandbox_precedes_requests(monkeypatch, identity):
    client = fake_client(monkeypatch, identity, sandbox=True)
    assert client._exchange.events[1] == ("sandbox", True)
    client.load_markets()
    assert client._exchange.events[2] == ("markets",)


@pytest.mark.parametrize(
    "identity,field",
    [("okx", "password"), ("kucoin", "password"), ("bitget", "password"), ("bitmart", "uid")],
)
def test_required_credentials_validated_before_client_or_storage(identity, field, store):
    creds = credentials(identity)
    del creds[field]
    with pytest.raises(ValueError, match="credentials"):
        create_client(identity, credentials=creds)
    with pytest.raises(ValidationError, match="passphrase|memo"):
        ConnectionCreate(exchange=identity, label="invalid", api_key="key", secret="secret")
    assert [item.exchange for item in store.connections()] == ["demo"]


def test_factory_rejects_arbitrary_classes_and_implicit_demo():
    with pytest.raises(ValueError, match="Unsupported"):
        create_client("Exchange")
    with pytest.raises(ValueError, match="Sandbox"):
        create_client("kraken", sandbox=True)
    with pytest.raises(ValueError, match="Demo"):
        create_client("demo", credentials={"apiKey": "key"})
    with pytest.raises(ValidationError):
        Settings(market_exchange="demo", _env_file=None)


def test_public_clients_do_not_attempt_private_requests(monkeypatch):
    client = fake_client(monkeypatch, private=False)
    with pytest.raises(ccxt.AuthenticationError):
        client.fetch_balance()
    assert len(client._exchange.events) == 1
    client._exchange.has["fetchMyTrades"] = False
    with pytest.raises(ccxt.AuthenticationError):
        client.fetch_my_trades("BTC/USDT")


def test_unsupported_operations_and_bad_symbols_do_not_submit(monkeypatch):
    client = fake_client(monkeypatch)
    with pytest.raises(ccxt.BadSymbol):
        client.fetch_ticker("BTC/USDT:USDT")
    with pytest.raises(ccxt.BadSymbol):
        client.fetch_order_book("OLD/USDT")
    with pytest.raises(ccxt.NotSupported):
        client.fetch_ohlcv("BTC/USDT", "1m")
    client._exchange.has["fetchOpenOrders"] = False
    with pytest.raises(ccxt.NotSupported):
        client.fetch_open_orders("BTC/USDT")
    assert client._exchange.calls == 0


def test_discrete_book_depth_and_invalid_candles(monkeypatch):
    client = fake_client(monkeypatch, "kucoin")
    client.fetch_order_book("BTC/USDT", limit=10)
    assert ("book", 20) in client._exchange.events
    monkeypatch.setattr(
        client._exchange, "fetch_ohlcv", lambda *args, **kwargs: [[1000, 100, 90, 99, 101, 1]]
    )
    with pytest.raises(ccxt.ExchangeError, match="bounds"):
        client.fetch_ohlcv("BTC/USDT")


@pytest.mark.parametrize("identity", [spec.id for spec in EXCHANGES if not spec.market_orders])
def test_new_adapters_do_not_enable_unreviewed_execution(monkeypatch, identity):
    client = fake_client(monkeypatch, identity)
    with pytest.raises(ccxt.NotSupported, match="not enabled"):
        client.create_order("BTC/USDT", "market", "buy", 1, {"clientOrderId": "unique-id"})
    assert client._exchange.calls == 0


@pytest.mark.parametrize("identity", [spec.id for spec in EXCHANGES if spec.market_orders])
def test_market_submission_never_retries_ambiguous_response(monkeypatch, identity):
    client = fake_client(monkeypatch, identity)
    client._exchange.failure = ccxt.RequestTimeout("PRIVATE-SENTINEL")
    with pytest.raises(ccxt.RequestTimeout):
        client.create_order("BTC/USDT", "market", "buy", 1, {"clientOrderId": "unique-id"})
    assert client._exchange.calls == 1
    with pytest.raises(ValueError):
        client.create_order("BTC/USDT", "limit", "buy", 1, {"clientOrderId": "unique-id"})
    assert client._exchange.calls == 1


def test_demo_is_offline_consistent_and_uses_durable_idempotent_paper_ledger(store, monkeypatch):
    monkeypatch.setattr(ccxt, "binance", lambda *args: pytest.fail("Demo must not construct a real adapter"))
    demo = create_client("demo", store=store)
    assert isinstance(demo, DemoClient)
    candles = demo.fetch_ohlcv("BTC/USDT", limit=180)
    assert demo.fetch_ohlcv("BTC/USDT", limit=60) == candles[-60:]
    assert demo.fetch_ticker("BTC/USDT")["last"] == candles[-1][4]
    assert candles[-1][0] + 86400000 <= datetime.now(UTC).timestamp() * 1000
    assert demo.fetch_order_book("BTC/USDT")["bids"][0][0] < demo.fetch_ticker("BTC/USDT")["last"]
    before = demo.fetch_balance()["total"]

    def submit(_):
        return demo.create_order("BTC/USDT", "market", "buy", 0.01, {"clientOrderId": "demo-contract-test"})

    with ThreadPoolExecutor(max_workers=4) as pool:
        orders = list(pool.map(submit, range(6)))
    assert len({row["id"] for row in orders}) == 1
    assert demo.fetch_balance()["free"]["BTC"] == pytest.approx(before["BTC"] + 0.01)
    assert demo.fetch_balance()["used"]["BTC"] == 0
    assert len(store.orders()) == 1
    restarted = DemoClient(store)
    assert restarted.fetch_order(orders[0]["id"], "BTC/USDT")["status"] == "closed"
    assert restarted.fetch_open_orders("BTC/USDT") == []
    trades = restarted.fetch_my_trades("BTC/USDT", since=0, limit=1)
    assert trades[0]["fee"]["cost"] > 0
    assert restarted.fetch_my_trades("BTC/USDT", since=int(trades[0]["timestamp"] + 1)) == []
    with pytest.raises(ccxt.OrderNotFound):
        restarted.fetch_order(orders[0]["id"], "ETH/USDT")


def test_demo_mode_does_not_replace_saved_private_clients(settings, store, monkeypatch):
    connection = store.add_connection(
        ConnectionCreate(exchange="okx", label="private", api_key="key", secret="secret", passphrase="pass")
    )
    monkeypatch.setattr(ccxt, "okx", Transport)
    market = Market(settings, store)
    assert market.client().id == "demo"
    assert market.client(connection).id == "okx"
    market.client(connection)._exchange.failure = ccxt.AuthenticationError("PRIVATE-SENTINEL")
    assert market.check_connection(connection)["status"] == "error"
    assert "PRIVATE" not in json.dumps(market.check_connection(connection))
    assert len(market.candles()) == 180
    transport = market.client(connection)._exchange
    market.forget(connection.id)
    assert transport.closed
    assert connection.id not in market._clients


def test_provider_catalog_and_private_routes_are_secret_free(client, monkeypatch):
    catalog = client.get("/api/v1/exchanges").json()
    assert len(catalog["items"]) == 23
    assert {spec["id"] for spec in catalog["items"]} == set(CLIENTS) | {"demo"}
    assert catalog["demo"]["credentials_required"] is False
    assert catalog == provider_catalog()
    connection = client.post(
        "/api/v1/connections",
        json={
            "exchange": "bitmart",
            "label": "Memo account",
            "api_key": "PRIVATE-KEY",
            "secret": "PRIVATE-SECRET",
            "uid": "PRIVATE-MEMO",
        },
    ).json()
    monkeypatch.setattr(ccxt, "bitmart", Transport)
    for path in ("balances", "open-orders", "trades"):
        response = client.get(f"/api/v1/connections/{connection['id']}/{path}")
        assert response.status_code == 200, response.text
        assert response.json()["source"] == "bitmart"
        assert "PRIVATE" not in response.text
        assert "info" not in response.text
    assert client.get("/api/v1/connections/unknown/balances").status_code == 404
    assert client.get(f"/api/v1/connections/{connection['id']}/trades?limit=501").status_code == 422
    trading = client.app.state.services.trading
    trading.market.settings.allow_live_trading = True
    with pytest.raises(ValueError, match="not enabled"):
        trading.preview(
            ExchangeOrderRequest(
                connection_id=connection["id"], side="buy", quantity=1, idempotency_key="unsupported-intent"
            )
        )
    assert trading.list_orders() == []


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_coinbase_native_request_preserves_base_quantity_and_client_id(monkeypatch, side):
    """Exercise actual CCXT request generation, replacing only the final transport."""
    client = create_client("coinbase", credentials=credentials("coinbase"))
    market = {
        "id": "BTC-USD",
        "symbol": "BTC/USD",
        "base": "BTC",
        "quote": "USD",
        "baseId": "BTC",
        "quoteId": "USD",
        "spot": True,
        "type": "spot",
        "active": True,
        "precision": {"amount": 0.00000001, "price": 0.01},
        "limits": {},
    }
    client._exchange.set_markets([market])
    observed = []

    def submit(request):
        observed.append(request)
        return {
            "success": True,
            "success_response": {
                "order_id": "test-order",
                "product_id": "BTC-USD",
                "side": side.upper(),
                "client_order_id": request["client_order_id"],
            },
        }

    monkeypatch.setattr(client._exchange, "v3PrivatePostBrokerageOrders", submit)
    result = client.create_order(
        "BTC/USD", "market", side, 0.0001, {"clientOrderId": "135d8630-4dcc-4bfe-8918-41555302a029"}
    )
    assert len(observed) == 1
    assert observed[0]["client_order_id"] == "135d8630-4dcc-4bfe-8918-41555302a029"
    assert observed[0]["order_configuration"] == {"market_market_ioc": {"base_size": "0.0001"}}
    assert "clientOrderId" not in observed[0]
    assert result["id"] == "test-order"
    client.close()


@pytest.mark.parametrize("identity", ["coinex", "bitmart"])
def test_spot_clients_do_not_require_deposit_network_discovery(identity):
    client = create_client(identity)
    assert client._exchange.has["fetchCurrencies"] is False
    client.close()


def test_passphrase_and_memo_are_encrypted_without_public_echo(store):
    connection = store.add_connection(
        ConnectionCreate(
            exchange="bitmart", label="memo", api_key="key", secret="secret", uid="PRIVATE-MEMO-SENTINEL"
        )
    )
    assert store.credentials(connection.id)["uid"] == "PRIVATE-MEMO-SENTINEL"
    assert b"PRIVATE-MEMO-SENTINEL" not in store.path.read_bytes()
    assert "PRIVATE" not in connection.model_dump_json()
    connection = store.add_connection(
        ConnectionCreate(
            exchange="okx",
            label="passphrase",
            api_key="key",
            secret="secret",
            passphrase="PRIVATE-PASS-SENTINEL",
        )
    )
    assert store.credentials(connection.id)["password"] == "PRIVATE-PASS-SENTINEL"
    assert b"PRIVATE-PASS-SENTINEL" not in store.path.read_bytes()
    assert "PRIVATE" not in connection.model_dump_json()


def test_kraken_request_retains_uuid_client_id(monkeypatch, settings, store):
    """The service's persisted ID reaches the actual SDK's native cl_ord_id field."""
    from uuid import UUID

    service = ExchangeTrading(Market(settings, store), store)
    service.market.settings.allow_live_trading = True
    connection = store.add_connection(
        ConnectionCreate(exchange="kraken", label="test", api_key="key", secret="secret")
    )
    client = create_client("kraken", credentials=credentials("kraken"))
    market = {
        "id": "XBTUSDT",
        "symbol": "BTC/USDT",
        "base": "BTC",
        "quote": "USDT",
        "baseId": "XBT",
        "quoteId": "USDT",
        "spot": True,
        "type": "spot",
        "active": True,
        "precision": {"amount": 0.00000001, "price": 0.01},
        "limits": {},
    }
    client._exchange.set_markets([market])
    monkeypatch.setattr(client, "fetch_ticker", lambda symbol: {"ask": 100, "bid": 99, "last": 100})
    monkeypatch.setattr(client, "fetch_balance", lambda: {"free": {"USDT": 1000}})
    service.market._clients[connection.id] = client
    intent = service.preview(
        ExchangeOrderRequest(
            connection_id=connection.id, side="buy", quantity=1, idempotency_key="kraken-id-contract"
        )
    )
    assert str(UUID(intent["client_order_id"])) == intent["client_order_id"]
    observed = []

    def submit(params):
        observed.append(params)
        return {"error": [], "result": {"txid": ["test-kraken-order"]}}

    monkeypatch.setattr(client._exchange, "privatePostAddOrder", submit)
    result = service.execute(intent["id"], intent["confirmation"])
    assert observed[0]["cl_ord_id"] == intent["client_order_id"]
    assert observed[0]["volume"] == "1"
    assert observed[0]["ordertype"] == "market"
    assert result["exchange_order_id"] == "test-kraken-order"
    assert len(observed) == 1
    client.close()


def test_live_provider_failure_cannot_become_demo_data(settings, store, monkeypatch):
    settings.mode = "live"
    settings.market_exchange = "coinex"
    monkeypatch.setattr(ccxt, "coinex", Transport)
    market = Market(settings, store)
    client = market.client()

    def unavailable(_symbol):
        raise ccxt.ExchangeNotAvailable("PRIVATE-PROVIDER-DETAIL")

    monkeypatch.setattr(client._exchange, "fetch_ticker", unavailable)
    with pytest.raises(ccxt.ExchangeNotAvailable):
        market.price("BTC/USDT")
    assert market.source == "coinex"
    assert not any(isinstance(adapter, DemoClient) for adapter in market._clients.values())
    market.close()
