"""Finite local-history controls; clearing does not change alert rules or exchange records."""

from typing import Literal

from pydantic import Field

from sibyl.models import Request

Kind = Literal["all", "price", "risk", "strategy", "connection", "order", "workspace"]


class RetentionPolicy(Request):
    enabled: bool = False
    days: int = Field(default=90, ge=7, le=3650, strict=True)
    revision: int = Field(ge=0, strict=True)


class ClearHistory(Request):
    revision: int = Field(ge=0, strict=True)
