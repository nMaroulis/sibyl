"""Explicit measured-return controls and read-only accounting evidence."""

from fastapi import APIRouter, Depends, Response

from sibyl.api.routes import S
from sibyl.services.portfolio.returns.contracts import (
    CoverageReview,
    FlowReview,
    ManualFlow,
    PeriodRevision,
    StartPeriod,
)


def private(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/api/v1/account-returns", tags=["Account performance"], dependencies=[Depends(private)]
)


@router.get("")
def periods(s: S, scope: str = "all"):
    """List periods by their original view, without fetching balances or prices."""
    return s.performance.returns.list(scope)


@router.post("", status_code=201)
def start(body: StartPeriod, s: S):
    """Capture a fully priced opening observation for the selected active account set."""
    return s.performance.returns.start(body)


@router.get("/{identity}")
def detail(identity: str, s: S):
    """Read/export current source-bound reviews, frozen valuations, returns and blockers."""
    return s.performance.returns.detail(identity)


@router.post("/{identity}/close")
def close(identity: str, body: PeriodRevision, s: S):
    """Capture one frozen closing observation; this cannot alter account funds."""
    return s.performance.returns.close(identity, body)


@router.post("/{identity}/flows/{event_id}")
def review(identity: str, event_id: str, body: FlowReview, s: S):
    """Save an audited classification, historical USDT principal value and timestamp."""
    return s.performance.returns.review(identity, event_id, body)


@router.post("/{identity}/coverage")
def coverage(identity: str, body: CoverageReview, s: S):
    """Confirm or withdraw an explicit coverage assertion for exactly the reviewed evidence."""
    return s.performance.returns.attest(identity, body)


@router.post("/{identity}/manual", status_code=201)
def manual(identity: str, body: ManualFlow, s: S):
    """Add a separately labeled user assertion for a missing external principal flow."""
    return s.performance.returns.manual(identity, body)


@router.post("/{identity}/manual/{event_id}/remove")
def remove_manual(identity: str, event_id: str, body: PeriodRevision, s: S):
    """Remove a manual assertion while retaining its original audit record."""
    return s.performance.returns.remove_manual(identity, event_id, body)


@router.post("/{identity}/remove")
def remove(identity: str, body: PeriodRevision, s: S):
    """Explicitly remove a measured report and its local review history, never native ledgers."""
    return s.performance.returns.remove(identity, body)
