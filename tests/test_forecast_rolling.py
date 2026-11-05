"""Chronological recipe evaluation: causality, purged boundaries, pooled scoring and saved native evidence."""

import copy
import json
from datetime import datetime

import numpy as np
import pytest
from protolink import Task
from pydantic import ValidationError
from test_forecasting import candles
from test_forecasting import model_input as model_input

from sibyl.forecasting.contracts import RollingEvaluationRequest
from sibyl.forecasting.engine import fingerprint
from sibyl.forecasting.rolling import evaluate
from sibyl.forecasting.service import ForecastModels

RECIPE = {"lags": 14, "alpha": 1.0, "max_horizon": 30}


def test_folds_refit_only_before_their_test_window_and_purge_cross_boundary_targets():
    request = RollingEvaluationRequest(folds=3, horizon=7)
    report = evaluate(candles(), RECIPE, request)
    all_targets = []
    for fold in report["folds"]:
        train, calibration, test = (fold["partitions"][name] for name in ("train", "calibration", "test"))
        assert train["end"] == calibration["start"] and calibration["end"] == test["start"]
        assert fold["fitted"]["training_samples"] == train["candles"] - RECIPE["lags"] - request.horizon
        assert fold["fitted"]["calibration_samples"] == request.calibration_days - request.horizon
        assert fold["evaluation"]["samples"] == request.test_days - request.horizon
        assert fold["evaluation"]["overlapping_targets"]
        for row in fold["evaluation"]["trace"]:
            assert test["start"] < row["origin"] < row["timestamp"] <= test["end"]
            assert (
                datetime.fromisoformat(row["timestamp"]) - datetime.fromisoformat(row["origin"])
            ).days == 7
            all_targets.append(row["timestamp"])
    assert len(set(all_targets)) == len(all_targets)  # No repeated scoring across folds.
    assert (
        report["folds"][1]["partitions"]["train"]["candles"]
        > report["folds"][0]["partitions"]["train"]["candles"]
    )


def test_future_test_prices_cannot_change_any_fit_band_or_earlier_predictions():
    data = candles()
    request = RollingEvaluationRequest(folds=3)
    first = evaluate(data, RECIPE, request)
    changed = copy.deepcopy(data)
    start = first["folds"][-1]["partitions"]["test"]["start_index"]
    for index in range(start, len(changed)):
        changed[index]["close"] *= float(np.exp((index - start + 1) * 0.01))
    second = evaluate(changed, RECIPE, request)
    assert first["folds"][:-1] == second["folds"][:-1]
    assert [fold["fitted"] for fold in first["folds"]] == [fold["fitted"] for fold in second["folds"]]
    assert first["aggregate"] != second["aggregate"]


def test_prior_test_observations_only_enter_later_fits_after_the_calibration_lag():
    data = candles()
    request = RollingEvaluationRequest(folds=3)
    first = evaluate(data, RECIPE, request)
    start = first["folds"][0]["partitions"]["test"]["start_index"]
    changed = copy.deepcopy(data)
    for i in range(start, start + 30):
        changed[i]["close"] *= float(np.exp((i - start + 1) * 0.01))
    second = evaluate(changed, RECIPE, request)
    assert first["folds"][0]["fitted"] == second["folds"][0]["fitted"]
    assert first["folds"][1]["fitted"]["coefficients"] == second["folds"][1]["fitted"]["coefficients"]
    assert first["folds"][2]["fitted"]["coefficients"] != second["folds"][2]["fitted"]["coefficients"]


def test_fixed_window_ignores_older_prices_and_keeps_training_sample_size_constant():
    data = candles()
    request = RollingEvaluationRequest(window="rolling", training_days=180)
    first = evaluate(data, RECIPE, request)
    oldest = first["folds"][0]["partitions"]["train"]["start_index"]
    changed = copy.deepcopy(data)
    for i in range(oldest):
        changed[i]["close"] *= 4
    assert evaluate(changed, RECIPE, request) == first
    assert {fold["partitions"]["train"]["candles"] for fold in first["folds"]} == {180}


def test_pooled_error_and_coverage_are_recomputed_over_all_actual_targets():
    result = evaluate(candles(), RECIPE, RollingEvaluationRequest(folds=3))
    rows = [r for fold in result["folds"] for r in fold["evaluation"]["trace"]]
    error = np.asarray([r["predicted"] - r["actual"] for r in rows])
    naive_error = np.asarray([r["naive"] - r["actual"] for r in rows])
    assert result["aggregate"]["samples"] == len(rows)
    assert result["aggregate"]["model"]["rmse"] == pytest.approx(np.sqrt(np.mean(error**2)))
    assert result["aggregate"]["mae_skill_vs_naive_pct"] == pytest.approx(
        (1 - np.mean(abs(error)) / np.mean(abs(naive_error))) * 100
    )
    assert result["aggregate"]["coverage_pct"] == pytest.approx(
        sum(r["lower"] <= r["actual"] <= r["upper"] for r in rows) / len(rows) * 100
    )
    assert fingerprint(result) == fingerprint(evaluate(candles(), RECIPE, RollingEvaluationRequest(folds=3)))


def test_constant_prices_have_undefined_skill_and_finite_exact_predictions():
    result = evaluate(candles(flat=True), RECIPE, RollingEvaluationRequest(horizon=1))
    assert result["aggregate"]["mae_skill_vs_naive_pct"] is None
    assert result["aggregate"]["model"]["mae"] == 0
    assert result["aggregate"]["coverage_pct"] == 100
    assert not result["folds"][0]["evaluation"]["overlapping_targets"]
    fingerprint(result)


@pytest.mark.parametrize(
    "changes",
    [
        {"folds": True},
        {"folds": 9},
        {"test_days": 20},
        {"calibration_days": 366},
        {"horizon": 0},
        {"training_days": 180},
        {"window": "rolling"},
        {"window": "rolling", "training_days": True},
        {"seed": 42},
        {"horizon": 7.5},
    ],
)
def test_ambiguous_or_unbounded_requests_are_rejected(changes):
    with pytest.raises(ValidationError):
        RollingEvaluationRequest(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"folds": 8, "test_days": 180},
        {"horizon": 30, "test_days": 30},
        {"horizon": 30, "calibration_days": 30},
        {"window": "rolling", "training_days": 120, "horizon": 30},
        {"window": "rolling", "training_days": 1000},
    ],
)
def test_infeasible_windows_fail_instead_of_shrinking_the_plan(changes):
    with pytest.raises(ValueError):
        evaluate(candles(360), {**RECIPE, "lags": 30}, RollingEvaluationRequest(**changes))
    with pytest.raises(ValueError, match="supported"):
        evaluate(candles(), {**RECIPE, "max_horizon": 1}, RollingEvaluationRequest(horizon=7))


def test_saved_evidence_and_exact_rerun_are_offline_and_do_not_mutate_model(model_input, monkeypatch):
    owner, _, _, body = model_input
    model = owner.train(body)["model"]
    before = owner.export(model["id"])
    monkeypatch.setattr(
        owner.market, "candles", lambda *a, **k: pytest.fail("Rolling report fetched provider data")
    )
    request = RollingEvaluationRequest()
    report = owner.evaluations.run(model["id"], request)
    rerun = owner.evaluations.run(model["id"], request)
    assert report["id"] != rerun["id"] and report["result_fingerprint"] == rerun["result_fingerprint"]
    assert owner.export(model["id"]) == before and len(owner.list()["items"]) == 1
    reopened = ForecastModels(owner.market, owner.store)
    assert reopened.evaluations.detail(report["id"]) == report
    assert reopened.evaluations.list(model["id"])["items"][0]["id"] == rerun["id"]
    assert "result" not in reopened.evaluations.list(model["id"])["items"][0]


def test_fit_admission_failure_rollback_and_recovery(model_input, monkeypatch):
    owner, _, _, body = model_input
    identity = owner.train(body)["model"]["id"]
    owner._training.acquire()
    try:
        with pytest.raises(ValueError, match="already running"):
            owner.evaluations.run(identity, RollingEvaluationRequest())
        with pytest.raises(ValueError, match="already training"):
            owner.train(body)
    finally:
        owner._training.release()
    solve = np.linalg.solve
    calls = 0

    def fail_second(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("Controlled fit failure")
        return solve(*args)

    monkeypatch.setattr(np.linalg, "solve", fail_second)
    with pytest.raises(ValueError):
        owner.evaluations.run(identity, RollingEvaluationRequest())
    assert owner.evaluations.list(identity)["items"] == []
    monkeypatch.setattr(np.linalg, "solve", solve)
    assert owner.evaluations.run(identity, RollingEvaluationRequest())["result"]["aggregate"]["samples"] > 0


def test_report_retention_and_corruption_are_explicit(model_input):
    owner, _, _, body = model_input
    identity = owner.train(body)["model"]["id"]
    first = owner.evaluations.run(identity, RollingEvaluationRequest())
    for _ in range(10):
        owner.evaluations.run(identity, RollingEvaluationRequest())
    assert len(owner.evaluations.list(identity)["items"]) == 10
    with pytest.raises(LookupError):
        owner.evaluations.detail(first["id"])
    saved = owner.evaluations.list(identity)["items"][0]
    full = owner.evaluations.detail(saved["id"])
    full["result"]["folds"][0]["fitted"]["intercept"] += 1
    with owner.store.db() as db:
        db.execute("UPDATE forecast_evaluations SET payload=? WHERE id=?", (json.dumps(full), saved["id"]))
    with pytest.raises(ValueError, match="integrity"):
        owner.evaluations.detail(saved["id"])


def test_http_and_native_chronos_read_exact_selected_report_without_new_fits(
    client, model_input, monkeypatch
):
    owner, _, _, body = model_input
    identity = owner.train(body)["model"]["id"]
    monkeypatch.setattr(owner.market, "candles", lambda *a, **k: pytest.fail("Unexpected provider read"))
    response = client.post(f"/api/v1/forecast-models/{identity}/evaluations", json={})
    assert response.status_code == 201, response.text
    report = response.json()
    url = f"/api/v1/forecast-models/evaluations/{report['id']}"
    assert client.get(url).json() == report and client.get(url).headers["Cache-Control"] == "no-store"
    assert (
        client.post(f"/api/v1/forecast-models/{identity}/evaluations", json={"folds": True}).status_code
        == 422
    )
    assert (
        client.post(
            f"/api/v1/forecast-models/{identity}/evaluations", json={"folds": 8, "test_days": 180}
        ).status_code
        == 400
    )
    reply = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "chronos",
            "message": "Explain this evaluation",
            "context": {"forecast_model_id": identity, "forecast_evaluation_id": report["id"]},
        },
    )
    assert reply.status_code == 200, reply.text
    evidence = reply.json()["evidence"]
    assert reply.json()["tool"] == "rolling_evaluation" and evidence["report"]["id"] == report["id"]
    assert "fitted" not in json.dumps(evidence) and '"trace"' not in json.dumps(evidence)
    assert "historical accuracy" in reply.json()["answer"]
    assert len(owner.evaluations.list(identity)["items"]) == 1
    network = client.app.state.services.agents.network
    result = client.portal.call(
        network.client.send_task,
        network.cards["chronos"].url,
        Task.create_tool_call("rolling_evaluation", {"evaluation_id": report["id"]}),
    )
    result.raise_for_status()
    assert result.get_last_item().parts[-1].as_tool_output().result["report"]["id"] == report["id"]
    missing = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "chronos",
            "message": "Explain",
            "context": {"forecast_model_id": identity, "forecast_evaluation_id": "f" * 32},
        },
    )
    assert missing.status_code == 404
    other = owner.train(body)["model"]["id"]
    mismatch = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "chronos",
            "message": "Explain",
            "context": {"forecast_model_id": other, "forecast_evaluation_id": report["id"]},
        },
    )
    assert mismatch.status_code == 404


def test_workspace_retention_is_bounded_and_foreign_models_stay_distinct(model_input):
    owner, _, _, body = model_input
    identity = owner.train(body)["model"]["id"]
    first = owner.evaluations.run(identity, RollingEvaluationRequest())
    # Seed independent historical receipts to exercise the workspace-wide cap without 100 refits.
    with owner.store.db() as db:
        for i in range(100):
            row = {**first, "id": f"{i:032x}", "model_id": f"{i + 100:032x}"}
            row["fingerprint"] = fingerprint({k: v for k, v in row.items() if k != "fingerprint"})
            db.execute(
                "INSERT INTO forecast_evaluations VALUES(?,?,?)",
                (row["id"], row["model_id"], json.dumps(row)),
            )
    latest = owner.evaluations.run(identity, RollingEvaluationRequest())
    with owner.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM forecast_evaluations").fetchone()[0] == 100
    with pytest.raises(LookupError):
        owner.evaluations.detail(first["id"])
    assert owner.evaluations.detail(latest["id"])["model_id"] == identity
