"""Explicit managed archives, recovery review and read-only process diagnostics."""

from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from starlette.concurrency import run_in_threadpool

from sibyl.api.routes import S
from sibyl.api.uploads import bounded_body
from sibyl.operations.archives import MAX_ARCHIVE


def private(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/v1/workspace", tags=["Workspace operations"], dependencies=[Depends(private)])


class Unlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    passphrase: SecretStr = Field(min_length=12, max_length=1024)


class Restore(Unlock):
    confirmation: Literal["RESTORE AS NEW WORKSPACE"]


class RecoveryReview(BaseModel):
    confirmation: Literal["I REVIEWED THE RESTORED WORKSPACE"]


@router.get("/health")
def health(s: S):
    """Read current worker progress, recent faults and recovery status."""
    result = s.workers.snapshot()
    result["recovery_required"] = s.workers.recovery_required
    result["recovery_reviewed"] = bool(s.store.data_profile("workspace-recovery").get("reviewed"))
    return result


@router.post("/recovery/complete")
def complete_recovery(body: RecoveryReview, s: S):
    """Record explicit review; only a subsequent restart can start paused workers."""
    profile = s.store.data_profile("workspace-recovery")
    s.store.save_data_profile("workspace-recovery", {**profile, "required": False, "reviewed": True})
    return {
        "restart_required": s.workers.recovery_required,
        "note": "Restart Sibyl to start automatic workers. Accounts remain inactive; explicitly review and enable them. Retained exchange orders may still exist at their venues.",
    }


@router.get("/backups")
def backups(s: S):
    """List local encrypted archives without decrypting their contents."""
    return s.archives.list()


@router.post("/backups", status_code=201)
def create(body: Unlock, s: S):
    """Create an explicitly requested passphrase-encrypted workspace snapshot."""
    return s.archives.create(body.passphrase.get_secret_value())


@router.post(
    "/backups/upload",
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
        }
    },
)
async def upload(request: Request, s: S):
    """Retain a bounded encrypted archive for later authenticated inspection."""
    with s.archives.admit_upload():
        content = await bounded_body(request, MAX_ARCHIVE)
        return await run_in_threadpool(s.archives.upload, content)


@router.post("/backups/{identifier}/inspect")
def inspect(identifier: str, body: Unlock, s: S):
    """Authenticate an archive and return version, date and size metadata."""
    return s.archives.inspect(identifier, body.passphrase.get_secret_value())


@router.post("/backups/{identifier}/restore", status_code=201)
def restore(identifier: str, body: Restore, s: S):
    """Create a separate validated workspace with automatic work quarantined."""
    return s.archives.restore(identifier, body.passphrase.get_secret_value())


@router.get("/backups/{identifier}/download")
def download(identifier: str, s: S):
    """Download an encrypted archive through the normal authenticated API."""
    return FileResponse(
        s.archives.path(identifier),
        media_type="application/octet-stream",
        filename=f"sibyl-{identifier}.sibylbackup",
        headers={"Cache-Control": "no-store"},
    )


@router.delete("/backups/{identifier}", status_code=204)
def delete(identifier: str, s: S):
    """Remove one local archive, preserving downloaded copies and restored workspaces."""
    s.archives.delete(identifier)
