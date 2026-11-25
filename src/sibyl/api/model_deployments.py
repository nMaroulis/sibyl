"""Settings routes for named API and local model deployments."""

from typing import Literal

from fastapi import APIRouter, Depends, Response

from sibyl.api.routes import S
from sibyl.local_models.catalog import read_catalog
from sibyl.local_models.ollama import OllamaRequest
from sibyl.services.workspace.llm_settings import DeploymentModel, DeploymentRequest
from sibyl.services.workspace.model_checks import check_configuration


def private(response: Response):
    """Keep connection settings and status out of shared caches."""
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/api/v1/settings/llm/deployments", tags=["Settings"], dependencies=[Depends(private)]
)


@router.post("", status_code=201)
def add(body: DeploymentRequest, s: S):
    """Save a separate named connection, optionally with a model ID."""
    return s.agents.models.deployments.save(body)


@router.put("/{reference}")
def edit(reference: str, body: DeploymentRequest, s: S):
    """Update only this deployment's connection settings."""
    return s.agents.models.deployments.save(body, reference)


@router.put("/{reference}/model")
def set_model(reference: str, body: DeploymentModel, s: S):
    """Choose the model used by this deployment."""
    return s.agents.models.deployments.set_model(reference, body.model)


@router.post("/{reference}/default")
def set_default(reference: str, s: S):
    """Route agents following the workspace default through this deployment."""
    return s.agents.models.deployments.select(reference)


@router.delete("/{reference}")
def delete(reference: str, s: S):
    """Remove the saved deployment and reset only its routing references."""
    return s.agents.models.deployments.delete(reference)


@router.post("/{reference}/check")
async def check(reference: str, s: S):
    """Test the chosen model with this deployment's saved configuration."""
    return await check_configuration(s.agents.models.deployments.read(reference))


@router.get("/{reference}/runtime")
def runtime(reference: str, s: S):
    """Read the installed and loaded models visible to this saved connection."""
    config = s.agents.models.deployments.read(reference)
    provider = config["provider"]
    if provider == "ollama":
        return s.ollama.check(
            OllamaRequest(base_url=config["base_url"], model=config["model"]), api_key=config["api_key"]
        )
    if provider in {"lmstudio", "vllm", "llama.cpp-server"}:
        return read_catalog(config)
    raise ValueError("This deployment does not run a local model server.")


@router.post("/{reference}/runtime/{action}")
def manage_runtime(reference: str, action: Literal["start", "stop"], s: S):
    """Start or stop an Ollama process only at this deployment's saved endpoint."""
    config = s.agents.models.deployments.read(reference)
    if config["provider"] != "ollama":
        raise ValueError("Ollama is the only runtime Sibyl can start and stop.")
    command = s.ollama.start if action == "start" else s.ollama.stop
    return command(
        OllamaRequest(base_url=config["base_url"], model=config["model"]),
        api_key=config["api_key"],
    )
