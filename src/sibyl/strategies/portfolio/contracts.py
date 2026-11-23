"""Strict bounded allocations and explicit historical input/rebalancing choices."""

import math
from typing import Literal

from pydantic import Field, model_validator

from sibyl.models import Request, Timeframe


class PortfolioLeg(Request):
    symbol: str = Field(pattern=r"^[A-Z0-9][A-Z0-9._-]{0,29}/[A-Z0-9][A-Z0-9._-]{0,29}$")
    weight_pct: float = Field(gt=0, le=100, strict=True)
    dataset_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class PortfolioStudy(Request):
    """Long-only assets plus residual quote cash; no leverage, shorting or currency conversion."""

    title: str = Field(default="My portfolio study", min_length=1, max_length=100)
    input_kind: Literal["current_feed", "saved_datasets", "demo"] = "current_feed"
    legs: list[PortfolioLeg] = Field(min_length=2, max_length=8)
    timeframe: Timeframe = "1d"
    candles: int = Field(default=180, ge=60, le=2000, strict=True)
    capital: float = Field(default=10000, ge=100, le=1e8, strict=True)
    fee_bps: float = Field(default=10, ge=0, le=200, strict=True)
    slippage_bps: float = Field(default=5, ge=0, le=200, strict=True)
    rule: Literal["interval", "drift"] = "interval"
    interval_bars: int = Field(default=30, ge=1, le=500, strict=True)
    drift_pct: float = Field(default=5, gt=0, le=50, strict=True)

    @model_validator(mode="after")
    def allocation(self):
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("Name this portfolio study.")
        if len({leg.symbol for leg in self.legs}) != len(self.legs):
            raise ValueError("Choose each asset/pair once.")
        if len({leg.symbol.split("/")[0] for leg in self.legs}) != len(self.legs):
            raise ValueError("A base asset cannot appear twice.")
        if len({leg.symbol.split("/")[1] for leg in self.legs}) != 1:
            raise ValueError("All assets must use the exact same quote currency; no conversion is assumed.")
        if math.fsum(leg.weight_pct for leg in self.legs) > 100:
            raise ValueError("Asset weights must total at most 100%; the rest is quote cash.")
        if any((leg.dataset_id is not None) != (self.input_kind == "saved_datasets") for leg in self.legs):
            raise ValueError("Supply one dataset per asset only for saved-dataset input.")
        if self.input_kind == "saved_datasets" and len({leg.dataset_id for leg in self.legs}) != len(
            self.legs
        ):
            raise ValueError("Choose a different saved dataset for every asset.")
        return self
