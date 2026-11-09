"""Purged chronological refits of a saved numerical recipe, with no future-data selection.

Every fold fits/scales on training data, fixes a radius from later calibration
errors, then scores only targets inside the still-later test block. Prior test
observations may join subsequent training windows, exactly as time advances.
"""

import numpy as np

from sibyl.forecasting.engine import (
    COVERAGE,
    engine_for,
    features,
    fingerprint,
    fit_horizon,
    metrics,
    score_horizon,
    validate,
)
from sibyl.market_data.archive import iso, step_ms

ROLLING_ENGINE = "chronos-rolling-1"


def evaluate(candles, recipe, request):
    """Refit a fixed recipe at each boundary; retain all fits, boundaries and test traces."""
    logs, times = validate(candles, 360)
    n, lags, h = len(logs), recipe["lags"], request.horizon
    family = recipe.get("family", "ridge")
    if family == "mlp" and (n > 1000 or h > 14):
        raise ValueError("Neural rolling studies support at most 1,000 candles and 14 forecast days.")
    if family == "huber" and n > 2000:
        raise ValueError("Huber rolling studies support at most 2,000 actual input candles.")
    if h > recipe["max_horizon"]:
        raise ValueError("Choose a horizon supported by the selected model recipe.")
    if min(request.test_days, request.calibration_days) - h < 20:
        raise ValueError("Calibration and test windows each need at least horizon + 20 days.")
    first = n - request.folds * request.test_days
    minimum_training = (
        lags + max(60, 3 * (lags + (6 if recipe.get("feature_set") == "returns_context" else 0))) + h
    )
    earliest_end = first - request.calibration_days
    available = earliest_end if request.window == "expanding" else request.training_days
    if earliest_end < minimum_training or available < minimum_training:
        raise ValueError(
            f"The first fold needs at least {minimum_training} training days before calibration. Use fewer folds, shorter test/calibration windows or more input data."
        )
    if request.window == "rolling" and request.training_days > earliest_end:
        raise ValueError(
            "The fixed training window starts before the saved input. Use fewer training days or fewer folds."
        )
    x, folds = features(logs, lags, recipe.get("feature_set", "returns")), []

    def partition(start, end):
        return {
            "start": iso(times[start]),
            "end": iso(times[end - 1] + step_ms("1d")),
            "candles": end - start,
            "start_index": start,
            "end_index": end,
        }

    for index in range(request.folds):
        test_start = first + index * request.test_days
        test_end = test_start + request.test_days
        train_end = test_start - request.calibration_days
        train_start = 0 if request.window == "expanding" else train_end - request.training_days
        training = np.arange(train_start + lags, train_end - h)
        calibration = np.arange(train_end, test_start - h)
        test = np.arange(test_start, test_end - h)
        model, predictions = fit_horizon(
            logs, x, lags, recipe["alpha"], h, training, calibration, family, recipe.get("huber_delta", 1.35)
        )
        drift = float(np.diff(logs[train_start:train_end]).mean())
        evidence = score_horizon(logs, times, predictions, model, test, drift, lags)
        folds.append(
            {
                "index": index + 1,
                "partitions": {
                    "train": partition(train_start, train_end),
                    "calibration": partition(train_end, test_start),
                    "test": partition(test_start, test_end),
                },
                "fitted": model,
                "training_drift": drift,
                "evaluation": evidence,
            }
        )
    traces = [row for fold in folds for row in fold["evaluation"]["trace"]]
    actual = np.asarray([row["actual"] for row in traces])
    aggregate = {
        key: metrics(actual, np.asarray([row[field] for row in traces]))
        for key, field in (("model", "predicted"), ("naive", "naive"), ("drift", "drift"))
    }
    aggregate.update(
        samples=len(traces),
        mae_skill_vs_naive_pct=(1 - aggregate["model"]["mae"] / aggregate["naive"]["mae"]) * 100
        if aggregate["naive"]["mae"] > 1e-12
        else None,
        coverage_pct=float(np.mean([row["lower"] <= row["actual"] <= row["upper"] for row in traces]) * 100),
        mean_interval_width_pct=float(
            np.mean([(row["upper"] - row["lower"]) / row["actual"] for row in traces]) * 100
        ),
        positive_skill_folds=sum(
            fold["evaluation"]["mae_skill_vs_naive_pct"] is not None
            and fold["evaluation"]["mae_skill_vs_naive_pct"] > 0
            for fold in folds
        ),
    )
    result = {
        "engine": ROLLING_ENGINE,
        "ridge_engine": engine_for(recipe.get("feature_set", "returns"), family),
        "numpy_version": np.__version__,
        "parameters": request.model_dump(),
        "recipe": recipe,
        "nominal_coverage": COVERAGE,
        "folds": folds,
        "aggregate": aggregate,
        "notes": [
            "Each fold refits a fixed recipe on earlier data, calibrates a fixed band, then scores the next test block. This does not change or assess the original saved coefficients.",
            "Targets crossing train/calibration/test boundaries are purged. Later folds may train on earlier folds' now-observed test data.",
            "Test price features update at each daily origin, while that fold's coefficients and band width remain fixed. Boundary purging leaves unscored gaps between test blocks.",
            "Metrics pool identical out-of-sample targets across methods; RMSE and skill are recomputed from pooled errors, not averaged percentages.",
            "Multi-day targets overlap within a fold. Time dependence limits interpretation; nominal 90% bands do not guarantee future coverage.",
            "The input and recipe may already have been inspected by the user. Repeated experiments can overfit this history; this is not a new independent holdout or live forward test.",
            "Historical forecast accuracy is not a trading-return or profitability measure. No model is selected, deployed or automatically recalibrated.",
        ],
    }
    fingerprint(result)
    return result
