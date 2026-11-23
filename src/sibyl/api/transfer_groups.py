"""Private retained-funding group reviews; no exchange writes or automatic matching."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from sibyl.api.routes import S
from sibyl.services.transfers.groups.contracts import GroupConfirm, GroupPreview


def private(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/api/v1/account-ledger/transfer-groups", tags=["Accountant"], dependencies=[Depends(private)]
)


@router.get("")
def report(
    s: S,
    account_id: str = Query("", max_length=100),
    asset: str = Query("", pattern=r"^$|^[A-Z0-9][A-Z0-9.]{0,19}$"),
    environment: Literal["", "demo", "test", "production"] = "",
    include_removed: bool = False,
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0, le=1000000),
):
    """Read a page of current/superseded user-asserted groups."""
    return s.transfers.groups.report(account_id, asset, environment, include_removed, limit, offset)


@router.post("/preview")
def preview(body: GroupPreview, s: S):
    """Check exact versions, wallet effects, fees and every matrix sum without saving."""
    return s.transfers.groups.preview(body)


@router.post("")
def confirm(body: GroupConfirm, s: S):
    """Reserve all records atomically after the exact preview and explicit assertions."""
    return s.transfers.groups.confirm(body)


@router.get("/{identity}")
def detail(identity: str, s: S):
    """Read saved and current evidence with the latest fifty audit decisions."""
    return s.transfers.groups.detail(identity)


@router.post("/{identity}/review")
def review(identity: str, body: GroupConfirm, s: S):
    """Re-review the same members or restore a removed revision without stealing reservations."""
    return s.transfers.groups.confirm(body, identity)


@router.delete("/{identity}")
def remove(identity: str, s: S, revision: int = Query(ge=1)):
    """Withdraw this revision and release its member reservations; audit stays retained."""
    return s.transfers.groups.remove(identity, revision)
