"""Explicit future-only private alert policies and private delivery history."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from sibyl.alerts.contracts import AlertConflict
from sibyl.alerts.delivery.contracts import AlertKind, DeliverySettings
from sibyl.api.routes import S


def private(response: Response):
    """Prevent private research/recipient receipts from entering shared caches."""
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/v1/alert-delivery", tags=["Alert delivery"], dependencies=[Depends(private)])


@router.get("/policies")
def policies(s: S):
    """Read active opt-in indicators without triggering alerts or provider requests."""
    return s.alert_delivery.policies()


@router.get("/targets")
def targets(s: S):
    """Read checked private destinations and current pause/window status, without probes."""
    return s.messaging.notifications.routes.targets()


@router.get("/history")
def history(
    s: S,
    rule_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=1000000)] = 0,
):
    """Read retained alert deliveries, including skipped, failed and uncertain parts."""
    return s.messaging.notifications.history(kind="alert", rule_id=rule_id, limit=limit, offset=offset)


@router.get("/{kind}/{identity}")
def detail(kind: AlertKind, identity: str, s: S):
    """Read a rule's current delivery selection and actual message-part outcomes."""
    return s.alert_delivery.detail(kind, identity)


@router.post("/{kind}/{identity}")
def save(kind: AlertKind, identity: str, body: DeliverySettings, s: S):
    """Select or pause delivery for future notices, without sending existing inbox entries."""
    try:
        return s.alert_delivery.save(kind, identity, body)
    except AlertConflict as exc:
        raise HTTPException(409, str(exc)) from exc
