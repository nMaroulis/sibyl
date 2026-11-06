"""Historical alert acceptance through actual valuation, basket math and durable state."""

import json
import math

import pytest
from pydantic import ValidationError
from test_risk_alerts import check, watch
from test_risk_alerts import risk as risk

from sibyl.accounting.risk.engine import DAY
from sibyl.alerts.delivery.formatting import alert_text
from sibyl.alerts.risk.contracts import RiskAlertCreate
from sibyl.alerts.risk.service import RiskAlerts
from sibyl.market_data.archive import iso, now_ms


@pytest.fixture
def history(risk, monkeypatch):
    state = {"flat": False, "gap": False, "lag": 0, "calls": []}

    def candles(symbol, count, timeframe):
        state["calls"].append((symbol, count, timeframe, risk.market.metadata()["source"]))
        end = now_ms() // DAY * DAY - state["lag"] * DAY
        return [
            {
                "timestamp": iso(end - (count - i) * DAY),
                "close": 100 if state["flat"] else 100 * math.exp(0.08 * math.sin(i * 0.8)),
            }
            for i in range(count)
            if not (state["gap"] and i == count - 10)
        ]

    monkeypatch.setattr(risk.market, "candles", candles)
    return state


def historical(risk, **changes):
    return watch(
        risk, **(dict(metric="volatility", threshold=1, reset_threshold=0.5, basket_assets=["BTC"]) | changes)
    )


def test_actual_basket_breach_hourly_evidence_recovery_and_restart(risk, history):
    rule = historical(risk)
    first = risk.alerts.check(rule["id"])
    assert first["in_breach"] and first["notifications"] == 1
    assert first["next_check"] == pytest.approx(risk.wall[0] + 3600)
    calls = len(history["calls"])
    assert risk.alerts.check(rule["id"])["checks"] == 1
    assert len(history["calls"]) == calls
    evidence = risk.alerts.journal.evidence(rule["id"])["sample"]
    basket = evidence["basket"]
    assert basket["observations"] == 90 and basket["share_of_account_value_pct"] == 50
    assert basket["assets"][0]["weight_pct"] == 100
    assert not basket["entire_account_basket"] and len(basket["converted_closes"]["BTC"]) == 91
    assert history["calls"] == [("BTC/USDT", 91, "1d", "binance")]
    notice = risk.alerts.inbox.page()["items"][0]
    assert "Selected basket: BTC" in alert_text(notice)
    assert "PRIVATE" not in json.dumps(evidence) + json.dumps(notice)
    restored = RiskAlerts(risk.market, risk.store, clock=lambda: risk.wall[0])
    assert restored.rules()["items"][0]["in_breach"]
    history["flat"] = True
    result = check(risk, rule, seconds=3601)
    assert not result["in_breach"] and result["notifications"] == 2
    assert [n["action"] for n in risk.alerts.inbox.page()["items"]] == ["recovered", "breached"]


def test_expected_shortfall_matches_saved_common_history(risk, history):
    from sibyl.accounting.risk.engine import analyze

    rule = historical(risk, metric="tail_loss", basket_assets=["BTC", "USDT"])
    check(risk, rule)
    sample = risk.alerts.journal.evidence(rule["id"])["sample"]
    b = sample["basket"]
    recomputed = analyze(
        {a: {v["timestamp"]: v["close"] for v in rows} for a, rows in b["converted_closes"].items()},
        {a["asset"]: a["weight_pct"] / 100 for a in b["assets"]},
    )
    assert sample["metric_value"] == recomputed["expected_shortfall_95_pct"]
    assert b["entire_account_basket"]


@pytest.mark.parametrize("bad", ["missing", "stale", "gap", "quote", "changed"])
def test_unusable_history_or_configuration_never_clears_incident(risk, history, monkeypatch, bad):
    rule = historical(risk)
    original = check(risk, rule)["last_sample_id"]
    if bad == "missing":
        risk.balances[risk.first.id] = {"USDT": 100}
    if bad == "stale":
        history["lag"] = 3
    if bad == "gap":
        history["gap"] = True
    if bad == "quote":
        risk.quotes["BTC/USDT"] = {"last": 100, "timestamp": 1}
    if bad == "changed":
        old = risk.market.candles

        def change(*a, **kw):
            rows = old(*a, **kw)
            risk.store.activate_account(risk.first.id, False)
            return rows

        monkeypatch.setattr(risk.market, "candles", change)
    result = check(risk, rule, seconds=3601)
    assert result["error"] and result["in_breach"] and result["notifications"] == 1
    assert result["last_sample_id"] == original


@pytest.mark.parametrize(
    "changes",
    [
        {"basket_assets": []},
        {"basket_assets": ["BTC", "BTC"]},
        {"basket_assets": ["btc"]},
        {"basket_assets": ["BTC/USDT"]},
        {"history_days": 45},
        {"metric": "volatility", "threshold": 10001},
        {"metric": "tail_loss", "threshold": 101},
        {"metric": "value_floor"},
    ],
)
def test_historical_rule_requires_explicit_bounded_basket(risk, changes):
    values = dict(
        account_ids=[risk.first.id],
        source="binance",
        metric="volatility",
        threshold=20,
        basket_assets=["BTC"],
    )
    with pytest.raises(ValidationError):
        RiskAlertCreate(**(values | changes))
