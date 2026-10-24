"""Encrypted provider profiles and request-scoped ProtoLink model configuration."""

import os
import threading
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from sibyl.agents.model_selection import AGENT_NAMES, AgentModelRequest, ModelConflict, readiness
from sibyl.agents.providers import PROVIDERS, ProviderId
from sibyl.config import Settings
from sibyl.storage import Store


class ModelSettingsRequest(BaseModel):
    """Save and activate a provider; omitting a key preserves its saved credential."""

    model_config = ConfigDict(extra="forbid")
    provider: ProviderId
    activate: bool = Field(default=True, strict=True)
    model: str = Field(default="", max_length=500)
    base_url: str = Field(default="", max_length=2048)
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=8192)

    @field_validator("model", "base_url")
    @classmethod
    def clean_text(cls, value: str) -> str:
        """Reject control characters before configuration can reach an adapter."""
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Configuration must not contain control characters.")
        return value.strip()

    @field_validator("api_key")
    @classmethod
    def clean_key(cls, value: SecretStr | None) -> SecretStr | None:
        """Keep credentials out of metadata, URLs, and HTTP header injection."""
        if value is None:
            return value
        key = value.get_secret_value().strip()
        if not key or any(ord(char) < 32 or ord(char) == 127 for char in key):
            raise ValueError("Enter a non-empty API key without control characters.")
        return SecretStr(key)

    @model_validator(mode="after")
    def validate_provider_fields(self):
        """Accept endpoint overrides only for adapters that expose an endpoint field."""
        provider = PROVIDERS[self.provider]
        if self.base_url:
            try:
                url = urlsplit(self.base_url)
            except ValueError as exc:
                raise ValueError("Use a valid HTTP(S) server URL.") from exc
            if (
                not provider.base_url
                or url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or url.query
                or url.fragment
            ):
                raise ValueError("Use an HTTP(S) server URL without credentials, query, or fragment.")
            try:
                _ = url.port
            except ValueError as exc:
                raise ValueError("Use a valid server port.") from exc
        if self.api_key is not None and self.provider in {"none", "mock", "llama.cpp-local"}:
            raise ValueError("This provider does not accept an API key.")
        if self.provider not in {"none", "mock"} and not self.model:
            raise ValueError("Choose a model or enter a custom model ID.")
        return self


class ModelSettings:
    """Persist provider profiles, a workspace default and explicit per-agent overrides.

    Environment configuration remains the fallback until a profile is selected.
    Every agent request receives a single resolved snapshot; a concurrent settings
    update cannot combine one provider's model with another provider's key.
    """

    def __init__(self, settings: Settings, store: Store):
        self.settings, self.store = settings, store
        self._lock = threading.RLock()

    def _environment_key(self, provider: str) -> str:
        return next((os.environ[name] for name in PROVIDERS[provider].key_env if os.getenv(name)), "")

    def _fallback(self, provider: str) -> dict:
        """Use environment fields only for the provider selected by the server."""
        definition = PROVIDERS[provider]
        model, base_url = "", definition.base_url
        if provider == self.settings.llm_provider:
            model = self.settings.llm_model
            if base_url and (provider == "ollama" or "llm_base_url" in self.settings.model_fields_set):
                base_url = self.settings.llm_base_url
        return {"model": model, "base_url": base_url}

    def _provider(self, provider: str, profiles: dict) -> dict:
        """Pair one provider's endpoint/model with only that provider's credential."""
        profile = profiles.get(provider, self._fallback(provider))
        return {
            "provider": provider,
            "model": profile.get("model", ""),
            "base_url": profile.get("base_url") or PROVIDERS[provider].base_url,
            "api_key": profile.get("api_key") or self._environment_key(provider),
        }

    def provider_config(self, provider: str) -> dict:
        """Read one saved provider for explicit local-server status checks."""
        with self._lock:
            _, _, profiles, _ = self.store.model_snapshot()
            return self._provider(provider, profiles)

    def _resolved(self, active, default_model, profiles, assignments) -> tuple[dict, dict]:
        """Resolve every agent from one read, never mixing credentials across providers."""
        default_provider = active if active is not None else self.settings.llm_provider
        configs = {}
        for provider in {default_provider, *(item["provider"] for item in assignments["agents"].values())}:
            configs[provider] = self._provider(provider, profiles)
        default = configs[default_provider].copy()
        default["model"] = (
            default_model
            if default_model is not None
            else self.settings.llm_model
            if active is None
            else default["model"]
        )
        agents = {}
        for agent in AGENT_NAMES:
            override = assignments["agents"].get(agent)
            agents[agent] = (
                {**configs[override["provider"]], "model": override["model"]} if override else default.copy()
            )
        return default, agents

    def resolve(self, agent: str | None = None) -> dict:
        """Decrypt one effective configuration; omitting agent returns the workspace default."""
        with self._lock:
            default, agents = self._resolved(*self.store.model_snapshot())
            return agents[agent] if agent else default

    def for_turn(self, agent: str) -> dict:
        """Freeze all agent/provider choices before queueing a native inference request.

        The private map travels only in ContextVar state, never task metadata,
        prompts or serialized history. Delegated agents share this exact snapshot.
        """
        with self._lock:
            active, default_model, profiles, assignments = self.store.model_snapshot()
            _, agents = self._resolved(active, default_model, profiles, assignments)
            return {
                **agents[agent],
                "_agents": agents,
                "_selections": {
                    key: "override" if key in assignments["agents"] else "default" for key in agents
                },
            }

    def assign(self, agent: str, body: AgentModelRequest) -> dict:
        """Save one model override, preserving the default and provider credentials."""
        if agent not in AGENT_NAMES:
            raise ValueError("Choose a registered Sibyl agent.")
        with self._lock:
            active, default_model, profiles, assignments = self.store.model_snapshot()
            selection = None
            if body.provider is not None:
                selection = {"provider": body.provider, "model": body.model}
                provider = PROVIDERS[body.provider]
                if (
                    body.provider not in {"none", "mock"}
                    and body.provider not in profiles
                    and body.provider != self.settings.llm_provider
                ):
                    raise ValueError(
                        "Save this provider profile first; its endpoint and key are shared with this agent."
                    )
                candidate = {
                    **profiles.get(body.provider, self._fallback(body.provider)),
                    "provider": body.provider,
                    "model": body.model,
                }
                candidate["api_key"] = candidate.get("api_key") or self._environment_key(body.provider)
                if provider.requires_key and not candidate["api_key"]:
                    raise ValueError("Add this provider's API key before assigning it to an agent.")
                if body.provider == "llama.cpp-local":
                    path = Path(body.model).expanduser()
                    if path.suffix.lower() != ".gguf" or not path.is_file():
                        raise ValueError("Choose an existing GGUF file on the Python server.")
                    selection["model"] = str(path.resolve())
            if not self.store.save_agent_model(agent, selection, body.revision):
                raise ModelConflict("Agent models changed. Refresh before saving this assignment.")
            return self.public()

    def public(self) -> dict:
        """Return provider profiles, key presence, and runtime metadata, never key values."""
        with self._lock:
            active, default_model, profiles, assignments = self.store.model_snapshot()
            current, agents = self._resolved(active, default_model, profiles, assignments)
            safe_profiles = {}
            for provider, definition in PROVIDERS.items():
                saved = profiles.get(provider)
                config = saved if saved is not None else self._fallback(provider)
                key_source = (
                    "saved"
                    if saved and saved.get("api_key")
                    else ("environment" if self._environment_key(provider) else "none")
                )
                safe_profiles[provider] = {
                    "model": config.get("model", ""),
                    "base_url": config.get("base_url") or definition.base_url,
                    "has_api_key": key_source != "none",
                    "key_source": key_source,
                    "saved": saved is not None,
                }
            return {
                "active_provider": current["provider"],
                "active_model": current["model"],
                "source": "workspace" if active is not None else "environment",
                "profiles": safe_profiles,
                "providers": [p.public() for p in PROVIDERS.values()],
                "agent_revision": assignments["revision"],
                "agents": [
                    {
                        "id": key,
                        "name": name,
                        "selection": assignments["agents"].get(key),
                        "provider": agents[key]["provider"],
                        "model": agents[key]["model"],
                        "inherited": key not in assignments["agents"],
                        "ready": not readiness(agents[key]),
                        "reason": readiness(agents[key]),
                        "simulated": agents[key]["provider"] == "mock",
                    }
                    for key, name in AGENT_NAMES.items()
                ],
            }

    def save(self, body: ModelSettingsRequest) -> dict:
        """Encrypt a provider profile; optionally select it as the workspace default."""
        with self._lock:
            _, profiles = self.store.model_profiles()
            existing = profiles.get(body.provider, {})
            definition = PROVIDERS[body.provider]
            key = body.api_key.get_secret_value() if body.api_key is not None else existing.get("api_key", "")
            if definition.requires_key and not (key or self._environment_key(body.provider)):
                raise ValueError("Add an API key for this provider before saving.")
            if body.provider == "llama.cpp-local":
                path = Path(body.model).expanduser()
                if path.suffix.lower() != ".gguf" or not path.is_file():
                    raise ValueError("Choose an existing GGUF file on the Python server.")
                model = str(path.resolve())
            else:
                model = body.model
            self.store.save_model_profile(
                body.provider,
                {
                    "model": model,
                    "base_url": body.base_url or definition.base_url,
                    "api_key": key,
                },
                activate=body.activate,
            )
            return self.public()

    def remove_key(self, provider: ProviderId) -> dict:
        """Remove a saved credential; return to tool mode if the active API loses access."""
        with self._lock:
            active, profiles = self.store.model_profiles()
            profile = profiles.get(provider)
            if profile:
                profile["api_key"] = ""
                fallback = (
                    (active if active is not None else self.settings.llm_provider) == provider
                    and PROVIDERS[provider].requires_key
                    and not self._environment_key(provider)
                )
                self.store.save_model_profile(provider, profile, activate=False, fallback_to_tools=fallback)
            return self.public()

    @staticmethod
    def constructor(config: dict) -> tuple[str, dict]:
        """Map one internal snapshot to the exact arguments accepted by ProtoLink."""
        provider = config["provider"]
        kwargs = {"model": config["model"]} if config["model"] else {}
        if PROVIDERS[provider].base_url:
            kwargs["base_url"] = config["base_url"]
        key = config["api_key"]
        if key:
            if provider in {"ollama", "llama.cpp-server"}:
                kwargs["headers"] = {"Authorization": f"Bearer {key}"}
            else:
                kwargs["api_key"] = key
        if provider == "mock":
            kwargs["default_response"] = "Mock runtime: this is a simulated model response, not analysis."
        return provider, kwargs
