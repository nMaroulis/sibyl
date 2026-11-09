"""Explicit consent for attributing existing base units, without moving exchange funds."""

from typing import Literal

from pydantic import Field, model_validator

from sibyl.models import Request


class OwnershipReview(Request):
    """Review a positive base quantity and, for adoption, an asserted total quote cost."""

    action: Literal["adopt", "release"]
    quantity: float = Field(gt=0, le=1_000_000, strict=True)
    cost_basis: float | None = Field(default=None, ge=0, le=100_000_000, strict=True)
    note: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def basis_required(self):
        if (self.action == "adopt") != (self.cost_basis is not None):
            raise ValueError(
                "Adoption needs an asserted total cost basis; release carries the recorded basis."
            )
        if not self.note.strip():
            raise ValueError("Explain the ownership change before reviewing it.")
        return self
