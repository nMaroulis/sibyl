"""Encrypted provider profiles and request-scoped ProtoLink model configuration."""

import os
import threading
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from sibyl.agents.utils.model_selection import AGENT_NAMES, AgentModelRequest, ModelConflict, readiness
from sibyl.agents.utils.providers import PROVIDERS, ProviderId
from sibyl.config import Settings
from sibyl.services.workspace.model_deployments import ModelDeployments
from sibyl.storage import Store

OLLAMA_CONTEXT_WINDOW = 32768


class ModelChoice(BaseModel):
    """Identify one model without accepting credentials or endpoint overrides."""

    model_config = ConfigDict(extra="forbid")
    provider: ProviderId
    model: str = Field(default="", max_length=500)

    @field_validator("model")
    @classmethod
    def clean_model(cls, value: str) -> str:
        """Reject control characters before a model ID reaches an adapter."""
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Model IDs must not contain control characters.")
        return value.strip()


class ModelSettingsRequest(ModelChoice):
    """Save and activate a provider; omitting a key preserves its saved credential."""

    activate: bool = Field(default=True, strict=True)
    base_url: str = Field(default="", max_length=2048)
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=8192)
    context_window: int | None = Field(default=None, ge=4096, le=131072, strict=True)

    @field_validator("base_url")
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
        """Validate provider-specific endpoint and context fields before saving."""
        provider = PROVIDERS[self.provider]
        if "context_window" in self.model_fields_set and self.provider != "ollama":
            raise ValueError("Context window configuration is currently available for Ollama only.")
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
        return self

    @model_validator(mode="after")
    def require_model(self):
        if self.provider not in {"none", "mock"} and not self.model:
            raise ValueError("Choose a model or enter a custom model ID.")
        return self


class DeploymentRequest(ModelSettingsRequest):
    """Create or edit one named deployment. A new connection may defer model selection."""

    name: str = Field(default="", max_length=80)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return cls.clean_text(value)

    @model_validator(mode="after")
    def require_model(self):
        if self.provider == "none":
            raise ValueError("Choose an AI model provider.")
        return self


class DeploymentModel(BaseModel):
    """Set a configured deployment's model ID."""

    model_config = ConfigDict(extra="forbid")
    model: str = Field(max_length=500)

    @field_validator("model")
    @classmethod
    def clean_model(cls, value: str) -> str:
        return ModelChoice.clean_model(value)


class ModelSettings:
    """Persist provider profiles, a workspace default and explicit per-agent overrides.

    Environment configuration remains the fallback until a profile is selected.
    Every agent request receives a single resolved snapshot; a concurrent settings
    update cannot combine one provider's model with another provider's key.
    """

    def __init__(self, settings: Settings, store: Store):
        self.settings, self.store = settings, store
        self._lock = threading.RLock()
        self.deployments = ModelDeployments(self)

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
            **(
                {"context_window": profile.get("context_window", OLLAMA_CONTEXT_WINDOW)}
                if provider == "ollama"
                else {}
            ),
        }

    def provider_config(self, provider: str) -> dict:
        """Read one saved provider for explicit local-server status checks."""
        with self._lock:
            _, _, profiles, _ = self.store.model_snapshot()
            return self._provider(provider, profiles)

    def _resolved(self, active, default_model, profiles, assignments) -> tuple[dict, dict]:
        """Resolve every agent from one read, never mixing credentials across providers."""
        reference = active if active is not None else self.settings.llm_provider
        default = self.deployments.config(reference, profiles)
        if reference in PROVIDERS:
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
            if not override:
                agents[agent] = default.copy()
            elif override.get("deployment"):
                agents[agent] = self.deployments.config(override["deployment"], profiles)
            else:
                agents[agent] = {**self._provider(override["provider"], profiles), "model": override["model"]}
        return default, agents

    def resolve(self, agent: str | None = None) -> dict:
        """Decrypt one effective configuration; omitting agent returns the workspace default."""
        with self._lock:
            default, agents = self._resolved(*self.store.model_snapshot())
            return agents[agent] if agent else default

    def for_turn(self, agent: str) -> dict:
        """Freeze all agent/provider choices before queueing a native inference request.

        The caller freezes this map in ProtoLink's private request_context, never
        task metadata, prompts or history. Owned local specialists inherit it;
        private dependencies never cross transport boundaries.
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
            if body.deployment:
                config = self.deployments.lookup(body.deployment, profiles)
                self.deployments.require_usable(config)
                selection = {"provider": config["provider"], "deployment": body.deployment}
            elif body.provider is not None:
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

    def _model_ids(self, provider: str, profile: dict | None, current: dict, agents: dict) -> list[str]:
        """Include saved, inherited legacy and explicitly assigned models once each."""
        profile = profile or {}
        candidates = [*profile.get("models", ())]
        if "model" in profile:
            candidates.append(profile["model"])
        if provider == self.settings.llm_provider:
            candidates.append(self.settings.llm_model)
        if current["provider"] == provider and not current.get("_deployment"):
            candidates.append(current["model"])
        candidates.extend(
            config["model"]
            for config in agents.values()
            if config["provider"] == provider and not config.get("_deployment")
        )
        return list(dict.fromkeys(model for model in candidates if model or provider == "mock"))

    def saved_config(self, choice: ModelChoice) -> dict:
        """Resolve an added model against the latest saved connection."""
        with self._lock:
            active, model, profiles, assignments = self.store.model_snapshot()
            default, agents = self._resolved(active, model, profiles, assignments)
            if choice.provider == "none" or choice.model not in self._model_ids(
                choice.provider, profiles.get(choice.provider), default, agents
            ):
                raise ValueError("Add this model before using it.")
            return {**self._provider(choice.provider, profiles), "model": choice.model}

    def select_default(self, choice: ModelChoice) -> dict:
        """Change only workspace routing. Both credentials and assignments are preserved."""
        with self._lock, self.store.vault.lock:
            if choice.provider != "none":
                config = self.saved_config(choice)
                if PROVIDERS[choice.provider].requires_key and not config["api_key"]:
                    raise ValueError("Add an API key for this provider before setting a default.")
            self.store.select_default_model(
                choice.provider, choice.model if choice.provider != "none" else ""
            )
            return self.public()

    def public(self) -> dict:
        """Return saved model IDs, a partial vault-key preview, and runtime metadata."""
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
                key = saved.get("api_key", "") if key_source == "saved" else ""
                safe_profiles[provider] = {
                    "models": self._model_ids(provider, saved, current, agents) if provider != "none" else [],
                    "key_preview": self.deployments.preview(key),
                    "model": config.get("model", ""),
                    "base_url": config.get("base_url") or definition.base_url,
                    "has_api_key": key_source != "none",
                    "key_source": key_source,
                    "saved": saved is not None,
                    **(
                        {"context_window": config.get("context_window", OLLAMA_CONTEXT_WINDOW)}
                        if provider == "ollama"
                        else {}
                    ),
                }
            return {
                "active_provider": current["provider"],
                "active_model": current["model"],
                "active_deployment": (active or current["provider"])
                if current["provider"] != "none"
                else None,
                "deployments": self.deployments.public(active, current, profiles, assignments, safe_profiles),
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

    def save(self, body: ModelSettingsRequest, *, add_only: bool = False) -> dict:
        """Save encrypted model settings, or append a model under an existing connection."""
        with self._lock, self.store.vault.lock:
            active, default_model, profiles, assignments = self.store.model_snapshot()
            default, agents = self._resolved(active, default_model, profiles, assignments)
            existing = profiles.get(body.provider, {})
            definition = PROVIDERS[body.provider]
            known = self._model_ids(body.provider, existing, default, agents)
            reuse_connection = add_only and (bool(existing) or default["provider"] == body.provider)
            base_url = (
                self._provider(body.provider, profiles)["base_url"] if reuse_connection else body.base_url
            )
            key = existing.get("api_key", "")
            if body.api_key is not None and not reuse_connection:
                key = body.api_key.get_secret_value()
            if definition.requires_key and not (key or self._environment_key(body.provider)):
                raise ValueError("Add an API key for this provider before saving.")
            if body.provider == "llama.cpp-local":
                path = Path(body.model).expanduser()
                if path.suffix.lower() != ".gguf" or not path.is_file():
                    raise ValueError("Choose an existing GGUF file on the Python server.")
                model = str(path.resolve())
            else:
                model = body.model
            if add_only and body.provider == "none":
                raise ValueError("Choose a model provider.")
            if add_only and model in known:
                raise ModelConflict("This model is already added.")
            self.store.save_model_profile(
                body.provider,
                {
                    "model": existing.get("model", model) if reuse_connection else model,
                    "models": list(dict.fromkeys([*known, model])) if body.provider != "none" else [],
                    "base_url": base_url or definition.base_url,
                    "api_key": key,
                    **(
                        {
                            "context_window": (
                                existing.get("context_window", OLLAMA_CONTEXT_WINDOW)
                                if reuse_connection
                                else body.context_window
                                or existing.get("context_window", OLLAMA_CONTEXT_WINDOW)
                            )
                        }
                        if body.provider == "ollama"
                        else {}
                    ),
                },
                activate=body.activate and not add_only,
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
        if provider == "ollama":
            # Let ProtoLink discover native tools; unknown models keep its JSON fallback.
            kwargs["tool_calling"] = "auto"
            kwargs["model_params"] = {
                "num_ctx": config.get("context_window", OLLAMA_CONTEXT_WINDOW),
                "num_predict": 2048,
            }
        if provider == "mock":
            kwargs["default_response"] = "Mock runtime: this is a simulated model response, not analysis."
        return provider, kwargs
