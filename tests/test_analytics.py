"""Check indicators, realistic execution timing, and absence of future-data signals."""

import ccxt
import numpy as np
import pandas as pd
import pytest

from sibyl.models import BacktestRequest
from sibyl.services.analytics import analyze, correlation, forecast, indicators
from sibyl.services.market import Market
from sibyl.services.strategies import CATALOG, Strategies, backtest, signals


def candles(prices):
    return [
        {
            "timestamp": (pd.Timestamp("2025-01-01", tz="UTC") + pd.Timedelta(days=i)).isoformat(),
            "open": float(price),
            "high": float(price * 1.01),
            "low": float(price * 0.99),
            "close": float(price),
            "volume": 1000.0,
        }
        for i, price in enumerate(prices)
    ]


def test_flat_market_rsi_and_forecast_are_finite():
    history = candles([100] * 100)
    result = analyze(history)
    assert result["rsi"] == 50
    assert result["volatility"] == 0
    assert forecast(history)["points"][-1]["value"] == pytest.approx(100)
    assert all(point["lower"] <= point["value"] <= point["upper"] for point in forecast(history)["points"])


def test_rsi_reaches_100_without_losses():
    assert analyze(candles(range(100, 200)))["rsi"] == 100


def test_signal_prefix_does_not_depend_on_future_data():
    history = candles(100 * np.exp(np.cumsum(np.random.default_rng(1).normal(0, 0.02, 150))))
    for item in CATALOG:
        prefix = signals(indicators(history[:100]), item["id"])
        extended = signals(indicators(history), item["id"]).iloc[:100]
        pd.testing.assert_series_equal(prefix, extended)


def test_backtest_uses_next_open_and_both_side_costs():
    history = candles(range(100, 180))
    history[30]["open"] = 999.0
    request = BacktestRequest(strategy="ema", capital=10000, fee_bps=10, slippage_bps=5)
    result = backtest(history, request)
    first, last = result["fills"][0], result["fills"][-1]
    assert first["timestamp"] == history[30]["timestamp"]
    assert first["price"] == pytest.approx(999 * 1.0005)
    assert last["price"] == pytest.approx(history[-1]["close"] * 0.9995)
    expected = 10000 / (first["price"] * 1.001) * last["price"] * 0.999
    assert result["final_equity"] == pytest.approx(expected)
    assert result["fees"] == pytest.approx(first["fee"] + last["fee"])
    assert result["max_drawdown"] > 0


def test_no_trade_path_keeps_capital():
    result = backtest(candles([100] * 100), BacktestRequest(strategy="rsi"))
    assert result["final_equity"] == 10000
    assert result["return_pct"] == result["max_drawdown"] == result["sharpe"] == 0
    assert result["trades"] == 0


def test_demo_history_is_consistent_across_request_lengths(settings, store):
    market = Market(settings, store)
    assert market.candles(limit=60) == market.candles(limit=180)[-60:]
    assert market.price("BTC/USDT") == market.candles(limit=1)[0]["close"]
    with pytest.raises(ccxt.BadSymbol, match="spot reference"):
        market.candles("INVALID/USDT")


def test_correlation_aligns_timestamps():
    first = candles([100, 102, 101, 105, 104, 108])
    second = [{**point, "close": point["close"] * 2} for point in first[1:]]
    result = correlation({"A": first, "B": second})
    assert result["matrix"][0][1] == pytest.approx(1)
    assert result["observations"] == 4


def test_live_reference_quotes_fall_back_and_exclude_open_candles(settings, store, monkeypatch):
    settings.mode = "live"
    market = Market(settings, store)
    now = pd.Timestamp.now(tz="UTC").floor("D")
    requested = []

    class QuoteProvider:
        def load_markets(self):
            return {"BTC/USD": {}}

        def fetch_ohlcv(self, symbol, timeframe, limit):
            requested.append(symbol)
            return [
                [int((now - pd.Timedelta(days=day)).timestamp() * 1000), 100, 105, 95, 101, 10]
                for day in reversed(range(31))
            ]

        def fetch_ticker(self, symbol):
            requested.append(symbol)
            return {"last": 102}

    monkeypatch.setattr(market, "client", lambda connection=None: QuoteProvider())
    result = market.candles("BTC/USDT", 30)
    assert len(result) == 30
    assert pd.Timestamp(result[-1]["timestamp"]) < now
    assert market.price("BTC/USDT") == 102
    assert requested == ["BTC/USD", "BTC/USD"]


def test_paper_job_restart_and_duplicate_candle(settings, store):
    market = Market(settings, store)
    service = Strategies(market, store)
    job = service.start(BacktestRequest(strategy="ema"))
    before_manual = store.balances()
    service.tick()
    first = service.jobs()[0]
    restarted = Strategies(market, store)
    restarted.tick()
    assert restarted.jobs()[0]["fills"] == first["fills"]
    assert store.balances() == before_manual
    assert restarted.status(job["id"], "paused")["status"] == "paused"
    assert restarted.status(job["id"], "running")["status"] == "running"
    market.settings.mode = "live"
    restarted.tick()
    assert restarted.jobs()[0]["status"] == "paused"
