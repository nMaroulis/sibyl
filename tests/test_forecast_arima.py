"""Native ARIMA fitting/filtering, independent causal evidence and retained research workflows."""

import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest
from pydantic import ValidationError
from test_forecast_drift import drift_input as drift_input
from test_forecast_drift import save as save_drift
from test_forecasting import candles
from test_forecasting import model_input as model_input

from sibyl.forecasting.contracts import ForecastRequest, RollingEvaluationRequest, TrainForecast
from sibyl.forecasting.engine import fingerprint, predict, train
from sibyl.forecasting.families.arima import ARIMAForecaster
from sibyl.forecasting.rolling import evaluate


def recipe(**values):
    return TrainForecast(family="arima", max_horizon=7, **values)


def test_native_fit_recovers_known_ar_structure_and_forecast_matches_statsmodels():
    from statsmodels.tsa.arima.model import ARIMA

    logs = np.log([r["close"] for r in candles()])
    fitted = ARIMAForecaster.fit(logs[:432], p=1, q=0)
    assert 0.5 < fitted["training"]["parameter_values"]["ar.L1"] < 0.95
    assert fitted["training"]["converged"] and fitted["training"]["training_returns"] == 431
    values = (np.diff(logs[-90:]) - fitted["return_center"]) / fitted["return_scale"]
    reference = ARIMA(values.reshape(-1, 1), order=(1, 0, 0), trend="c").filter(
        fitted["parameters"], cov_type="none"
    )
    expected = np.cumsum(np.asarray(reference.forecast(7)) * fitted["return_scale"] + fitted["return_center"])
    np.testing.assert_allclose(ARIMAForecaster.forecast(fitted, logs, 7), expected, rtol=1e-12)


def test_fit_identifies_both_ar_and_ma_in_a_controlled_return_process():
    rng = np.random.default_rng(833)
    innovations = rng.normal(0, 0.01, 1000)
    values = np.zeros(1000)
    for t in range(1, len(values)):
        values[t] = 0.6 * values[t - 1] + innovations[t] + 0.35 * innovations[t - 1]
    logs = np.r_[0.0, np.cumsum(values[201:] + 0.001)]
    fitted = ARIMAForecaster.fit(logs, p=1, q=1)
    coefficients = fitted["training"]["parameter_values"]
    assert abs(coefficients["ar.L1"] - 0.6) < 0.15
    assert abs(coefficients["ma.L1"] - 0.35) < 0.15


def test_actual_arima_artifact_is_reproducible_and_bands_match_saved_recipe():
    data = candles()
    first, second = train(data, recipe()), train(data, recipe())
    assert first == second
    assert first["engine"] == "chronos-arima-1"
    assert first["parameters"] == {
        "family": "arima",
        "arima_p": 1,
        "arima_q": 1,
        "difference": 1,
        "context_candles": 90,
        "max_horizon": 7,
    }
    assert first["arima"]["training"]["converged"]
    assert all(row["training_samples"] == 431 for row in first["models"])
    output = predict(first, data[-90:], 7)
    assert "ARIMA(1,1,1)" in output["model"] and len(output["points"]) == 7
    assert output["shift"]["features"] == 89
    assert all(np.isfinite(p["value"]) and p["lower"] <= p["value"] <= p["upper"] for p in output["points"])


@pytest.mark.parametrize("partition", ["calibration", "test"])
def test_held_out_prices_never_change_fit_or_scaling_and_test_never_changes_radius(partition):
    data = candles()
    changed = copy.deepcopy(data)
    start, end = (432, 576) if partition == "calibration" else (576, 720)
    for index, row in enumerate(changed[start:end]):
        row["close"] *= float(np.exp(0.03 * np.sin(index)))
    before, after = train(data, recipe()), train(changed, recipe())
    assert before["arima"] == after["arima"]
    if partition == "test":
        assert before["models"] == after["models"]
    else:
        assert any(a["radius"] != b["radius"] for a, b in zip(before["models"], after["models"], strict=True))


def test_future_closes_cannot_change_earlier_filter_forecasts_and_context_is_exactly_90():
    logs = np.log([r["close"] for r in candles()])
    fitted = ARIMAForecaster.fit(logs[:432])
    changed = logs.copy()
    changed[650:] += np.arange(len(changed) - 650) * 0.02
    a = ARIMAForecaster.panel(fitted, logs, [610, 649, 670], 7)
    b = ARIMAForecaster.panel(fitted, changed, [610, 649, 670], 7)
    np.testing.assert_array_equal(a[[610, 649]], b[[610, 649]])
    assert not np.array_equal(a[670], b[670])
    old = logs.copy()
    old[:-90] += 3
    np.testing.assert_array_equal(
        ARIMAForecaster.forecast(fitted, old, 7), ARIMAForecaster.forecast(fitted, logs, 7)
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("arima_p", True),
        ("arima_q", False),
        ("arima_p", 1.0),
        ("arima_q", "1"),
        ("arima_p", 0),
        ("arima_p", 4),
        ("arima_q", -1),
        ("arima_q", 3),
    ],
)
def test_order_is_strict_and_bounded(field, value):
    with pytest.raises(ValidationError):
        recipe(**{field: value})


def test_family_limits_and_ignored_controls_are_rejected():
    for values in ({"arima_p": 2}, {"arima_q": 0}):
        with pytest.raises(ValidationError, match="only"):
            TrainForecast(**values)
    for values in ({"lags": 5}, {"alpha": 2.0}, {"feature_set": "returns_context"}):
        with pytest.raises(ValidationError, match="own order"):
            recipe(**values)
    with pytest.raises(ValidationError, match="14"):
        TrainForecast(family="arima")
    with pytest.raises(ValidationError, match="1,000"):
        recipe(input_kind="saved_dataset", dataset_id="0" * 64, candles=1001)
    with pytest.raises(ValueError, match="1,000"):
        train(candles(1001), recipe())
    with pytest.raises(ValueError, match="1,000"):
        evaluate(
            candles(1001),
            {"family": "arima", "arima_p": 1, "arima_q": 1, "max_horizon": 7},
            RollingEvaluationRequest(),
        )


def test_constant_return_or_short_context_is_explicitly_rejected():
    with pytest.raises(ValueError, match="varying"):
        train(candles(360, flat=True), recipe())
    artifact = train(candles(), recipe())
    with pytest.raises(ValueError, match="90"):
        predict(artifact, candles()[-89:], 7)
    with pytest.raises(ValueError, match="supported"):
        predict(artifact, candles()[-90:], 8)


def test_nonconvergence_releases_training_slot_without_saving_a_model(model_input, monkeypatch):
    service, _, _, body = model_input
    from sibyl.forecasting.families.arima import native_model

    def failed(values, p, q):
        result = native_model(values, p, q)
        original = result.fit

        def fit(**kwargs):
            fitted = original(**kwargs)
            fitted.mle_retvals["converged"] = False
            return fitted

        result.fit = fit
        return result

    monkeypatch.setattr("sibyl.forecasting.families.arima.native_model", failed)
    with pytest.raises(ValueError, match="did not converge"):
        service.train(body.model_copy(update={"family": "arima"}))
    assert service.list()["items"] == [] and not service._training.locked()


def test_iteration_cap_is_forwarded_to_native_optimizer(monkeypatch):
    captured = []

    def fake(values, p, q):
        def fit(**kwargs):
            captured.append(kwargs)
            return SimpleNamespace(
                params=np.array([0.0, 0.5, 0.1, 1.0]),
                aic=1.0,
                bic=2.0,
                llf=-1.0,
                mle_retvals={"converged": True, "iterations": 3},
                param_names=["const", "ar.L1", "ma.L1", "sigma2"],
            )

        return SimpleNamespace(fit=fit)

    monkeypatch.setattr("sibyl.forecasting.families.arima.native_model", fake)
    result = ARIMAForecaster.fit(np.log([r["close"] for r in candles(360)]))
    assert result["training"]["iterations"] == 3
    assert captured[0]["method_kwargs"]["maxiter"] == 100
    assert captured[0]["method"] == "statespace"


def test_portable_refit_and_exact_rerun_preserve_arima_order_without_provider_reads(model_input, monkeypatch):
    owner, _, _, body = model_input
    model = owner.train(body.model_copy(update={"family": "arima", "arima_q": 0}))
    identity = model["model"]["id"]
    assert model["arima_training"]["converged"]
    monkeypatch.setattr(
        owner.market, "client", lambda *a, **kw: pytest.fail("Offline ARIMA contacted provider")
    )
    rerun = owner.rerun(identity)
    assert rerun["model"]["version"] == 2 and rerun["model"]["fingerprint"] == model["model"]["fingerprint"]
    bundle = owner.bundles.export(identity)
    restored = owner.bundles.import_bundle(json.dumps(bundle).encode())
    assert restored["model"]["environment"] == "imported"
    assert restored["model"]["parameters"]["arima_q"] == 0
    assert restored["model"]["imported_from"]["recorded_fit_matches_local"]
    tampered = copy.deepcopy(bundle)
    tampered["model"]["request"]["arima_q"] = 1
    tampered["digest"] = fingerprint({k: v for k, v in tampered.items() if k != "digest"})
    with pytest.raises(ValueError, match="recipe"):
        owner.bundles.import_bundle(json.dumps(tampered).encode())
    forecast = owner.forecast(identity, ForecastRequest(horizon=7))
    assert len(forecast["points"]) == 7


def test_rolling_arima_refits_purged_windows_and_pools_actual_price_errors(model_input):
    owner, data, _, body = model_input
    model = owner.train(body.model_copy(update={"family": "arima", "arima_q": 0}))["model"]
    request = RollingEvaluationRequest(horizon=7, window="rolling", training_days=240)
    result = evaluate(data, model["parameters"], request)
    assert result["ridge_engine"] == "chronos-arima-1"
    for fold in result["folds"]:
        assert fold["fitted"]["arima"]["order"] == [1, 1, 0]
        assert fold["fitted"]["training_samples"] == 239
        bounds = fold["partitions"]
        assert all(
            bounds["test"]["start"] <= r["origin"] < r["timestamp"] <= bounds["test"]["end"]
            for r in fold["evaluation"]["trace"]
        )
    traces = [r for f in result["folds"] for r in f["evaluation"]["trace"]]
    expected = np.sqrt(np.mean([(r["predicted"] - r["actual"]) ** 2 for r in traces]))
    assert result["aggregate"]["model"]["rmse"] == pytest.approx(expected)
    changed = copy.deepcopy(data)
    for r in changed[660:]:
        r["close"] *= 1.2
    second = evaluate(changed, model["parameters"], request)
    assert result["folds"][0] == second["folds"][0]
    assert result["folds"][1]["fitted"] == second["folds"][1]["fitted"]
    before_window = copy.deepcopy(data)
    for row in before_window[:300]:
        row["close"] *= 1.4
    isolated = evaluate(before_window, model["parameters"], request)
    assert isolated["folds"] == result["folds"]
    retained = owner.evaluations.run(model["id"], request)
    assert retained["result"]["recipe"]["family"] == "arima"


def test_native_chronos_reads_actual_arima_fit_without_training_or_provider_calls(
    model_input, client, monkeypatch
):
    from protolink import create_llm

    owner, _, _, body = model_input
    model = owner.train(body.model_copy(update={"family": "arima"}))["model"]
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    monkeypatch.setattr(
        "sibyl.agents.utils.registry.create_llm",
        lambda *a, **kw: create_llm(
            "mock",
            sequential_responses=[
                {"type": "tool_call", "tool": "model_report", "args": {}},
                "Compare this ARIMA model's held-out errors and calibrated bands with its benchmarks.",
            ],
        ),
    )
    monkeypatch.setattr(owner, "train", lambda *a, **kw: pytest.fail("Chronos fitted a model"))
    monkeypatch.setattr(owner.market, "client", lambda *a, **kw: pytest.fail("Chronos fetched provider"))
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "chronos",
            "message": "Explain this ARIMA fit.",
            "context": {"forecast_model_id": model["id"]},
        },
    )
    assert response.status_code == 200, response.text
    evidence = response.json()["evidence"]
    assert evidence["arima_training"]["converged"] and evidence["model"]["parameters"]["arima_p"] == 1


def test_actual_demo_http_fit_has_real_evidence_and_does_not_activate_demo_account(manual_client):
    client = manual_client
    before = [r.model_dump() for r in client.app.state.services.store.connections()]
    response = client.post(
        "/api/v1/forecast-models",
        json={"family": "arima", "max_horizon": 7, "input_kind": "demo", "candles": 360},
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["model"]["environment"] == "demo" and result["arima_training"]["converged"]
    assert [r.model_dump() for r in client.app.state.services.store.connections()] == before
    bad = client.post(
        "/api/v1/forecast-models",
        json={"family": "arima", "max_horizon": 7, "input_kind": "demo", "arima_q": True},
    )
    assert bad.status_code == 422


def test_retained_source_candidate_preserves_arima_family_and_leaves_parent_unchanged(
    drift_input, monkeypatch
):
    from sibyl.forecasting.drift import Recalibrate

    owner, old, meta, data = drift_input
    parent = owner.train(recipe(input_kind="saved_dataset", dataset_id=old["dataset"]["id"], arima_q=0))[
        "model"
    ]
    before = owner.export(parent["id"])
    owner.market.archive.capture(meta, "BTC/USDT", "1d", data[720:])
    state = save_drift(owner, parent)
    monkeypatch.setattr(owner.market, "client", lambda *a, **kw: pytest.fail("Candidate read provider"))
    outcome = owner.drift.recalibrate(Recalibrate(model_id=parent["id"], revision=state["revision"]))
    assert outcome["status"] == "completed"
    candidate = owner.export(outcome["candidate_id"])
    assert candidate["metadata"]["parameters"]["arima_q"] == 0
    assert candidate["metadata"]["parameters"]["family"] == "arima"
    assert candidate["metadata"]["parent_id"] == parent["id"] and candidate["metadata"]["version"] == 2
    assert owner.export(parent["id"]) == before
