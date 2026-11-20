"""Public job controls contain domain arguments, never Python paths or credentials."""

from typing import Literal

from pydantic import AwareDatetime, Field, field_validator

from sibyl.models import Request


class CreateJob(Request):
    label: str = Field(min_length=1, max_length=80)
    kind: str = Field(pattern=r"^[a-z][a-z0-9.-]{0,63}$")
    arguments: dict = Field(default_factory=dict)
    interval_seconds: int | None = Field(default=None, ge=60, le=2_678_400, strict=True)
    start_at: AwareDatetime | None = None
    missed: Literal["skip", "once"] = "skip"
    enabled: bool = Field(default=False, strict=True)

    @field_validator("label")
    @classmethod
    def clean_label(cls, value):
        if not value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError("Use a nonblank job label without control characters.")
        return value.strip()


class JobAction(Request):
    action: Literal["pause", "resume", "archive"]
    revision: int = Field(ge=0, strict=True)


class StartJob(Request):
    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class AccountingArguments(Request):
    account_id: str = Field(default="", max_length=100)
    environment: Literal["", "demo", "test", "production"] = ""
    currency: str = Field(default="USDT", pattern=r"^[A-Z0-9][A-Z0-9.]{0,19}$")
    source: str = Field(default="binance", pattern=r"^[a-z0-9:-]{1,120}$")


class NoArguments(Request):
    pass
