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
from sibyl.research_library.evaluations.contracts import EvaluationRun, EvaluationSuite
from sibyl.research_library.semantic.contracts import (
    IndexBatch,
    LocalEndpoint,
    SemanticRevision,
    SemanticSettings,
)


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
    method: str = "keyword",
):
    """Find exact attributable passages with keyword, semantic or hybrid retrieval."""
    return s.library.search(query, kind, limit, method)


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


@router.get("/semantic")
def semantic_status(s: S):
    """Read saved local configuration and actual index coverage without contacting Ollama."""
    return s.library.semantic.status()


@router.post("/semantic/models")
def semantic_models(body: LocalEndpoint, s: S):
    """List local Ollama model names; no document text is sent and no models are downloaded."""
    with s.library.semantic.operation():
        return s.library.semantic.provider.models(body.endpoint)


@router.post("/semantic/settings")
def semantic_settings(body: SemanticSettings, s: S):
    """Check local embedding capability and save a fresh vector space with an empty index."""
    return s.library.semantic.configure(body)


@router.post("/semantic/index")
def semantic_index(body: IndexBatch, s: S):
    """Explicitly embed one bounded passage batch; publish only unchanged current sources."""
    return s.library.semantic.build(body)


@router.post("/semantic/clear")
def semantic_clear(body: SemanticRevision, s: S):
    """Remove semantic vectors and invalidate in-flight work, keeping source files and keywords."""
    return s.library.semantic.clear(body.revision)


@router.delete("/semantic")
def semantic_disable(s: S, revision: int = Query(ge=0)):
    """Disable semantic retrieval and discard its vectors; source files stay retained."""
    return s.library.semantic.clear(revision, disable=True)


@router.get("/evaluations")
def evaluations(s: S):
    """List owner-labeled suites and saved evaluation progress without starting inference."""
    return s.library.evaluations.catalog()


@router.post("/evaluations/suites", status_code=201)
def evaluation_suite(body: EvaluationSuite, s: S):
    """Pin explicit relevant passages; labels are local user judgments, not model scores."""
    return s.library.evaluations.save(body)


@router.post("/evaluations/suites/{identity}/runs", status_code=202)
def evaluation_start(identity: str, body: EvaluationRun, s: S):
    """Queue a bounded comparison against the current fixed corpus and index."""
    return s.library.evaluations.start(identity, body)


@router.get("/evaluations/runs/{identity}")
def evaluation_report(identity: str, s: S):
    """Read saved query rankings, citations, relevance metrics and timings."""
    return s.library.evaluations.get(identity)


@router.post("/evaluations/runs/{identity}/stop")
def evaluation_stop(identity: str, s: S):
    """Stop future queries and discard any late result from the current query."""
    return s.library.evaluations.stop(identity)


@router.delete("/evaluations/suites/{identity}", status_code=204)
def evaluation_delete(identity: str, s: S):
    """Explicitly remove an inactive suite and its saved reports, keeping sources."""
    s.library.evaluations.delete(identity)
