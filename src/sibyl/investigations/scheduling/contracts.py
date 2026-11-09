"""Daily/weekly scheduling inputs and revision-checked user controls."""

from datetime import time
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator

from sibyl.messaging.contracts import TelegramTarget
from sibyl.messaging.delivery.contracts import NotificationChannel, PrivateTarget
from sibyl.models import Request


class BriefingSchedule(Request):
    """A local calendar with optional text delivery to one checked private connection."""

    frequency: Literal["daily", "weekly"] = "daily"
    local_time: str = Field(default="08:00", pattern=r"^\d{2}:\d{2}$")
    timezone: str = Field(default="UTC", min_length=1, max_length=80)
    weekday: int = Field(default=0, ge=0, le=6, strict=True)
    channel: NotificationChannel | None = None
    private_target: PrivateTarget | None = None
    message_format: Literal["text", "document"] = "text"
    # Boundary aliases keep existing Telegram calendars/clients readable.
    telegram: bool = Field(default=False, strict=True)
    telegram_target: TelegramTarget | None = None
    telegram_format: Literal["text", "document"] = "text"
    delivery_format: Literal["summary", "full"] = "summary"
    keep_reports: int = Field(default=20, ge=5, le=40, strict=True)

    @model_validator(mode="after")
    def reviewed_recipient(self):
        """Normalize legacy Telegram inputs and reject contradictory or stale-route consent."""
        if self.telegram:
            if "channel" in self.model_fields_set and self.channel != "telegram":
                raise ValueError("Choose one delivery channel; Telegram conflicts with this selection.")
            self.channel = "telegram"
        elif self.channel == "telegram":
            if "telegram" in self.model_fields_set:
                raise ValueError("Telegram delivery conflicts with the disabled legacy setting.")
            self.telegram = True
        if self.channel == "telegram":
            if self.telegram_target is None or self.private_target is not None:
                raise ValueError("Select the checked Telegram bot and private user before enabling delivery.")
        elif self.channel is not None:
            if (
                self.private_target is None
                or self.private_target.channel != self.channel
                or self.telegram_target is not None
            ):
                raise ValueError("Select this channel's checked private recipient before enabling delivery.")
        elif self.private_target is not None or self.telegram_target is not None:
            raise ValueError("A delivery target requires an explicit selected channel.")
        if "telegram_format" in self.model_fields_set:
            if "message_format" in self.model_fields_set and self.telegram_format != self.message_format:
                raise ValueError("Choose one consistent message format.")
            self.message_format = self.telegram_format
        self.telegram_format = self.message_format
        if self.channel not in {None, "telegram"} and self.message_format == "document":
            raise ValueError(
                "Document briefings are supported only by Telegram; choose text for this channel."
            )
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


def delivery_channel(schedule):
    """Read canonical destination or an unchanged legacy Telegram calendar."""
    return schedule.get("channel", "telegram" if schedule.get("telegram") else None)


def delivery_binding(schedule):
    """Keep original target facts separate from the model-facing schedule projection."""
    return schedule.get("delivery_binding") or schedule.get("telegram_binding") or {}


def message_format(schedule):
    return schedule.get("message_format", schedule.get("telegram_format", "text"))
