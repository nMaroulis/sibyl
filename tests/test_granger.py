"""Known directional process, leakage guards, gap handling and native source scope."""

from copy import deepcopy

import numpy as np
import pytest
from scipy.stats import f
from test_agent_guidance import tool_call
from test_relationships import prices

from sibyl.market_data.analysis.granger import granger


def process(n=720):
    rng = np.random.default_rng(429)
    x = rng.normal(0, 0.009, n)
    y = np.zeros(n)
    for i in range(1, n):
        y[i] = 0.7 * x[i - 1] + 0.25 * y[i - 1] + rng.normal(0, 0.003)
    return {"BTC/USDT": prices(100 * np.exp(np.cumsum(x))), "ETH/USDT": prices(100 * np.exp(np.cumsum(y)))}


def test_known_lagged_predictor_and_independent_error_comparison():
    result = granger(process(), seconds=86400, lags=2)
    a, b = result["items"]
    assert a["reference"] == "BTC/USDT" and a["target"] == "ETH/USDT"
    assert a["adjusted_p_value"] < 0.001
    assert a["held_out"]["skill_vs_own_lags_pct"] > 25
    assert b["adjusted_p_value"] > 0.05
    assert a["training_samples"] + 2 + a["held_out"]["samples"] == result["observations"]
    dfs = a["degrees_of_freedom"]
    statistic = ((a["restricted_rss"] - a["augmented_rss"]) / 2) / (a["augmented_rss"] / dfs["denominator"])
    assert a["f_statistic"] == pytest.approx(statistic)
    assert a["p_value"] == pytest.approx(f.sf(statistic, 2, dfs["denominator"]))
    assert a["adjusted_p_value"] == pytest.approx(min(1, 2 * a["p_value"]))


def test_held_out_changes_cannot_select_models_or_classical_test():
    data = process()
    old = granger(data, seconds=86400, lags=3)
    changed = deepcopy(data)
    for rows in changed.values():
        for i, row in enumerate(rows[504:]):
            row["close"] *= np.exp(0.003 * i)
    new = granger(changed, seconds=86400, lags=3)
    for a, b in zip(old["items"], new["items"], strict=True):
        for key in (
            "models",
            "f_statistic",
            "p_value",
            "adjusted_p_value",
            "training_samples",
            "residual_diagnostic",
        ):
            assert a[key] == b[key]
    assert old["items"][0]["held_out"] != new["items"][0]["held_out"]


def test_gap_uses_only_latest_consecutive_return_suffix():
    data = process(360)
    data["ETH/USDT"].pop(250)
    result = granger(data, seconds=86400)
    assert result["observations"] == 108 and result["discarded_earlier_returns"] > 0
    assert result["start"] == data["BTC/USDT"][252]["timestamp"]


@pytest.mark.parametrize("kind", ["constant", "collinear", "short"])
def test_invalid_inference_remains_unavailable(kind):
    data = process(60 if kind == "short" else 360)
    if kind == "constant":
        data["ETH/USDT"] = prices([100] * 360)
    if kind == "collinear":
        data["ETH/USDT"] = deepcopy(data["BTC/USDT"])
    result = granger(data, seconds=86400)
    assert all(row["status"] == "unavailable" and row["p_value"] is None for row in result["items"])


@pytest.mark.parametrize("lag", [0, 6, True, 1.5])
def test_reject_invalid_order(lag):
    with pytest.raises(ValueError):
        granger(process(), seconds=86400, lags=lag)


def test_all_planned_directions_remain_in_adjustment_family():
    data = process()
    data["FLAT/USDT"] = prices([100] * 720)
    result = granger(data, seconds=86400)
    assert result["hypotheses"] == 4
    first = result["items"][0]
    assert first["adjusted_p_value"] == pytest.approx(min(1, 4 * first["p_value"]))
    assert result["items"][-1]["p_value"] is None


def test_api_and_native_agent_preserve_actual_requested_source(manual_client, monkeypatch):
    client = manual_client
    market = client.app.state.services.market
    data = process(360)
    calls = []

    def read(pair, count, timeframe):
        calls.append((pair, market.metadata()["source"]))
        return data[pair][-count:]

    monkeypatch.setattr(market, "candles", read)
    body = dict(symbols=list(data), source="demo", timeframe="1d", limit=360, lags=2)
    response = client.post("/api/v1/markets/granger", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["source"] == "demo"
    native = tool_call(
        client,
        "analyst",
        "market_relationships",
        **{k: v for k, v in body.items() if k != "source"},
        source="demo",
    )
    assert native["granger"]["items"][0]["p_value"] == response.json()["items"][0]["p_value"]
    assert "models" not in native["granger"]["items"][0]
    assert all(source == "demo" for _, source in calls)
    for values in ({"lags": 6}, {"symbols": ["BTC/USDT"]}, {"symbols": ["BTC/USDT", "BTC/USDT"]}):
        assert client.post("/api/v1/markets/granger", json=body | values).status_code == 422


def test_factual_dialog_reads_selected_lag_evidence_without_an_llm(manual_client, monkeypatch):
    client = manual_client
    data = process(360)
    monkeypatch.setattr(
        client.app.state.services.market, "candles", lambda pair, count, timeframe: data[pair][-count:]
    )
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "analyst",
            "message": "Explain this lag comparison",
            "context": {
                "comparison_symbols": list(data),
                "granger_lags": 3,
                "market_source": "demo",
                "timeframe": "1d",
                "limit": 360,
            },
        },
    )
    assert response.status_code == 200, response.text
    assert "Granger lag research · order 3" in response.json()["answer"]
    assert "later-target MAE improvement" in response.json()["answer"]
