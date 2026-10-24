"""Valuation routes preserve units, source attribution, failures and account boundaries."""

import json
from datetime import UTC, datetime

import ccxt
import pytest

from sibyl.exchanges.demo import DemoClient
from sibyl.models import ConnectionCreate
from sibyl.services.data_settings import MarketSettingsRequest
from sibyl.services.valuation import Valuation

VALUATION_TIME = datetime(2026, 10, 1, tzinfo=UTC)


def feed(client, monkeypatch, pairs, balances=None):
    """Install an isolated exact-pair adapter; no test contacts a public provider."""
    market = client.app.state.services.market
    client.app.state.services.data_settings.save_market(MarketSettingsRequest(source="binance"))

    class Quotes(DemoClient):
        def __init__(self):
            super().__init__(market.store)
            self.calls = []

        def load_markets(self):
            return {
                symbol: {
                    "symbol": symbol,
                    "base": symbol.split("/")[0],
                    "quote": symbol.split("/")[1],
                    "name": symbol.split("/")[0],
                }
                for symbol in pairs
            }

        def fetch_ticker(self, symbol):
            self.calls.append(symbol)
            value = pairs[symbol]
            if isinstance(value, Exception):
                raise value
            return (
                {"last": value, "percentage": 10, "timestamp": datetime.now(UTC).timestamp() * 1000}
                if isinstance(value, (int, float))
                else value
            )

        def fetch_balance(self):
            rows = balances if balances is not None else {"USDT": 100}
            return {"total": rows, "free": rows, "used": dict.fromkeys(rows, 0)}

        def fetch_ohlcv(self, *args, **kwargs):
            raise ccxt.NotSupported("No candle endpoint in this test.")

    adapter = Quotes()
    monkeypatch.setattr(market, "client", lambda connection=None: adapter)
    return market, adapter


def test_values_arbitrary_holdings_and_depegged_stablecoins(client, monkeypatch):
    market, adapter = feed(
        client, monkeypatch, {"XRP/USDT": 2, "USDC/USDT": 0.93}, {"XRP": 15, "USDC": 100, "USDT": 20}
    )
    result = client.get("/api/v1/portfolio").json()
    assert result["total"] == pytest.approx(143)
    assert result["complete"]
    assert result["coverage"] == {"priced": 3, "total": 3}
    rows = {row["asset"]: row for row in result["holdings"]}
    assert rows["USDC"]["price"] == 0.93
    assert rows["USDC"]["path"] == ["USDC", "USDT"]
    assert rows["USDT"]["status"] == "identity"
    assert rows["USDT"]["price"] == 1
    assert rows["XRP"]["route"][0]["symbol"] == "XRP/USDT"
    assert result["source"] == "binance"
    assert set(adapter.calls) == {"XRP/USDT", "USDC/USDT"}
    account = client.get("/api/v1/portfolio/accounts").json()["accounts"][0]
    assert account["total"] == pytest.approx(result["total"])
    assert len(adapter.calls) == 2  # The account endpoint shares exact quote caches.


def test_inverse_and_two_leg_conversion_preserve_units_and_changes(client, monkeypatch):
    market, _ = feed(
        client, monkeypatch, {"ADA/BTC": 0.00001, "USDT/BTC": 0.00002, "EUR/USD": 1.1, "USDT/USD": 1.02}
    )
    with market.snapshot():
        valuation = Valuation(market)
        ada = valuation.price("ADA")
        euro = valuation.price("EUR")
    assert ada["price"] == pytest.approx(0.5)
    assert ada["path"] == ["ADA", "BTC", "USDT"]
    assert ada["route"][1]["inverse"]
    assert ada["change"] == pytest.approx(0)  # +10% base leg and inverse +10% quote cancel.
    assert euro["price"] == pytest.approx(1.1 / 1.02)
    assert euro["path"] == ["EUR", "USD", "USDT"]


def test_three_leg_route_and_shared_bridge_are_bounded(client, monkeypatch):
    market, adapter = feed(
        client, monkeypatch, {"NEW/ETH": 2, "OTHER/ETH": 3, "ETH/BTC": 0.05, "BTC/USDT": 60000}
    )
    with market.snapshot():
        valuation = Valuation(market)
        assert valuation.price("NEW")["price"] == 6000
        assert valuation.price("OTHER")["price"] == pytest.approx(9000)
        assert valuation.price("NEW")["path"] == ["NEW", "ETH", "BTC", "USDT"]
    assert adapter.calls.count("ETH/BTC") == adapter.calls.count("BTC/USDT") == 1


def test_failed_direct_quote_uses_a_fresh_supported_path_without_parity(client, monkeypatch):
    market, adapter = feed(
        client,
        monkeypatch,
        {"ALT/USDT": ccxt.ExchangeNotAvailable("PRIVATE-KEY"), "ALT/USDC": 2, "USDC/USDT": 0.9},
        {"ALT": 10},
    )
    result = client.get("/api/v1/portfolio").json()
    assert result["total"] == 18
    assert result["holdings"][0]["path"] == ["ALT", "USDC", "USDT"]
    assert "PRIVATE-KEY" not in json.dumps(result)
    assert len(adapter.calls) == 3


@pytest.mark.parametrize(
    "ticker,status",
    [
        ({"last": 10, "timestamp": 1}, "stale"),
        ({"last": 10, "timestamp": VALUATION_TIME.timestamp() * 1000 + 120000}, "unavailable"),
        ({"last": float("nan")}, "unavailable"),
        ({"last": -1}, "unavailable"),
        ({"last": True}, "unavailable"),
    ],
)
def test_invalid_or_stale_leg_excludes_the_holding(client, monkeypatch, ticker, status):
    # Parametrization runs during collection, potentially minutes before CI
    # reaches this test. Keep the quote and valuation clock fixed together.
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return VALUATION_TIME.astimezone(tz) if tz else VALUATION_TIME.replace(tzinfo=None)

    monkeypatch.setattr("sibyl.services.valuation.datetime", FrozenDatetime)
    feed(client, monkeypatch, {"ALT/USDT": ticker}, {"ALT": 2, "USDT": 10})
    result = client.get("/api/v1/portfolio").json()
    assert result["total"] == 10
    assert not result["complete"]
    assert result["change"] is None
    assert result["unpriced"][0]["status"] == status
    assert result["unpriced"][0]["price"] is None
    assert result["history"] == []  # Never save a partial account value as a complete observation.


def test_undated_quotes_and_missing_daily_changes_are_explicit(client, monkeypatch):
    feed(client, monkeypatch, {"ALT/USDT": {"last": 3}}, {"ALT": 10})
    result = client.get("/api/v1/portfolio").json()
    assert result["total"] == 30
    assert result["holdings"][0]["status"] == "undated"
    assert result["holdings"][0]["observed_at"] is None
    assert result["change"] is None
    assert any("undated" in warning for warning in result["warnings"])


def test_unknown_asset_and_provider_failure_have_safe_reasons(client, monkeypatch):
    feed(client, monkeypatch, {"BAD/USDT": ccxt.AuthenticationError("TOPSECRET")}, {"UNKNOWN": 7, "BAD": 2})
    result = client.get("/api/v1/portfolio").json()
    assert result["total"] == 0
    assert len(result["unpriced"]) == 2
    assert all(row["reason"] for row in result["unpriced"])
    assert "TOPSECRET" not in json.dumps(result)
    assert result["coverage"] == {"priced": 0, "total": 2}


def test_failure_does_not_overwrite_a_complete_snapshot(client, monkeypatch):
    market, _ = feed(client, monkeypatch, {"ALT/USDT": 4}, {"ALT": 2})
    before = client.get("/api/v1/portfolio").json()
    assert before["history"][-1]["value"] == 8
    monkeypatch.setattr(market, "valuation_ticker", lambda symbol: {"error": "Unavailable"})
    after = client.get("/api/v1/portfolio").json()
    assert after["total"] == 0
    assert after["history"] == before["history"]
    assert not after["complete"]


def test_history_aligns_exact_conversion_legs_without_filling_gaps(client, monkeypatch):
    market, _ = feed(client, monkeypatch, {"ALT/BTC": 2, "USDT/BTC": 4}, {"ALT": 1})
    histories = {
        "ALT/BTC": [{"timestamp": "2026-10-01", "close": 4}, {"timestamp": "2026-10-02", "close": 8}],
        "USDT/BTC": [{"timestamp": "2026-10-02", "close": 2}, {"timestamp": "2026-10-03", "close": 4}],
    }
    monkeypatch.setattr(market, "candles", lambda symbol, limit: histories[symbol])
    with market.snapshot():
        valuation = Valuation(market)
        quote = valuation.price("ALT")
        assert valuation.history(quote) == [{"timestamp": "2026-10-02", "value": 4}]


def test_quote_budget_is_explicit_and_keeps_known_values(client, monkeypatch):
    market, adapter = feed(client, monkeypatch, {"ONE/USDT": 1, "TWO/USDT": 2})
    monkeypatch.setattr("sibyl.services.valuation.MAX_QUOTES", 1)
    with market.snapshot():
        valuation = Valuation(market)
        assert valuation.price("ONE")["price"] == 1
        assert valuation.price("TWO")["status"] == "limited"
        assert valuation.price("USDT")["price"] == 1
    assert len(adapter.calls) == 1


def test_empty_wallet_needs_no_public_catalog_or_quotes(client, monkeypatch):
    market, adapter = feed(client, monkeypatch, {}, {})
    monkeypatch.setattr(market, "symbols", lambda: pytest.fail("Empty wallet requested a catalog"))
    result = client.get("/api/v1/portfolio").json()
    assert result["total"] == 0 and result["holdings"] == [] and result["complete"]
    assert not adapter.calls


def test_demo_exercises_extra_coin_depeg_and_fiat_with_the_normal_engine(client):
    result = client.get("/api/v1/portfolio").json()
    rows = {row["asset"]: row for row in result["holdings"]}
    assert result["complete"]
    assert rows["ADA"]["path"] == ["ADA", "BTC", "USDT"]
    assert rows["USDC"]["price"] == pytest.approx(0.997)
    assert rows["EUR"]["path"] == ["EUR", "USD", "USDT"]
    assert rows["EUR"]["price"] == pytest.approx(1.08 / 1.002)
    assert result["history_kind"] == "illustrative"
    assert len(result["history"]) == 90
    assert result["history"][-1]["value"] == pytest.approx(result["total"])
    accounts = client.get("/api/v1/portfolio/accounts").json()
    assert accounts["quote_rates"]["USD"] != 1
    assert accounts["accounts"][0]["total"] == pytest.approx(result["total"])


def test_failed_account_is_not_reported_as_zero_balance(client, monkeypatch):
    market, _ = feed(client, monkeypatch, {})
    monkeypatch.setattr(
        market,
        "account_balances",
        lambda connection: (_ for _ in ()).throw(ccxt.ExchangeNotAvailable("private")),
    )
    result = client.get("/api/v1/portfolio/accounts").json()
    assert result["accounts"][0]["total"] is None
    assert not result["accounts"][0]["complete"]
    assert result["accounts"][0]["status"] == "error"


def test_test_and_production_accounts_keep_separate_totals(client, monkeypatch):
    services = client.app.state.services
    services.settings.mode = "live"
    real = services.store.add_connection(
        ConnectionCreate(exchange="binance", label="Real", api_key="key", secret="secret")
    )
    sandbox = services.store.add_connection(
        ConnectionCreate(exchange="binance-testnet", label="Test", api_key="key", secret="secret")
    )
    feed(client, monkeypatch, {"ALT/USDT": 4}, {"ALT": 10})
    overview = client.get("/api/v1/portfolio").json()
    assert overview["total"] == 40
    assert [row["id"] for row in overview["venues"]] == [real.id]
    accounts = client.get("/api/v1/portfolio/accounts").json()["accounts"]
    assert {row["id"] for row in accounts} == {real.id}
    test_view = client.get(f"/api/v1/portfolio/accounts?scope=account:{sandbox.id}").json()
    assert test_view["mode"] == "test"
    assert test_view["accounts"][0]["sandbox"]


def test_quotes_only_api_uses_observed_usdt_usd_conversion(client, monkeypatch):
    import httpx

    from sibyl.market_data.clients import CoinGeckoClient

    market = client.app.state.services.market
    client.app.state.services.data_settings.save_market(
        MarketSettingsRequest(source="coingecko", api_key="TEST-ONLY")
    )
    requests = []

    def reply(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                coin: {"usd": price, "usd_24h_change": 2, "last_updated_at": datetime.now(UTC).timestamp()}
                for coin, price in [("bitcoin", 100), ("tether", 1.02), ("usd-coin", 0.97)]
            },
        )

    adapter = CoinGeckoClient("TEST-ONLY", transport=httpx.MockTransport(reply))
    monkeypatch.setattr(market, "client", lambda connection=None: adapter)
    monkeypatch.setattr(market, "balance", lambda connection: {"BTC": 2, "USDC": 5, "USD": 3})
    result = client.get("/api/v1/portfolio").json()
    assert result["complete"]
    assert result["total"] == pytest.approx((200 + 5 * 0.97 + 3) / 1.02)
    assert result["holdings"][0]["path"] == ["BTC", "USD", "USDT"]
    assert all(row["sparkline"] == [] for row in result["holdings"])
    assert len(requests) == 1  # API batching includes real stablecoin observations.
    assert "TEST-ONLY" not in str(requests[0].url)
    adapter.close()


def test_cached_quote_is_rechecked_for_freshness_and_is_source_scoped(client, monkeypatch):
    import sibyl.services.valuation as module

    market, adapter = feed(client, monkeypatch, {"ALT/USDT": 10})
    with market.snapshot():
        assert Valuation(market).price("ALT")["price"] == 10
    tick = adapter.fetch_ticker("ALT/USDT")["timestamp"]

    class Later(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromtimestamp(tick / 1000 + 301, UTC)

    monkeypatch.setattr(module, "datetime", Later)
    with market.snapshot():
        assert Valuation(market).price("ALT")["status"] == "stale"
    assert adapter.calls.count("ALT/USDT") == 2  # The validation read above plus one actual cached load.
    monkeypatch.setattr(module, "datetime", datetime)
    client.app.state.services.data_settings.save_market(MarketSettingsRequest(source="kraken"))
    monkeypatch.setattr(adapter, "fetch_ticker", lambda symbol: {"last": 22})
    with market.snapshot():
        assert Valuation(market).price("ALT")["price"] == 22
        assert market.metadata()["source"] == "kraken"


def test_catalog_outage_still_reports_native_cash_and_keeps_other_quantities(client, monkeypatch):
    market, _ = feed(client, monkeypatch, {}, {"USDT": 20, "ALT": 2})

    def outage():
        raise ccxt.ExchangeNotAvailable("PRIVATE")

    monkeypatch.setattr(market, "symbols", outage)
    result = client.get("/api/v1/portfolio").json()
    assert result["total"] == 20
    assert result["unpriced"][0]["asset"] == "ALT"
    assert "catalog" in result["unpriced"][0]["reason"]
    assert "PRIVATE" not in json.dumps(result)


def test_chart_budget_does_not_hide_current_prices(client, monkeypatch):
    market, _ = feed(client, monkeypatch, {"ALT/USDT": 2}, {"ALT": 10})
    monkeypatch.setattr("sibyl.services.valuation.MAX_HISTORY", 0)
    monkeypatch.setattr(market, "candles", lambda *args: pytest.fail("Chart budget exceeded"))
    result = client.get("/api/v1/portfolio").json()
    assert result["total"] == 20 and result["complete"]
    assert result["holdings"][0]["sparkline"] == []
