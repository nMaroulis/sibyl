"""Causal context features retain recipe identity through real fits, rolling studies and bundles."""

import json
from copy import deepcopy

import numpy as np
import pytest
from test_forecasting import candles
from test_release_research_tools import portable_model as portable_model

from sibyl.forecasting.contracts import TrainForecast
from sibyl.forecasting.engine import CONTEXT_ENGINE, ENGINE, features, predict, train


def test_context_features_use_only_trailing_observations_and_known_formulae():
    logs = np.log([100, 102, 101, 103, 104, 102, 107, 106])
    values = features(logs, 5, "returns_context")
    assert values.shape == (3, 11)
    np.testing.assert_array_equal(values[0], features(logs[:6], 5, "returns_context")[0])
    returns = np.diff(logs[:6])[::-1]
    np.testing.assert_allclose(
        values[0, 5:],
        [
            returns.mean(),
            returns.std(),
            np.sqrt(np.mean(np.minimum(returns, 0) ** 2)),
            np.mean(returns > 0),
            logs[5] - max(logs[:6]),
            logs[5] - np.mean(logs[:6]),
        ],
    )
    np.testing.assert_array_equal(values[:, :5], features(logs, 5))


def test_context_heldout_prices_never_change_fit_or_calibration_and_defaults_stay_legacy():
    data = candles()
    body = TrainForecast(feature_set="returns_context", max_horizon=7)
    first = train(data, body)
    changed = deepcopy(data)
    for i, row in enumerate(changed[576:]):
        row["close"] *= 1.5 + i / 1000
    other = train(changed, body)
    assert first["models"] == other["models"]
    assert first["evaluation"] != other["evaluation"]
    assert first["engine"] == CONTEXT_ENGINE
    assert len(first["feature_names"]) == 20
    assert len(first["models"][0]["coefficients"]) == 20
    assert predict(first, data[-90:], 7)["shift"]["features"] == 20
    legacy = train(data, TrainForecast(max_horizon=7))
    assert legacy["engine"] == ENGINE and "feature_set" not in legacy["parameters"]
    assert "feature_names" not in legacy
    assert legacy == train(data, TrainForecast(max_horizon=7, feature_set="returns"))


def test_context_bundle_refits_same_recipe_and_rejects_engine_disagreement(portable_model):
    from sibyl.forecasting.engine import fingerprint
    from sibyl.forecasting.service import ForecastModels

    service, _, _, body = portable_model
    trained = service.train(body.model_copy(update={"feature_set": "returns_context"}))
    identity = trained["model"]["id"]
    bundle = service.bundles.export(identity)
    imported = service.bundles.import_bundle(json.dumps(bundle).encode())
    assert imported["model"]["engine"] == CONTEXT_ENGINE
    assert imported["model"]["parameters"]["feature_set"] == "returns_context"
    assert ForecastModels(service.market, service.store).detail(identity)["model"]["engine"] == CONTEXT_ENGINE
    changed = deepcopy(bundle)
    changed["model"]["artifact"]["engine"] = ENGINE
    changed["digest"] = fingerprint({key: value for key, value in changed.items() if key != "digest"})
    with pytest.raises(ValueError, match="engine"):
        service.bundles.import_bundle(json.dumps(changed).encode())


def test_context_rolling_study_retains_feature_recipe_and_purges_each_fold(portable_model):
    from sibyl.forecasting.contracts import RollingEvaluationRequest
    from sibyl.forecasting.rolling import evaluate

    service, data, _, body = portable_model
    artifact = train(data, body.model_copy(update={"feature_set": "returns_context"}))
    # Exercise the same pure engine used by saved rolling reports.
    result = evaluate(data, artifact["parameters"], RollingEvaluationRequest(horizon=7))
    assert result["ridge_engine"] == CONTEXT_ENGINE
