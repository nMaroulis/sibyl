"""Real robust fits, causal partitions and native retained-model workflows, without providers."""

import copy
import json

import numpy as np
import pytest
from pydantic import ValidationError
from test_forecast_drift import drift_input as drift_input
from test_forecast_drift import save as save_drift
from test_forecasting import candles
from test_forecasting import model_input as model_input

from sibyl.forecasting.contracts import RollingEvaluationRequest, TrainForecast
from sibyl.forecasting.engine import fingerprint, predict, train
from sibyl.forecasting.families.huber import HuberAR
from sibyl.forecasting.rolling import evaluate


def recipe(**values):
    return TrainForecast(family="huber", max_horizon=7, **values)


def test_huber_solves_robust_objective_and_limits_large_residual_influence():
    rng = np.random.default_rng(81)
    x = rng.normal(size=(500, 3))
    clean = 0.05 + x @ np.array([0.4, -0.7, 0.2]) + rng.normal(0, 0.005, 500)
    contaminated = clean.copy()
    contaminated[:25] += 20
    fitted = HuberAR.fit(x, contaminated, 0.01, 1.35)
    predictions = fitted["intercept"] + x @ fitted["coefficients"]
    baseline = np.linalg.lstsq(np.column_stack([np.ones(len(x)), x]), contaminated, rcond=None)[0]
    assert np.mean(np.abs(predictions - clean)) < np.mean(np.abs(baseline[0] + x @ baseline[1:] - clean)) / 5
    evidence = fitted["training"]
    assert evidence["converged"] and evidence["final_loss"] < evidence["initial_loss"]
    assert evidence["downweighted_samples"] >= 25 and evidence["minimum_weight"] > 0
    assert evidence["effective_weight_sum"] < 500 and evidence["feature_leverage_robust"] is False
    # Independent first-order optimality check for the stated fixed-scale objective.
    y = (contaminated - evidence["target_center"]) / evidence["target_scale"]
    beta = np.r_[
        (fitted["intercept"] - evidence["target_center"]) / evidence["target_scale"],
        np.asarray(fitted["coefficients"]) / evidence["target_scale"],
    ]
    design = np.column_stack([np.ones(len(x)), x])
    gradient = (-design.T @ np.clip(y - design @ beta, -1.35, 1.35) + np.r_[0, 0.01 * beta[1:]]) / len(x)
    assert np.max(np.abs(gradient)) < 1e-7


def test_actual_huber_artifact_is_reproducible_and_forecasts_finite_bands():
    data = candles()
    first = train(data, recipe(feature_set="returns_context", huber_delta=0.9))
    assert first == train(data, recipe(feature_set="returns_context", huber_delta=0.9))
    assert first["engine"] == "chronos-huber-context-1"
    assert first["parameters"]["huber_delta"] == 0.9
    for model in first["models"]:
        assert model["training"]["final_loss"] <= model["training"]["initial_loss"]
        assert 1 <= model["training"]["steps"] <= 60 and len(model["coefficients"]) == 20
    output = predict(first, data[-90:], 7)
    assert len(output["points"]) == 7
    assert all(np.isfinite(p["value"]) and p["lower"] <= p["value"] <= p["upper"] for p in output["points"])


@pytest.mark.parametrize("partition", ["calibration", "test"])
def test_held_out_observations_never_choose_huber_scale_weights_or_stopping(partition):
    data = candles()
    changed = copy.deepcopy(data)
    start, end = (432, 576) if partition == "calibration" else (576, 720)
    for row in changed[start:end]:
        row["close"] *= 1.5
    first, second = train(data, recipe()), train(changed, recipe())
    for a, b in zip(first["models"], second["models"], strict=True):
        assert {k: v for k, v in a.items() if k != "radius"} == {k: v for k, v in b.items() if k != "radius"}
        if partition == "test":
            assert a["radius"] == b["radius"]


def test_flat_prices_have_zero_loss_and_no_fabricated_training_outliers():
    data = candles(360, flat=True)
    artifact = train(data, recipe())
    for model in artifact["models"]:
        assert model["training"]["converged"] and model["training"]["final_loss"] == 0
        assert model["training"]["downweighted_samples"] == 0
        assert model["training"]["steps"] == 1
    output = predict(artifact, data[-90:], 7)
    assert all(point["value"] == pytest.approx(100) for point in output["points"])


def test_step_limit_is_reported_as_unconverged_not_hidden(monkeypatch):
    monkeypatch.setattr("sibyl.forecasting.families.huber.MAX_STEPS", 1)
    artifact = train(candles(), recipe())
    assert all(m["training"]["steps"] == 1 and not m["training"]["converged"] for m in artifact["models"])
    assert any("not reported as converged" in note for note in artifact["notes"])


@pytest.mark.parametrize("delta", [True, False, float("nan"), float("inf"), 0.24, 5.01])
def test_huber_threshold_is_finite_strict_and_bounded(delta):
    with pytest.raises(ValidationError):
        TrainForecast(family="huber", huber_delta=delta)


def test_family_limits_reject_ignored_controls_and_oversized_actual_inputs():
    with pytest.raises(ValidationError, match="only"):
        TrainForecast(family="ridge", huber_delta=0.9)
    with pytest.raises(ValidationError, match="2,000"):
        TrainForecast(family="huber", input_kind="saved_dataset", dataset_id="0" * 64, candles=2001)
    with pytest.raises(ValueError, match="2,000"):
        train(candles(2001), recipe())
    with pytest.raises(ValueError, match="2,000"):
        evaluate(
            candles(2001),
            {"family": "huber", "lags": 14, "alpha": 1.0, "max_horizon": 7, "huber_delta": 1.35},
            RollingEvaluationRequest(),
        )


def test_delta_is_recipe_identity_and_legacy_ridge_artifacts_remain_unchanged():
    data = candles()
    a, b = train(data, recipe(huber_delta=0.5)), train(data, recipe(huber_delta=2.0))
    assert fingerprint(a) != fingerprint(b)
    legacy = train(data, TrainForecast(max_horizon=7))
    assert legacy["engine"] == "chronos-ridge-1"
    assert legacy["parameters"] == {"lags": 14, "alpha": 1.0, "max_horizon": 7}


def test_portable_huber_refit_and_exact_rerun_use_saved_data_only(model_input, monkeypatch):
    service, data, _, body = model_input
    trained = service.train(body.model_copy(update={"family": "huber", "huber_delta": 0.8}))
    identity = trained["model"]["id"]
    assert all(row["family"] == "huber" and row["delta"] == 0.8 for row in trained["training"])
    monkeypatch.setattr(
        service.market, "client", lambda *a, **kw: pytest.fail("Offline research contacted provider")
    )
    rerun = service.rerun(identity)
    assert rerun["model"]["version"] == 2 and rerun["model"]["fingerprint"] == trained["model"]["fingerprint"]
    bundle = service.bundles.export(identity)
    restored = service.bundles.import_bundle(json.dumps(bundle).encode())
    assert restored["model"]["parameters"]["huber_delta"] == 0.8
    assert restored["model"]["imported_from"]["recorded_fit_matches_local"]
    assert restored["model"]["environment"] == "imported"
    tampered = copy.deepcopy(bundle)
    tampered["model"]["request"]["huber_delta"] = 0.9
    tampered["digest"] = fingerprint({k: v for k, v in tampered.items() if k != "digest"})
    with pytest.raises(ValueError, match="recipe"):
        service.bundles.import_bundle(json.dumps(tampered).encode())


def test_rolling_refits_preserve_family_threshold_and_causal_boundaries(model_input):
    service, data, _, body = model_input
    metadata = service.train(body.model_copy(update={"family": "huber", "huber_delta": 0.75}))["model"]
    study = RollingEvaluationRequest(horizon=7)
    first = evaluate(data, metadata["parameters"], study)
    changed = copy.deepcopy(data)
    for row in changed[660:]:
        row["close"] *= 1.3
    second = evaluate(changed, metadata["parameters"], study)
    assert first["ridge_engine"] == "chronos-huber-1"
    for before, after in zip(first["folds"], second["folds"], strict=True):
        assert before["fitted"] == after["fitted"]
        assert before["fitted"]["training"]["delta"] == 0.75
    report = service.evaluations.run(metadata["id"], study)
    assert report["result"]["recipe"]["family"] == "huber"


def test_chronos_reads_actual_huber_training_evidence_without_fitting(model_input, client, monkeypatch):
    from protolink import create_llm

    service, _, _, body = model_input
    trained = service.train(body.model_copy(update={"family": "huber", "huber_delta": 1.1}))
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    monkeypatch.setattr(
        "sibyl.agents.utils.registry.create_llm",
        lambda *a, **kw: create_llm(
            "mock",
            sequential_responses=[
                {"type": "tool_call", "tool": "model_report", "args": {}},
                "This Huber fit downweights large residuals; compare the retained held-out errors, not just its training convergence.",
            ],
        ),
    )
    monkeypatch.setattr(service, "train", lambda *a, **kw: pytest.fail("Agent fitted a model"))
    monkeypatch.setattr(service.market, "client", lambda *a, **kw: pytest.fail("Agent contacted a provider"))
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "chronos",
            "message": "Explain this robust forecast and its convergence.",
            "context": {"forecast_model_id": trained["model"]["id"]},
        },
    )
    assert response.status_code == 200, response.text
    evidence = response.json()["evidence"]
    assert evidence["model"]["engine"] == "chronos-huber-1"
    assert evidence["training"][0]["delta"] == 1.1
    assert isinstance(evidence["training"][0]["converged"], bool)


def test_actual_demo_http_training_stays_separate_from_account_and_provider_setup(manual_client):
    client = manual_client
    before = [row.model_dump() for row in client.app.state.services.store.connections()]
    response = client.post(
        "/api/v1/forecast-models",
        json={"input_kind": "demo", "family": "huber", "huber_delta": 1.2, "max_horizon": 3, "candles": 360},
    )
    assert response.status_code == 201, response.text
    model = response.json()
    assert model["model"]["environment"] == "demo"
    assert model["model"]["parameters"]["family"] == "huber"
    assert len(model["training"]) == 3 and all(row["family"] == "huber" for row in model["training"])
    assert [row.model_dump() for row in client.app.state.services.store.connections()] == before
    bad = client.post(
        "/api/v1/forecast-models",
        json={"input_kind": "demo", "family": "huber", "huber_delta": True, "max_horizon": 3, "candles": 360},
    )
    assert bad.status_code == 422


def test_retained_source_recalibration_preserves_huber_recipe_and_parent(drift_input, monkeypatch):
    from sibyl.forecasting.drift import Recalibrate

    owner, original, meta, data = drift_input
    body = TrainForecast(
        input_kind="saved_dataset",
        dataset_id=original["dataset"]["id"],
        family="huber",
        huber_delta=0.85,
        max_horizon=7,
    )
    parent = owner.train(body)["model"]
    before = owner.export(parent["id"])
    owner.market.archive.capture(meta, "BTC/USDT", "1d", data[720:])
    state = save_drift(owner, parent)
    monkeypatch.setattr(
        owner.market, "client", lambda *a, **kw: pytest.fail("Retained recalibration contacted a provider")
    )
    result = owner.drift.recalibrate(Recalibrate(model_id=parent["id"], revision=state["revision"]))
    assert result["status"] == "completed"
    candidate = owner.export(result["candidate_id"])
    assert candidate["metadata"]["parameters"]["family"] == "huber"
    assert candidate["metadata"]["parameters"]["huber_delta"] == 0.85
    assert candidate["metadata"]["version"] == 2 and candidate["metadata"]["parent_id"] == parent["id"]
    assert owner.export(parent["id"]) == before
