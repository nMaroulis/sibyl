"""Explicit local job admission, schedules and retained outcome inspection."""

from fastapi import APIRouter, Depends, Response

from sibyl.api.routes import S
from sibyl.operations.jobs.contracts import CreateJob, JobAction, StartJob


def private(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/v1/workspace/jobs", tags=["Local jobs"], dependencies=[Depends(private)])


@router.get("")
def state(s: S):
    """List schedules and implemented handlers without starting work."""
    return s.jobs.state()


@router.post("", status_code=201)
def create(body: CreateJob, s: S):
    """Validate domain arguments and save a paused or explicitly armed schedule."""
    return s.jobs.create(body)


@router.post("/{identity}/action")
def action(identity: str, body: JobAction, s: S):
    """Pause, resume or archive future scheduling using the displayed revision."""
    return s.jobs.action(identity, body)


@router.get("/{identity}/runs")
def runs(identity: str, s: S):
    """Inspect real saved outcomes without rerunning a job."""
    return s.jobs.runs(identity)


@router.post("/{identity}/runs", status_code=202)
def run(identity: str, body: StartJob, s: S):
    """Queue one idempotent explicit run, even while the schedule is paused."""
    return s.jobs.start(identity, body.request_id)


@router.post("/{identity}/runs/{run_id}/cancel")
def cancel(identity: str, run_id: str, s: S):
    """Stop interest in this exact run; already committed domain work is retained."""
    return s.jobs.cancel(identity, run_id)


@router.get("/{identity}/runs/{run_id}")
def receipt(identity: str, run_id: str, s: S):
    """Export one retained job receipt without starting work."""
    return s.jobs.run(identity, run_id)
