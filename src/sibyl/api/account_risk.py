"""Private explicit current-basket studies; no reads start just by opening saved evidence."""

from fastapi import APIRouter, Depends, Query, Response

from sibyl.accounting.risk.contracts import RiskStudy
from sibyl.api.routes import S


def private(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/v1/account/risk", tags=["Accountant"], dependencies=[Depends(private)])


@router.get("")
def studies(s: S, scope: str = Query("all", max_length=120, pattern=r"^[a-z0-9:-]+$")):
    return s.portfolio.risk.list(scope)


@router.post("", status_code=201)
def create(body: RiskStudy, s: S):
    """Read current selected holdings and exact-source history, then save measured basket statistics."""
    return s.portfolio.risk.create(body)


@router.get("/{identity}")
def study(identity: str, s: S):
    return s.portfolio.risk.get(identity)


@router.delete("/{identity}", status_code=204)
def remove(identity: str, s: S):
    s.portfolio.risk.delete(identity)
