"""Explicit scheduling controls and private report/delivery history."""

from fastapi import APIRouter, Depends, HTTPException, Response

from sibyl.api.routes import S
from sibyl.investigations.scheduling.contracts import (
    BriefingAction,
    CreateBriefing,
    EditBriefing,
    RunBriefing,
)
from sibyl.investigations.scheduling.repository import BriefingConflict


def private_briefings(response: Response):
    """Keep personal calendars and report/delivery outcomes out of shared caches."""
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/v1", tags=["Briefing schedules"], dependencies=[Depends(private_briefings)])


@router.get("/investigations/{identity}/schedules")
def schedules(identity: str, s: S, archived: bool = False):
    """Read the saved calendars for an investigation, without model or Telegram calls."""
    s.investigations.repository.get(identity)
    return s.briefings.repository.list(identity, archived)


@router.post("/investigations/{identity}/schedules", status_code=201)
def create(identity: str, body: CreateBriefing, s: S):
    """Authorize future read-only briefings and optional delivery to a reviewed recipient."""
    try:
        return s.briefings.create(identity, body)
    except BriefingConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/briefing-schedules/status")
def status(s: S):
    """Read this local worker's last completed check and its explicit scheduling bounds."""
    return {
        "last_tick": s.briefings.last_tick,
        "backend_required": True,
        "catch_up": False,
        "waiting_window_seconds": 900,
        "delivery_expiry_seconds": 3600,
        "history_limit": 200,
    }


@router.get("/briefing-schedules/{identity}")
def detail(identity: str, s: S):
    """Read the calendar, retained occurrences and confirmed delivery/part outcomes."""
    return s.briefings.detail(identity)


@router.post("/briefing-schedules/{identity}")
def edit(identity: str, body: EditBriefing, s: S):
    """Review a calendar revision and reset its next occurrence into the future."""
    try:
        return s.briefings.edit(identity, body)
    except BriefingConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/briefing-schedules/{identity}/actions")
def action(identity: str, body: BriefingAction, s: S):
    """Pause/resume/archive future work and withdraw unsent old briefing deliveries."""
    try:
        return s.briefings.change(identity, body)
    except BriefingConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/briefing-schedules/{identity}/run-now", status_code=202)
async def run_now(identity: str, body: RunBriefing, s: S):
    """Request one additional briefing without moving its regular calendar time."""
    try:
        return await s.briefings.run_now(identity, body)
    except BriefingConflict as exc:
        raise HTTPException(409, str(exc)) from exc
