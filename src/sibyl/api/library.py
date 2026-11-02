"""Explicit local imports and read-only source retrieval for the Research workspace."""

import base64
import binascii
from datetime import date
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.concurrency import run_in_threadpool

from sibyl.api.routes import S
from sibyl.api.uploads import bounded_body


def private(response: Response):
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/v1/library", tags=["Research library"], dependencies=[Depends(private)])


class DocumentImport(BaseModel):
    """Import only owner-selected files; source URLs are attribution and are never fetched."""

    model_config = ConfigDict(extra="forbid")
    filename: str = Field(min_length=1, max_length=240)
    data_base64: str = Field(min_length=1, max_length=12 * 1024 * 1024)
    title: str = Field(default="", max_length=200)
    publisher: str = Field(default="", max_length=160)
    source_url: str = Field(default="", max_length=2000)
    published_at: date | None = None

    @field_validator("source_url")
    @classmethod
    def valid_url(cls, value):
        if value and (
            urlsplit(value).scheme not in {"http", "https"}
            or not urlsplit(value).hostname
            or urlsplit(value).username is not None
            or urlsplit(value).password is not None
        ):
            raise ValueError("Use an HTTP(S) source URL without credentials.")
        return value


@router.get("")
def catalog(
    s: S, kind: str = "all", limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0, le=100000)
):
    """List source metadata and counts without returning original files."""
    return s.library.catalog(kind, limit, offset)


@router.get("/search")
def search(
    s: S,
    query: str = Query(min_length=1, max_length=300),
    kind: str = "all",
    limit: int = Query(8, ge=1, le=20),
):
    """Find exact attributable passages with bounded keyword retrieval."""
    return s.library.search(query, kind, limit)


@router.get("/passages/{identifier}")
def passage(identifier: str, s: S):
    """Read a retained citation or report that it is unavailable."""
    return s.library.passage(identifier)


@router.get("/documents/{identifier}")
def document(identifier: str, s: S, offset: int = Query(0, ge=0, le=10000)):
    """Read source metadata and a coherent page of retained passages."""
    return s.library.document(identifier, offset)


@router.post(
    "/documents",
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": DocumentImport.model_json_schema()}},
        }
    },
)
async def import_document(request: Request, s: S):
    """Bound uploads before validation; extraction runs off the event loop."""
    raw = await bounded_body(request, 12 * 1024 * 1024)
    try:
        body = DocumentImport.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(
            422,
            "Invalid document metadata. Choose PDF/text/Markdown, valid source information and a file up to 8 MiB.",
        ) from None
    try:
        content = base64.b64decode(body.data_base64, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(422, "Invalid encoded document.") from None
    return await run_in_threadpool(
        s.library.import_document,
        body.filename,
        content,
        title=body.title,
        publisher=body.publisher,
        url=body.source_url,
        published_at=body.published_at.isoformat() if body.published_at else "",
    )


@router.post("/synchronize-news")
def sync_news(s: S):
    """Synchronize search entries from the existing retained news archive."""
    return s.library.synchronize_news()


@router.post("/documents/{identifier}/reindex")
def reindex(identifier: str, s: S):
    """Re-extract an uploaded original and atomically replace its passages."""
    return s.library.reindex(identifier)


@router.delete("/documents/{identifier}", status_code=204)
def delete(identifier: str, s: S):
    """Remove an uploaded source, original and active search representation."""
    s.library.delete(identifier)
