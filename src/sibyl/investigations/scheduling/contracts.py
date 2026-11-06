"""Daily/weekly scheduling inputs and revision-checked user controls."""

from datetime import time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator

from sibyl.messaging.contracts import TelegramTarget
from sibyl.models import Request


class BriefingSchedule(Request):
    """An explicit local calendar and optional delivery to a verified private Telegram user."""

    frequency: Literal["daily", "weekly"] = "daily"
    local_time: str = Field(default="08:00", pattern=r"^\d{2}:\d{2}$")
    timezone: str = Field(default="UTC", min_length=1, max_length=80)
    weekday: int = Field(default=0, ge=0, le=6, strict=True)
    telegram: bool = Field(default=False, strict=True)
    telegram_target: TelegramTarget | None = None
    telegram_format: Literal["text", "document"] = "text"
    delivery_format: Literal["summary", "full"] = "summary"
    keep_reports: int = Field(default=20, ge=5, le=40, strict=True)

    @model_validator(mode="after")
    def reviewed_recipient(self):
        if self.telegram and self.telegram_target is None:
            raise ValueError("Select the checked Telegram bot and private user before enabling delivery.")
        return self

    @field_validator("local_time")
    @classmethod
    def clock_time(cls, value):
        """Reject invalid wall-clock times before computing an occurrence."""
        time.fromisoformat(value)
        return value

    @field_validator("timezone")
    @classmethod
    def known_zone(cls, value):
        """Use an explicit IANA zone, including daylight-saving calendar rules."""
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Choose an IANA time zone, such as Europe/Zurich or UTC.") from exc
        return value


class CreateBriefing(BriefingSchedule):
    """Saving an armed schedule authorizes future read-only research at its shown times."""

    enabled: bool = Field(default=True, strict=True)


class EditBriefing(BriefingSchedule):
    """Change a reviewed revision, resetting its next occurrence into the future."""

    revision: int = Field(ge=1, strict=True)


class BriefingAction(Request):
    """Pause/resume/archive one schedule without changing an already running report."""

    revision: int = Field(ge=1, strict=True)
    action: Literal["pause", "resume", "archive"]


class RunBriefing(Request):
    """Run an armed schedule once in addition to its next calendar occurrence."""

    revision: int = Field(ge=1, strict=True)
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
