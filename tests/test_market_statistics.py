"""Independent market math, disclosed score behavior and source-scoped API evidence."""

import json
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from sibyl.services.analytics import analyze

NOW = datetime(2026, 10, 23, 12, tzinfo=UTC)


def candles(prices, *, seconds=86400, volumes=None):
    """Finish the final candle at a fixed clock; fixtures never age during a CI run."""
    return [
        {
            "timestamp": (NOW - timedelta(seconds=(len(prices) - i) * seconds)).isoformat(),
            "open": float(price),
            "high": float(price * 1.02),
            "low": float(price * 0.98),
            "close": float(price),
            "volume": float(volumes[i] if volumes is not None else 100),
        }
        for i, price in enumerate(prices)
    ]


def stats(prices, **kwargs):
    return analyze(candles(prices, **kwargs), now=NOW)["statistics"]


def test_return_distribution_and_drawdowns_match_hand_calculation():
    s = stats([100, 120, 90, 99])
    assert s["returns"]["sample_pct"] == pytest.approx(-1)
    assert s["returns"]["bar1_pct"] == pytest.approx(10)
    assert s["returns"]["mean_pct"] == pytest.approx((20 - 25 + 10) / 3)
    assert s["returns"]["median_pct"] == pytest.approx(10)
    assert s["returns"]["positive_pct"] == pytest.approx(200 / 3)
    assert s["risk"]["max_drawdown_pct"] == pytest.approx(25)
    assert s["risk"]["current_drawdown_pct"] == pytest.approx(17.5)
    assert s["returns"]["bar5_pct"] is None
    assert s["risk"]["var95_pct"] is None


def test_risk_and_tail_statistics_match_independent_sample_math():
    returns = np.array([-0.1, 0.02, -0.03, 0.04, 0] * 8)
    s = stats(100 * np.cumprod(np.r_[1, 1 + returns]))
    deviation = np.std(returns, ddof=1)
    downside = np.sqrt(np.mean(np.minimum(returns, 0) ** 2))
    assert s["volatility"]["period_pct"] == pytest.approx(deviation * 100)
    assert s["volatility"]["annualized_pct"] == pytest.approx(deviation * np.sqrt(365) * 100)
    assert s["risk"]["sharpe"] == pytest.approx(returns.mean() / deviation * np.sqrt(365))
    assert s["risk"]["sortino"] == pytest.approx(returns.mean() / downside * np.sqrt(365))
    assert s["risk"]["var95_pct"] == pytest.approx(10)
    assert s["risk"]["expected_shortfall95_pct"] == pytest.approx(10)


def test_quantile_is_interpolated_and_tail_uses_actual_observations():
    returns = np.arange(-0.20, 0, 0.01)
    s = stats(100 * np.cumprod(np.r_[1, 1 + returns]))
    assert s["risk"]["var95_pct"] == pytest.approx(19.05)
    assert s["risk"]["expected_shortfall95_pct"] == pytest.approx(20)


def test_flat_prices_are_neutral_with_undefined_ratios_not_fake_zero():
    s = stats([100] * 220)
    assert s["assessment"]["score"] == 50
    assert s["assessment"]["label"] == "Mixed"
    assert s["momentum"]["rsi14"] == 50
    assert s["volatility"]["annualized_pct"] == 0
    assert s["volatility"]["bollinger_percent_b"] is None
    assert s["risk"]["sharpe"] is s["risk"]["sortino"] is None
    assert s["risk"]["max_drawdown_pct"] == 0
    assert s["trend"]["sma200"] == 100
    assert s["sample"]["warnings"] == []
    json.dumps(s, allow_nan=False)


@pytest.mark.parametrize("count", [1, 2, 14, 20, 34, 49, 50, 199, 200])
def test_warmup_and_json_contract(count):
    s = stats([100] * count)
    assert (s["assessment"]["score"] is not None) == (count >= 50)
    assert (s["trend"]["sma200"] is not None) == (count >= 200)
    assert (s["momentum"]["macd"] is not None) == (count >= 35)
    assert (s["momentum"]["rsi14"] is not None) == (count >= 15)
    json.dumps(s, allow_nan=False)


def test_score_weights_and_direction_are_exposed_not_probabilities():
    bullish, bearish = stats(np.arange(100, 200)), stats(np.arange(200, 100, -1))
    assert bullish["assessment"]["score"] > 65
    assert bearish["assessment"]["score"] < 35
    for s in [bullish, bearish]:
        a = s["assessment"]
        assert sum(c["weight"] for c in a["components"]) == 100
        expected = sum(c["weight"] * c["value"] for c in a["components"]) / 100
        assert a["score"] == round(expected)
        assert a["available_weight"] == 100
        assert a["version"] == "technical-bias-v1"
        assert "not safer" in a["note"]


def test_zero_volume_reports_missing_flow_and_normalizes_disclosed_available_weight():
    s = stats([100] * 100, volumes=[0] * 100)
    assert s["volume"]["cmf20"] is None
    assert s["volume"]["vwap20"] is None
    assert s["volume"]["relative20"] is None
    assert s["volume"]["obv_change20"] is None
    assert s["assessment"]["available_weight"] == 85
    assert s["assessment"]["score"] == 50
    assert any("no positive volume" in text for text in s["sample"]["warnings"])


def test_volume_denominator_excludes_latest_candle_and_levels_exclude_current():
    rows = candles(np.arange(100, 130), volumes=[100] * 29 + [300])
    rows[-1].update(high=1000, low=1)
    s = analyze(rows, now=NOW)["statistics"]
    assert s["volume"]["relative20"] == 3
    expected_vwap = (
        sum((row["high"] + row["low"] + row["close"]) / 3 * row["volume"] for row in rows[-20:]) / 2200
    )
    assert s["volume"]["vwap20"] == pytest.approx(expected_vwap)
    assert s["levels"]["prior_high20"] == rows[-2]["high"]
    assert s["levels"]["prior_low20"] == rows[-21]["low"]
    prior = rows[-2]
    pivot = (prior["high"] + prior["low"] + prior["close"]) / 3
    assert s["levels"]["pivot"] == pytest.approx(pivot)
    assert s["levels"]["r1"] == pytest.approx(2 * pivot - prior["low"])
    assert s["levels"]["s2"] == pytest.approx(pivot - prior["high"] + prior["low"])
    assert s["volume"]["obv_change20"] == 2200


def test_intraday_annualization_uses_actual_interval_not_calendar_days():
    rows = candles([100, 110, 99, 105] * 20, seconds=3600)
    daily_scale = analyze(rows, 365 * 24, now=NOW)["statistics"]
    assert daily_scale["sample"]["interval_seconds"] == 3600
    assert daily_scale["volatility"]["annualized_pct"] / daily_scale["volatility"][
        "period_pct"
    ] == pytest.approx(np.sqrt(365 * 24))


def test_gap_restarts_indicators_and_statistics_without_bridging_returns():
    rows = candles([100] * 65 + [1000] * 5)
    del rows[-6]
    result = analyze(rows, now=NOW)
    s = result["statistics"]
    assert s["sample"]["loaded"] == 69 and s["sample"]["observations"] == 5
    assert s["sample"]["missing_intervals"] == 1
    assert s["sample"]["gap_count"] == 1
    assert s["returns"]["sample_pct"] == 0
    assert s["volatility"]["period_pct"] == 0
    assert s["assessment"]["score"] is None
    assert result["candles"][-5]["ema_fast"] == 1000
    assert result["candles"][-1]["rsi"] is None
    assert any("latest 5 consecutive" in text for text in s["sample"]["warnings"])


def test_old_gap_does_not_disable_score_for_a_fresh_contiguous_tail():
    rows = candles([100] * 100)
    del rows[10:13]
    s = analyze(rows, now=NOW)["statistics"]
    assert s["sample"]["observations"] == 87
    assert s["sample"]["missing_intervals"] == 3
    assert s["assessment"]["score"] == 50


def test_stale_data_retains_statistics_but_has_no_current_score():
    s = analyze(candles([100] * 90), now=NOW + timedelta(days=3))["statistics"]
    assert s["sample"]["stale"]
    assert s["returns"]["sample_pct"] == 0
    assert s["assessment"]["score"] is None
    assert "too old" in s["assessment"]["reason"]


@pytest.mark.parametrize(
    "mutation", ["duplicate", "unordered", "nan", "bool", "negative", "invalid_range", "future"]
)
def test_invalid_observations_are_rejected(mutation):
    rows = candles([100] * 80)
    if mutation == "duplicate":
        rows[-1]["timestamp"] = rows[-2]["timestamp"]
    elif mutation == "unordered":
        rows[0], rows[1] = rows[1], rows[0]
    elif mutation == "future":
        rows[-1]["timestamp"] = NOW.isoformat()
    else:
        key, value = {
            "nan": ("close", float("nan")),
            "bool": ("close", True),
            "negative": ("volume", -1),
            "invalid_range": ("high", 1),
        }[mutation]
        rows[-1][key] = value
    with pytest.raises(ValueError):
        analyze(rows, now=NOW)


def test_api_and_protolink_analyst_read_the_same_exact_source(client):
    result = client.get("/api/v1/markets/analysis?source=demo&symbol=ETH/BTC&timeframe=1h&limit=90")
    assert result.status_code == 200
    data = result.json()
    assert data["source"] == "demo" and data["symbol"] == "ETH/BTC"
    assert data["statistics"]["sample"]["interval_seconds"] == 3600
    assert data["statistics"]["sample"]["loaded"] == len(data["candles"]) == 90
    assert data["statistics"]["levels"]["sample_high"] < 1
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "analyst",
            "message": "Explain this technical score and risk",
            "context": {"symbol": "ETH/BTC", "timeframe": "1h", "limit": 90, "market_source": "demo"},
        },
    )
    assert response.status_code == 200
    assert "technical bias" in response.json()["answer"]
    assert "not safer" in response.json()["answer"]
