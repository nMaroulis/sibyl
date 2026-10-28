"""Personal watchlists persist independently of portfolio pricing and exchange accounts."""

from concurrent.futures import ThreadPoolExecutor

import ccxt
import pytest

from sibyl.exchanges.demo import DemoClient
from sibyl.storage import Store

CONFIG = "/api/v1/markets/watchlist"
ITEMS = CONFIG + "/items"


def test_default_watchlist_config_does_not_fetch_prices(client, monkeypatch):
    monkeypatch.setattr(DemoClient, "fetch_ticker", lambda *a: pytest.fail("No quote needed for preferences"))
    response = client.get(CONFIG)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["symbols"] == [
        "BTC/USDT",
        "ETH/USDT",
        "SOL/USDT",
        "LINK/USDT",
        "AVAX/USDT",
        "DOT/USDT",
    ]
    assert response.json()["limit"] == 30
    assert response.json()["source"] == "demo"


def test_append_remove_reorder_and_duplicates_persist_after_reopening_store(client, settings):
    initial = client.get(CONFIG).json()
    added = client.post(ITEMS, json={"symbol": "eth/btc"})
    assert added.status_code == 200
    assert added.json()["symbols"] == initial["symbols"] + ["ETH/BTC"]
    duplicate = client.post(ITEMS, json={"symbol": "ETH/BTC"}).json()
    assert duplicate["revision"] == added.json()["revision"]
    reordered = [duplicate["symbols"][-1], *duplicate["symbols"][:-1]]
    result = client.post(CONFIG + "/order", json={"symbols": reordered})
    assert result.status_code == 200 and result.json()["symbols"] == reordered
    reopened = Store(settings.data_dir)
    assert reopened.market_watchlist("demo")["symbols"] == reordered
    removed = client.delete(ITEMS, params={"symbol": "BTC/USDT"}).json()
    assert "BTC/USDT" not in removed["symbols"] and "ETH/BTC" in removed["symbols"]
    again = client.delete(ITEMS, params={"symbol": "BTC/USDT"}).json()
    assert again["revision"] == removed["revision"]
    quotes = client.get("/api/v1/markets").json()
    assert [item["symbol"] for item in quotes["items"]] == removed["symbols"]
    assert quotes["items"][0]["quote"] == "BTC"


@pytest.mark.parametrize(
    "payload,status",
    [
        ({"symbol": "NOTREAL/USDT"}, 400),
        ({"symbol": "BTCUSDT"}, 422),
        ({"symbol": "秘密/USD"}, 422),
        ({"symbol": "https://example.com"}, 422),
        ({"symbol": "BTC/USDT", "api_key": "PRIVATE"}, 422),
    ],
)
def test_invalid_watchlist_members_do_not_change_preferences(client, payload, status):
    before = client.get(CONFIG).json()
    response = client.post(ITEMS, json=payload)
    assert response.status_code == status
    assert client.get(CONFIG).json() == before
    assert "PRIVATE" not in response.text


def test_reorder_cannot_erase_a_concurrent_add_or_introduce_members(client):
    initial = client.get(CONFIG).json()["symbols"]
    client.post(ITEMS, json={"symbol": "ETH/BTC"})
    assert client.post(CONFIG + "/order", json={"symbols": initial}).status_code == 400
    assert client.post(CONFIG + "/order", json={"symbols": [*initial, "XRP/USDT"]}).status_code == 400
    assert client.post(CONFIG + "/order", json={"symbols": [*initial, initial[0]]}).status_code == 422
    assert client.get(CONFIG).json()["symbols"] == [*initial, "ETH/BTC"]


def test_empty_watchlist_stays_empty_without_touching_portfolio(client, settings, monkeypatch):
    before = client.get("/api/v1/portfolio").json()["total"]
    for symbol in client.get(CONFIG).json()["symbols"]:
        assert client.delete(ITEMS, params={"symbol": symbol}).status_code == 200
    assert client.get(CONFIG).json()["symbols"] == []
    assert client.get("/api/v1/markets").json()["items"] == []
    assert Store(settings.data_dir).market_watchlist("demo")["symbols"] == []
    assert client.get("/api/v1/portfolio").json()["total"] == before
    market = client.app.state.services.market
    monkeypatch.setattr(market, "client", lambda *a: pytest.fail("Empty watchlist should need no provider"))
    assert client.get("/api/v1/markets").json()["items"] == []


def test_watchlists_and_quote_caches_are_isolated_by_feed(client, monkeypatch):
    market = client.app.state.services.market
    monkeypatch.setattr("sibyl.services.market.create_client", lambda *a, **kw: DemoClient(market.store))
    demo = client.get(CONFIG).json()["symbols"]
    client.post(ITEMS, params={"source": "kraken"}, json={"symbol": "ETH/BTC"})
    assert client.get(CONFIG).json()["symbols"] == demo
    kraken = client.get("/api/v1/markets", params={"source": "kraken"}).json()
    assert kraken["source"] == "kraken" and kraken["items"][-1]["symbol"] == "ETH/BTC"
    assert client.get("/api/v1/settings/market").json()["active"]["id"] == "demo"
    client.delete(ITEMS, params={"source": "kraken", "symbol": "BTC/USDT"})
    assert "BTC/USDT" in client.get(CONFIG).json()["symbols"]
    assert "BTC/USDT" not in client.get(CONFIG, params={"source": "kraken"}).json()["symbols"]


def test_unavailable_quotes_are_retained_and_removable_without_provider_calls(client, monkeypatch):
    original = client.get(CONFIG).json()["symbols"]
    monkeypatch.setattr(
        DemoClient, "fetch_ticker", lambda *a: (_ for _ in ()).throw(ccxt.RequestTimeout("PRIVATE-UPSTREAM"))
    )
    response = client.get("/api/v1/markets")
    assert response.status_code == 200
    assert "PRIVATE" not in response.text
    assert [row["symbol"] for row in response.json()["items"]] == original
    assert all(row["price"] is None and row["status"] == "unavailable" for row in response.json()["items"])
    market = client.app.state.services.market
    monkeypatch.setattr(
        market, "client", lambda *a: pytest.fail("Removing saved pairs should not call a provider")
    )
    assert client.delete(ITEMS, params={"symbol": original[0]}).status_code == 200
    assert client.get(CONFIG).json()["symbols"] == original[1:]


def test_concurrent_list_appends_are_atomic_and_capacity_is_enforced(store):
    store.seed_market_watchlist("demo", [])

    def append(index):
        try:
            store.change_market_watchlist("demo", "add", f"A{index}/USDT", limit=30)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(append, range(40)))
    saved = store.market_watchlist("demo")
    assert sum(results) == len(set(saved["symbols"])) == len(saved["symbols"]) == 30
    assert saved["revision"] == 30
    assert store.change_market_watchlist("demo", "add", saved["symbols"][0], limit=30)["revision"] == 30


def test_api_list_limit_and_exact_pair_validation(client):
    assert client.post(CONFIG + "/order", json={"symbols": ["BTC/USDT"] * 31}).status_code == 422
    assert client.post(ITEMS, json={"symbol": "BTC/EUR"}).status_code == 400
    assert client.delete(ITEMS, params={"symbol": "BTC/USDT?secret"}).status_code == 422


def test_reorder_and_other_reads_reuse_quote_cache(client, monkeypatch):
    observed = []
    native = DemoClient.fetch_ticker

    def ticker(self, symbol):
        observed.append(symbol)
        return native(self, symbol)

    monkeypatch.setattr(DemoClient, "fetch_ticker", ticker)
    first = client.get("/api/v1/markets").json()
    count = len(observed)
    assert count == len(first["items"])
    order = list(reversed(first["symbols"]))
    client.post(CONFIG + "/order", json={"symbols": order})
    second = client.get("/api/v1/markets").json()
    assert len(observed) == count
    assert [item["symbol"] for item in second["items"]] == order


def test_native_coin_outside_default_six_can_be_watched_and_priced(client, monkeypatch):
    from datetime import UTC, datetime

    market = client.app.state.services.market

    class WideClient(DemoClient):
        def load_markets(self):
            return {
                **super().load_markets(),
                "ADA/USDT": {"symbol": "ADA/USDT", "base": "ADA", "quote": "USDT"},
            }

        def fetch_ticker(self, symbol):
            if symbol == "ADA/USDT":
                return {"last": 0.25, "percentage": 2, "quoteVolume": 1000}
            return super().fetch_ticker(symbol)

        def fetch_ohlcv(self, symbol, timeframe="1d", limit=180):
            if symbol == "ADA/USDT":
                day = int(datetime.now(UTC).timestamp()) // 86400 * 86400
                return [
                    [(day - i * 86400) * 1000, 0.24, 0.26, 0.23, 0.25, 50]
                    for i in reversed(range(1, limit + 1))
                ]
            return super().fetch_ohlcv(symbol, timeframe, limit)

    adapter = WideClient(market.store)
    monkeypatch.setattr(market, "client", lambda connection=None: adapter)
    saved = client.post(ITEMS, json={"symbol": "ADA/USDT"})
    assert saved.status_code == 200
    row = client.get("/api/v1/markets").json()["items"][-1]
    assert row["symbol"] == "ADA/USDT" and row["name"] == "Cardano"
    assert row["price"] == 0.25 and row["quote"] == "USDT"
    assert row["sparkline"] and row["change"] == 2
