"""Validated local alert subscriptions; no execution or credential fields."""

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


class AlertAction(Request):
    """Apply a lifecycle action only to the revision the user actually reviewed."""

    action: Literal["pause", "arm", "archive", "restore"]
    revision: int = Field(ge=1, strict=True)


# Existing strategy callers retain the same shared lifecycle contract.
StrategyAlertAction = AlertAction


class ConnectionAlertCreate(Request):
    """Watch transport failures per operation on one configured/observed source."""

    source: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9:-]+$")
    failures_required: int = Field(default=3, ge=1, le=10, strict=True)
    successes_required: int = Field(default=2, ge=1, le=5, strict=True)
    notify_recovery: bool = Field(default=True, strict=True)
    label: str = Field(default="", max_length=80)

    @field_validator("label")
    @classmethod
    def single_line(cls, value):
        return StrategyAlertCreate.single_line(value)


class ConnectionAlertUpdate(ConnectionAlertCreate):
    """Save reviewed changes paused; restart observation only on explicit Resume."""

    revision: int = Field(ge=1, strict=True)
