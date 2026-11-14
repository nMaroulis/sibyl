"""Bounded, separate fit and validation judgments; no LLM-generated ground truth."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from sibyl.models import Request

PassageID = Annotated[str, Field(pattern=r"^(?:news-)?[a-f0-9]{32}-[0-9]{1,4}-[a-f0-9]{12}$")]


class CalibrationCase(Request):
    """Empty expected IDs explicitly mean no relevant passage exists in this source scope."""

    query: str = Field(min_length=1, max_length=300)
    partition: Literal["fit", "validation"]
    expected: list[PassageID] = Field(max_length=10)

    @model_validator(mode="after")
    def review(self):
        self.query = self.query.strip()
        if not self.query or len(set(self.expected)) != len(self.expected):
            raise ValueError("Use a nonblank query and distinct relevant passage IDs.")
        return self


class CalibrationCreate(Request):
    """At least two answerable and two no-source questions in each independent partition."""

    title: str = Field(min_length=1, max_length=100)
    kind: Literal["all", "document", "news"] = "document"
    cases: list[CalibrationCase] = Field(min_length=8, max_length=32)

    @model_validator(mode="after")
    def review(self):
        self.title = self.title.strip()
        if not self.title or len({c.query.casefold() for c in self.cases}) != len(self.cases):
            raise ValueError("Use a title and distinct questions across both partitions.")
        for partition in ("fit", "validation"):
            rows = [c for c in self.cases if c.partition == partition]
            if sum(bool(c.expected) for c in rows) < 2 or sum(not c.expected for c in rows) < 2:
                raise ValueError("Each partition needs two relevant-source and two no-source questions.")
        return self


class CalibrationPolicy(Request):
    """Activation is separate from fitting and fenced against another editor."""

    revision: int = Field(ge=0, strict=True)
    enabled: bool = Field(strict=True)
    report_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")

    @model_validator(mode="after")
    def review(self):
        if self.enabled and not self.report_id:
            raise ValueError("Choose a completed calibration report before enabling the cutoff.")
        return self
