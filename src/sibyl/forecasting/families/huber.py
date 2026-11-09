"""Fixed-scale Huber autoregression fitted by iteratively reweighted least squares.

The target center/MAD scale use training observations only and stay fixed during
optimization. Each step solves a weighted ridge system with an unpenalized
intercept. Calibration/test data never choose scale, weights or stopping. This is
not scikit-learn's joint-scale HuberRegressor. Every row remains in the fit;
large residuals receive less influence, while extreme feature leverage can still
matter. Artifacts contain ordinary finite coefficients and numerical receipts.
"""

import numpy as np

MAX_CANDLES = 2000
MAX_STEPS = 60
TOLERANCE = 1e-8
SCALE_FLOOR = 1e-6


class HuberAR:
    """Bounded deterministic Huber loss plus feature L2, in standardized training units."""

    @staticmethod
    def fit(z, y, alpha, delta):
        """Fit one horizon and expose actual descent, convergence and downweight evidence."""
        z, y = np.asarray(z, dtype=float), np.asarray(y, dtype=float)
        if (
            z.ndim != 2
            or y.ndim != 1
            or len(z) != len(y)
            or not 60 <= len(y) <= MAX_CANDLES
            or not 1 <= z.shape[1] <= 36
        ):
            raise ValueError("Huber fitting needs 60–2,000 training observations and at most 36 features.")
        if (
            not np.isfinite(z).all()
            or not np.isfinite(y).all()
            or not np.isfinite([alpha, delta]).all()
            or not 0.01 <= alpha <= 1000
            or not 0.25 <= delta <= 5
        ):
            raise ValueError("Use finite Huber training values, a supported penalty and delta.")
        center = float(np.median(y))
        scale = max(SCALE_FLOOR, 1.4826 * float(np.median(np.abs(y - center))))
        target = (y - center) / scale
        design = np.column_stack((np.ones(len(z)), z))
        beta = np.zeros(design.shape[1])
        penalty = np.diag([0.0, *([alpha] * z.shape[1])])

        def objective(coefficients):
            residual = np.abs(target - design @ coefficients)
            loss = np.where(residual <= delta, 0.5 * residual**2, delta * (residual - 0.5 * delta))
            return float((loss.sum() + 0.5 * alpha * np.sum(coefficients[1:] ** 2)) / len(y))

        initial = previous = objective(beta)
        converged = False
        steps = 0
        for _ in range(MAX_STEPS):
            steps += 1
            residual = np.abs(target - design @ beta)
            weights = np.ones(len(y))
            outside = residual > delta
            weights[outside] = delta / residual[outside]
            try:
                updated = np.linalg.solve(
                    design.T @ (weights[:, None] * design) + penalty, design.T @ (weights * target)
                )
            except np.linalg.LinAlgError:
                raise ValueError(
                    "Huber fitting could not solve its weighted system. Choose another input or penalty."
                ) from None
            current = objective(updated)
            if (
                not np.isfinite(updated).all()
                or not np.isfinite(current)
                or current > previous + 1e-9 * max(1, abs(previous))
            ):
                raise ValueError(
                    "Huber fitting did not produce finite objective descent. Choose another input or penalty."
                )
            change = float(np.max(np.abs(updated - beta)))
            limit = TOLERANCE * (1 + float(np.max(np.abs(beta))))
            beta, previous = updated, current
            if change <= limit:
                converged = True
                break
        residual = np.abs(target - design @ beta)
        outside = residual > delta
        weights = np.ones(len(y))
        weights[outside] = delta / residual[outside]
        return {
            "family": "huber",
            "coefficients": (scale * beta[1:]).tolist(),
            "intercept": float(center + scale * beta[0]),
            "training": {
                "optimizer": "fixed-scale IRLS",
                "objective": "mean Huber standardized-target loss + alpha/(2n) feature L2",
                "delta": delta,
                "steps": steps,
                "max_steps": MAX_STEPS,
                "converged": converged,
                "stopping_rule": "max coefficient change <= 1e-8 * (1 + previous coefficient max norm)",
                "initial_loss": initial,
                "final_loss": previous,
                "target_center": center,
                "target_scale": scale,
                "target_scale_method": "max(1e-6, 1.4826 * training target MAD)",
                "residual_threshold": delta * scale,
                "downweighted_samples": int(outside.sum()),
                "training_samples": len(y),
                "effective_weight_sum": float(weights.sum()),
                "minimum_weight": float(weights.min()),
                "feature_leverage_robust": False,
            },
        }
