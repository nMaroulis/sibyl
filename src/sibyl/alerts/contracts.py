"""Validated subscriptions to the existing strategy journal; no execution fields."""

from typing import Literal

from pydantic import Field, field_validator

from sibyl.models import Request


class AlertConflict(Exception):
    """An explicit rule/configuration change made an open editor stale."""


StrategyAlertGroup = Literal["attention", "lifecycle"]


class StrategyAlertCreate(Request):
    """Watch future events from one retained run; start at its current journal tail."""

    job_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    events: list[StrategyAlertGroup] = Field(
        default_factory=lambda: ["attention"], min_length=1, max_length=2
    )
    label: str = Field(default="", max_length=80)

    @field_validator("events")
    @classmethod
    def unique_groups(cls, value):
        """Reject duplicate categories instead of silently altering the user's rule."""
        if len(set(value)) != len(value):
            raise ValueError("Choose each event category once.")
        return sorted(value)

    @field_validator("label")
    @classmethod
    def single_line(cls, value):
        """Keep notification names short and free of control characters."""
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Use a single-line alert name.")
        return value.strip()


class StrategyAlertUpdate(StrategyAlertCreate):
    """Save reviewed settings paused, preserving old notifications."""

    revision: int = Field(ge=1, strict=True)


class StrategyAlertAction(Request):
    """Apply a lifecycle action only to the revision the user actually reviewed."""

    action: Literal["pause", "arm", "archive", "restore"]
    revision: int = Field(ge=1, strict=True)
