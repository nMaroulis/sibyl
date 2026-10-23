"""Explicit account sets and user-defined limits; no execution or credential fields."""

from typing import Literal

from pydantic import Field, field_validator, model_validator

from sibyl.alerts.contracts import StrategyAlertCreate
from sibyl.models import Request


class RiskAlertCreate(Request):
    """Watch a fixed homogeneous set of active spot accounts on one reference feed."""

    account_ids: list[str] = Field(min_length=1, max_length=10)
    source: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9:-]+$")
    metric: Literal["value_floor", "concentration", "drawdown"]
    threshold: float = Field(gt=0, le=1e15, strict=True)
    reset_threshold: float | None = Field(default=None, ge=0, le=1e16, strict=True)
    asset: str = Field(default="", max_length=24, pattern=r"^[A-Z0-9]*$")
    cooldown_seconds: int = Field(default=300, ge=60, le=86400, strict=True)
    notify_recovery: bool = Field(default=True, strict=True)
    label: str = Field(default="", max_length=80)

    @field_validator("account_ids")
    @classmethod
    def exact_accounts(cls, value):
        if len(set(value)) != len(value) or any(
            item != "demo" and (len(item) != 32 or any(c not in "0123456789abcdef" for c in item))
            for item in value
        ):
            raise ValueError("Choose each saved account once, using its exact ID.")
        return sorted(value)

    @field_validator("label")
    @classmethod
    def single_line(cls, value):
        return StrategyAlertCreate.single_line(value)

    @model_validator(mode="after")
    def limits(self):
        """Keep reset levels on the clear side, expressed in the metric's own units."""
        if self.metric != "value_floor" and self.threshold > 100:
            raise ValueError("Percentage limits must be at most 100.")
        if (self.metric == "concentration") != bool(self.asset):
            raise ValueError("Choose an asset only for a concentration rule.")
        if self.reset_threshold is None:
            self.reset_threshold = (
                self.threshold * 1.01 if self.metric == "value_floor" else max(0, self.threshold - 1)
            )
        if self.metric == "value_floor":
            if self.reset_threshold <= self.threshold:
                raise ValueError("The recovery value must be above the value floor.")
        elif self.reset_threshold >= self.threshold:
            raise ValueError("The recovery percentage must be below the alert limit.")
        return self


class RiskAlertUpdate(RiskAlertCreate):
    """Replace reviewed settings and save paused; Resume starts a new peak/window."""

    revision: int = Field(ge=1, strict=True)
