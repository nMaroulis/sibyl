"""Bounded bivariate lag tests with one user-chosen order and a later holdout.

The null is that the reference's past returns add no linear information about
this target beyond its own lags. Classical F inference assumes a stable correctly
specified model and well-behaved errors; crypto returns need not satisfy this.
Granger predictability does not identify structural/economic causation.
"""

import math

import numpy as np
from scipy.stats import chi2, f

from sibyl.market_data.analysis.relationships import aligned

ENGINE = "granger-holdout-1"


def fit(design, target):
    """Normalize regressors on training rows only and refuse rank-deficient fits."""
    mean, scale = design.mean(axis=0), design.std(axis=0)
    if (scale < 1e-12).any():
        raise ValueError("Constant or nearly constant lag regressors.")
    x = np.column_stack((np.ones(len(design)), (design - mean) / scale))
    beta, _, rank, singular = np.linalg.lstsq(x, target, rcond=None)
    if rank != x.shape[1] or singular[-1] <= singular[0] * 1e-10:
        raise ValueError("Collinear or ill-conditioned lag regressors.")
    residual = target - x @ beta
    return {"mean": mean.tolist(), "scale": scale.tolist(), "coefficients": beta.tolist()}, residual


def predict(model, design):
    x = np.column_stack((np.ones(len(design)), (design - model["mean"]) / model["scale"]))
    return x @ np.asarray(model["coefficients"])


def direction(rows, reference, target, order, split):
    """Fit both nested models before the holdout, then score identical later targets."""
    y, x = rows[target].to_numpy(), rows[reference].to_numpy()
    own = np.array([[y[t - lag] for lag in range(1, order + 1)] for t in range(order, len(rows))])
    other = np.array([[x[t - lag] for lag in range(1, order + 1)] for t in range(order, len(rows))])
    augmented = np.column_stack((own, other))
    train_end = split - order
    item = {
        "reference": reference,
        "target": target,
        "status": "unavailable",
        "reason": None,
        "f_statistic": None,
        "p_value": None,
        "adjusted_p_value": None,
        "training_samples": max(0, train_end),
        "held_out": None,
        "models": None,
    }
    if train_end < max(60, 10 * (1 + 2 * order)) or len(rows) - split < 21:
        item["reason"] = (
            "Need at least 60 training targets, 10 per augmented coefficient, and 21 held-out targets."
        )
        return item
    response = y[order:split]
    if response.std() < 1e-12:
        item["reason"] = "Constant or nearly constant training target returns."
        return item
    try:
        restricted, error_r = fit(own[:train_end], response)
        full, error_u = fit(augmented[:train_end], response)
    except (ValueError, np.linalg.LinAlgError) as exc:
        item["reason"] = str(exc) if isinstance(exc, ValueError) else "The numerical lag fit is unavailable."
        return item
    rss_r, rss_u = float(error_r @ error_r), float(error_u @ error_u)
    if rss_u <= max(1e-28, float(response @ response) * 1e-14):
        item["reason"] = "Near-perfect training fit leaves no reliable residual variance for an F test."
        return item
    df = train_end - (1 + 2 * order)
    statistic = max(0, (rss_r - rss_u) / order / (rss_u / df))
    actual = y[split:]
    first, second = predict(restricted, own[train_end:]), predict(full, augmented[train_end:])
    mae_r, mae_u = float(np.mean(np.abs(actual - first))), float(np.mean(np.abs(actual - second)))
    residual = error_u - error_u.mean()
    denominator = float(residual @ residual)
    diagnostic_lags = min(10, train_end // 5)
    autocorrelations = [
        float(residual[k:] @ residual[:-k]) / denominator for k in range(1, diagnostic_lags + 1)
    ]
    q = train_end * (train_end + 2) * sum(a * a / (train_end - k) for k, a in enumerate(autocorrelations, 1))
    # Descriptive residual diagnostic, not an automatic model-order selection rule.
    diagnostic_p = float(chi2.sf(q, diagnostic_lags))
    item.update(
        status="observed",
        f_statistic=statistic,
        p_value=float(f.sf(statistic, order, df)),
        degrees_of_freedom={"numerator": order, "denominator": df},
        restricted_rss=rss_r,
        augmented_rss=rss_u,
        residual_diagnostic={
            "name": "Ljung–Box, unadjusted residual degrees",
            "lags": diagnostic_lags,
            "statistic": q,
            "p_value": diagnostic_p,
            "serial_correlation_flag": diagnostic_p < 0.05,
        },
        held_out={
            "samples": len(actual),
            "start": rows.index[split].isoformat(),
            "last_target": rows.index[-1].isoformat(),
            "own_lags_mae_pct": mae_r * 100,
            "augmented_mae_pct": mae_u * 100,
            "zero_return_mae_pct": float(np.mean(np.abs(actual))) * 100,
            "skill_vs_own_lags_pct": (1 - mae_u / mae_r) * 100 if mae_r > 1e-14 else None,
        },
        models={"own_lags": restricted, "augmented": full},
    )
    return item


def granger(histories, *, seconds, lags=2):
    """Test reference↔each target at one fixed order; never bridge missing intervals."""
    if type(lags) is not int or not 1 <= lags <= 5 or not 2 <= len(histories) <= 8:
        raise ValueError("Choose two to eight markets and a lag order from one to five.")
    if type(seconds) is not int or seconds <= 0:
        raise ValueError("Choose a supported fixed candle interval.")
    rows = aligned(histories, seconds=seconds).tail(719)
    available = len(rows)
    if len(rows):
        differences = rows.index.to_series().diff().dt.total_seconds()
        gaps = np.flatnonzero(differences.iloc[1:].to_numpy() != seconds)
        if len(gaps):
            rows = rows.iloc[int(gaps[-1]) + 1 :]
    symbols = list(rows.columns)
    split = math.floor(len(rows) * 0.7)
    items = []
    for target in symbols[1:]:
        items.extend(
            direction(rows, source, destination, lags, split)
            for source, destination in ((symbols[0], target), (target, symbols[0]))
        )
    hypotheses = 2 * (len(symbols) - 1)
    for item in items:
        if item["p_value"] is not None:
            item["adjusted_p_value"] = min(1, item["p_value"] * hypotheses)
    return {
        "engine": ENGINE,
        "symbols": symbols,
        "lags": lags,
        "observations": len(rows),
        "available_observations": available,
        "discarded_earlier_returns": available - len(rows),
        "start": rows.index[0].isoformat() if len(rows) else None,
        "last_target": rows.index[-1].isoformat() if len(rows) else None,
        "training_end_exclusive": rows.index[split].isoformat() if len(rows) else None,
        "hypotheses": hypotheses,
        "adjustment": "Bonferroni across both directions for this reference-first request only",
        "items": items,
        "assumptions": [
            "One chosen lag order includes lags 1 through p; each direction controls the target's own lags plus an intercept. Only the most recent shared consecutive log-return suffix is used.",
            "The first 70% fits fixed coefficients and the classical nested-model F test; the later 30% scores one-step forecasts using only actually observed prior returns. The holdout never chooses coefficients, lag order or p-values.",
            "Classical p-values assume stable linear specification and suitable independent, homoskedastic errors. Stationarity, heteroskedasticity, omitted variables and regime stability are not established. The residual diagnostic flags some serial dependence but cannot verify all assumptions.",
            "Bonferroni covers this request's planned directions, including unavailable tests. Repeated windows, lag choices and user experiments are not corrected. Small adjusted p-values or positive held-out skill do not establish causation, persistent predictive ability or a profitable trading rule.",
        ],
    }
