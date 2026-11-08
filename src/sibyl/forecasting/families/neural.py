"""A small reproducible tanh network fitted by full-batch Adam using NumPy only.

Scaling and objective observations belong exclusively to the training partition.
Fixed architecture/iterations avoid test-driven early stopping or hidden tuning.
Weights are plain finite JSON arrays; loading never executes serialized code.
"""

import numpy as np

HIDDEN = 8
EPOCHS = 120
RATE = 0.02
SEED = 1729
MAX_CANDLES = 1000
MAX_HORIZON = 14


class TinyMLP:
    """One hidden layer and a scalar standardized cumulative-log-return output."""

    @staticmethod
    def fit(z, y, alpha, horizon):
        if not 60 <= len(z) <= MAX_CANDLES or z.shape[1] > 36:
            raise ValueError("Neural fitting needs 60–1,000 training observations and at most 36 features.")
        rng = np.random.default_rng(SEED + horizon)
        center, scale = float(y.mean()), float(y.std())
        scale = scale if scale > 1e-12 else 1.0
        target = (y - center) / scale
        parameters = {
            "input_weights": rng.normal(0, 0.2, (z.shape[1], HIDDEN)),
            "hidden_bias": np.zeros(HIDDEN),
            "output_weights": rng.normal(0, 0.1, HIDDEN),
            "output_bias": np.zeros(1),
        }
        moments = {key: np.zeros_like(value) for key, value in parameters.items()}
        squares = {key: np.zeros_like(value) for key, value in parameters.items()}
        penalty = alpha / len(z)

        def loss():
            hidden = np.tanh(z @ parameters["input_weights"] + parameters["hidden_bias"])
            error = hidden @ parameters["output_weights"] + parameters["output_bias"][0] - target
            return float(
                np.mean(error**2)
                + penalty
                * (np.sum(parameters["input_weights"] ** 2) + np.sum(parameters["output_weights"] ** 2))
            )

        initial = loss()
        for step in range(1, EPOCHS + 1):
            hidden = np.tanh(z @ parameters["input_weights"] + parameters["hidden_bias"])
            error = hidden @ parameters["output_weights"] + parameters["output_bias"][0] - target
            delta = 2 * error / len(z)
            back = delta[:, None] * parameters["output_weights"] * (1 - hidden**2)
            gradients = {
                "input_weights": z.T @ back + 2 * penalty * parameters["input_weights"],
                "hidden_bias": back.sum(axis=0),
                "output_weights": hidden.T @ delta + 2 * penalty * parameters["output_weights"],
                "output_bias": np.array([delta.sum()]),
            }
            for key, gradient in gradients.items():
                moments[key] = 0.9 * moments[key] + 0.1 * gradient
                squares[key] = 0.999 * squares[key] + 0.001 * gradient**2
                parameters[key] -= (
                    RATE
                    * (moments[key] / (1 - 0.9**step))
                    / (np.sqrt(squares[key] / (1 - 0.999**step)) + 1e-8)
                )
        final = loss()
        if not np.isfinite([initial, final]).all() or any(
            not np.isfinite(value).all() for value in parameters.values()
        ):
            raise ValueError("The neural numerical fit is unstable. Choose another input or penalty.")
        return {
            "family": "mlp",
            **{key: value.tolist() for key, value in parameters.items()},
            "target_center": center,
            "target_scale": scale,
            "training": {
                "seed": SEED + horizon,
                "epochs": EPOCHS,
                "hidden_units": HIDDEN,
                "optimizer": "full-batch Adam",
                "learning_rate": RATE,
                "objective": "standardized return MSE + alpha/n * weight L2",
                "initial_loss": initial,
                "final_loss": final,
            },
        }

    @staticmethod
    def predict(model, z):
        hidden = np.tanh(z @ np.asarray(model["input_weights"]) + np.asarray(model["hidden_bias"]))
        return model["target_center"] + model["target_scale"] * (
            hidden @ np.asarray(model["output_weights"]) + model["output_bias"][0]
        )
