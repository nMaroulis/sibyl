"""Explicit, revision-bound risk policies; production and virtual funds never mix."""

from typing import Literal

from pydantic import Field, model_validator

from sibyl.models import Request

Environment = Literal["production", "test"]
SAVE_CONFIRMATION = "SAVE STRATEGY LIMITS"
RELEASE_CONFIRMATION = "RELEASE DAILY LOSS LOCK"


class LimitPolicy(Request):
    """Reference-USDT caps across every exchange strategy in one funds environment."""

    enabled: bool = Field(default=False, strict=True)
    source: str = Field(default="binance", min_length=1, max_length=150)
    max_allocated: float | None = Field(default=None, gt=0, le=1e12, strict=True)
    max_exposure: float | None = Field(default=None, gt=0, le=1e12, strict=True)
    max_daily_loss: float | None = Field(default=None, gt=0, le=1e12, strict=True)

    @model_validator(mode="after")
    def complete(self):
        if self.enabled and any(
            value is None for value in (self.max_allocated, self.max_exposure, self.max_daily_loss)
        ):
            raise ValueError("Set all three shared limits before enabling this policy.")
        if self.source == "demo":
            raise ValueError("Exchange strategy limits require an observed market feed, not Demo.")
        return self


class SaveLimits(LimitPolicy):
    """Saving changes pauses affected runs and invalidates their unused approvals."""

    revision: int = Field(ge=0, strict=True)
    confirmation: str = Field(max_length=120)


class ReleaseLossLock(Request):
    """Release a prior UTC day's lock after a fresh assessment; never resume runs."""

    revision: int = Field(ge=0, strict=True)
    confirmation: str = Field(max_length=120)
