"""Explicit Bitcoin research requests; identifiers stay out of local access-log URLs."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Response
from pydantic import Field, model_validator

from sibyl.api.routes import S
from sibyl.blockchain.bitcoin import BitcoinUnavailable
from sibyl.blockchain.identifiers import address, txid
from sibyl.models import Request

router = APIRouter(prefix="/api/v1/bitcoin", tags=["Explorer"])


class BitcoinLookup(Request):
    """Inspect one public reference or an explicitly selected synthetic Demo fixture."""

    kind: Literal["transaction", "address"]
    value: str = Field(min_length=14, max_length=90)
    demo: bool = Field(default=False, strict=True)
    input_offset: int = Field(default=0, ge=0, le=9999, strict=True)
    output_offset: int = Field(default=0, ge=0, le=9999, strict=True)

    @model_validator(mode="after")
    def identifier(self):
        self.value = txid(self.value) if self.kind == "transaction" else address(self.value)
        if self.kind == "address" and (self.input_offset or self.output_offset):
            raise ValueError("Input/output pagination is only available for transactions.")
        return self


class BitcoinHistory(Request):
    """Read a confirmed history page or a separate bounded pending observation."""

    address: str = Field(min_length=14, max_length=90)
    cursor: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    pending: bool = Field(default=False, strict=True)
    demo: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def selection(self):
        self.address = address(self.address)
        if self.pending and self.cursor:
            raise ValueError("Pending transactions have no history pagination cursor.")
        return self


def read(method, *args, **kwargs):
    """Keep domain errors readable without exposing upstream bodies, query IDs or URLs."""
    try:
        return method(*args, **kwargs)
    except BitcoinUnavailable as exc:
        headers = {"Cache-Control": "no-store"}
        if exc.status == 429:
            headers["Retry-After"] = "30"
        raise HTTPException(exc.status, detail=str(exc), headers=headers) from None
    except LookupError:
        raise HTTPException(
            404, detail="Bitcoin reference not found by this source.", headers={"Cache-Control": "no-store"}
        ) from None


@router.get("")
def capabilities(s: S, response: Response):
    """Describe supported mainnet lookup scope without contacting its public source."""
    response.headers["Cache-Control"] = "no-store"
    return s.research.bitcoin.capabilities()


@router.post("/inspect")
def inspect(body: BitcoinLookup, s: S, response: Response):
    """Inspect a single reference; POST avoids putting entered identifiers in local URL logs."""
    response.headers["Cache-Control"] = "no-store"
    if body.kind == "transaction":
        return read(
            s.research.bitcoin.transaction,
            body.value,
            simulated=body.demo,
            input_offset=body.input_offset,
            output_offset=body.output_offset,
        )
    return read(s.research.bitcoin.address, body.value, simulated=body.demo)


@router.post("/history")
def history(body: BitcoinHistory, s: S, response: Response):
    """Read one bounded confirmed/pending address page without a persisted lookup history."""
    response.headers["Cache-Control"] = "no-store"
    return read(
        s.research.bitcoin.history,
        body.address,
        cursor=body.cursor,
        pending=body.pending,
        simulated=body.demo,
    )
