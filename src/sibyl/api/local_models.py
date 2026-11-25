"""Explicit local-server detection and process controls for model settings."""

from fastapi import APIRouter, Response

from sibyl.api.routes import S
from sibyl.local_models.catalog import CatalogProvider, check_catalog
from sibyl.local_models.ollama import OllamaRequest

router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])


@router.post("/ollama/check")
def check(body: OllamaRequest, s: S):
    """Probe an endpoint and report actual installed/loaded model IDs without inference."""
    return s.ollama.check(body)


@router.post("/ollama/start")
def start(body: OllamaRequest, s: S):
    """Start an installed local Ollama server; no shell or arbitrary executable input."""
    return s.ollama.start(body)


@router.post("/ollama/stop")
def stop(body: OllamaRequest, s: S):
    """Stop only the local server process started by this Sibyl instance."""
    return s.ollama.stop(body)


@router.get("/llm/local/{provider}/check")
def check_local(provider: CatalogProvider, s: S, response: Response):
    """Read the configured local server's reported model catalog."""
    response.headers["Cache-Control"] = "no-store"
    return check_catalog(s.agents.models, provider)
