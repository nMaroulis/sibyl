"""Trusted local research extensions; no code upload, trading tools or execution jobs."""

import math
import re
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Literal

from pydantic import Field, field_validator, model_validator

from sibyl.models import OrderRequest, Request, Timeframe


class Parameter(Request):
    """One bounded numeric control shown directly in the custom-backtest form."""

    label: str = Field(min_length=1, max_length=60)
    kind: Literal["int", "float"] = "int"
    minimum: float = Field(ge=-1e6, le=1e6)
    maximum: float = Field(ge=-1e6, le=1e6)
    default: float

    @model_validator(mode="after")
    def bounds(self):
        if self.minimum > self.maximum or not self.minimum <= self.default <= self.maximum:
            raise ValueError("Invalid plugin parameter bounds/default.")
        if self.kind == "int" and any(v != int(v) for v in (self.minimum, self.maximum, self.default)):
            raise ValueError("Integer parameter bounds/default must be integral.")
        return self

    def value(self, value):
        if (
            type(value) not in {int, float}
            or not math.isfinite(value)
            or not self.minimum <= value <= self.maximum
        ):
            raise ValueError("A plugin parameter is outside its declared numeric bounds.")
        if self.kind == "int" and value != int(value):
            raise ValueError("A plugin parameter requires an integer.")
        return int(value) if self.kind == "int" else float(value)


class PluginSpec(Request):
    """A stable manifest; warmup covers every permitted parameter setting."""

    name: str = Field(min_length=1, max_length=60)
    description: str = Field(min_length=1, max_length=400)
    warmup: int = Field(default=50, ge=30, le=200, strict=True)
    parameters: dict[str, Parameter] = Field(default_factory=dict, max_length=8)

    @field_validator("parameters")
    @classmethod
    def names(cls, values):
        if any(not re.fullmatch(r"[a-z][a-z0-9_]{0,30}", key) for key in values):
            raise ValueError("Plugin parameter names must be simple lowercase identifiers.")
        return values

    def values(self, values):
        if set(values) - set(self.parameters):
            raise ValueError("Unknown plugin parameter.")
        return {key: spec.value(values.get(key, spec.default)) for key, spec in self.parameters.items()}


class StrategyPlugin(ABC):
    """One fresh instance per backtest, receiving immutable past/current OHLCV only.

    Installed plugin code is trusted Python with backend process privileges. This
    interface limits supplied domain data; it is not an OS sandbox or timeout.
    Implementations must be deterministic and avoid I/O and hidden mutable state.
    """

    @property
    @abstractmethod
    def spec(self) -> PluginSpec:
        """Describe the algorithm, bounded controls and fixed warmup."""

    @abstractmethod
    def signal(self, candles: tuple[Mapping, ...], parameters: Mapping) -> int:
        """Return Python int BUY=1, SELL=-1 or HOLD=0 using this candle prefix."""


class PluginBacktest(Request):
    plugin_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    values: dict[str, float | int] = Field(default_factory=dict, max_length=8)
    input_kind: Literal["current_feed", "saved_dataset", "demo"] = "current_feed"
    dataset_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    symbol: str = "BTC/USDT"
    timeframe: Timeframe = "1d"
    candles: int = Field(default=180, ge=60, le=2000, strict=True)
    capital: float = Field(default=10000, ge=100, le=1e7, strict=True)
    fee_bps: float = Field(default=10, ge=0, le=200, strict=True)
    slippage_bps: float = Field(default=5, ge=0, le=200, strict=True)
    stop_loss_pct: float | None = Field(default=None, gt=0, le=90, strict=True)
    take_profit_pct: float | None = Field(default=None, gt=0, le=1000, strict=True)
    max_trades: int | None = Field(default=None, ge=1, le=10000, strict=True)

    _symbol = field_validator("symbol")(OrderRequest.valid_symbol.__func__)

    @field_validator("values", mode="before")
    @classmethod
    def numeric_values(cls, values):
        if not isinstance(values, dict) or any(type(v) not in {int, float} for v in values.values()):
            raise ValueError("Plugin values must be numeric, not booleans or strings.")
        return values

    @model_validator(mode="after")
    def input(self):
        if (self.input_kind == "saved_dataset") != (self.dataset_id is not None):
            raise ValueError("Choose a dataset only for saved-input research.")
        if self.input_kind != "saved_dataset" and self.candles > 720:
            raise ValueError("Current/Demo pages support up to 720 candles.")
        return self
