"""Explicit measurement periods and audited, source-bound cash-flow assertions."""

from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator

from sibyl.models import Request


class StartPeriod(Request):
    label: str = Field(default="Account performance", min_length=1, max_length=80)
    scope: str = Field(default="all", max_length=140)

    @field_validator("label")
    @classmethod
    def plain(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("Use a non-empty single-line period label.")
        return value.strip()


class PeriodRevision(Request):
    revision: int = Field(ge=1, strict=True)


class FlowReview(PeriodRevision):
    source_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    classification: Literal["external", "own_transfer", "performance", "outside"]
    value: Decimal = Field(ge=0, le=Decimal("1e24"))
    occurred_at: AwareDatetime
    note: str = Field(min_length=1, max_length=1000)


class CoverageReview(PeriodRevision):
    evidence_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmed: bool = Field(strict=True)
    note: str = Field(min_length=1, max_length=1000)


class ManualFlow(PeriodRevision):
    """A user-supplied external principal value; never an imported exchange observation."""

    account_id: str = Field(min_length=1, max_length=100)
    direction: Literal["in", "out"]
    value: Decimal = Field(gt=0, le=Decimal("1e24"))
    occurred_at: AwareDatetime
    note: str = Field(min_length=1, max_length=1000)
