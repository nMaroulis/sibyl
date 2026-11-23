"""Descriptive sample relationships: analytic examples, gaps and unavailable statistics."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from sibyl.accounting.diversification import diversification
from sibyl.market_data.analysis.relationships import aligned, regressions
from sibyl.services.markets.analytics import correlation


def prices(values):
    return [
        {
            "timestamp": (datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=i)).isoformat(),
            "close": float(value),
        }
        for i, value in enumerate(values)
    ]


def test_distance_finds_nonlinear_dependence_with_weak_linear_correlation():
    x = np.linspace(-1, 1, 301)
    # Distance supports signed observations; input closes remain positive.
    history = {"X": prices(x + 2), "Y": prices(x * x + 1)}
    linear = correlation(history, "pearson", "prices")
    nonlinear = correlation(history, "distance", "prices")
    assert abs(linear["matrix"][0][1]) < 1e-12
    assert nonlinear["matrix"][0][1] > 0.45
    assert nonlinear["matrix"][0][0] == pytest.approx(1)
    assert nonlinear["matrix"][1][0] == nonlinear["matrix"][0][1]


def test_distance_is_bounded_scale_invariant_and_capped_to_recent_observations():
    x = np.linspace(1, 10, 720)
    history = {"X": prices(x), "Y": prices(x * 1e8)}
    result = correlation(history, "distance", "prices")
    assert result["matrix"][0][1] == pytest.approx(1)
    assert result["observations"] == 360 and result["available_observations"] == 720
    assert result["start"] == history["X"][-360]["timestamp"]
    constant = correlation({"X": prices([1] * 40), "Y": prices(range(1, 41))}, "distance", "prices")
    assert constant["matrix"][0][0] is None and constant["matrix"][0][1] is None


def test_regression_recovers_known_log_return_beta_and_intercept():
    rng = np.random.default_rng(11)
    x = rng.normal(0, 0.01, 200)
    y = 0.0003 + 1.75 * x
    result = regressions(
        {"Reference": prices(np.exp(np.cumsum(x))), "Target": prices(np.exp(np.cumsum(y)))}, seconds=86400
    )
    item = result["items"][0]
    assert item["beta"] == pytest.approx(1.75)
    assert item["intercept_pct"] == pytest.approx(0.03)
    assert item["r_squared"] == pytest.approx(1)
    assert item["residual_rms_pct"] < 1e-10
    assert item["observations"] == 199


def test_gaps_are_not_bridged_and_constant_or_short_regressions_are_explicit():
    data = prices(np.exp(np.arange(80) * 0.001))
    data.pop(20)
    observations = aligned({"A": data, "B": data}, seconds=86400)
    assert len(observations) == 77
    flat = regressions({"A": prices([100] * 80), "B": prices(range(100, 180))}, seconds=86400)["items"][0]
    assert flat["status"] == "constant_reference" and flat["beta"] is None
    short = regressions({"A": prices(range(1, 11)), "B": prices(range(2, 12))})["items"][0]
    assert short["status"] == "insufficient" and short["points"] == []


@pytest.mark.parametrize("bad", [True, 0, -1, float("nan"), float("inf")])
def test_invalid_prices_never_enter_relationships(bad):
    data = prices(range(1, 50))
    data[20]["close"] = bad
    with pytest.raises(ValueError):
        correlation({"A": data, "B": data})


def test_matrix_undefined_series_and_timezone_contract():
    data = prices([1] * 40)
    assert correlation({"A": data, "B": data})["matrix"] == [[None, None], [None, None]]
    data[0]["timestamp"] = "2020-01-01"
    with pytest.raises(ValueError, match="timezone"):
        correlation({"A": data, "B": data})


def test_diversification_combines_same_assets_and_requires_complete_coverage():
    rows = [{"asset": "BTC", "value": 25}, {"asset": "BTC", "value": 25}, {"asset": "USDT", "value": 50}]
    result = diversification(rows)
    assert result["assets"] == 2 and result["hhi"] == 50 and result["effective_assets"] == 2
    assert result["top_three_pct"] == 100 and result["largest_pct"] == 50
    partial = diversification(rows, complete=False)
    assert partial["status"] == "incomplete" and partial["hhi"] is None
    assert diversification([])["hhi"] is None
    assert diversification([{"asset": "X", "value": -1}])["status"] == "invalid"
    equal = diversification([{"asset": str(i), "value": 1} for i in range(20)])
    assert equal["hhi"] == pytest.approx(5) and equal["top_three_pct"] == pytest.approx(15)
    assert equal["effective_assets"] == pytest.approx(20)


def test_relationship_api_labels_exact_source_and_does_not_claim_inference(client):
    response = client.get("/api/v1/markets/correlation?source=demo&method=distance&limit=90")
    assert response.status_code == 200
    data = response.json()
    assert data["method"] == "distance" and data["source"] == "demo" and len(data["regression"]["items"]) == 3
    assert data["regression"]["transform"] == "same-interval log returns"
    assert data["regression"]["observations"] == 89
    assert client.get("/api/v1/markets/correlation?method=granger").status_code == 422


def test_native_analyst_follows_frozen_comparison_context_without_large_plot_payloads(client, monkeypatch):
    from protolink import create_llm
    from pydantic import ValidationError

    from sibyl.models import AgentContext

    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    steps = [
        {"type": "tool_call", "tool": "market_relationships", "args": {}},
        "The observed return relationships are descriptive.",
    ]
    monkeypatch.setattr(
        "sibyl.agents.utils.registry.create_llm",
        lambda *a, **k: create_llm("mock", sequential_responses=steps),
    )
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "analyst",
            "message": "Explain this comparison",
            "context": {
                "market_source": "demo",
                "timeframe": "4h",
                "limit": 90,
                "comparison_symbols": ["SOL/USDT", "ETH/USDT"],
                "correlation_method": "distance",
                "correlation_transform": "prices",
            },
        },
    )
    assert response.status_code == 200, response.text
    evidence = response.json()["observations"][0]["evidence"]
    assert (
        evidence["symbols"] == ["SOL/USDT", "ETH/USDT"]
        and evidence["method"] == "distance"
        and evidence["transform"] == "prices"
    )
    assert evidence["regression"]["reference"] == "SOL/USDT"
    assert all("points" not in item for item in evidence["regression"]["items"])
    assert evidence["timeframe"] == "4h" and evidence["source"] == "demo"
    with pytest.raises(ValidationError):
        AgentContext(comparison_symbols=["BTC/USDT", "BTC/USDT"])
    with pytest.raises(ValidationError):
        AgentContext(comparison_symbols=["BTC/USDT", "INVALID"])


def test_robust_return_fit_preserves_the_common_window_and_recovers_known_slope():
    rng = np.random.default_rng(17)
    returns = rng.normal(0, 0.012, 500)
    target = 0.002 + 1.8 * returns
    target[-1] += 0.5
    returns[-1] = 0.125
    history = {"X": prices(np.exp(np.cumsum(returns))), "Y": prices(np.exp(np.cumsum(target)))}
    normal = regressions(history, seconds=86400)
    comparison = regressions(history, seconds=86400, robust=True)
    (fit,) = comparison["items"]
    assert normal["observations"] == comparison["available_observations"] == 499
    assert fit["observations"] == len(fit["points"]) == 360
    assert fit["points"] == normal["items"][0]["points"]
    assert fit["beta"] != pytest.approx(1.8)
    assert fit["theil_sen"]["beta"] == pytest.approx(1.8)
    assert fit["theil_sen"]["intercept_pct"] == pytest.approx(0.2)
    assert (
        fit["theil_sen"]["median_absolute_residual_pct"]
        < fit["theil_sen"]["ols_median_absolute_residual_pct"]
    )
    assert "theil_sen" not in normal["items"][0]


def test_market_robust_comparison_available_to_analyst_without_model(client):
    query = "?source=demo&symbols=BTC/USDT,ETH/USDT&robust=true&limit=90"
    response = client.get("/api/v1/markets/correlation" + query)
    assert response.status_code == 200, response.text
    regression = response.json()["regression"]
    assert regression["robust"] and regression["observations"] == 89
    reply = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "analyst",
            "message": "Explain the return fits",
            "context": {
                "market_source": "demo",
                "robust_regression": True,
                "comparison_symbols": ["BTC/USDT", "ETH/USDT"],
                "timeframe": "1d",
                "limit": 90,
            },
        },
    )
    assert reply.status_code == 200, reply.text
    (row,) = reply.json()["observations"][0]["evidence"]["regression"]["items"]
    assert row["theil_sen"] == regression["items"][0]["theil_sen"]
    assert "points" not in row and "Theil–Sen beta" in reply.text
