"""Bounded, owner-selected basket studies; no optimization, forecasts or trading actions."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from sibyl.models import Request


class RiskStudy(Request):
    scope: str = Field(default="all", max_length=120, pattern=r"^[a-z0-9:-]+$")
    assets: list[Annotated[str, Field(pattern=r"^[A-Z0-9]{1,12}$")]] = Field(min_length=1, max_length=8)
    days: Literal[30, 60, 90, 180, 365] = 90

    @model_validator(mode="after")
    def distinct(self):
        if len(set(self.assets)) != len(self.assets):
            raise ValueError("Choose each holding once.")
        return self
