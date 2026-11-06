"""Direct multi-horizon ridge models with chronological train/calibration/test splits.

Features contain only daily log returns observed at the forecast origin. Every
horizon excludes targets crossing a partition boundary. Scalers, coefficients and
benchmark drift use training data only; calibration residuals set a fixed band
before the independent test window is scored. No final full-data refit is hidden.
"""

import hashlib
import json
import math

import numpy as np

from sibyl.market_data.archive import iso, milliseconds, now_ms, step_ms

ENGINE = "chronos-ridge-1"
CONTEXT_ENGINE = "chronos-ridge-context-1"


def engine_for(feature_set="returns"):
    """Keep the legacy engine exact and identify the optional richer causal recipe separately."""
    if feature_set not in {"returns", "returns_context"}:
        raise ValueError("Unsupported forecast feature recipe.")
    return CONTEXT_ENGINE if feature_set == "returns_context" else ENGINE


def parameters(request):
    """Preserve legacy artifact parameters byte-for-byte when richer features are not selected."""
    values = {key: getattr(request, key) for key in ("lags", "alpha", "max_horizon")}
    if request.feature_set != "returns":
        values["feature_set"] = request.feature_set
    return values


COVERAGE = 0.9


def fingerprint(value):
    """Hash JSON-safe numerical artifacts or exact input windows, without executable serialization."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def validate(candles, minimum=31):
    """Reject missing, open, unordered or nonpositive daily observations; never interpolate."""
    if not minimum <= len(candles) <= 5000:
        raise ValueError(f"Use {minimum}–5,000 complete daily candles.")
    times = [milliseconds(row["timestamp"]) for row in candles]
    day = step_ms("1d")
    if any(t % day for t in times) or any(b - a != day for a, b in zip(times, times[1:], strict=False)):
        raise ValueError("Forecast input must contain consecutive daily candles without gaps or duplicates.")
    if times[-1] + day > now_ms():
        raise ValueError("Forecast input includes an unfinished or future candle.")
    if any(
        type(row["close"]) not in {int, float} or not math.isfinite(row["close"]) or row["close"] <= 0
        for row in candles
    ):
        raise ValueError("Every forecast close must be a finite positive number.")
    return np.log(np.asarray([row["close"] for row in candles], dtype=float)), times


def features(log_prices, lags, feature_set="returns"):
    """Build features through close t only; all trend/volatility windows fit inside the lag context."""
    engine_for(feature_set)
    returns = np.diff(log_prices)
    lagged = np.asarray([returns[t - lags : t][::-1] for t in range(lags, len(log_prices))])
    if feature_set == "returns":
        return lagged
    context = []
    for t, row in zip(range(lags, len(log_prices)), lagged, strict=True):
        past = log_prices[t - lags : t + 1]
        context.append(
            [
                float(row.mean()),
                float(row.std()),
                float(np.sqrt(np.mean(np.minimum(row, 0) ** 2))),
                float(np.mean(row > 0)),
                float(log_prices[t] - past.max()),
                float(log_prices[t] - past.mean()),
            ]
        )
    return np.column_stack((lagged, np.asarray(context)))


def prices(log_prices):
    """Fail visibly rather than clipping an unstable or numerically unusable forecast."""
    values = np.asarray(log_prices, dtype=float)
    if not np.isfinite(values).all() or (np.abs(values) > 690).any():
        raise ValueError(
            "This model produces an unstable price range. Use another dataset or model configuration."
        )
    return np.exp(values)


def metrics(actual, predicted):
    """Score identical held-out price targets; null skill ratios stay explicitly undefined."""
    error = predicted - actual
    result = {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "mape_pct": float(np.mean(np.abs(error / actual)) * 100),
    }
    if not all(math.isfinite(value) for value in result.values()):
        raise ValueError("Input prices exceed the supported numerical evaluation range.")
    return result


def fit_horizon(logs, x, lags, alpha, horizon, training, calibration):
    """Fit one causal ridge model and calibrate it using only the supplied earlier partitions."""
    if len(training) < max(60, 3 * x.shape[1]) or len(calibration) < 20:
        raise ValueError("Use more training and calibration observations for this horizon.")
    raw = x[training - lags]
    mean, scale = raw.mean(axis=0), raw.std(axis=0)
    scale = np.where(scale < 1e-12, 1, scale)
    z = (raw - mean) / scale
    y = logs[training + horizon] - logs[training]
    intercept = float(y.mean())
    try:
        coefficients = np.linalg.solve(z.T @ z + alpha * np.eye(x.shape[1]), z.T @ (y - intercept))
    except np.linalg.LinAlgError:
        raise ValueError("This numerical fit did not converge. Choose another dataset or penalty.") from None

    predictions = intercept + ((x - mean) / scale) @ coefficients
    residuals = np.abs(logs[calibration + horizon] - logs[calibration] - predictions[calibration - lags])
    rank = math.ceil((len(residuals) + 1) * COVERAGE)
    if rank > len(residuals):
        raise ValueError("Not enough calibration observations for the selected interval.")
    radius = float(np.sort(residuals)[rank - 1])
    model = {
        "horizon": horizon,
        "mean": mean.tolist(),
        "scale": scale.tolist(),
        "coefficients": coefficients.tolist(),
        "intercept": intercept,
        "radius": radius,
        "training_samples": len(training),
        "calibration_samples": len(calibration),
        "feature_min": raw.min(axis=0).tolist(),
        "feature_max": raw.max(axis=0).tolist(),
    }
    return model, predictions


def score_horizon(logs, times, predictions, model, test, drift, lags):
    """Score one fixed fit and matching benchmarks against identical held-out price targets."""
    horizon, radius = model["horizon"], model["radius"]
    predicted_logs = logs[test] + predictions[test - lags]
    actual, predicted = prices(logs[test + horizon]), prices(predicted_logs)
    naive, drift_prices = prices(logs[test]), prices(logs[test] + drift * horizon)
    lower, upper = prices(predicted_logs - radius), prices(predicted_logs + radius)
    model_metrics, naive_metrics = metrics(actual, predicted), metrics(actual, naive)
    return {
        "horizon": horizon,
        "samples": len(test),
        "model": model_metrics,
        "naive": naive_metrics,
        "drift": metrics(actual, drift_prices),
        "mae_skill_vs_naive_pct": (1 - model_metrics["mae"] / naive_metrics["mae"]) * 100
        if naive_metrics["mae"] > 1e-12
        else None,
        "coverage_pct": float(np.mean((actual >= lower) & (actual <= upper)) * 100),
        "mean_interval_width_pct": float(np.mean((upper - lower) / actual) * 100),
        "overlapping_targets": horizon > 1,
        "trace": [
            {
                "origin": iso(times[int(t)] + step_ms("1d")),
                "timestamp": iso(times[int(t) + horizon] + step_ms("1d")),
                "actual": float(a),
                "predicted": float(p),
                "lower": float(lo),
                "upper": float(hi),
                "naive": float(b),
                "drift": float(d),
            }
            for t, a, p, lo, hi, b, d in zip(
                test, actual, predicted, lower, upper, naive, drift_prices, strict=True
            )
        ],
    }


def train(candles, request):
    """Fit independently for each horizon and retain reproducible artifacts and test evidence."""
    logs, times = validate(candles, 360)
    n, lags = len(logs), request.lags
    train_end, calibration_end = math.floor(n * 0.6), math.floor(n * 0.8)
    x = features(logs, lags, request.feature_set)
    fitted, evaluation = [], []
    drift = float(np.diff(logs[:train_end]).mean())
    for horizon in range(1, request.max_horizon + 1):
        training = np.arange(lags, train_end - horizon)
        calibration = np.arange(train_end, calibration_end - horizon)
        test = np.arange(calibration_end, n - horizon)
        if len(training) < max(60, 3 * lags) or min(len(calibration), len(test)) < 20:
            raise ValueError("The selected horizon needs more training/calibration/test observations.")
        model, predictions = fit_horizon(logs, x, lags, request.alpha, horizon, training, calibration)
        fitted.append(model)
        evaluation.append(score_horizon(logs, times, predictions, model, test, drift, lags))
    artifact = {
        "engine": engine_for(request.feature_set),
        "numpy_version": np.__version__,
        "algorithm": "Direct autoregressive ridge on daily log returns",
        "parameters": parameters(request),
        "nominal_coverage": COVERAGE,
        "models": fitted,
        "partitions": {
            "train": {"start": iso(times[0]), "end": iso(times[train_end]), "candles": train_end},
            "calibration": {
                "start": iso(times[train_end]),
                "end": iso(times[calibration_end]),
                "candles": calibration_end - train_end,
            },
            "test": {
                "start": iso(times[calibration_end]),
                "end": iso(times[-1] + step_ms("1d")),
                "candles": n - calibration_end,
            },
        },
        "evaluation": evaluation,
        "notes": [
            "Training, calibration and test use chronological 60/20/20 partitions with boundary-crossing targets purged.",
            "Models stay fixed after training; test observations never select coefficients, penalties or interval widths.",
            "Bands use held-out absolute log errors at nominal 90% coverage. Time-series dependence prevents a distribution-free coverage guarantee.",
            "Test targets overlap for horizons above one day; the reported observations are not independent trials.",
            "Repeated user experiments can overfit the retained test window. Negative skill means the naive forecast performed better.",
        ],
    }
    if request.feature_set != "returns":
        artifact["algorithm"] = "Direct ridge on lagged returns and causal trend/volatility context"
        artifact["feature_names"] = [f"return_lag_{i + 1}" for i in range(lags)] + [
            "mean_return",
            "return_volatility",
            "downside_rms",
            "positive_fraction",
            "log_distance_from_peak",
            "log_trend_deviation",
        ]
        artifact["notes"].append(
            "Six context features use only the same trailing lag window; they add no volume, external signals or automatic feature/model selection. More features do not establish better future accuracy."
        )
    fingerprint(artifact)  # Reject any non-finite persisted artifact.
    return artifact


def predict(artifact, candles, horizon):
    """Apply unchanged trained coefficients to a closed causal window, with a descriptive shift check."""
    if artifact["engine"] != engine_for(artifact["parameters"].get("feature_set", "returns")):
        raise ValueError("This forecast engine version is not supported by the installed application.")
    lags = artifact["parameters"]["lags"]
    logs, times = validate(candles, lags + 1)
    if not 1 <= horizon <= len(artifact["models"]):
        raise ValueError("Choose a horizon supported by this trained model.")
    vector = features(logs, lags, artifact["parameters"].get("feature_set", "returns"))[-1]
    points, shifts = [], []
    for model in artifact["models"][:horizon]:
        z = (vector - np.asarray(model["mean"])) / np.asarray(model["scale"])
        center = float(logs[-1] + model["intercept"] + z @ np.asarray(model["coefficients"]))
        low, value, high = prices([center - model["radius"], center, center + model["radius"]])
        points.append(
            {
                "timestamp": iso(times[-1] + (model["horizon"] + 1) * step_ms("1d")),
                "value": float(value),
                "lower": float(low),
                "upper": float(high),
            }
        )
        shifts.append(int(np.sum((vector < model["feature_min"]) | (vector > model["feature_max"]))))
    return {
        "trained": True,
        "model": artifact["algorithm"],
        "horizon": horizon,
        "origin": iso(times[-1] + step_ms("1d")),
        "last_price": float(np.exp(logs[-1])),
        "points": points,
        "nominal_coverage": COVERAGE,
        "shift": {
            "outside_training_range": max(shifts),
            "features": len(vector),
            "note": (
                "Model features outside observed training ranges; a descriptive warning, not a calibrated regime-change test."
                if artifact["parameters"].get("feature_set") == "returns_context"
                else "Lag features outside observed training ranges; a descriptive warning, not a calibrated regime-change test."
            ),
        },
        "note": "A fitted research model with empirical calibration. Future coverage and profitable trades are not guaranteed.",
    }
