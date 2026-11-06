"""Measured covariance/tails, contiguous data contracts and real saved Demo studies."""

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from sibyl.accounting.risk.engine import DAY, analyze, closes, converted


def histories():
    time = int(datetime(2025, 1, 1, tzinfo=UTC).timestamp() * 1000)
    r = np.sin(np.arange(60) / 4) * 0.02
    values = 100 * np.cumprod(np.r_[1, 1 + r])
    other = 100 * np.cumprod(np.r_[1, 1 - r])
    return {
        "A": {time + i * DAY: float(v) for i, v in enumerate(values)},
        "B": {time + i * DAY: float(v) for i, v in enumerate(other)},
    }


def test_covariance_weights_quantiles_and_offsets_match_actual_daily_returns():
    data = histories()
    result = analyze(data, {"A": 0.75, "B": 0.25})
    a = np.array(list(data["A"].values()))
    b = np.array(list(data["B"].values()))
    returns = 0.75 * (a[1:] / a[:-1] - 1) + 0.25 * (b[1:] / b[:-1] - 1)
    assert result["observations"] == 60
    assert result["annualized_volatility_pct"] == pytest.approx(returns.std(ddof=1) * np.sqrt(365) * 100)
    q = np.quantile(returns, 0.05)
    assert result["historical_var_95_pct"] == pytest.approx(-q * 100)
    assert result["expected_shortfall_95_pct"] == pytest.approx(-returns[returns <= q].mean() * 100)
    assert result["correlation"][0][1] == pytest.approx(-1)
    assert sum(a["variance_contribution_pct"] for a in result["assets"]) == pytest.approx(100)
    assert result["assets"][1]["variance_contribution_pct"] < 0


def test_cash_has_no_fabricated_correlation_and_gaps_never_bridge():
    data = histories()
    data["CASH"] = {t: 1.0 for t in data["A"]}
    result = analyze({"A": data["A"], "CASH": data["CASH"]}, {"A": 0.5, "CASH": 0.5})
    assert result["correlation"][0][1] is None
    assert result["assets"][1]["variance_contribution_pct"] == 0
    del data["A"][sorted(data["A"])[10]]
    result = analyze({"A": data["A"]}, {"A": 1.0})
    assert result["observations"] == 49 and result["discarded_earlier_closes"] == 10
    del data["A"][sorted(data["A"])[-10]]
    with pytest.raises(ValueError, match="consecutive"):
        analyze({"A": data["A"]}, {"A": 1.0})


def test_observed_inverse_bridge_and_invalid_closed_history():
    times = sorted(histories()["A"])
    maps = {"A/USD": {t: 2.0 for t in times}, "USDT/USD": {t: 0.9 for t in times}}
    route = [{"symbol": "A/USD", "inverse": False}, {"symbol": "USDT/USD", "inverse": True}]
    assert converted(route, maps, times)[times[0]] == pytest.approx(2 / 0.9)
    assert set(converted([], maps, times)) == set(times)
    with pytest.raises(ValueError, match="positive"):
        closes([{"timestamp": "2025-01-01T00:00:00+00:00", "close": True}])
    with pytest.raises(ValueError, match="closed"):
        closes(
            [
                {
                    "timestamp": (datetime.now(UTC) + timedelta(days=1))
                    .replace(hour=0, minute=0, second=0, microsecond=0)
                    .isoformat(),
                    "close": 1,
                }
            ]
        )


def test_api_demo_study_pins_inputs_and_native_accountant_does_not_refresh(manual_client, monkeypatch):
    from test_agent_guidance import tool_call

    response = manual_client.post(
        "/api/v1/account/risk", json={"scope": "all", "assets": ["BTC", "ETH", "USDT"], "days": 90}
    )
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved["source"]["source"] == "demo" and saved["observations"] >= 30
    assert saved["inputs"]["market_candles"] and len(saved["fingerprint"]) == 64
    assert saved["correlation"][-1][-1] is None
    monkeypatch.setattr(
        manual_client.app.state.services.market,
        "balance",
        lambda *a: pytest.fail("Saved read refreshed accounts"),
    )
    assert manual_client.get("/api/v1/account/risk/" + saved["id"]).json() == saved
    evidence = tool_call(manual_client, "accountant", "basket_risk", study_id=saved["id"])
    assert evidence["fingerprint"] == saved["fingerprint"] and "inputs" not in evidence
    result = manual_client.post(
        "/api/v1/agents/ask",
        json={
            "module": "accountant",
            "message": "Explain this risk study",
            "context": {"risk_study_id": saved["id"]},
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["tool"] == "basket_risk"
    assert manual_client.get("/api/v1/account/risk").headers["cache-control"] == "no-store"


def test_empty_accounts_and_unknown_asset_never_substitute_demo(manual_client):
    assert manual_client.post("/api/v1/account/risk", json={"assets": ["UNKNOWN"]}).status_code == 400
    for row in manual_client.app.state.services.store.connections():
        manual_client.app.state.services.store.activate_account(row.id, False)
    response = manual_client.post("/api/v1/account/risk", json={"assets": ["BTC"]})
    assert response.status_code == 400 and "active" in response.text


def test_wholly_offset_basket_and_extreme_numbers_do_not_invent_a_risk_ratio():
    data = histories()
    result = analyze(data, {"A": 0.5, "B": 0.5})
    assert result["annualized_volatility_pct"] < 1e-10
    assert result["diversification_ratio"] is None
    assert all(a["variance_contribution_pct"] is None for a in result["assets"])
    first = next(iter(data["A"]))
    extreme = {first + i * DAY: (1e-300 if i % 2 else 1e300) for i in range(40)}
    with pytest.raises(ValueError, match="numerical"):
        analyze({"A": extreme}, {"A": 1.0})


def test_reference_selection_is_frozen_during_explicit_risk_read(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    original = owner.market.candles
    seen = []

    def changing(*args, **kwargs):
        seen.append(owner.market.source)
        owner.store.save_data_profile("market", {"source": "kraken", "profiles": {}})
        return original(*args, **kwargs)

    monkeypatch.setattr(owner.market, "candles", changing)
    response = manual_client.post("/api/v1/account/risk", json={"assets": ["BTC", "ETH"], "days": 60})
    assert response.status_code == 201, response.text
    assert response.json()["source"]["source"] == "demo"
    assert seen and set(seen) == {"demo"}
