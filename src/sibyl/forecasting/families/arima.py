"""Bounded ARIMA and weekly seasonal ARIMA with native statsmodels fitting/filtering.

ARMA(p,q) on daily log returns is ARIMA(p,1,q) on log prices with a drift.
Training-only normalization improves numerical conditioning; one frozen native
parameter vector serves every horizon. At each origin a native Kalman filter
uses exactly the preceding 90 closes (89 returns), then forecasts without refit.
Calibration/testing and inference use the same finite context and never smoothing.
Only finite JSON parameters/receipts are retained; no executable model is loaded.
"""

import warnings

import numpy as np

MAX_CANDLES = 1000
MAX_HORIZON = 14
CONTEXT = 90
MAX_STEPS = 100


def seasonal_order(period):
    """Use one seasonal autoregressive term for the supported seven-day period."""
    if type(period) is not int or period not in (0, 7):
        raise ValueError("ARIMA seasonality supports Off or a seven-day lag.")
    return (1, 0, 0, period) if period else (0, 0, 0, 0)


def native_model(values, p, q, *, season=0):
    """Construct the reviewed stationary/invertible return model; import only on explicit use."""
    from statsmodels.tsa.arima.model import ARIMA

    return ARIMA(
        np.asarray(values).reshape(-1, 1),
        order=(p, 0, q),
        seasonal_order=seasonal_order(season),
        trend="c",
        enforce_stationarity=True,
        enforce_invertibility=True,
    )


class ARIMAForecaster:
    """Fit once on earlier returns, then filter observed context with unchanged parameters."""

    @staticmethod
    def fit(logs, p=1, q=1, *, season=0):
        """Estimate native maximum likelihood on training data only; reject failed/degenerate fits."""
        import statsmodels
        from statsmodels.tools.sm_exceptions import EstimationWarning, ValueWarning

        values = np.diff(np.asarray(logs, dtype=float))
        if not 119 <= len(values) < MAX_CANDLES or not np.isfinite(values).all():
            raise ValueError("ARIMA needs 120–1,000 finite training closes.")
        if type(p) is not int or type(q) is not int or p not in (1, 2, 3) or q not in (0, 1, 2):
            raise ValueError("ARIMA supports p 1–3, d fixed at 1 and q 0–2.")
        center, scale = float(values.mean()), float(values.std())
        if scale < 1e-10:
            raise ValueError(
                "ARIMA needs varying daily returns; this input cannot identify the selected model."
            )
        seasonal = seasonal_order(season)
        model = native_model((values - center) / scale, p, q, season=season)
        try:
            with warnings.catch_warnings(record=True) as recorded:
                warnings.simplefilter("always")
                result = model.fit(
                    method="statespace", method_kwargs={"maxiter": MAX_STEPS, "disp": False}, cov_type="none"
                )
            params = np.asarray(result.params, dtype=float)
            aic, bic, likelihood = float(result.aic), float(result.bic), float(result.llf)
            converged = bool(result.mle_retvals.get("converged", False))
            if not converged or not np.isfinite([*params, aic, bic, likelihood]).all():
                raise ValueError("ARIMA did not converge to a finite fit. Try another order or input.")
            if params[-1] <= 0:
                raise ValueError("ARIMA did not identify a positive innovation variance.")
        except (np.linalg.LinAlgError, FloatingPointError, OverflowError) as exc:
            raise ValueError("ARIMA fitting was numerically unstable. Try another order or input.") from exc
        return {
            "order": [p, 1, q],
            **({"seasonal_order": list(seasonal)} if season else {}),
            "return_center": center,
            "return_scale": scale,
            "parameters": params.tolist(),
            "parameter_names": list(result.param_names),
            "return_min": float(values.min()),
            "return_max": float(values.max()),
            "context_candles": CONTEXT,
            "training": {
                "library": "statsmodels",
                "library_version": statsmodels.__version__,
                "estimator": "state-space maximum likelihood · L-BFGS",
                "converged": converged,
                "iterations": int(result.mle_retvals.get("iterations", 0)),
                "max_iterations": MAX_STEPS,
                "training_returns": len(values),
                "aic": aic,
                "bic": bic,
                "log_likelihood": likelihood,
                "warning_categories": sorted(
                    {
                        row.category.__name__
                        for row in recorded
                        if row.category is UserWarning
                        or issubclass(row.category, (EstimationWarning, ValueWarning, RuntimeWarning))
                    }
                ),
                "parameter_values": dict(zip(result.param_names, params.tolist(), strict=True)),
                "scale_units": "training-standardized daily log returns",
            },
        }

    @staticmethod
    def forecast(fitted, logs, horizon):
        """Filter exactly 90 observed closes with saved parameters; return cumulative log-return means."""
        logs = np.asarray(logs, dtype=float)
        if len(logs) < CONTEXT or not 1 <= horizon <= MAX_HORIZON:
            raise ValueError("ARIMA forecasting needs 90 closed daily candles and a 1–14 day horizon.")
        p, _, q = fitted["order"]
        values = (np.diff(logs[-CONTEXT:]) - fitted["return_center"]) / fitted["return_scale"]
        try:
            season = fitted.get("seasonal_order", (0, 0, 0, 0))[-1]
            result = native_model(values, p, q, season=season).filter(fitted["parameters"], cov_type="none")
            returns = np.asarray(result.forecast(horizon)) * fitted["return_scale"] + fitted["return_center"]
            predicted = np.cumsum(returns)
        except (np.linalg.LinAlgError, FloatingPointError, OverflowError) as exc:
            raise ValueError("ARIMA could not filter this observation window.") from exc
        if not np.isfinite(predicted).all():
            raise ValueError("ARIMA produced non-finite forecasts. Choose another input or model.")
        return predicted

    @classmethod
    def panel(cls, fitted, logs, origins, horizon):
        """Calculate all requested origins/horizons causally; later closes never enter an earlier filter."""
        values = np.zeros((len(logs), horizon))
        for origin in origins:
            values[origin] = cls.forecast(fitted, logs[: origin + 1], horizon)
        return values
