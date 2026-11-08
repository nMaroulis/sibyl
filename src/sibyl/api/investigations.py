"""Private research reports; accepted runs continue independently of browser polling."""

from fastapi import APIRouter, Depends, HTTPException, Response

from sibyl.agents.utils.network import ModelRequired
from sibyl.api.routes import S
from sibyl.investigations.contracts import InvestigationCreate, InvestigationRun, WorkflowContinuation
from sibyl.investigations.repository import InvestigationConflict
from sibyl.investigations.scheduling.repository import BriefingConflict


def private_reports(response: Response):
    """Prevent account research and model answers from entering shared HTTP caches."""
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/api/v1/investigations", tags=["Investigations"], dependencies=[Depends(private_reports)]
)


@router.get("")
def listing(s: S):
    """List saved questions and latest run summaries without inference."""
    return s.investigations.repository.list()


@router.post("", status_code=201)
def create(body: InvestigationCreate, s: S):
    """Save a reusable question; no LLM connection is required for this action."""
    try:
        return s.investigations.repository.create(body)
    except InvestigationConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/{identity}")
def definition(identity: str, s: S):
    """Read a saved investigation and its version metadata."""
    return s.investigations.repository.get(identity)


@router.delete("/{identity}", status_code=204)
def delete(identity: str, s: S):
    """Remove this investigation's reports; independent conversations are retained."""
    try:
        s.briefings.require_deletable(identity)
        s.investigations.repository.delete(identity)
    except (InvestigationConflict, BriefingConflict) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{identity}/runs", status_code=202)
async def start(identity: str, body: InvestigationRun, s: S):
    """Accept one explicitly requested, bounded native Sibyl investigation."""
    try:
        return await s.investigations.start(identity, body)
    except (ModelRequired, InvestigationConflict) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/{identity}/runs/{run_id}")
def report(identity: str, run_id: str, s: S):
    """Read the exact saved version, supporting tool receipts and native progress."""
    return s.investigations.detail(identity, run_id)


@router.get("/{identity}/runs/{run_id}/export")
def export(identity: str, run_id: str, s: S):
    """Export the question, selected version and bounded source snapshots as JSON."""
    return {
        "format": "sibyl-investigation-v1",
        "investigation": s.investigations.repository.get(identity),
        "run": s.investigations.detail(identity, run_id),
    }


@router.post("/{identity}/runs/{run_id}/cancel", status_code=202)
async def cancel(identity: str, run_id: str, s: S):
    """Stop the selected attempt without deleting already completed tool observations."""
    try:
        return await s.investigations.cancel(identity, run_id)
    except InvestigationConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{identity}/runs/{run_id}/resume", status_code=202)
async def resume(identity: str, run_id: str, body: WorkflowContinuation, s: S):
    """Continue only the owned native checkpoint and its exact pending fingerprint."""
    try:
        return await s.investigations.workflows.resume(identity, run_id, body)
    except (ModelRequired, InvestigationConflict) as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/{identity}/runs/{run_id}/verify-note/{action_id}")
def verify_note(identity: str, run_id: str, action_id: str, s: S):
    """Observe matching local content and reconcile its native receipt; never save a note."""
    try:
        return s.investigations.workflows.verify_note(identity, run_id, action_id)
    except InvestigationConflict as exc:
        raise HTTPException(409, str(exc)) from exc
