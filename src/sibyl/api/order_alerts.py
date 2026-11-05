"""Execution-observation subscriptions; no provider or trading operations."""

from fastapi import APIRouter, Depends, Query, Response

from sibyl.alerts.contracts import AlertAction
from sibyl.alerts.orders.service import OrderAlertCreate, OrderAlertUpdate
from sibyl.api.routes import S


def private(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/v1/order-alerts", tags=["Alerts"], dependencies=[Depends(private)])


@router.get("")
def rules(s: S, include_archived: bool = False, offset: int = Query(0, ge=0, le=1000000)):
    """Read retained per-account execution rules and their actual progress."""
    return s.trading.alerts.rules(include_archived, offset)


@router.post("", status_code=201)
def create(body: OrderAlertCreate, s: S):
    """Subscribe to future observations, starting after the current journal tail."""
    return s.trading.alerts.create(body)


@router.post("/{identity}/edit")
def edit(identity: str, body: OrderAlertUpdate, s: S):
    """Save reviewed changes paused; previous notifications remain immutable."""
    return s.trading.alerts.edit(identity, body)


@router.post("/{identity}/action")
def action(identity: str, body: AlertAction, s: S):
    """Pause/resume/archive only this subscription, never its exchange or orders."""
    return s.trading.alerts.change(identity, body)
