"""Private cross-market accounting reads and explicit local inventory assertions."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from sibyl.accounting.executions.service import ASSET, AssetOpening
from sibyl.accounting.executions.versions import history
from sibyl.api.routes import S


def private(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/api/v1/account-books", tags=["Account accounting"], dependencies=[Depends(private)]
)


@router.get("")
def report(
    s: S,
    account_id: str = Query("", max_length=100),
    environment: Literal["", "demo", "test", "production"] = "",
    currency: str = Query("USDT", pattern=ASSET),
    source: str = Query("binance", pattern=r"^[a-z0-9:-]{1,120}$"),
):
    """Read cross-pair FIFO with dated fee conversions; never refresh provider data."""
    return s.performance.account_books.report(account_id, environment, currency, source)


@router.get("/openings")
def openings(s: S, account_id: str = Query("", max_length=100), currency: str = Query("USDT", pattern=ASSET)):
    """List reporting-unit-specific user assertions."""
    return s.performance.account_books.openings(account_id, currency)


@router.post("/openings/{account_id}")
def opening(account_id: str, body: AssetOpening, s: S):
    """Save a revision-checked opening; provider facts remain immutable."""
    return s.performance.account_books.save_opening(account_id, body)


@router.delete("/openings/{identity}")
def remove(identity: str, revision: int, s: S):
    """Withdraw one explicitly selected revision while preserving its audit."""
    return s.performance.account_books.remove_opening(identity, revision)


@router.get("/fills/{fill_id}/versions")
def versions(
    fill_id: str, s: S, offset: int = Query(0, ge=0, le=100000), limit: int = Query(50, ge=1, le=100)
):
    """Read real retained fill observations, distinguishing legacy baselines."""
    return history(s.store, fill_id, offset, limit)
