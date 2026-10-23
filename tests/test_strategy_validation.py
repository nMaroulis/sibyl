"""Chronological selection boundaries, honest test accounting and offline study replay."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from math import sin

import pytest
from pydantic import ValidationError

from sibyl.strategies.backtest import BacktestEngine
from sibyl.strategies.validation import (
    SEARCH_FIELDS,
    StrategyValidation,
    ValidationParameters,
    WalkForwardEngine,
    WalkForwardRequest,
)


def candles(count=180):
    """Alternating trends give the actual rule engine completed round trips."""
    result = []
    for i in range(count):
        close = 100 + i / 10 + 15 * sin(i / 7)
        opening = close - 0.5
        result.append(
            {
                "timestamp": (datetime(2025, 1, 1, tzinfo=UTC) + timedelta(days=i)).isoformat(),
                "open": opening,
                "high": close + 1,
                "low": opening - 1,
                "close": close,
                "volume": 1000,
            }
        )
    return result


def request(**changes):
    return WalkForwardRequest(
        **{
            "dataset_id": "a" * 64,
            "parameters": {"strategy": "ema", "candles": 180},
            "grid": {"fast_period": [5, 9], "slow_period": [18, 30]},
            **changes,
        }
    )


def test_future_prices_cannot_change_first_training_ranking_or_selection():
    bars, body = candles(), request()
    original = WalkForwardEngine().run(bars, body)
    changed = deepcopy(bars)
    cutoff = len(bars) * body.initial_train_pct // 100
    for i, bar in enumerate(changed[cutoff:]):
        for key in ("open", "high", "low", "close"):
            bar[key] *= 2 + i / 10
    other = WalkForwardEngine().run(changed, body)
    assert original["folds"][0]["training_ranking"] == other["folds"][0]["training_ranking"]
    assert original["folds"][0]["selected"] == other["folds"][0]["selected"]
    assert original["folds"][0]["out_of_sample"]["curve"] != other["folds"][0]["out_of_sample"]["curve"]


def test_windows_are_disjoint_complete_and_start_in_cash_with_prior_indicator_context():
    bars, body = candles(), request(grid={})
    result = WalkForwardEngine().run(bars, body)
    test_times = []
    for fold in result["folds"]:
        test = fold["out_of_sample"]
        test_times += [p["timestamp"] for p in test["curve"]]
        assert test["initial_capital"] == body.parameters.capital
        assert fold["train"]["end"] == fold["test"]["start"]
        assert fold["fixed_parameters"]["return_pct"] == test["return_pct"]
        assert len(test["curve"]) == fold["test"]["bars"] == len(test["price_series"])
        assert all(fold["test"]["start"] <= f["timestamp"] < fold["test"]["end"] for f in test["fills"])
        assert test["final_equity"] - test["initial_capital"] == pytest.approx(
            sum(t["pnl"] for t in test["round_trips"])
        )
        if test["fills"]:
            assert test["fills"][0]["side"] == "buy"
            assert test["fills"][-1]["side"] == "sell"
    assert len(test_times) == len(set(test_times)) == result["summary"]["test_bars"] == 72
    assert test_times == [b["timestamp"] for b in bars[108:]]
    assert result["summary"]["mean_return_pct"] == pytest.approx(
        sum(f["out_of_sample"]["return_pct"] for f in result["folds"]) / 3
    )


def test_all_training_candidates_share_the_longest_warmup_and_ranking_uses_only_objective():
    body = request(grid={"slow_period": [21, 45]}, objective="max_drawdown")
    result = WalkForwardEngine().run(candles(), body)
    assert result["common_warmup"] == 45
    for fold in result["folds"]:
        assert fold["train"]["scored_bars"] == fold["train"]["bars"] - 45
        rows = fold["training_ranking"]
        assert rows == sorted(rows, key=lambda r: (r["max_drawdown"], r["candidate_id"]))
        assert fold["selected"]["candidate_id"] == rows[0]["candidate_id"]


def test_score_ties_are_stable_and_inactive_candidates_remain_disclosed():
    bars = candles()
    for bar in bars:
        bar.update(open=100, high=101, low=99, close=100)
    result = WalkForwardEngine().run(bars, request())
    assert all(f["selected"]["candidate_id"] == 1 for f in result["folds"])
    assert all(f["out_of_sample"]["trades"] == 0 for f in result["folds"])
    with pytest.raises(ValueError, match="minimum training trades"):
        WalkForwardEngine().run(bars, request(min_train_trades=1))


def test_test_first_open_can_use_previous_training_close_without_inheriting_position():
    bars = candles()
    body = request(grid={}, folds=1)
    result = WalkForwardEngine().run(bars, body)["folds"][0]
    direct = BacktestEngine().run(bars, body.parameters, evaluation_start=108)
    assert result["out_of_sample"] == direct
    assert direct["curve"][0]["timestamp"] == bars[108]["timestamp"]
    assert all(f["timestamp"] >= bars[108]["timestamp"] for f in direct["fills"])
    assert direct["benchmark_curve"][-1]["value"] == pytest.approx(
        body.parameters.capital * (1 + direct["benchmark_pct"] / 100)
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"grid": {"capital": [1000]}},
        {"grid": {"rsi_period": [7]}},
        {"grid": {"fast_period": []}},
        {"grid": {"fast_period": [5, 5.0]}},
        {"grid": {"fast_period": [5, 6, 7, 8, 9]}},
        {"grid": {"fast_period": [22], "slow_period": [18]}},
        {"grid": {"fast_period": [3.5]}},
        {"grid": {"fast_period": [True]}},
        {"grid": {"fast_period": [float("nan")]}},
        {"grid": {"fast_period": [float("inf")]}},
        {"grid": {"fast_period": ["5"]}},
        {"folds": True},
    ],
)
def test_invalid_or_irrelevant_candidates_are_rejected_not_silently_skipped(changes):
    with pytest.raises(ValidationError):
        request(**changes)


def test_small_windows_and_excessive_compute_are_rejected_before_simulating(monkeypatch):
    monkeypatch.setattr(BacktestEngine, "run", lambda *_a, **_kw: pytest.fail("Invalid budget simulated"))
    with pytest.raises(ValueError, match="20 bars"):
        WalkForwardEngine().run(candles(), request(folds=5, initial_train_pct=80))
    with pytest.raises(ValueError, match="training window"):
        WalkForwardEngine().run(candles(), request(grid={"slow_period": [100]}, initial_train_pct=50))
    with pytest.raises(ValueError, match="60,000"):
        WalkForwardEngine().run(candles(10000), request(parameters={"candles": 10000}))


@pytest.mark.parametrize("start", [0, 29, 180, -1, 30.5, True])
def test_engine_rejects_invalid_evaluation_boundaries(start):
    with pytest.raises(ValueError):
        BacktestEngine().run(candles(), ValidationParameters(), evaluation_start=start)


def saved_request(client):
    run = client.post("/api/v1/strategies/backtest/demo", json={"candles": 180}).json()
    return {**request().model_dump(), "dataset_id": run["dataset"]["id"], "parameters": run["parameters"]}


def test_api_retains_offline_study_and_reruns_exact_inputs_without_account_or_order_changes(
    client, monkeypatch
):
    body = saved_request(client)
    services = client.app.state.services
    before = (services.accounts.public(), services.strategies.jobs(), services.store.orders())
    monkeypatch.setattr(
        services.market, "client", lambda *_a, **_kw: pytest.fail("Validation fetched a provider")
    )
    response = client.post("/api/v1/strategies/validations", json=body)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["source"] == result["environment"] == "demo"
    assert result["dataset"]["id"] == body["dataset_id"]
    assert result["request"]["grid"] == body["grid"]
    assert len(client.get("/api/v1/strategies/validations?demo=true").json()) == 1
    assert client.get("/api/v1/strategies/validations?demo=false").json() == []
    rebuilt = StrategyValidation(services.store, services.market.archive)
    assert rebuilt.get(result["id"]) == result
    replay = client.post(f"/api/v1/strategies/validations/{result['id']}/rerun")
    assert replay.status_code == 201, replay.text
    repeated = replay.json()
    assert repeated["id"] != result["id"] and repeated["rerun_of"] == result["id"]
    for key in ("request", "folds", "summary", "dataset", "assumptions"):
        assert repeated[key] == result[key]
    assert client.get(f"/api/v1/strategies/validations/{result['id']}").json() == result
    assert (services.accounts.public(), services.strategies.jobs(), services.store.orders()) == before


def test_api_rejects_mismatched_input_and_failed_studies_are_not_saved(client):
    body = saved_request(client)
    body["parameters"]["symbol"] = "ETH/USDT"
    response = client.post("/api/v1/strategies/validations", json=body)
    assert response.status_code == 400, response.text
    assert client.get("/api/v1/strategies/validations").json() == []
    assert client.get("/api/v1/strategies/validations/missing").status_code == 404
    assert client.post("/api/v1/strategies/validations/missing/rerun").status_code == 404


def test_local_validation_lock_blocks_concurrent_searches_and_is_released_after_failure(client):
    service = client.app.state.services.strategies.validation
    body = request()
    service._lock.acquire()
    try:
        with pytest.raises(ValueError, match="Another strategy"):
            service.run(body)
    finally:
        service._lock.release()
    with pytest.raises(LookupError):
        service.run(body)
    assert service._lock.acquire(blocking=False)
    service._lock.release()


@pytest.mark.parametrize("strategy", list(SEARCH_FIELDS))
def test_every_implemented_algorithm_can_validate_its_reported_default_search(strategy):
    fields = WalkForwardEngine.options()["strategies"][strategy][:2]
    body = request(parameters={"strategy": strategy}, grid={f["key"]: f["values"] for f in fields})
    result = WalkForwardEngine().run(candles(), body)
    assert len(result["folds"]) == 3
    assert all(len(f["out_of_sample"]["curve"]) == 24 for f in result["folds"])


def test_broker_reads_selected_validation_through_native_tool_without_running_research(client, monkeypatch):
    from protolink import create_llm

    result = client.post("/api/v1/strategies/validations", json=saved_request(client)).json()
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    monkeypatch.setattr(
        "sibyl.agents.registry.create_llm",
        lambda *args, **kwargs: create_llm(
            "mock",
            sequential_responses=[
                {"type": "tool_call", "tool": "validation_report", "args": {}},
                "These are separate historical test windows, not a live return.",
            ],
        ),
    )
    monkeypatch.setattr(
        client.app.state.services.strategies.validation,
        "run",
        lambda *_a, **_kw: pytest.fail("Agent started a search"),
    )
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "broker",
            "message": "Explain this validation",
            "context": {"validation_id": result["id"]},
        },
    )
    assert response.status_code == 200, response.text
    evidence = response.json()["evidence"]
    assert evidence["id"] == result["id"]
    assert evidence["summary"] == result["summary"]
    assert evidence["selected_window"]["training_ranking"] == result["folds"][0]["training_ranking"]
