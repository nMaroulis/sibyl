"""Real neural fits: learning, causal partitions and portable recipe identity."""

import json
from copy import deepcopy

import numpy as np
import pytest
from pydantic import ValidationError
from test_forecasting import candles
from test_forecasting import model_input as model_input

from sibyl.forecasting.contracts import RollingEvaluationRequest, TrainForecast
from sibyl.forecasting.engine import fingerprint, predict, train
from sibyl.forecasting.rolling import evaluate


def recipe(**values):
    return TrainForecast(family="mlp", max_horizon=7, **values)


def test_neural_fit_learns_and_is_reproducible():
    data = candles()
    first = train(data, recipe(feature_set="returns_context"))
    assert first == train(data, recipe(feature_set="returns_context"))
    assert first["engine"] == "chronos-mlp-context-1"
    for model in first["models"]:
        assert model["training"]["final_loss"] < model["training"]["initial_loss"]
        assert model["training"]["epochs"] == 120
        assert np.shape(model["input_weights"]) == (20, 8)
    output = predict(first, data[-90:], 7)
    assert all(
        np.isfinite(row["value"]) and row["lower"] <= row["value"] <= row["upper"] for row in output["points"]
    )


@pytest.mark.parametrize("partition", ["test", "calibration"])
def test_held_out_prices_do_not_choose_neural_weights(partition):
    data = candles()
    changed = deepcopy(data)
    start, end = (576, 720) if partition == "test" else (432, 576)
    for row in changed[start:end]:
        row["close"] *= 1.5
    first, second = train(data, recipe()), train(changed, recipe())
    for a, b in zip(first["models"], second["models"], strict=True):
        assert {k: v for k, v in a.items() if k != "radius"} == {k: v for k, v in b.items() if k != "radius"}
        if partition == "test":
            assert a["radius"] == b["radius"]


def test_constant_neural_predictions_stay_finite():
    data = candles(360, flat=True)
    output = predict(train(data, recipe()), data[-90:], 7)
    assert all(row["value"] == pytest.approx(100, rel=1e-5) for row in output["points"])


def test_neural_bounds_cover_requests_and_actual_saved_input():
    with pytest.raises(ValidationError):
        TrainForecast(family="mlp")
    with pytest.raises(ValueError, match="1,000"):
        train(candles(1001), recipe())


def test_neural_bundle_refits_and_rolling_keeps_family(model_input):
    service, data, _, body = model_input
    trained = service.train(body.model_copy(update={"family": "mlp", "max_horizon": 7}))
    assert len(trained["training"]) == 7
    bundle = service.bundles.export(trained["model"]["id"])
    restored = service.bundles.import_bundle(json.dumps(bundle).encode())
    assert restored["model"]["engine"] == "chronos-mlp-1"
    changed = deepcopy(bundle)
    changed["model"]["artifact"]["engine"] = "chronos-ridge-1"
    changed["digest"] = fingerprint({k: v for k, v in changed.items() if k != "digest"})
    with pytest.raises(ValueError, match="engine"):
        service.bundles.import_bundle(json.dumps(changed).encode())
    result = evaluate(data, trained["model"]["parameters"], RollingEvaluationRequest(horizon=7))
    assert result["ridge_engine"] == "chronos-mlp-1"
    assert all(row["evaluation"]["samples"] > 0 for row in result["folds"])
