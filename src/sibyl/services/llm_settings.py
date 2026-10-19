"""Encrypted provider profiles and request-scoped ProtoLink model configuration."""

import os
import threading
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from sibyl.agents.providers import PROVIDERS, ProviderId
from sibyl.config import Settings
from sibyl.storage import Store


class ModelSettingsRequest(BaseModel):
    """Save and activate a provider; omitting a key preserves its saved credential."""

    model_config = ConfigDict(extra="forbid")
    provider: ProviderId
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
    """Persist provider-specific secrets and activate changes without an API restart.

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

    def resolve(self) -> dict:
        """Read one active configuration, decrypting its key only for internal use."""
        with self._lock:
            active, profiles = self.store.model_profiles()
            provider = active if active is not None else self.settings.llm_provider
            profile = profiles.get(provider, self._fallback(provider))
            return {
                "provider": provider,
                "model": profile.get("model", ""),
                "base_url": profile.get("base_url") or PROVIDERS[provider].base_url,
                "api_key": profile.get("api_key") or self._environment_key(provider),
            }

    def public(self) -> dict:
        """Return provider profiles, key presence, and runtime metadata, never key values."""
        with self._lock:
            active, profiles = self.store.model_profiles()
            current = self.resolve()
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
            }

    def save(self, body: ModelSettingsRequest) -> dict:
        """Encrypt a profile and make it effective for subsequent agent requests."""
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
                    active == provider
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
