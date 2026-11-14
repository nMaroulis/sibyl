"""Bounded review inputs for native-asset split and merged transfers.

Each leg binds a retained funding version. Edges are explicit user allocations,
not inferred transaction tracing. Their listed order determines FIFO slicing.
"""

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from sibyl.models import Request

ID = r"^[a-f0-9]{64}$"


class GroupLeg(Request):
    """Select one source version and explain its amount and same-asset fee."""

    event_id: str = Field(pattern=ID)
    source_version: str = Field(pattern=ID)
    amount: Literal["total_debit", "principal", "net_credit", "gross_receipt"]
    fee_quantity: Decimal | None = Field(default=None, ge=0, le=Decimal("1e30"), allow_inf_nan=False)


class GroupEdge(Request):
    """Allocate dispatched principal to one receipt, before that receipt's fee."""

    outgoing_id: str = Field(pattern=ID)
    incoming_id: str = Field(pattern=ID)
    quantity: Decimal = Field(gt=0, le=Decimal("1e30"), allow_inf_nan=False)


class GroupPreview(Request):
    """Review 3–16 records and an exact, ordered principal allocation matrix."""

    outgoing: list[GroupLeg] = Field(min_length=1, max_length=8)
    incoming: list[GroupLeg] = Field(min_length=1, max_length=8)
    edges: list[GroupEdge] = Field(min_length=2, max_length=64)
    distinct_fees_confirmed: bool = False

    @model_validator(mode="after")
    def unique_members(self):
        ids = [leg.event_id for leg in [*self.outgoing, *self.incoming]]
        if len(ids) < 3 or len(set(ids)) != len(ids):
            raise ValueError("Use at least three distinct records; use a pair review for two.")
        edges = [(edge.outgoing_id, edge.incoming_id) for edge in self.edges]
        if len(set(edges)) != len(edges):
            raise ValueError("Use one quantity per source/destination edge.")
        return self


class GroupConfirm(GroupPreview):
    """Accept the exact preview and explicit ownership/wallet assertions."""

    review_fingerprint: str = Field(pattern=ID)
    revision: int = Field(default=0, ge=0, strict=True)
    note: str = Field(min_length=8, max_length=1000)
    own_accounts_confirmed: bool
    configured_wallets_confirmed: bool

    @model_validator(mode="after")
    def assertions(self):
        if not self.own_accounts_confirmed or not self.configured_wallets_confirmed:
            raise ValueError(
                "Confirm that these are your accounts and all legs affect their configured wallets."
            )
        if len(self.note.strip()) < 8:
            raise ValueError("Explain the evidence behind this transfer group in at least eight characters.")
        return self
