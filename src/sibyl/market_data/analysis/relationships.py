"""Bounded descriptive dependence and return regressions over exact aligned observations.

No p-values, causal claims, forecast accuracy or trading recommendations are
inferred. Price-level correlation can be spurious; regression always uses
same-interval log returns, independently of the matrix's display transform.
"""

import math

import numpy as np
import pandas as pd

DISTANCE_LIMIT = 360
ROBUST_LIMIT = 360


def aligned(histories, transform="log_returns", *, seconds=None):
    """Align timestamps, rejecting invalid/duplicate prices and never filling gaps."""
    columns = {}
    for symbol, rows in histories.items():
        timestamps, values = [], []
        for row in rows:
            value = row["close"]
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError("Relationship analysis requires finite positive closes.")
            try:
                stamp = pd.Timestamp(row["timestamp"])
            except (ValueError, TypeError, OverflowError):
                raise ValueError("Relationship input requires valid candle timestamps.") from None
            if stamp.tzinfo is None:
                raise ValueError("Relationship timestamps need a timezone.")
            timestamps.append(stamp.tz_convert("UTC"))
            values.append(value)
        if len(set(timestamps)) != len(timestamps):
            raise ValueError("Relationship input has duplicate timestamps.")
        columns[symbol] = pd.Series(values, index=pd.DatetimeIndex(timestamps), dtype=float)
    prices = pd.DataFrame(columns).sort_index()
    if transform == "prices":
        return prices.dropna()
    if transform not in {"log_returns", "changes"}:
        raise ValueError("Choose log returns, price levels or absolute changes.")
    observations = np.log(prices).diff() if transform == "log_returns" else prices.diff()
    if seconds:
        contiguous = prices.index.to_series().diff().dt.total_seconds().eq(seconds)
        observations = observations.loc[contiguous]
    return observations.replace([np.inf, -np.inf], np.nan).dropna()


def distance_matrix(observations):
    """Biased empirical distance correlation from double-centered Euclidean distances.

    At most 360 recent observations bound quadratic storage/work. Zero variance
    gives unavailable values, including the diagonal; unsigned sample dependence
    does not prove independence or statistical significance.
    """
    rows = observations.tail(DISTANCE_LIMIT)
    if len(rows) < 2:
        return rows, [[None for _ in rows.columns] for _ in rows.columns]
    centered = []
    variances = []
    for symbol in rows.columns:
        values = rows[symbol].to_numpy()
        scale = float(np.max(np.abs(values))) if len(values) else 0
        if scale:
            values = values / scale
        distances = np.abs(values[:, None] - values[None, :])
        distances -= distances.mean(axis=0, keepdims=True)
        distances -= distances.mean(axis=1, keepdims=True)
        centered.append(distances)
        variances.append(float(np.mean(distances**2)) if len(values) else 0)
    matrix = []
    for i, first in enumerate(centered):
        values = []
        for j, second in enumerate(centered):
            denominator = math.sqrt(variances[i] * variances[j])
            value = (
                math.sqrt(max(0, float(np.mean(first * second))) / denominator)
                if denominator > 1e-28
                else None
            )
            values.append(min(1, value) if value is not None else None)
        matrix.append(values)
    return rows, matrix


def regressions(histories, *, seconds=None, robust=False):
    """Fit y = intercept + beta*x to aligned contemporaneous log returns.

    The first selected market is x. In robust mode, fit OLS and Theil–Sen
    to the same latest 360 or fewer returns and compare their median residual size.
    """
    rows = aligned(histories, seconds=seconds)
    available = len(rows)
    if robust:
        rows = rows.tail(ROBUST_LIMIT)
    symbols = list(rows.columns)
    n = len(rows)
    results = []
    if not symbols:
        return {"items": [], "observations": 0}
    x = rows.iloc[:, 0].to_numpy()
    x_mean = float(x.mean()) if n else 0
    centered_x = x - x_mean
    variance_x = float(np.dot(centered_x, centered_x))
    for symbol in symbols[1:]:
        item = {
            "reference": symbols[0],
            "target": symbol,
            "observations": n,
            "status": "insufficient"
            if n < 30
            else "constant_reference"
            if variance_x <= 1e-24
            else "observed",
            "beta": None,
            "intercept_pct": None,
            "r_squared": None,
            "residual_rms_pct": None,
            "points": [],
        }
        if item["status"] == "observed":
            y = rows[symbol].to_numpy()
            mean_y = float(y.mean())
            beta = float(np.dot(centered_x, y - mean_y) / variance_x)
            intercept = mean_y - beta * x_mean
            residual = y - (intercept + beta * x)
            if robust:
                from scipy.stats import theilslopes

                fit = theilslopes(y, x, method="joint")
                item["theil_sen"] = {
                    "beta": float(fit.slope),
                    "intercept_pct": float(fit.intercept) * 100,
                    "median_absolute_residual_pct": float(
                        np.median(np.abs(y - fit.intercept - fit.slope * x))
                    )
                    * 100,
                    "ols_median_absolute_residual_pct": float(np.median(np.abs(residual))) * 100,
                }
            total = float(np.dot(y - mean_y, y - mean_y))
            squared_error = float(np.dot(residual, residual))
            item.update(
                beta=beta,
                intercept_pct=intercept * 100,
                r_squared=max(0, min(1, 1 - squared_error / total)) if total > 1e-24 else None,
                residual_rms_pct=math.sqrt(squared_error / n) * 100,
                points=[
                    {"timestamp": stamp.isoformat(), "x": float(a) * 100, "y": float(b) * 100}
                    for stamp, a, b in zip(rows.index, x, y, strict=True)
                ][-360:],
            )
        results.append(item)
    return {
        "items": results,
        "observations": n,
        "reference": symbols[0],
        "available_observations": available,
        "robust": robust,
        "transform": "same-interval log returns",
        "point_limit": 360,
        "note": (
            "OLS and Theil–Sen use the same latest 360 or fewer aligned returns. Theil–Sen uses a median "
            "pairwise slope and median of y minus slope times x for its intercept. Residuals are in-sample. "
            "No significance or causal effect is estimated."
            if robust
            else "In-sample OLS with an intercept; first market is the reference. Returns are not risk-free-adjusted. No significance test, causality or predictive skill is established; serial dependence, outliers and window selection affect the fit."
        ),
    }
