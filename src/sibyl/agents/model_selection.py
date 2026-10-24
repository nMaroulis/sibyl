"""Validated model assignments and passive readiness for native ProtoLink agents."""

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from sibyl.agents.providers import PROVIDERS, ProviderId
from sibyl.models import Request

AgentId = Literal[
    "sibyl",
    "oracle",
    "accountant",
    "analyst",
    "broker",
    "chronos",
    "reporter",
    "technician",
    "wiki",
    "explorer",
    "stocks",
]
AGENT_NAMES = {
    "sibyl": "Sibyl",
    "oracle": "Oracle",
    "accountant": "Accountant",
    "analyst": "Analyst",
    "broker": "Broker",
    "chronos": "Chronos",
    "reporter": "Reporter",
    "technician": "Technician",
    "wiki": "Wiki",
    "explorer": "Explorer",
    "stocks": "Equity Analyst",
}


class ModelConflict(ValueError):
    """A different editor changed agent model assignments before this write."""


class AgentModelRequest(Request):
    """Reuse a provider's saved endpoint/key, with a fixed per-agent model ID.

    A null provider removes the override. Credentials and endpoints cannot be
    supplied here: configure them once in the encrypted provider profile.
    """

    revision: int = Field(ge=0, strict=True)
    provider: ProviderId | None = None
    model: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_selection(self):
        if any(ord(char) < 32 or ord(char) == 127 for char in self.model):
            raise ValueError("Model IDs must not contain control characters.")
        self.model = self.model.strip()
        if self.provider is None or self.provider == "none":
            if self.model:
                raise ValueError("Inherited and tool-only selections do not take a model ID.")
        elif self.provider != "mock" and not self.model:
            raise ValueError("Choose a model or enter a custom model ID.")
        return self


def readiness(config: dict) -> str:
    """Explain local configuration gaps without probing or claiming provider connectivity."""
    provider = PROVIDERS[config["provider"]]
    if provider.id == "none":
        return "Choose an AI model for conversational reasoning. Read-only tools remain available."
    if provider.requires_key and not config["api_key"]:
        return f"Add an API key for {provider.name} in AI model settings."
    if provider.id != "mock" and not config["model"]:
        return "Choose a model in AI model settings."
    if not provider.public()["installed"]:
        return f"Install the {provider.name} provider dependency shown in AI model settings."
    if provider.id == "llama.cpp-local" and not Path(config["model"]).is_file():
        return "The selected GGUF file is missing on the Python server. Update AI model settings."
    return ""
