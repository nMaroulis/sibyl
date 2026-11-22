"""Bounded native statsmodels elastic-net fits on standardized training observations."""

import numpy as np

MAX_ITERATIONS = 200
L1_SHARE = 0.5


def fit(features, target, alpha):
    """Fit a fixed L1/L2 mix and return ordinary log-return coefficients."""
    from statsmodels import __version__
    from statsmodels.regression.linear_model import OLS

    center = float(target.mean())
    scale = float(target.std())
    if scale < 1e-12:
        scale = 1.0
    weight = alpha / len(target)
    result = OLS((target - center) / scale, features).fit_regularized(
        alpha=weight,
        L1_wt=L1_SHARE,
        maxiter=MAX_ITERATIONS,
        refit=False,
    )
    coefficients = np.asarray(result.params) * scale
    if not result.converged or not np.isfinite(coefficients).all():
        raise ValueError("Elastic net did not converge to a finite fit. Try a different penalty or input.")
    return {
        "intercept": center,
        "coefficients": coefficients.tolist(),
        "training": {
            "library": "statsmodels",
            "library_version": __version__,
            "l1_share": L1_SHARE,
            "penalty_weight": weight,
            "active_features": int(np.count_nonzero(coefficients)),
            "feature_count": int(features.shape[1]),
        },
    }
