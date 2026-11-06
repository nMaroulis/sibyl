"""Sample covariance, historical tails and constant-weight basket returns.

Current weights are reapplied daily as a frictionless hypothetical basket. These
are descriptive returns over one shared consecutive daily suffix, not measured
account performance, a forecast, significance test or executable allocation.
"""

import math

import numpy as np

from sibyl.market_data.archive import iso, milliseconds, now_ms, step_ms

DAY = step_ms("1d")


def closes(rows):
    result = {}
    for row in rows:
        stamp, value = milliseconds(row["timestamp"]), row["close"]
        if stamp % DAY or stamp in result or stamp + DAY > now_ms():
            raise ValueError("Risk history needs unique, aligned, closed daily candles.")
        if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
            raise ValueError("Risk history needs finite positive closes.")
        result[stamp] = float(value)
    return result


def converted(route, histories, anchors):
    """Compose the same observed conversion legs without parity assumptions or gap filling."""
    times = set.intersection(*(set(histories[leg["symbol"]]) for leg in route)) if route else set(anchors)
    return {
        stamp: math.prod(
            (1 / histories[leg["symbol"]][stamp] if leg["inverse"] else histories[leg["symbol"]][stamp])
            for leg in route
        )
        for stamp in times
    }


def analyze(histories, weights):
    assets = list(weights)
    if (
        not assets
        or set(assets) != set(histories)
        or any(not math.isfinite(w) or w <= 0 for w in weights.values())
        or not math.isclose(sum(weights.values()), 1, abs_tol=1e-9)
    ):
        raise ValueError("Use matching histories and positive normalized basket weights.")
    common = sorted(set.intersection(*(set(histories[asset]) for asset in assets)))
    start = len(common) - 1
    while start > 0 and common[start] - common[start - 1] == DAY:
        start -= 1
    times = common[start:]
    if len(times) < 31:
        raise ValueError(
            "The selected basket needs at least 31 common consecutive daily closes. Remove an asset with limited history or fetch more history."
        )
    matrix = np.array([[histories[asset][stamp] for asset in assets] for stamp in times], dtype=float)
    if not np.isfinite(matrix).all() or (matrix <= 0).any():
        raise ValueError("A composed historical conversion is invalid.")
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        returns = matrix[1:] / matrix[:-1] - 1
    if not np.isfinite(returns).all():
        raise ValueError("Historical returns exceed the supported numerical range.")
    w = np.array(list(weights.values()))
    basket = returns @ w
    covariance = np.atleast_2d(np.cov(returns, rowvar=False, ddof=1))
    variance = max(0, float(np.var(basket, ddof=1)))
    if not np.isfinite(covariance).all() or not math.isfinite(variance):
        raise ValueError("Historical covariance exceeds the supported numerical range.")
    daily_vol = math.sqrt(variance)
    standalone = np.sqrt(np.maximum(0, np.diag(covariance)))
    quantile = float(np.quantile(basket, 0.05, method="linear"))
    tail = basket[basket <= quantile]
    with np.errstate(over="ignore", invalid="ignore"):
        equity = np.cumprod(np.r_[1, 1 + basket])
    if not np.isfinite(equity).all() or (equity <= 0).any():
        raise ValueError("The hypothetical basket path exceeds the supported numerical range.")
    correlation = [
        [
            float(np.clip(covariance[i, j] / (standalone[i] * standalone[j]), -1, 1))
            if standalone[i] > 1e-14 and standalone[j] > 1e-14
            else None
            for j in range(len(assets))
        ]
        for i in range(len(assets))
    ]
    contributions = w * (covariance @ w) / variance * 100 if variance > 1e-28 else None
    return {
        "observations": len(basket),
        "start": iso(times[0]),
        "end": iso(times[-1] + DAY),
        "discarded_earlier_closes": start,
        "daily_volatility_pct": daily_vol * 100,
        "annualized_volatility_pct": daily_vol * math.sqrt(365) * 100,
        "historical_var_95_pct": -quantile * 100,
        "expected_shortfall_95_pct": -float(tail.mean()) * 100,
        "tail_observations": len(tail),
        "max_drawdown_pct": float(np.max(1 - equity / np.maximum.accumulate(equity))) * 100,
        "hypothetical_return_pct": float(equity[-1] - 1) * 100,
        "diversification_ratio": float(w @ standalone) / daily_vol if daily_vol > 1e-14 else None,
        "assets": [
            {
                "asset": asset,
                "weight_pct": weights[asset] * 100,
                "annualized_volatility_pct": float(standalone[i]) * math.sqrt(365) * 100,
                "variance_contribution_pct": float(contributions[i]) if contributions is not None else None,
            }
            for i, asset in enumerate(assets)
        ],
        "correlation": correlation,
        "covariance_daily": covariance.tolist(),
        "daily_returns": [
            {"timestamp": iso(stamp), "return_pct": float(value) * 100, "index": float(level) * 100}
            for stamp, value, level in zip(times[1:], basket, equity[1:], strict=True)
        ],
        "method": "current-weight-daily-basket-v1",
        "assumptions": [
            "Current selected holding values determine fixed weights, hypothetically rebalanced daily with no fees/slippage. This is not the account's historical return or a suggested allocation.",
            "All assets and conversion legs use the same exact-source, most recent common consecutive daily suffix. Missing days are never bridged or forward filled; USDT itself is the denomination identity, other currencies require observed rates.",
            "Covariance uses sample daily simple returns (ddof=1); annualized volatility uses sqrt(365), not a future volatility forecast. Variance contributions can be negative for offsets; constant-series correlations and zero-risk ratios stay undefined.",
            "Historical 95% VaR is minus the empirical 5th return percentile (linear interpolation). Expected shortfall is minus the mean of observed returns at or below it, including ties. Negative losses indicate gains in that historical tail. These are not calibrated probabilities or maximum-loss guarantees; small samples and changing correlations limit interpretation.",
        ],
    }
