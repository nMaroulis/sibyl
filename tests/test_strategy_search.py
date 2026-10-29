"""Seeded candidate provenance, bounded computation and chronological research acceptance."""

import copy
import json

import pytest
from protolink import create_llm
from pydantic import ValidationError
from test_strategy_validation import candles, saved_request

from sibyl.strategies.backtest import BacktestEngine
from sibyl.strategies.research.search import digest
from sibyl.strategies.validation import WalkForwardEngine, WalkForwardRequest


def request(**changes):
    return WalkForwardRequest(
        **{
            "dataset_id": "a" * 64,
            "parameters": {"strategy": "ema", "candles": 180},
            "grid": {"fast_period": list(range(3, 11)), "slow_period": list(range(21, 29))},
            "search_method": "random",
            "sample_size": 8,
            "seed": 42,
            **changes,
        }
    )


def test_seeded_sample_is_distinct_reproducible_price_independent_and_bounded():
    first, plan = request().plan()
    assert first == request().candidates()
    assert [item["id"] for item in first] == list(range(1, 9))
    positions = [row["space_index"] for row in first]
    # Conformance vector for the versioned sampler; changing draw order requires a new version.
    assert positions == [30, 54, 16, 53, 10, 2, 17, 15]
    assert len(set(positions)) == 8
    assert all(1 <= position <= 64 for position in positions)
    assert positions != [row["space_index"] for row in request(seed=43).candidates()]
    assert plan["space_size"] == 64 and plan["coverage_pct"] == 12.5
    assert plan["evaluated_candidates"] == 8 and plan["seed"] == 42
    assert plan["sampler"] == "sha256-rank-v1"
    assert (
        digest({key: value for key, value in plan.items() if key != "plan_fingerprint"})
        == plan["plan_fingerprint"]
    )
    # Dict insertion order is irrelevant; value-list order is part of the recipe.
    reordered = request(grid=dict(reversed(list(request().grid.items())))).plan()[1]
    assert reordered == plan
    assert (
        request(grid={"fast_period": list(range(10, 2, -1)), "slow_period": list(range(21, 29))}).plan()[1][
            "space_fingerprint"
        ]
        != plan["space_fingerprint"]
    )


def test_maximum_finite_space_is_validated_but_only_sixteen_candidates_are_sampled():
    body = request(
        parameters={"strategy": "impulse-breakout", "candles": 180},
        grid={
            "window": list(range(10, 18)),
            "rsi_period": list(range(7, 15)),
            "band_std": [1 + i / 10 for i in range(8)],
            "volume_multiplier": [1 + i / 10 for i in range(8)],
        },
        sample_size=16,
    )
    candidates, evidence = body.plan()
    assert len(candidates) == 16 and evidence["space_size"] == 4096
    assert evidence["coverage_pct"] == 16 / 4096 * 100
    assert len(evidence["candidates"]) == 16


def test_all_draws_can_cover_a_small_space_without_replacement():
    body = request(grid={"fast_period": [5, 9], "slow_period": [18, 30]}, sample_size=4)
    _, evidence = body.plan()
    assert {row["space_index"] for row in evidence["candidates"]} == {1, 2, 3, 4}
    assert evidence["coverage_pct"] == 100


@pytest.mark.parametrize(
    "changes",
    [
        {"seed": None},
        {"seed": True},
        {"seed": -1},
        {"seed": 1.5},
        {"seed": 2**32},
        {"sample_size": None},
        {"sample_size": True},
        {"sample_size": 0},
        {"sample_size": 17},
        {"grid": {}},
        {"grid": {"fast_period": [5]}, "sample_size": 2},
        {"grid": {"fast_period": list(range(2, 11))}},
        {"grid": {"fast_period": [5, 5.0]}},
        {"grid": {"fast_period": [True]}},
        {"grid": {"fast_period": [float("nan")]}},
        {"search_method": "bayesian"},
        {"search_method": "grid"},
        {"grid": {"capital": [1000, 5000]}},
    ],
)
def test_search_contracts_reject_invalid_or_misleading_selection(changes):
    with pytest.raises(ValidationError):
        request(**changes)


def test_invalid_unsampled_combinations_are_not_silently_dropped():
    with pytest.raises(ValidationError, match="Fast EMA"):
        request(grid={"fast_period": [5, 30], "slow_period": [21, 40]}, sample_size=1)


def test_grid_limits_remain_small_and_fixed_mode_has_an_explicit_plan():
    with pytest.raises(ValidationError, match="at most 2"):
        request(
            parameters={"strategy": "rsi"},
            grid={"rsi_period": [7], "rsi_lower": [20], "rsi_upper": [60]},
            search_method="grid",
            seed=None,
            sample_size=None,
        )
    candidates, plan = request(grid={}, search_method="grid", seed=None, sample_size=None).plan()
    assert len(candidates) == 1 and plan["method"] == "fixed" and plan["coverage_pct"] == 100
    assert plan["seed"] is None


def test_only_the_recorded_sample_is_scored_and_reused_across_folds(monkeypatch):
    original, calls = BacktestEngine.run, []

    def measured(self, data, parameters, **kwargs):
        calls.append((len(data), parameters.fast_period, parameters.slow_period, kwargs["evaluation_start"]))
        return original(self, data, parameters, **kwargs)

    monkeypatch.setattr(BacktestEngine, "run", measured)
    body = request()
    report = WalkForwardEngine().run(candles(), body)
    assert len(calls) == body.folds * (body.sample_size + 2)
    selected = [(row["parameters"].fast_period, row["parameters"].slow_period) for row in body.candidates()]
    for i, fold in enumerate(report["folds"]):
        block = calls[i * 10 : (i + 1) * 10]
        assert [(row[1], row[2]) for row in block[:8]] == selected
        assert all(row[0] == fold["train"]["bars"] for row in block[:8])
        assert {row["candidate_id"] for row in fold["training_ranking"]} == set(range(1, 9))
        assert len(fold["training_ranking"]) == report["search"]["evaluated_candidates"]
        assert (
            fold["selected"]["space_index"]
            == report["search"]["candidates"][fold["selected"]["candidate_id"] - 1]["space_index"]
        )


def test_later_test_prices_never_choose_sample_or_first_training_winner():
    data, body = candles(), request()
    original = WalkForwardEngine().run(data, body)
    changed = copy.deepcopy(data)
    for i, row in enumerate(changed[108:]):
        for key in ("open", "high", "low", "close"):
            row[key] *= 2 + i / 10
    other = WalkForwardEngine().run(changed, body)
    assert other["search"] == original["search"]
    assert other["folds"][0]["training_ranking"] == original["folds"][0]["training_ranking"]
    assert other["folds"][0]["selected"] == original["folds"][0]["selected"]
    assert other["folds"][0]["out_of_sample"]["curve"] != original["folds"][0]["out_of_sample"]["curve"]


def test_random_search_keeps_the_same_work_guard_before_any_simulation(monkeypatch):
    monkeypatch.setattr(BacktestEngine, "run", lambda *a, **kw: pytest.fail("Over-budget study simulated"))
    body = request(parameters={"strategy": "ema", "candles": 10_000}, folds=1, sample_size=16)
    with pytest.raises(ValueError, match="60,000"):
        WalkForwardEngine().run(candles(10_000), body)


def api_body(client):
    return {**saved_request(client), "search_method": "random", "sample_size": 4, "seed": 17}


def test_saved_random_study_replays_offline_and_preserves_plan_rankings_and_input(client, monkeypatch):
    body = api_body(client)
    response = client.post("/api/v1/strategies/validations", json=body)
    assert response.status_code == 201, response.text
    first = response.json()
    assert first["search"]["method"] == "random" and first["search"]["space_size"] == 4
    # Full four-candidate coverage remains explicit; random draw order is still retained.
    listed = client.get("/api/v1/strategies/validations").json()[0]
    assert listed["search"] == first["search"]
    monkeypatch.setattr(
        client.app.state.services.market, "client", lambda *a: pytest.fail("Offline replay contacted a feed")
    )
    repeated = client.post(f"/api/v1/strategies/validations/{first['id']}/rerun")
    assert repeated.status_code == 201, repeated.text
    second = repeated.json()
    assert first["id"] != second["id"] and second["rerun_of"] == first["id"]
    for key in ("search", "request", "folds", "summary", "dataset"):
        assert first[key] == second[key]


def test_altered_candidate_plan_is_not_silently_replayed(client):
    first = client.post("/api/v1/strategies/validations", json=api_body(client)).json()
    with client.app.state.services.store.db() as db:
        first["search"]["candidates"][0]["space_index"] = 999
        db.execute("UPDATE strategy_validations SET payload=? WHERE id=?", (json.dumps(first), first["id"]))
    response = client.post(f"/api/v1/strategies/validations/{first['id']}/rerun")
    assert response.status_code == 400 and "search plan" in response.json()["detail"]
    assert len(client.get("/api/v1/strategies/validations").json()) == 1


def test_broker_reads_saved_sampling_evidence_through_native_protolink_without_searching(client, monkeypatch):
    report = client.post("/api/v1/strategies/validations", json=api_body(client)).json()
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    monkeypatch.setattr(
        "sibyl.agents.registry.create_llm",
        lambda *a, **kw: create_llm(
            "mock",
            sequential_responses=[
                {"type": "tool_call", "tool": "validation_report", "args": {}},
                "The recorded sample has fixed seed and coverage; held-out windows are separate.",
            ],
        ),
    )
    monkeypatch.setattr(
        client.app.state.services.strategies.validation,
        "run",
        lambda *a, **kw: pytest.fail("Agent ran a search"),
    )
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "broker",
            "message": "Explain this random search.",
            "context": {"validation_id": report["id"]},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["evidence"]["search"] == report["search"]
    assert response.json()["observations"][0]["tool"] == "validation_report"


def test_tool_mode_broker_reads_selected_study_without_an_llm_or_new_simulation(client, monkeypatch):
    report = client.post("/api/v1/strategies/validations", json=api_body(client)).json()
    monkeypatch.setattr(
        client.app.state.services.strategies.validation,
        "run",
        lambda *a, **kw: pytest.fail("Snapshot reran a search"),
    )
    monkeypatch.setattr(
        client.app.state.services.market, "client", lambda *a: pytest.fail("Snapshot read live prices")
    )
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "broker",
            "message": "Explain this random search.",
            "context": {"validation_id": report["id"]},
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["mode"] == "tools" and "Demo study" in result["answer"] and "seed 17" in result["answer"]
    assert result["evidence"]["selected_validation"]["search"] == report["search"]
