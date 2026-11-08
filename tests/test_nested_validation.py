"""Actual nested strategy scoring, chronology, work admission and deterministic evidence."""

from copy import deepcopy
from statistics import mean

import pytest
from test_release_research_tools import portable_model as portable_model
from test_strategy_validation import candles, request

from sibyl.strategies.backtest import BacktestEngine
from sibyl.strategies.validation import WalkForwardEngine


def test_nested_outer_future_cannot_change_selection_and_inner_scores_are_real():
    data = candles(360)
    body = request(parameters={"strategy": "ema", "candles": 360}, selection="nested")
    result = WalkForwardEngine().run(data, body)
    assert result["method"] == "nested-next-open-v1"
    assert result == WalkForwardEngine().run(data, body)
    changed = deepcopy(data)
    for index, row in enumerate(changed[216:]):
        for key in ("open", "high", "low", "close"):
            row[key] *= 2 + index / 100
    other = WalkForwardEngine().run(changed, body)
    first = result["folds"][0]
    assert first["training_ranking"] == other["folds"][0]["training_ranking"]
    assert first["selected"] == other["folds"][0]["selected"]
    assert first["out_of_sample"]["curve"] != other["folds"][0]["out_of_sample"]["curve"]
    work = 0
    for fold in result["folds"]:
        for candidate in fold["training_ranking"]:
            parameters = body.parameters.model_copy(update=candidate["overrides"])
            windows = candidate["inner_results"]
            assert len(windows) == body.inner_folds
            assert candidate["return_pct"] == mean(row["return_pct"] for row in windows)
            assert candidate["max_drawdown"] == max(row["max_drawdown"] for row in windows)
            assert candidate["trades"] == sum(row["trades"] for row in windows)
            for interval in windows:
                assert interval["last_candle"] < fold["train"]["end"] == fold["test"]["start"]
                start = next(i for i, r in enumerate(data) if r["timestamp"] == interval["start"])
                end = start + interval["bars"]
                direct = BacktestEngine().run(data[:end], parameters, evaluation_start=start)
                assert all(
                    interval[key] == direct[key]
                    for key in ("return_pct", "sharpe", "max_drawdown", "trades", "fees")
                )
                work += end
        end = (
            next(i for i, r in enumerate(data) if r["timestamp"] == fold["test"]["start"])
            + fold["test"]["bars"]
        )
        work += 2 * end
    assert result["processed_bars"] == work


def test_nested_work_budget_rejects_before_any_simulation(monkeypatch):
    body = request(parameters={"strategy": "ema", "candles": 360}, selection="nested")
    monkeypatch.setattr("sibyl.strategies.validation.MAX_WORK_BARS", 100)
    monkeypatch.setattr(BacktestEngine, "run", lambda *a, **k: pytest.fail("Simulation ran before admission"))
    with pytest.raises(ValueError, match="60,000"):
        WalkForwardEngine().run(candles(360), body)


def test_nested_insufficient_inner_context_or_no_eligible_candidate_fails():
    with pytest.raises(ValueError, match="inner window"):
        WalkForwardEngine().run(candles(), request(selection="nested", inner_folds=4))
    data = candles(360)
    for row in data:
        row.update(open=100, close=100, high=101, low=99)
    with pytest.raises(ValueError, match="minimum training trades"):
        WalkForwardEngine().run(
            data,
            request(parameters={"strategy": "ema", "candles": 360}, selection="nested", min_train_trades=1),
        )


def test_saved_nested_replay_and_native_broker_keep_exact_inner_evidence(portable_model, client):
    from test_agent_guidance import tool_call

    service, data, dataset, _ = portable_model
    body = request(
        dataset_id=dataset["id"],
        parameters={"strategy": "ema", "candles": len(data)},
        grid={"fast_period": [5, 9]},
        selection="nested",
    )
    response = client.post("/api/v1/strategies/validations", json=body.model_dump())
    assert response.status_code in (200, 201), response.text
    saved = response.json()
    replay = client.post(f"/api/v1/strategies/validations/{saved['id']}/rerun")
    assert replay.status_code in (200, 201), replay.text
    assert replay.json()["folds"] == saved["folds"]
    evidence = tool_call(client, "broker", "validation_report", validation_id=saved["id"])
    assert evidence["selected_window"]["selection"]["mode"] == "nested"
    assert evidence["selected_window"]["training_ranking"] == saved["folds"][0]["training_ranking"]
