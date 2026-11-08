"""Small research inputs and the structured answer requested through ProtoLink."""

from typing import Literal

from pydantic import Field, field_validator

from sibyl.models import Request, Timeframe


class InvestigationContext(Request):
    """Starting selections for the specialists, not a trading or authorization policy."""

    symbol: str = Field(default="BTC/USDT", pattern=r"^[A-Z0-9][A-Z0-9.:-]{0,24}/[A-Z0-9][A-Z0-9.:-]{0,24}$")
    timeframe: Timeframe = "1d"
    market_source: str = Field(default="", max_length=120)
    portfolio_scope: str = Field(
        default="all", pattern=r"^(all|account:[a-zA-Z0-9_-]{1,80}|exchange:[a-z0-9_-]{1,40})$"
    )
    news_mode: Literal["", "demo", "live"] = ""


class InvestigationCreate(Request):
    """Save a research question independently of provider availability or model execution."""

    title: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=2400)
    context: InvestigationContext = Field(default_factory=InvestigationContext)

    @field_validator("title", "question")
    @classmethod
    def nonblank(cls, value: str) -> str:
        """Reject empty labels/questions before saving or making a model request."""
        if not value.strip():
            raise ValueError("Enter a title and a research question.")
        return value.strip()


class InvestigationRun(Request):
    """A caller-generated identity makes a repeated HTTP submission idempotent."""

    request_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    checkpoints: bool = Field(default=False, strict=True)


class Finding(Request):
    """One model interpretation linked to actual observed agent/tool pairs."""

    title: str = Field(min_length=1, max_length=160)
    detail: str = Field(min_length=1, max_length=4000)
    sources: list[str] = Field(default_factory=list, max_length=10)


class InvestigationReport(Request):
    """The final answer schema; tool receipts remain separate from model interpretation."""

    summary: str = Field(min_length=1, max_length=4000)
    findings: list[Finding] = Field(max_length=12)
    uncertainties: list[str] = Field(max_length=12)
    next_questions: list[str] = Field(max_length=6)

    @field_validator("uncertainties", "next_questions")
    @classmethod
    def bounded_text(cls, values: list[str]) -> list[str]:
        """Keep model-produced lists small enough for the report and JSON export."""
        if any(not value.strip() or len(value) > 2000 for value in values):
            raise ValueError("Report list entries must contain 1–2000 characters.")
        return values


class WorkflowContinuation(Request):
    """Answer only the currently displayed native interruption and fingerprint."""

    kind: Literal["continue", "answer", "approve", "reject"]
    request_id: str | None = Field(default=None, max_length=200)
    fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    answer: str | None = Field(default=None, min_length=1, max_length=4000)
