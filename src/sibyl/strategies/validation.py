"""Bounded, reproducible parameter selection on chronological training prefixes.

Each expanding window selects on training simulations only. Its chosen settings
and the user's fixed settings then run on the next disjoint test window. Tests
start in cash, retain earlier indicator context and liquidate at their own end;
their independent returns must not be presented as a continuous live account.
"""

import json
import math
import threading
from datetime import UTC, datetime
from itertools import product
from statistics import mean, median
from typing import Literal
from uuid import uuid4

from pydantic import Field, StrictFloat, StrictInt, model_validator

from sibyl import __version__
from sibyl.exchanges.data import TIMEFRAMES
from sibyl.models import BacktestRequest, Request
from sibyl.strategies.backtest import BacktestEngine

MAX_WORK_BARS = 60_000
MIN_TEST_BARS = 20

# Only fields that actually influence the chosen algorithm can be searched.
SEARCH_FIELDS = {
    "ema": ("fast_period", "slow_period"),
    "rsi": ("rsi_period", "rsi_lower", "rsi_upper"),
    "bollinger": ("window", "band_std"),
    "bollinger-surge": (
        "window",
        "band_std",
        "rsi_period",
        "rsi_lower",
        "rsi_upper",
        "fast_period",
        "slow_period",
        "volume_multiplier",
    ),
    "impulse-breakout": (
        "window",
        "band_std",
        "rsi_period",
        "rsi_lower",
        "rsi_upper",
        "fast_period",
        "slow_period",
        "volume_multiplier",
        "macd_fast_period",
        "macd_slow_period",
        "macd_signal_period",
        "adx_period",
    ),
    "quantum-momentum": (
        "tsi_short_period",
        "tsi_long_period",
        "cmf_period",
        "atr_period",
        "macd_fast_period",
        "macd_slow_period",
        "macd_signal_period",
    ),
}
SEARCH_PRESETS = {
    "fast_period": [5, 9, 13],
    "slow_period": [18, 21, 30],
    "rsi_period": [7, 14, 21],
    "rsi_lower": [20, 30, 40],
    "rsi_upper": [60, 70, 80],
    "window": [14, 20, 30],
    "band_std": [1.5, 2, 2.5],
    "volume_multiplier": [1, 1.5, 2],
    "macd_fast_period": [8, 12, 16],
    "macd_slow_period": [20, 26, 35],
    "macd_signal_period": [5, 9, 13],
    "adx_period": [10, 14, 20],
    "atr_period": [10, 14, 20],
    "cmf_period": [10, 20, 30],
    "tsi_short_period": [8, 13, 18],
    "tsi_long_period": [20, 25, 35],
}


class ValidationParameters(BacktestRequest):
    """A simulation over the full immutable input, including larger offline datasets."""

    candles: int = Field(default=180, ge=60, le=20_000)


class WalkForwardRequest(Request):
    """One exact input and a small explicit grid; no network reads or live execution."""

    dataset_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    parameters: ValidationParameters
    grid: dict[str, list[StrictInt | StrictFloat]] = Field(default_factory=dict, max_length=2)
    folds: int = Field(default=3, ge=1, le=5, strict=True)
    initial_train_pct: int = Field(default=60, ge=40, le=80, strict=True)
    objective: Literal["return_pct", "sharpe", "max_drawdown"] = "return_pct"
    min_train_trades: int = Field(default=0, ge=0, le=100, strict=True)

    @model_validator(mode="after")
    def valid_grid(self):
        """Reject irrelevant, duplicate or oversized search axes instead of skipping them."""
        for key, values in self.grid.items():
            if key not in SEARCH_FIELDS[self.parameters.strategy]:
                raise ValueError(f"{key} is not a searchable parameter for this strategy.")
            if not 1 <= len(values) <= 4 or len(set(values)) != len(values):
                raise ValueError("Each search parameter needs one to four distinct numeric values.")
            if not all(math.isfinite(value) for value in values):
                raise ValueError("Search values must be finite.")
        self.candidates()  # Full strategy validation also catches unordered EMA/MACD/TSI pairs.
        return self

    def candidates(self) -> list[dict]:
        """Enumerate the explicit Cartesian grid with stable, deterministic tie order."""
        keys = sorted(self.grid)
        candidates = []
        for index, values in enumerate(product(*(self.grid[key] for key in keys))):
            overrides = dict(zip(keys, values, strict=True))
            params = ValidationParameters(**(self.parameters.model_dump() | overrides))
            candidates.append({"id": index + 1, "overrides": overrides, "parameters": params})
        return candidates


class WalkForwardEngine:
    """Select on past data, then evaluate exactly one chosen candidate per test window."""

    version = "expanding-next-open-v1"

    @staticmethod
    def options() -> dict:
        """Expose actual implemented search fields, limits and editable starter values."""
        return {
            "strategies": {
                strategy: [{"key": key, "values": SEARCH_PRESETS[key]} for key in keys]
                for strategy, keys in SEARCH_FIELDS.items()
            },
            "max_candidates": 16,
            "max_axes": 2,
            "max_values": 4,
            "max_folds": 5,
            "min_test_bars": MIN_TEST_BARS,
            "max_work_bars": MAX_WORK_BARS,
        }

    def run(self, candles: list[dict], request: WalkForwardRequest) -> dict:
        """Return independent folds and evidence, never ranking candidates on their tests."""
        n = len(candles)
        if n != request.parameters.candles:
            raise ValueError("Observation count must match the immutable dataset.")
        candidates = request.candidates()
        warmup = max(c["parameters"].warmup for c in candidates + [{"parameters": request.parameters}])
        initial = n * request.initial_train_pct // 100
        boundaries = [initial + (n - initial) * i // request.folds for i in range(request.folds + 1)]
        if initial < warmup + 20:
            raise ValueError(
                "The initial training window needs at least 20 bars after every candidate's warm-up."
            )
        windows = list(zip(boundaries[:-1], boundaries[1:], strict=True))
        if any(b - a < MIN_TEST_BARS for a, b in windows):
            raise ValueError(
                "Each test window needs at least 20 bars. Use fewer windows or a longer dataset."
            )
        work = sum(len(candidates) * a + 2 * b for a, b in windows)
        if work > MAX_WORK_BARS:
            raise ValueError(
                "This search exceeds 60,000 processed bars. Reduce candidates, windows or dataset size."
            )

        engine, folds = BacktestEngine(), []
        for index, (start, end) in enumerate(windows, 1):
            leaders = []
            for candidate in candidates:
                training = engine.run(candles[:start], candidate["parameters"], evaluation_start=warmup)
                leaders.append(
                    {
                        "candidate_id": candidate["id"],
                        "overrides": candidate["overrides"],
                        "eligible": training["trades"] >= request.min_train_trades,
                        **self._metrics(training),
                    }
                )
            sign = 1 if request.objective == "max_drawdown" else -1
            leaders.sort(
                key=lambda row: (not row["eligible"], sign * row[request.objective], row["candidate_id"])
            )
            if not leaders[0]["eligible"]:
                raise ValueError(
                    f"No candidate meets the minimum training trades in window {index}. Choose a longer input or lower the minimum."
                )
            chosen = candidates[leaders[0]["candidate_id"] - 1]
            test = engine.run(candles[:end], chosen["parameters"], evaluation_start=start)
            fixed = engine.run(candles[:end], request.parameters, evaluation_start=start)
            folds.append(
                {
                    "index": index,
                    "train": {
                        "start": candles[0]["timestamp"],
                        "end": candles[start]["timestamp"],
                        "bars": start,
                        "scored_bars": start - warmup,
                    },
                    "test": {
                        "start": candles[start]["timestamp"],
                        "end": self._end(candles[end - 1], request),
                        "bars": end - start,
                    },
                    "selected": {
                        "candidate_id": chosen["id"],
                        "overrides": chosen["overrides"],
                        "parameters": chosen["parameters"].model_dump(),
                    },
                    "training_ranking": leaders,
                    "out_of_sample": test,
                    "fixed_parameters": self._metrics(fixed),
                }
            )
        returns = [f["out_of_sample"]["return_pct"] for f in folds]
        return {
            "method": self.version,
            "engine_revision": engine.version,
            "engine_version": __version__,
            "request": request.model_dump(),
            "candidate_count": len(candidates),
            "processed_bars": work,
            "common_warmup": warmup,
            "folds": folds,
            "summary": {
                "mean_return_pct": mean(returns),
                "median_return_pct": median(returns),
                "worst_return_pct": min(returns),
                "mean_fixed_return_pct": mean(f["fixed_parameters"]["return_pct"] for f in folds),
                "mean_benchmark_pct": mean(f["out_of_sample"]["benchmark_pct"] for f in folds),
                "profitable_windows": sum(value > 0 for value in returns),
                "test_bars": n - initial,
                "trades": sum(f["out_of_sample"]["trades"] for f in folds),
            },
            "assumptions": [
                "Expanding chronological training windows; parameter selection never reads its later test window.",
                "All candidates share the same initial training warm-up and scored period. Equal scores use candidate order.",
                "Each test starts flat with the same virtual capital and liquidates at its final close, including costs. Returns are independent, not compounded.",
                "Earlier test windows become training history for later windows. Repeated user experiments can overfit; these are not untouched final holdouts or forecasts.",
                "Candidates with no training trades can qualify when the minimum is zero; compare trade counts and fixed settings, not just the winning score.",
            ],
        }

    @staticmethod
    def _metrics(result: dict) -> dict:
        return {key: result[key] for key in ("return_pct", "sharpe", "max_drawdown", "trades", "fees")}

    @staticmethod
    def _end(candle: dict, request: WalkForwardRequest) -> str:
        """Express interval ends as exclusive UTC boundaries, like immutable datasets."""
        from datetime import timedelta

        return (
            datetime.fromisoformat(candle["timestamp"].replace("Z", "+00:00"))
            + timedelta(seconds=TIMEFRAMES[request.parameters.timeframe])
        ).isoformat()


class StrategyValidation:
    """Persist completed research separately from executions; reruns reuse exact input."""

    def __init__(self, store, archive):
        self.store, self.archive = store, archive
        self._lock = threading.Lock()
        with store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS strategy_validations (id TEXT PRIMARY KEY, source TEXT NOT NULL, created_at TEXT NOT NULL, metadata TEXT NOT NULL, payload TEXT NOT NULL)"
            )

    def run(self, request: WalkForwardRequest, *, rerun_of: str | None = None) -> dict:
        """Run one bounded offline search; failures save no misleading partial result."""
        if not self._lock.acquire(blocking=False):
            raise ValueError("Another strategy validation is running. Try again when it completes.")
        try:
            document = self.archive.dataset(request.dataset_id)
            dataset = document["dataset"]
            if (dataset["symbol"], dataset["timeframe"], dataset["count"]) != (
                request.parameters.symbol,
                request.parameters.timeframe,
                request.parameters.candles,
            ):
                raise ValueError("Pair, timeframe and observation count must match the immutable dataset.")
            result = {
                **WalkForwardEngine().run(document["candles"], request),
                "id": uuid4().hex,
                "created_at": datetime.now(UTC).isoformat(),
                "dataset": dataset,
                "source": dataset["source"],
                "environment": dataset["environment"],
            }
            if rerun_of:
                result["rerun_of"] = rerun_of
            metadata = {
                key: result[key]
                for key in (
                    "id",
                    "created_at",
                    "dataset",
                    "source",
                    "environment",
                    "summary",
                    "candidate_count",
                    "request",
                    "method",
                    "engine_revision",
                )
            }
            with self.store.db() as db:
                db.execute(
                    "INSERT INTO strategy_validations VALUES(?,?,?,?,?)",
                    (
                        result["id"],
                        result["source"],
                        result["created_at"],
                        json.dumps(metadata, allow_nan=False),
                        json.dumps(result, allow_nan=False),
                    ),
                )
            return result
        finally:
            self._lock.release()

    def list(self, *, demo: bool | None = None) -> list[dict]:
        """Return the latest 50 small summaries, optionally scoped to the Demo boundary."""
        with self.store.db() as db:
            rows = db.execute(
                "SELECT metadata FROM strategy_validations WHERE (? IS NULL OR (source='demo')=?) ORDER BY created_at DESC LIMIT 50",
                (demo, demo),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def get(self, identity: str) -> dict:
        """Read saved train/test evidence without fetching prices or recomputing."""
        with self.store.db() as db:
            row = db.execute("SELECT payload FROM strategy_validations WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise LookupError("Strategy validation not found.")
        return json.loads(row[0])

    def rerun(self, identity: str) -> dict:
        """Recompute retained input and choices with the current engine, keeping the original."""
        previous = self.get(identity)
        return self.run(WalkForwardRequest(**previous["request"]), rerun_of=identity)
