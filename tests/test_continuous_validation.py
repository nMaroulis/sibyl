"""One real simulated balance crosses walk-forward boundaries without resetting capital."""

from copy import deepcopy

import pytest
from test_strategy_validation import candles, request

from sibyl.strategies.backtest import BacktestEngine
from sibyl.strategies.validation import ValidationParameters, WalkForwardEngine


def test_constant_schedule_matches_single_backtest_exactly_and_carries_a_position():
    data = candles(360)
    # A rising market holds the EMA position through every boundary.
    for i, row in enumerate(data):
        row.update(open=100 + i, close=100.5 + i, high=102 + i, low=99 + i)
    body = request(parameters={"strategy": "ema", "candles": 360}, grid={}, continuous=True)
    result = WalkForwardEngine().run(data, body)
    replay = result["deployment"]["adaptive"]
    direct = BacktestEngine().run(data, body.parameters, evaluation_start=216)
    assert replay["curve"] == direct["curve"] and replay["fills"] == direct["fills"]
    assert replay["trades"] == 1
    assert all(row["quantity"] > 0 and row["cash"] == 0 for row in replay["transitions"][1:])
    assert sum(t["pnl"] for t in replay["round_trips"]) == pytest.approx(
        replay["final_equity"] - body.parameters.capital
    )
    assert replay["fees"] < sum(f["out_of_sample"]["fees"] for f in result["folds"])
    assert result["deployment"]["fixed"]["curve"] == direct["curve"]


def test_continuous_selected_schedule_and_first_selection_are_causal():
    data = candles(360)
    body = request(parameters={"strategy": "ema", "candles": 360}, continuous=True, selection="nested")
    first = WalkForwardEngine().run(data, body)
    assert first == WalkForwardEngine().run(data, body)
    changed = deepcopy(data)
    for row in changed[264:]:
        for key in ("open", "high", "low", "close"):
            row[key] *= 2
    second = WalkForwardEngine().run(changed, body)
    assert first["folds"][0]["selected"] == second["folds"][0]["selected"]
    assert first["deployment"]["adaptive"]["curve"][:48] == second["deployment"]["adaptive"]["curve"][:48]
    assert first["deployment"]["adaptive"]["curve"] != second["deployment"]["adaptive"]["curve"]
    for fold, transition in zip(first["folds"], first["deployment"]["adaptive"]["transitions"], strict=True):
        assert transition["parameters"] == fold["selected"]["parameters"]


def test_global_trade_cap_and_schedule_contract_rejects_capital_resets():
    data = candles(360)
    body = ValidationParameters(strategy="ema", candles=360, max_trades=1)
    result = BacktestEngine().run(
        data,
        body,
        evaluation_start=216,
        parameter_schedule=[(216, 280, body), (280, 360, body.model_copy(update={"fast_period": 5}))],
    )
    assert result["trades"] <= 1
    with pytest.raises(ValueError, match="capital"):
        BacktestEngine().run(
            data,
            body,
            evaluation_start=216,
            parameter_schedule=[(216, 360, body.model_copy(update={"capital": 2000}))],
        )
    with pytest.raises(ValueError, match="gaps"):
        BacktestEngine().run(data, body, evaluation_start=216, parameter_schedule=[(217, 360, body)])


def test_additional_work_is_admitted_before_any_simulation(monkeypatch):
    body = request(grid={}, continuous=True)
    basic = WalkForwardEngine().run(candles(), body.model_copy(update={"continuous": False}))
    monkeypatch.setattr("sibyl.strategies.validation.MAX_WORK_BARS", basic["processed_bars"])
    monkeypatch.setattr(BacktestEngine, "run", lambda *a, **k: pytest.fail("Simulated before admission"))
    with pytest.raises(ValueError, match="60,000"):
        WalkForwardEngine().run(candles(), body)
