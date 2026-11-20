"""Provider-neutral app-origin receipt review; never resends a message."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from sibyl.api.routes import S
from sibyl.messaging.review import DeliveryDecision


def private(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/api/v1/message-deliveries", tags=["Message receipts"], dependencies=[Depends(private)]
)


@router.get("")
def history(
    s: S,
    kind: Literal["alert", "briefing", "reply"] = "alert",
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0, le=100000),
):
    """Page safe private outcomes; conversation reply review currently covers Telegram only."""
    if kind == "reply":
        return s.messaging.replies.history(limit, offset)
    return s.messaging.notifications.history(kind=kind, limit=limit, offset=offset)


@router.get("/targets")
def targets(s: S):
    """Read checked private destinations without provider probes or secret values."""
    return s.messaging.notifications.routes.targets()


@router.get("/{identity}")
def detail(identity: str, s: S):
    """Read exact saved text and native confirmations; credentials are never returned."""
    return s.messaging.notifications.review.get(identity)


@router.post("/{identity}/review")
def review(identity: str, body: DeliveryDecision, s: S):
    """Withdraw unsent remainder or acknowledge uncertainty without changing provider outcomes."""
    return s.messaging.notifications.review.decide(identity, body)
