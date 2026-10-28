"""Local funding balance reviews; no native API calls or movement of funds."""

from fastapi import APIRouter, Response

from sibyl.accounting.funding.reviews import ReviewFunding, ReviewVersion
from sibyl.api.routes import S

router = APIRouter(prefix="/api/v1/account-ledger/funding", tags=["Accountant"])


@router.get("/{event_id}/review")
def read(event_id: str, s: S, response: Response):
    """Read a retained observation, derived effect and its local review audit."""
    response.headers["Cache-Control"] = "no-store"
    return s.funding_sync.ledger.reviews.state(event_id)


@router.post("/{event_id}/review")
def save(event_id: str, body: ReviewFunding, s: S, response: Response):
    """Save a source-version-checked local wallet/fee convention assertion."""
    response.headers["Cache-Control"] = "no-store"
    return s.funding_sync.ledger.reviews.save(event_id, body)


@router.post("/{event_id}/review/withdraw")
def withdraw(event_id: str, body: ReviewVersion, s: S, response: Response):
    """Withdraw a local assertion while retaining its audit history and original facts."""
    response.headers["Cache-Control"] = "no-store"
    return s.funding_sync.ledger.reviews.save(event_id, body, withdraw=True)
