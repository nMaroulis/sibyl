"""Small bounded distributions and immutable-input study recipes."""

import math
from typing import Annotated, Literal, get_args

from pydantic import Field, StrictFloat, StrictInt, TypeAdapter, model_validator

from sibyl.models import Request
from sibyl.strategies.validation import SEARCH_FIELDS, ValidationParameters


class Distribution(Request):
    """An explicit numeric domain; log sampling is positive and incompatible with a float step."""

    kind: Literal["int", "float"] = "int"
    low: StrictInt | StrictFloat
    high: StrictInt | StrictFloat
    step: StrictInt | StrictFloat | None = None
    log: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def bounds(self):
        if (
            not all(math.isfinite(value) and abs(value) <= 1e6 for value in (self.low, self.high))
            or self.low >= self.high
        ):
            raise ValueError("Choose finite increasing distribution bounds within ±1,000,000.")
        if self.kind == "int" and any(value != int(value) for value in (self.low, self.high)):
            raise ValueError("Integer distribution bounds must be integral.")
        if self.log and self.low <= 0:
            raise ValueError("Log distributions need positive bounds.")
        if self.step is not None:
            if not math.isfinite(self.step) or self.step <= 0 or self.step > self.high - self.low:
                raise ValueError("Choose a positive step within the range.")
            if self.kind == "int" and self.step != int(self.step):
                raise ValueError("An integer distribution needs an integer step.")
            if self.log and (self.kind == "float" or self.step != 1):
                raise ValueError("Log sampling supports no float step and only unit integer steps.")
            quotient = (self.high - self.low) / self.step
            if not math.isclose(quotient, round(quotient), rel_tol=1e-10, abs_tol=1e-10):
                raise ValueError(
                    "The range must be an exact number of steps; bounds are never silently changed."
                )
        return self

    def suggest(self, trial, name):
        """Use the installed sampler's typed distribution primitives directly."""
        if self.kind == "int":
            return trial.suggest_int(
                name, int(self.low), int(self.high), step=int(self.step or 1), log=self.log
            )
        return trial.suggest_float(name, float(self.low), float(self.high), step=self.step, log=self.log)


class AdaptiveStudy(Request):
    """One retained dataset, up to four distributions and independent chronological tests."""

    dataset_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    parameters: ValidationParameters
    engine: Literal["builtin", "plugin"] = "builtin"
    plugin_id: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9-]{0,63}$")
    plugin_revision: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    plugin_values: dict[str, StrictInt | StrictFloat] = Field(default_factory=dict, max_length=8)
    distributions: dict[str, Distribution] = Field(min_length=1, max_length=4)
    sampler: Literal["tpe", "random"] = "tpe"
    trials: int = Field(default=12, ge=4, le=24, strict=True)
    seed: int = Field(default=42, ge=0, le=2**32 - 1, strict=True)
    folds: int = Field(default=3, ge=1, le=5, strict=True)
    initial_train_pct: int = Field(default=60, ge=40, le=80, strict=True)
    objective: Literal["return_pct", "sharpe", "max_drawdown"] = "return_pct"
    min_train_trades: int = Field(default=0, ge=0, le=100, strict=True)

    @model_validator(mode="after")
    def validate_recipe(self):
        if self.parameters.candles > 2000:
            raise ValueError("Adaptive studies support at most 2,000 retained candles.")
        if self.sampler == "tpe" and self.trials < 8:
            raise ValueError(
                "TPE needs at least eight trials; the first five completed trials are startup sampling."
            )
        if self.engine == "plugin":
            if not self.plugin_id or not self.plugin_revision:
                raise ValueError("Select an explicitly installed plugin and its revision.")
        elif self.plugin_id or self.plugin_revision or self.plugin_values:
            raise ValueError("Plugin settings apply only to custom plugin studies.")
        if self.engine == "builtin":
            fields = ValidationParameters.model_fields
            for name, distribution in self.distributions.items():
                if name not in SEARCH_FIELDS[self.parameters.strategy]:
                    raise ValueError("Only this algorithm's effective parameters can be sampled.")
                field = fields[name]
                integer = field.annotation is int or int in get_args(field.annotation)
                if integer != (distribution.kind == "int"):
                    raise ValueError("The distribution type must match the algorithm parameter.")
                adapter = TypeAdapter(Annotated[field.annotation, *field.metadata])
                for value in (distribution.low, distribution.high):
                    adapter.validate_python(int(value) if integer else value)
        return self
