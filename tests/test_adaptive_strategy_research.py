"""Actual native samplers, chronological isolation, plugin pins and durable research jobs."""

from copy import deepcopy
from uuid import uuid4

import pytest
from pydantic import ValidationError
from test_strategy_plugins import custom as custom
from test_strategy_plugins import installed as installed
from test_strategy_plugins import request as plugin_request
from test_strategy_validation import candles

from sibyl.operations.jobs.contracts import CreateJob
from sibyl.strategies.research.adaptive.contracts import AdaptiveStudy, Distribution
from sibyl.strategies.research.adaptive.engine import AdaptiveEngine, available


@pytest.fixture
def optuna():
    return pytest.importorskip(
        "optuna", reason="Native adaptive sampler acceptance requires the optimization extra."
    )


def recipe(**changes):
    return AdaptiveStudy(
        **{
            "dataset_id": "a" * 64,
            "parameters": {"strategy": "ema", "candles": 180},
            "distributions": {
                "fast_period": {"kind": "int", "low": 4, "high": 10},
                "slow_period": {"kind": "int", "low": 15, "high": 30},
            },
            "trials": 8,
            "folds": 2,
            **changes,
        }
    )


@pytest.mark.parametrize("sampler", ["tpe", "random"])
def test_actual_sampler_reproducibility_and_future_prices_do_not_change_first_training_choices(
    optuna, sampler
):
    bars = candles()
    body = recipe(sampler=sampler)
    original = AdaptiveEngine().run(bars, body)
    repeat = AdaptiveEngine().run(bars, body)
    assert original["decision_fingerprint"] == repeat["decision_fingerprint"]
    changed = deepcopy(bars)
    boundary = len(bars) * body.initial_train_pct // 100
    for i, bar in enumerate(changed[boundary:]):
        for key in ("open", "high", "low", "close"):
            bar[key] *= 2 + i / 20
    other = AdaptiveEngine().run(changed, body)
    assert original["status"] == "completed"
    assert original["folds"][0]["trials"] == other["folds"][0]["trials"]
    assert original["folds"][0]["selected"] == other["folds"][0]["selected"]
    assert original["folds"][0]["out_of_sample"]["curve"] != other["folds"][0]["out_of_sample"]["curve"]
    assert original["sampler"]["library"] == "optuna" and original["sampler"]["version"] == optuna.__version__
    seen = []
    for fold in original["folds"]:
        assert len(fold["trials"]) == body.trials
        assert fold["train_end_exclusive"] == fold["test_start"]
        test = fold["out_of_sample"]
        seen += [point["timestamp"] for point in test["curve"]]
        assert test["initial_capital"] == body.parameters.capital
        assert test["fees"] >= 0
        assert test["final_equity"] - test["initial_capital"] == pytest.approx(
            sum(trade["pnl"] for trade in test["round_trips"])
        )
    assert len(seen) == len(set(seen)) == len(bars) - boundary


def test_invalid_sampled_relations_are_explicit_and_minimum_trade_failure_never_scores_test(optuna):
    body = recipe(
        distributions={
            "fast_period": {"kind": "int", "low": 15, "high": 20},
            "slow_period": {"kind": "int", "low": 16, "high": 21},
        },
        sampler="random",
        trials=24,
        folds=1,
    )
    result = AdaptiveEngine().run(candles(), body)
    assert any(row["state"] == "invalid_parameters" for row in result["folds"][0]["trials"])
    bars = candles()
    for bar in bars:
        bar.update(open=100, high=101, low=99, close=100)
    unavailable = AdaptiveEngine().run(bars, recipe(min_train_trades=1))
    assert (
        unavailable["status"] == "no_eligible_candidates" and unavailable["summary"]["evaluated_windows"] == 0
    )
    assert unavailable["folds"][0]["selected"] is unavailable["folds"][0]["out_of_sample"] is None
    assert all(row["state"] == "insufficient_trades" for row in unavailable["folds"][0]["trials"])


@pytest.mark.parametrize(
    "patch",
    [
        {"distributions": {"capital": {"low": 100, "high": 200}}},
        {"distributions": {"fast_period": {"kind": "float", "low": 2, "high": 9}}},
        {"distributions": {"fast_period": {"low": 1, "high": 500}}},
        {"engine": "plugin"},
        {"trials": 4},
        {"parameters": {"candles": 2500}},
    ],
)
def test_bad_study_contracts_fail_before_sampling(patch):
    with pytest.raises(ValidationError):
        recipe(**patch)


@pytest.mark.parametrize(
    "patch",
    [
        {"low": 1, "high": 5, "step": 3},
        {"low": -1, "high": 5, "log": True},
        {"kind": "float", "low": 1, "high": 5, "log": True, "step": 1},
        {"low": 1, "high": 5, "step": True},
        {"low": 1, "high": float("inf")},
    ],
)
def test_distribution_bounds_are_not_silently_rewritten(patch):
    with pytest.raises(ValidationError):
        Distribution(**patch)


def dataset(client):
    # The ordinary Demo backtest pins exactly the same research input used by the UI.
    response = client.post(
        "/api/v1/strategies/plugins/backtests",
        json={**plugin_request(client), "input_kind": "demo"},
    )
    assert response.status_code == 201, response.text
    return response.json()["dataset"]


def payload(client, data):
    plugin = next(
        item
        for item in client.get("/api/v1/strategies/plugins").json()["items"]
        if item["id"] == "fixture-momentum"
    )
    return recipe(
        dataset_id=data["id"],
        parameters={
            "strategy": "ema",
            "symbol": data["symbol"],
            "timeframe": data["timeframe"],
            "candles": data["count"],
        },
        engine="plugin",
        plugin_id=plugin["id"],
        plugin_revision=plugin["revision"],
        distributions={"period": {"kind": "int", "low": 2, "high": 15}},
        sampler="random",
    ).model_dump(mode="json")


def test_trusted_plugin_chronological_validation_offline_replay_and_changed_source_rejection(
    optuna, custom, installed, monkeypatch
):
    data = dataset(custom)
    body = payload(custom, data)
    market = custom.app.state.services.market
    monkeypatch.setattr(market, "client", lambda *args: pytest.fail("Adaptive study fetched a provider."))
    response = custom.post("/api/v1/strategies/adaptive", json=body)
    assert response.status_code == 201, response.text
    report = response.json()
    assert report["plugin"]["id"] == "fixture-momentum" and report["status"] == "completed"
    assert all(
        row["signal_fingerprint"]
        for fold in report["folds"]
        for row in fold["trials"]
        if row["state"] == "complete"
    )
    again = custom.post(f"/api/v1/strategies/adaptive/{report['id']}/rerun", json={})
    assert again.status_code == 201, again.text
    assert again.json()["decision_fingerprint"] == report["decision_fingerprint"]
    module, _ = installed
    module.write_text(module.read_text() + "\n# new revision\n")
    rejected = custom.post(f"/api/v1/strategies/adaptive/{report['id']}/rerun", json={})
    assert rejected.status_code == 400 and "implementation changed" in rejected.text
    assert custom.get(f"/api/v1/strategies/adaptive/{report['id']}").status_code == 200
    assert custom.app.state.services.strategies.jobs() == []
    with custom.app.state.services.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM exchange_orders").fetchone()[0] == 0


def test_oneoff_native_research_jobs_keep_actual_artifact_receipts_and_never_repeat(optuna, custom):
    data = dataset(custom)
    body = payload(custom, data)
    jobs = custom.app.state.services.jobs
    job = jobs.create(CreateJob(label="Pinned custom validation", kind="strategy.adaptive", arguments=body))
    receipt = jobs.start(job["id"], uuid4().hex)
    jobs.tick()
    completed = jobs.run(job["id"], receipt["id"])
    assert completed["state"] == "completed", completed
    report = custom.app.state.services.strategies.adaptive.get(completed["result"]["report_id"])
    assert report["plugin"]["id"] == "fixture-momentum"
    with pytest.raises(ValueError, match="one-off"):
        jobs.create(
            CreateJob(
                label="No repeated optimization",
                kind="strategy.adaptive",
                arguments=body,
                interval_seconds=60,
            )
        )
    restarted = type(jobs)(jobs.store, list(jobs.handlers.values()))
    assert restarted.run(job["id"], receipt["id"])["state"] == "completed"


def test_missing_optional_sampler_has_an_honest_setup_message_and_saved_reads_still_work(custom, monkeypatch):
    from sibyl.strategies.research.adaptive import engine

    monkeypatch.setattr(engine, "find_spec", lambda _: None)
    assert not available()
    # Verify the dependency failure path without importing/using a provider.
    import builtins

    original = builtins.__import__

    def import_module(name, *args, **kwargs):
        if name == "optuna":
            raise ImportError("not installed")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_module)
    with pytest.raises(ValueError, match="optimization extra"):
        engine.optuna_module()


def test_native_broker_and_no_model_page_snapshot_keep_selected_study_and_window(optuna, custom, monkeypatch):
    from test_agent_guidance import tool_call

    data = dataset(custom)
    body = payload(custom, data)
    created = custom.post("/api/v1/strategies/adaptive", json=body)
    assert created.status_code == 201, created.text
    report = created.json()
    monkeypatch.setattr(
        custom.app.state.services.market,
        "client",
        lambda *args: pytest.fail("A saved report opened a provider."),
    )
    observed = tool_call(custom, "broker", "adaptive_report", study_id=report["id"], window=2)
    assert observed["window"]["index"] == 2
    assert observed["window"]["trials"] == report["folds"][1]["trials"]
    assert len(observed["window"]["recent_test_round_trips"]) <= 10
    assert "out_of_sample" not in observed["window"]
    response = custom.post(
        "/api/v1/agents/ask",
        json={
            "module": "broker",
            "message": "Explain this selected research study",
            "context": {"adaptive_study_id": report["id"], "adaptive_window": 2},
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["evidence"]["selected_adaptive"]["id"] == report["id"]
    assert result["evidence"]["selected_adaptive"]["window"]["index"] == 2
    assert "historical research" in result["answer"]


def test_queue_rejects_impossible_work_and_unpinned_plugins_before_admission(optuna, custom):
    data = dataset(custom)
    body = payload(custom, data)
    body.update(folds=5)
    # A short dataset cannot provide twenty independent bars per window.
    response = custom.post(
        "/api/v1/workspace/jobs",
        json={
            "label": "Bad window coverage",
            "kind": "strategy.adaptive",
            "arguments": body,
        },
    )
    assert response.status_code == 400 and "twenty" in response.text
    from test_strategy_plugins import request as plugin_request

    rejected = custom.post(
        "/api/v1/workspace/jobs",
        json={
            "label": "No implicit live input",
            "kind": "strategy.plugin",
            "arguments": plugin_request(custom),
        },
    )
    assert rejected.status_code == 400 and "immutable saved dataset" in rejected.text
