"""Explicit local-server detection and process controls for model settings."""

from fastapi import APIRouter

from sibyl.api.routes import S
from sibyl.local_models.ollama import OllamaRequest

router = APIRouter(prefix="/api/v1/settings/ollama", tags=["Settings"])


@router.post("/check")
def check(body: OllamaRequest, s: S):
    """Probe an endpoint and report actual installed/loaded model IDs without inference."""
    return s.ollama.check(body)


@router.post("/start")
def start(body: OllamaRequest, s: S):
    """Start an installed local Ollama server; no shell or arbitrary executable input."""
    return s.ollama.start(body)


@router.post("/stop")
def stop(body: OllamaRequest, s: S):
    """Stop only the local server process started by this Sibyl instance."""
    return s.ollama.stop(body)
