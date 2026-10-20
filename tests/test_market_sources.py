"""Market feeds: source isolation, native provider contracts and write-only API keys."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event

import ccxt
import httpx
import pytest

from sibyl.config import Settings
from sibyl.exchanges.demo import DemoClient
from sibyl.market_data.clients import CoinGeckoClient, CryptoCompareClient
from sibyl.models import ConnectionCreate
from sibyl.services.data_settings import DataSettings, MarketSettingsRequest
from sibyl.services.market import Market
from sibyl.storage import Store


def test_catalog_has_public_feeds_and_saved_account_environments(client):
    account = client.post(
        "/api/v1/connections",
        json={
            "exchange": "binance-testnet",
            "label": "My test account",
            "api_key": "not-a-real-key",
            "secret": "not-a-real-secret",
        },
    ).json()
    response = client.get("/api/v1/settings/market")
    assert response.headers["cache-control"] == "no-store"
    catalog = response.json()["catalog"]
    public = [s for s in catalog if s["kind"] == "exchange"]
    assert len(public) == 20
    assert all(s["available"] and not s["requires_key"] for s in public)
    assert not any(s["id"] == "binance-testnet" for s in public)
    saved = next(s for s in catalog if s["id"] == f"connection:{account['id']}")
    assert saved["environment"] == "test" and saved["provider"] == "binance-testnet"
    assert "not-a-real" not in response.text


def test_keys_encrypted_persistent_write_only_and_independent(client, settings):
    key = "PRIVATE-MARKET-KEY-32594"
    response = client.post("/api/v1/settings/market", json={"source": "coingecko", "api_key": key})
    assert response.status_code == 200 and response.json()["active"]["has_api_key"]
    assert key not in response.text
    assert key.encode() not in (settings.data_dir / "sibyl.db").read_bytes()
    assert client.get("/api/v1/system").json()["mode"] == "demo"
    assert not client.get("/api/v1/system").json()["allow_live_trading"]
    assert client.post("/api/v1/settings/market", json={"source": "demo"}).status_code == 200
    assert client.post("/api/v1/settings/market", json={"source": "coingecko"}).json()["active"][
        "has_api_key"
    ]
    reopened = DataSettings(Settings(data_dir=settings.data_dir, _env_file=None), Store(settings.data_dir))
    assert reopened.resolve_market()["api_key"] == key
    assert client.delete("/api/v1/settings/market/coingecko/key").status_code == 400
    client.post("/api/v1/settings/market", json={"source": "demo"})
    removed = client.delete("/api/v1/settings/market/coingecko/key")
    assert removed.status_code == 200
    assert not next(s for s in removed.json()["catalog"] if s["id"] == "coingecko")["has_api_key"]
    assert client.get("/api/v1/markets?source=coingecko").status_code == 400


@pytest.mark.parametrize(
    "payload,status",
    [
        ({"source": "unknown"}, 400),
        ({"source": "coingecko"}, 400),
        ({"source": "kraken", "api_key": "secret"}, 400),
        ({"source": "coingecko", "api_key": "secret\nkey"}, 422),
        ({"source": "https://evil.example"}, 422),
    ],
)
def test_invalid_selection_does_not_replace_default(client, payload, status):
    response = client.post("/api/v1/settings/market", json=payload)
    assert response.status_code == status and "secret" not in response.text
    assert client.get("/api/v1/settings/market").json()["active"]["id"] == "demo"


def test_disconnected_source_fails_without_demo_fallback(settings, store):
    account = store.add_connection(ConnectionCreate(exchange="kraken", label="Spot", api_key="a", secret="b"))
    preferences = DataSettings(settings, store)
    preferences.save_market(MarketSettingsRequest(source=f"connection:{account.id}"))
    # Remove via the same storage API used by the route.
    store.delete_connection(account.id)
    assert not preferences.public_market()["active"]["available"]
    with pytest.raises(ValueError, match="unavailable"):
        Market(settings, store, preferences).overview()


def test_saved_account_client_reuses_test_environment(settings, store, monkeypatch):
    account = store.add_connection(
        ConnectionCreate(exchange="binance-testnet", label="Test", api_key="a", secret="b")
    )
    preferences = DataSettings(settings, store)
    market = Market(settings, store, preferences)
    seen = []

    def create(provider, **kwargs):
        seen.append((provider, kwargs))
        return DemoClient(store)

    monkeypatch.setattr("sibyl.services.market.create_client", create)
    with market.snapshot(f"connection:{account.id}"):
        assert market.metadata()["environment"] == "test"
        assert market.client() is market.client(account)
    assert seen[0][0] == "binance-testnet" and seen[0][1]["sandbox"]
    assert seen[0][1]["credentials"]["apiKey"] == "a"


def test_page_source_override_isolated_and_exact_quote_labels(client, monkeypatch):
    market = client.app.state.services.market
    monkeypatch.setattr("sibyl.services.market.create_client", lambda *a, **kw: DemoClient(market.store))
    response = client.get("/api/v1/markets?source=kraken")
    assert response.status_code == 200 and response.json()["source"] == "kraken"
    assert client.get("/api/v1/settings/market").json()["active"]["id"] == "demo"
    assert client.get("/api/v1/markets").json()["source"] == "demo"
    assert all(item["symbol"].split("/")[1] == item["quote"] for item in response.json()["items"])
    # No USD->USDT substitution in exact-pair analysis endpoints.
    assert client.get("/api/v1/markets/analysis?symbol=BTC/EUR").status_code == 502


def test_source_snapshot_survives_concurrent_settings_change(settings, store, monkeypatch):
    preferences = DataSettings(settings, store)
    market = Market(settings, store, preferences)
    monkeypatch.setattr("sibyl.services.market.create_client", lambda *a, **kw: DemoClient(store))
    entered, updated = Event(), Event()

    def read():
        with market.snapshot():
            first = market.price("BTC/USDT")
            entered.set()
            assert updated.wait(3)
            return market.source, first, market.metadata()["source"]

    with ThreadPoolExecutor() as pool:
        future = pool.submit(read)
        assert entered.wait(3)
        preferences.save_market(MarketSettingsRequest(source="kraken"))
        updated.set()
        assert future.result(timeout=3)[::2] == ("demo", "demo")
    assert market.source == "kraken"


@pytest.mark.parametrize("pro", [False, True])
def test_coingecko_batches_quotes_with_header_auth_and_nullable_fields(pro):
    seen = []

    def handler(request):
        seen.append(request)
        assert request.url.host == ("pro-api.coingecko.com" if pro else "api.coingecko.com")
        assert request.headers["x-cg-pro-api-key" if pro else "x-cg-demo-api-key"] == "PRIVATE"
        assert "PRIVATE" not in str(request.url)
        return httpx.Response(
            200,
            json={
                coin: {
                    "usd": 100,
                    "last_updated_at": datetime.now(UTC).timestamp(),
                    "usd_24h_change": None,
                    "usd_24h_vol": None,
                }
                for coin in ("bitcoin", "ethereum")
            },
        )

    client = CoinGeckoClient("PRIVATE", pro=pro, transport=httpx.MockTransport(handler))
    assert client.fetch_ticker("BTC/USD")["percentage"] is None
    assert client.fetch_ticker("ETH/USD")["quoteVolume"] is None
    assert len(seen) == 1
    with pytest.raises(ccxt.NotSupported):
        client.fetch_ohlcv("BTC/USD")
    client.close()


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {"bitcoin": []},
        {"bitcoin": {"usd": True}},
        {"bitcoin": {"usd": 2, "last_updated_at": -1}},
        {"status": {"error_code": 10002, "error_message": "PRIVATE"}},
    ],
)
def test_malformed_or_rejected_api_payloads_are_sanitized(payload):
    client = CoinGeckoClient(
        "PRIVATE", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    )
    with pytest.raises(ccxt.BaseError) as exc:
        client.fetch_ticker("BTC/USD")
    assert "PRIVATE" not in str(exc.value)
    client.close()


def test_cryptocompare_direct_ohlcv_and_aggregation_limit():
    seen = []

    def handler(request):
        seen.append(request)
        assert request.headers["authorization"] == "Apikey PRIVATE"
        assert request.url.params["aggregate"] == "4"
        assert request.url.params["tryConversion"] == "false"
        return httpx.Response(
            200,
            json={
                "Data": {
                    "Data": [
                        {"time": 1700000000, "open": 10, "high": 13, "low": 9, "close": 11, "volumefrom": 42},
                        {"time": 1700001000, "open": 0, "high": 0, "low": 0, "close": 0, "volumefrom": 0},
                    ]
                }
            },
        )

    client = CryptoCompareClient("PRIVATE", httpx.MockTransport(handler))
    assert client.fetch_ohlcv("BTC/USD", "4h", 100) == [[1700000000000, 10, 13, 9, 11, 42]]
    with pytest.raises(ValueError, match="at most"):
        client.fetch_ohlcv("BTC/USD", "4h", 501)
    assert len(seen) == 1
    client.close()


def test_quote_only_ui_contract_and_analyst_context(client, monkeypatch):
    client.post("/api/v1/settings/market", json={"source": "coingecko", "api_key": "PRIVATE"})
    market = client.app.state.services.market
    adapter = CoinGeckoClient(
        "PRIVATE",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    coin: {"usd": 100, "last_updated_at": datetime.now(UTC).timestamp()}
                    for coin in ("bitcoin", "ethereum", "solana", "chainlink", "avalanche-2", "polkadot")
                },
            )
        ),
    )
    monkeypatch.setattr(market, "client", lambda connection=None: adapter)
    quotes = client.get("/api/v1/markets")
    assert quotes.status_code == 200
    assert not quotes.json()["capabilities"]["candles"]
    assert all(row["sparkline"] == [] and row["quote"] == "USD" for row in quotes.json()["items"])
    assert client.get("/api/v1/markets/symbols").json()["timeframes"] == []
    assert client.get("/api/v1/markets/analysis?symbol=BTC/USD").status_code == 400
    assert client.get("/api/v1/markets/orderbook?symbol=BTC/USD").status_code == 400
    answer = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "analyst",
            "message": "Explain",
            "context": {"symbol": "BTC/USD", "market_source": "coingecko"},
        },
    )
    assert answer.status_code == 200
    assert "Quotes only" in answer.json()["answer"]
    with market.snapshot():
        assert market.price("BTC/USD") == 100
    assert client.get("/api/v1/portfolio").status_code == 200
    adapter.close()


def test_observed_portfolio_history_is_partitioned_by_feed(store):
    assert store.snapshot(100, "demo:kraken")[0]["value"] == 100
    assert store.snapshot(200, "demo:coinbase")[0]["value"] == 200
    assert store.snapshot(110, "demo:kraken") == [
        {"timestamp": store.snapshot(110, "demo:kraken")[0]["timestamp"], "value": 110}
    ]


def test_stale_quote_shown_but_rejected_for_reference_price(settings, store, monkeypatch):
    preferences = DataSettings(settings, store)
    preferences.save_market(MarketSettingsRequest(source="coingecko", api_key="PRIVATE"))
    market = Market(settings, store, preferences)
    adapter = CoinGeckoClient(
        "PRIVATE",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    coin: {"usd": 10, "last_updated_at": datetime.now(UTC).timestamp() - 3600}
                    for coin in ("bitcoin", "ethereum", "solana", "chainlink", "avalanche-2", "polkadot")
                },
            )
        ),
    )
    monkeypatch.setattr(market, "client", lambda connection=None: adapter)
    assert all(row["status"] == "stale" for row in market.overview()["items"])
    with pytest.raises(ValueError, match="stale"):
        market.price("BTC/USD")
    adapter.close()


def test_cache_does_not_mix_sources_and_quote_survives_history_failure(settings, store, monkeypatch):
    class Quotes(DemoClient):
        def __init__(self, identity):
            super().__init__(store)
            self.identity = identity

        def fetch_ticker(self, symbol):
            return {
                "last": 123 if self.identity == "kraken" else 456,
                "percentage": None,
                "quoteVolume": None,
            }

        def fetch_ohlcv(self, *args, **kwargs):
            raise ccxt.ExchangeNotAvailable("history unavailable")

    preferences = DataSettings(settings, store)
    market = Market(settings, store, preferences)
    monkeypatch.setattr("sibyl.services.market.create_client", lambda provider, **kwargs: Quotes(provider))
    for source, expected in [("kraken", 123), ("coinbase", 456), ("kraken", 123)]:
        with market.snapshot(source):
            overview = market.overview()
            assert overview["source"] == source
            assert all(row["price"] == expected and row["sparkline"] == [] for row in overview["items"])
            assert overview["warnings"]
            assert all(row["change"] is None for row in overview["items"])


def test_aggregator_open_bar_excluded_before_indicators(settings, store, monkeypatch):
    from sibyl.exchanges.data import TIMEFRAMES

    seconds = TIMEFRAMES["1h"]
    boundary = int(datetime.now(UTC).timestamp()) // seconds * seconds
    payload = {
        "Data": {
            "Data": [
                {
                    "time": boundary - i * seconds,
                    "open": 10,
                    "high": 12,
                    "low": 9,
                    "close": 11,
                    "volumefrom": 42,
                }
                for i in range(31)
            ]
        }
    }
    adapter = CryptoCompareClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
    preferences = DataSettings(settings, store)
    market = Market(settings, store, preferences)
    monkeypatch.setattr(market, "client", lambda connection=None: adapter)
    preferences.save_market(MarketSettingsRequest(source="cryptocompare", api_key="PRIVATE"))
    with market.snapshot("cryptocompare"):
        candles = market.candles("BTC/USD", limit=30, timeframe="1h")
    assert len(candles) == 30
    assert datetime.fromisoformat(candles[-1]["timestamp"]).timestamp() == boundary - seconds
    adapter.close()


def test_stale_quotes_are_not_used_to_value_connected_account_holdings(client, monkeypatch):
    market = client.app.state.services.market
    monkeypatch.setattr(
        market,
        "overview",
        lambda: {
            "items": [{"asset": "BTC", "price": 100, "status": "stale", "change": None, "sparkline": []}],
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        market, "account_balances", lambda connection: [{"asset": "BTC", "total": 2, "free": 2, "used": 0}]
    )
    account = client.get("/api/v1/portfolio/accounts").json()["accounts"][0]
    assert account["holdings"][0]["price"] is None
    assert account["holdings"][0]["value"] is None
    assert account["unpriced"] == 1


def test_binance_is_initial_default_even_with_demo_accounts_and_saved_demo_is_respected(tmp_path):
    settings = Settings(data_dir=tmp_path, mode="demo", _env_file=None)
    store = Store(tmp_path)
    preferences = DataSettings(settings, store)
    assert preferences.public_market()["active"]["id"] == "binance"
    assert Market(settings, store, preferences).metadata()["source"] == "binance"
    assert preferences.public_market()["account_mode"] == "demo"
    preferences.save_market(MarketSettingsRequest(source="demo"))
    assert preferences.public_market()["active"]["id"] == "demo"
    assert preferences.public_market()["account_mode"] == "demo"


def test_market_source_catalog_orders_exchanges_first_and_demo_last(client):
    catalog = client.get("/api/v1/settings/market").json()["catalog"]
    assert catalog[0]["id"] == "binance"
    assert catalog[-1]["id"] == "demo"
    assert [row["kind"] for row in catalog[:20]] == ["exchange"] * 20
    assert all(row["kind"] == "api" for row in catalog[20:-1])


def test_full_spot_catalog_and_arbitrary_pair_analysis_are_not_limited_to_watchlist(client, monkeypatch):
    market = client.app.state.services.market
    demo = DemoClient(market.store)
    received = []

    class ExtraMarkets(DemoClient):
        def load_markets(self):
            return {
                f"{base}/USDT": {"symbol": f"{base}/USDT", "base": base, "quote": "USDT", "name": name}
                for base, name in [("ADA", "ADA"), ("LTC", "Litecoin"), ("ARB", "Arbitrum")]
            }

        def fetch_ohlcv(self, symbol, timeframe="1d", limit=180):
            self.market(symbol)
            received.append(symbol)
            return demo.fetch_ohlcv("BTC/USDT", timeframe, limit)

    adapter = ExtraMarkets(market.store)
    monkeypatch.setattr(market, "client", lambda connection=None: adapter)
    catalog = client.get("/api/v1/markets/symbols?source=binance").json()
    assert {row["symbol"] for row in catalog["items"]} == {"ADA/USDT", "LTC/USDT", "ARB/USDT"}
    assert next(row for row in catalog["items"] if row["base"] == "ADA")["name"] == "Cardano"
    assert next(row for row in catalog["items"] if row["base"] == "ARB")["name"] == "Arbitrum"
    result = client.get("/api/v1/markets/analysis?source=binance&symbol=ADA/USDT")
    assert result.status_code == 200
    assert result.json()["symbol"] == "ADA/USDT"
    assert result.json()["source"] == "binance"
    assert result.json()["candles"] and received == ["ADA/USDT"]
