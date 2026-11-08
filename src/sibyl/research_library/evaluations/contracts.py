"""Small explicit judgments and bounded retrieval experiments; no generated gold labels."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from sibyl.models import Request


class Judgment(Request):
    query: str = Field(min_length=1, max_length=300)
    expected: list[Annotated[str, Field(pattern=r"^(?:news-)?[a-f0-9]{32}-[0-9]{1,4}-[a-f0-9]{12}$")]] = (
        Field(min_length=1, max_length=10)
    )

    @model_validator(mode="after")
    def distinct(self):
        self.query = self.query.strip()
        if not self.query or len(set(self.expected)) != len(self.expected):
            raise ValueError("Use a nonempty query and distinct relevant passage IDs.")
        return self


class EvaluationSuite(Request):
    title: str = Field(min_length=1, max_length=100)
    kind: Literal["all", "document", "news"] = "all"
    cases: list[Judgment] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def distinct(self):
        self.title = self.title.strip()
        if not self.title or len({row.query.casefold() for row in self.cases}) != len(self.cases):
            raise ValueError("Use a title and distinct evaluation queries.")
        return self


class EvaluationRun(Request):
    methods: list[Literal["keyword", "semantic", "hybrid"]] = Field(
        default=["keyword"], min_length=1, max_length=3
    )
    k: int = Field(default=5, ge=1, le=10, strict=True)

    @model_validator(mode="after")
    def distinct(self):
        if len(set(self.methods)) != len(self.methods):
            raise ValueError("Choose each retrieval method once.")
        return self
