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


def features(log_prices, lags):
    """Return causal lag vectors; row t contains returns through close t and no later prices."""
    returns = np.diff(log_prices)
    return np.asarray([returns[t - lags : t][::-1] for t in range(lags, len(log_prices))])


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


def train(candles, request):
    """Fit independently for each horizon and retain reproducible artifacts and test evidence."""
    logs, times = validate(candles, 360)
    n, lags = len(logs), request.lags
    train_end, calibration_end = math.floor(n * 0.6), math.floor(n * 0.8)
    x = features(logs, lags)
    fitted, evaluation = [], []
    drift = float(np.diff(logs[:train_end]).mean())
    for horizon in range(1, request.max_horizon + 1):
        training = np.arange(lags, train_end - horizon)
        calibration = np.arange(train_end, calibration_end - horizon)
        test = np.arange(calibration_end, n - horizon)
        if len(training) < max(60, 3 * lags) or min(len(calibration), len(test)) < 20:
            raise ValueError("The selected horizon needs more training/calibration/test observations.")
        raw = x[training - lags]
        mean, scale = raw.mean(axis=0), raw.std(axis=0)
        scale = np.where(scale < 1e-12, 1, scale)
        z = (raw - mean) / scale
        y = logs[training + horizon] - logs[training]
        intercept = float(y.mean())
        try:
            coefficients = np.linalg.solve(z.T @ z + request.alpha * np.eye(lags), z.T @ (y - intercept))
        except np.linalg.LinAlgError:
            raise ValueError(
                "This numerical fit did not converge. Choose another dataset or penalty."
            ) from None

        predictions = intercept + ((x - mean) / scale) @ coefficients
        residuals = np.abs(logs[calibration + horizon] - logs[calibration] - predictions[calibration - lags])
        rank = math.ceil((len(residuals) + 1) * COVERAGE)
        if rank > len(residuals):
            raise ValueError("Not enough calibration observations for the selected interval.")
        radius = float(np.sort(residuals)[rank - 1])
        fitted.append(
            {
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
        )
        predicted_logs = logs[test] + predictions[test - lags]
        actual, predicted = prices(logs[test + horizon]), prices(predicted_logs)
        naive, drift_prices = prices(logs[test]), prices(logs[test] + drift * horizon)
        lower, upper = prices(predicted_logs - radius), prices(predicted_logs + radius)
        model_metrics, naive_metrics = metrics(actual, predicted), metrics(actual, naive)
        evaluation.append(
            {
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
        )
    artifact = {
        "engine": ENGINE,
        "numpy_version": np.__version__,
        "algorithm": "Direct autoregressive ridge on daily log returns",
        "parameters": {"lags": lags, "alpha": request.alpha, "max_horizon": request.max_horizon},
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
    fingerprint(artifact)  # Reject any non-finite persisted artifact.
    return artifact


def predict(artifact, candles, horizon):
    """Apply unchanged trained coefficients to a closed causal window, with a descriptive shift check."""
    if artifact["engine"] != ENGINE:
        raise ValueError("This forecast engine version is not supported by the installed application.")
    lags = artifact["parameters"]["lags"]
    logs, times = validate(candles, lags + 1)
    if not 1 <= horizon <= len(artifact["models"]):
        raise ValueError("Choose a horizon supported by this trained model.")
    vector = features(logs, lags)[-1]
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
            "features": lags,
            "note": "Lag features outside observed training ranges; a descriptive warning, not a calibrated regime-change test.",
        },
        "note": "A fitted research model with empirical calibration. Future coverage and profitable trades are not guaranteed.",
    }
