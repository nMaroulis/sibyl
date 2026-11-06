"""Authenticated local inbox exports and explicit opt-in history management."""

from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from sibyl.alerts.history.contracts import ClearHistory, Kind, RetentionPolicy
from sibyl.alerts.history.service import csv_document
from sibyl.api.routes import S


def private(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/api/v1/notifications", tags=["Notification history"], dependencies=[Depends(private)]
)


@router.get("/retention")
def status(s: S):
    """Read the current retention policy, eligible counts and completed cleanup receipts."""
    return s.alerts._inbox.history.status()


@router.post("/retention")
def save(body: RetentionPolicy, s: S):
    """Save an opt-in policy without an inline deletion."""
    return s.alerts._inbox.history.save(body)


@router.post("/retention/clear")
def clear(body: ClearHistory, s: S):
    """Explicitly remove one bounded batch after reviewing its latest cutoff and protections."""
    return s.alerts._inbox.history.clear(body.revision)


@router.get("/export")
def export(
    s: S,
    format: Literal["json", "csv"] = "json",
    kind: Kind = "all",
    start: str | None = Query(None, max_length=40),
    end: str | None = Query(None, max_length=40),
):
    """Export up to 2,000 dated notices; filter ranges to split a larger history."""
    document = s.alerts._inbox.history.export(kind, start, end)
    if format == "json":
        return document
    return Response(
        csv_document(document),
        media_type="text/csv",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="sibyl-notifications.csv"',
            "X-Export-Total": str(document["total"]),
            "X-Export-Truncated": str(document["truncated"]).lower(),
        },
    )
