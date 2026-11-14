"""Explicit Bitcoin research requests; identifiers stay out of local access-log URLs."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Path, Response
from pydantic import Field, model_validator

from sibyl.api.routes import S
from sibyl.blockchain.bitcoin import BitcoinUnavailable
from sibyl.blockchain.identifiers import address, txid
from sibyl.blockchain.watches import WatchConflict
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


class BitcoinOutputSpends(Request):
    """Inspect spending observations for one exact transaction output page."""

    transaction_id: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    output_offset: int = Field(default=0, ge=0, le=9999, strict=True)
    demo: bool = Field(default=False, strict=True)


@router.post("/output-spends")
def output_spends(body: BitcoinOutputSpends, s: S, response: Response):
    """Read current output-spend evidence without creating a watch or persisting lookup IDs."""
    response.headers["Cache-Control"] = "no-store"
    return read(
        s.research.bitcoin.output_spends,
        body.transaction_id,
        output_offset=body.output_offset,
        simulated=body.demo,
    )


class BitcoinWatchRequest(Request):
    """Choose one exact output and a fixed data source for periodic checks."""

    transaction_id: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    output_index: int = Field(ge=0, le=9999, strict=True)
    demo: bool = Field(default=False, strict=True)


class BitcoinWatchControl(Request):
    """Apply a control against the locally observed watch revision."""

    action: Literal["pause", "resume", "remove"]
    revision: int = Field(ge=1, strict=True)


def write_watch(method, *args):
    """Keep watch controls private and report expired revisions as conflicts."""
    try:
        return method(*args)
    except (WatchConflict, ValueError, LookupError) as exc:
        status = 409 if isinstance(exc, WatchConflict) else 404 if isinstance(exc, LookupError) else 400
        raise HTTPException(status, detail=str(exc), headers={"Cache-Control": "no-store"}) from None


@router.get("/watches")
def watches(s: S, response: Response):
    """List saved watches and their latest reliable evidence without a provider read."""
    response.headers["Cache-Control"] = "no-store"
    return s.bitcoin_watches.list()


@router.post("/watches", status_code=201)
def create_watch(body: BitcoinWatchRequest, s: S, response: Response):
    """Enable a periodic check of an exact output."""
    response.headers["Cache-Control"] = "no-store"
    return write_watch(s.bitcoin_watches.create, body.transaction_id, body.output_index, body.demo)


@router.post("/watches/{watch_id}", responses={409: {"description": "Watch changed or recovery required"}})
def control_watch(
    body: BitcoinWatchControl, s: S, response: Response, watch_id: str = Path(pattern=r"^[a-f0-9]{32}$")
):
    """Update a local watch by opaque ID."""
    response.headers["Cache-Control"] = "no-store"
    return write_watch(s.bitcoin_watches.control, watch_id, body.action, body.revision)
