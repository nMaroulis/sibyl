"""Native Optuna ask/tell on training prefixes, followed by untouched next-open tests."""

import math
from importlib.util import find_spec
from statistics import mean

from pydantic import ValidationError

from sibyl.forecasting.engine import fingerprint
from sibyl.strategies.backtest import BacktestEngine
from sibyl.strategies.plugins.engine import plugin_signals

METRICS = ("return_pct", "max_drawdown", "sharpe", "trades", "benchmark_pct")
VERSION = "native-optuna-prefix-v1"
MAX_WORK = 60_000


def available():
    """Presence only; importing optional samplers is lazy and never contacts a provider."""
    return find_spec("optuna") is not None


def optuna_module():
    try:
        import optuna
    except ImportError:
        raise ValueError(
            "Install Sibyl's optimization extra on the backend: uv sync --extra optimization, or pip install 'sibyl[optimization]'."
        ) from None
    return optuna


def metrics(result):
    return {key: result[key] for key in METRICS}


class AdaptiveEngine:
    """Keep the optimizer's observations wholly inside each expanding training prefix."""

    def __init__(self, plugin=None):
        self.plugin = plugin

    def simulation(self, candles, parameters, values, start):
        directions = None
        if self.plugin:
            factory, spec = self.plugin["factory"], self.plugin["spec"]
            directions = plugin_signals(factory, spec, values, candles)
        result = BacktestEngine().run(candles, parameters, evaluation_start=start, signal_override=directions)
        return result, fingerprint(directions) if directions is not None else None

    def plan(self, recipe, n):
        """Validate input, common scoring windows and a work bound before queuing or sampling."""
        if n != recipe.parameters.candles:
            raise ValueError("The immutable input count must match this study recipe.")
        if self.plugin:
            spec = self.plugin["spec"]
            baseline = spec.values(recipe.plugin_values)
            for name, distribution in recipe.distributions.items():
                if name not in spec.parameters or distribution.kind != spec.parameters[name].kind:
                    raise ValueError("Use this plugin's declared parameter names and types.")
                for value in (distribution.low, distribution.high):
                    spec.parameters[name].value(value)
            warmup = spec.warmup
        else:
            baseline = {}
            warmup = max(
                [recipe.parameters.warmup]
                + [
                    int(domain.high)
                    for name, domain in recipe.distributions.items()
                    if name.endswith("_period") or name == "window"
                ]
            )
        initial = n * recipe.initial_train_pct // 100
        boundaries = [initial + (n - initial) * index // recipe.folds for index in range(recipe.folds + 1)]
        windows = list(zip(boundaries[:-1], boundaries[1:], strict=True))
        if initial < warmup + 20 or any(end - start < 20 for start, end in windows):
            raise ValueError(
                "Use at least twenty scored training bars after the common warmup and twenty bars per test window."
            )
        work = sum(recipe.trials * start + 2 * end for start, end in windows)
        if work > MAX_WORK:
            raise ValueError("This study exceeds 60,000 processed bars. Reduce trials, folds or input size.")
        return {"baseline": baseline, "warmup": warmup, "windows": windows, "work": work}

    def run(self, candles, recipe):
        optuna = optuna_module()
        plan = self.plan(recipe, len(candles))
        baseline, warmup, windows, work = (plan[key] for key in ("baseline", "warmup", "windows", "work"))
        spec = self.plugin["spec"] if self.plugin else None
        folds = []
        incomplete = False
        for index, (start, end) in enumerate(windows, 1):
            sampler = (
                optuna.samplers.TPESampler(
                    seed=(recipe.seed + index - 1) % (2**32),
                    n_startup_trials=5,
                    n_ei_candidates=24,
                    multivariate=False,
                    constant_liar=False,
                )
                if recipe.sampler == "tpe"
                else optuna.samplers.RandomSampler(seed=(recipe.seed + index - 1) % (2**32))
            )
            study = optuna.create_study(
                direction="minimize" if recipe.objective == "max_drawdown" else "maximize", sampler=sampler
            )
            trials = []
            choices = {}
            # Native samplers are sequential and local, never persisted through
            # pickle or sent to a model. Every ask has exactly one native tell.
            for _ in range(recipe.trials):
                trial = study.ask()
                values = {
                    name: domain.suggest(trial, name) for name, domain in sorted(recipe.distributions.items())
                }
                try:
                    parameters = type(recipe.parameters)(
                        **(recipe.parameters.model_dump() | (values if not self.plugin else {}))
                    )
                    plugin_values = spec.values(baseline | values) if self.plugin else {}
                except (ValidationError, ValueError):
                    study.tell(trial, state=optuna.trial.TrialState.PRUNED)
                    trials.append(
                        {
                            "number": trial.number,
                            "values": values,
                            "state": "invalid_parameters",
                            "score": None,
                        }
                    )
                    continue
                result, decision = self.simulation(candles[:start], parameters, plugin_values, warmup)
                score = result[recipe.objective]
                eligible = (
                    result["trades"] >= recipe.min_train_trades
                    and type(score) in {int, float}
                    and math.isfinite(score)
                )
                state = "complete" if eligible else "insufficient_trades"
                study.tell(trial, float(score)) if eligible else study.tell(
                    trial, state=optuna.trial.TrialState.PRUNED
                )
                trials.append(
                    {
                        "number": trial.number,
                        "values": values,
                        "state": state,
                        "score": float(score) if eligible else None,
                        "metrics": metrics(result),
                        "signal_fingerprint": decision,
                    }
                )
                if eligible:
                    choices[trial.number] = (parameters, plugin_values)
            eligible_trials = [row for row in trials if row["state"] == "complete"]
            fold = {
                "index": index,
                "train_start": candles[0]["timestamp"],
                "train_end_exclusive": candles[start]["timestamp"],
                "train_bars": start,
                "test_start": candles[start]["timestamp"],
                "test_last_close": candles[end - 1]["timestamp"],
                "test_bars": end - start,
                "trials": trials,
                "training_fingerprint": fingerprint(candles[:start]),
            }
            if not eligible_trials:
                fold.update(
                    selected=None,
                    out_of_sample=None,
                    note="No sampled candidate met the training requirements; no test was scored.",
                )
                folds.append(fold)
                incomplete = True
                break
            chosen = sorted(
                eligible_trials,
                key=lambda row: (
                    (1 if recipe.objective == "max_drawdown" else -1) * row["score"],
                    row["number"],
                ),
            )[0]
            parameters, plugin_values = choices[chosen["number"]]
            test, decision = self.simulation(candles[:end], parameters, plugin_values, start)
            fixed, _ = self.simulation(candles[:end], recipe.parameters, baseline, start)
            fold.update(
                selected=chosen,
                out_of_sample=test,
                fixed_parameters=metrics(fixed),
                test_signal_fingerprint=decision,
            )
            folds.append(fold)
        evaluated = [fold for fold in folds if fold["out_of_sample"] is not None]
        return {
            "status": "no_eligible_candidates" if incomplete else "completed",
            "method": VERSION,
            "sampler": {
                "name": recipe.sampler,
                "library": "optuna",
                "version": optuna.__version__,
                "seed": recipe.seed,
                "startup_trials": 5 if recipe.sampler == "tpe" else 0,
                "independent_per_fold": True,
            },
            "common_warmup": warmup,
            "processed_bars_budget": work,
            "folds": folds,
            "summary": {
                "evaluated_windows": len(evaluated),
                "requested_windows": recipe.folds,
                "mean_return_pct": mean(fold["out_of_sample"]["return_pct"] for fold in evaluated)
                if evaluated
                else None,
                "worst_return_pct": min(
                    (fold["out_of_sample"]["return_pct"] for fold in evaluated), default=None
                ),
                "mean_fixed_return_pct": mean(fold["fixed_parameters"]["return_pct"] for fold in evaluated)
                if evaluated
                else None,
            },
            "decision_fingerprint": fingerprint(folds),
            "note": "Historical research only. Native Optuna TPE uses five completed startup trials, then training-only density-based suggestions; random samples explicit numeric distributions. Invalid combinations/pruned trade counts remain visible. Each test resets cash and includes shared next-open fees/slippage; test scores never feed the sampler. Repeated studies can overfit. No parameter choice is deployed and no exchange order is submitted.",
        }
