"""Named, independently credentialed deployments backed by the encrypted model vault."""

from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from sibyl.agents.utils.model_selection import ModelConflict, readiness
from sibyl.agents.utils.providers import PROVIDERS

if TYPE_CHECKING:
    from sibyl.services.workspace.llm_settings import DeploymentRequest, ModelSettings


class ModelDeployments:
    """Manage deployment identities while retaining existing provider profiles as legacy cards."""

    def __init__(self, owner: "ModelSettings"):
        self.owner = owner
        self.store = owner.store

    @staticmethod
    def name(provider: str, used: set[str]) -> str:
        definition = PROVIDERS[provider]
        base = f"{definition.name} {'API ' if definition.kind == 'api' else ''}model"
        name, count = base, 1
        while name.casefold() in used:
            name = f"{base} ({count})"
            count += 1
        return name

    def config(self, reference: str, profiles: dict) -> dict:
        """Resolve a known identity without borrowing credentials from a different deployment."""
        if reference in PROVIDERS:
            return self.owner._provider(reference, profiles)
        profile = profiles.get(reference)
        if not profile:
            raise LookupError("Model deployment not found.")
        return {
            "provider": profile["provider"],
            "model": profile["model"],
            "base_url": profile["base_url"],
            "api_key": profile.get("api_key", ""),
            "_deployment": reference,
            **({"context_window": profile["context_window"]} if "context_window" in profile else {}),
        }

    def lookup(self, reference: str, profiles: dict) -> dict:
        """Require a saved deployment or the provider-backed environment deployment."""
        if reference == "none" or (
            reference not in profiles and reference != self.owner.settings.llm_provider
        ):
            raise LookupError("Model deployment not found.")
        return self.config(reference, profiles)

    def read(self, reference: str) -> dict:
        """Read the deployed model and connection as one private snapshot."""
        with self.owner._lock:
            active, model, profiles, _ = self.store.model_snapshot()
            config = self.lookup(reference, profiles)
            if reference == (active or self.owner.settings.llm_provider):
                if reference in PROVIDERS:
                    config["model"] = model if model is not None else config["model"]
            return config

    @staticmethod
    def require_usable(config: dict):
        """Prevent selection of deployments that lack a model or required key."""
        if not config["model"]:
            raise ValueError("Choose a model for this deployment first.")
        if PROVIDERS[config["provider"]].requires_key and not config["api_key"]:
            raise ValueError("Add an API key to this deployment first.")

    def public(self, active, current, profiles, assignments, safe_profiles):
        """Present one card per deployment, with routing state and masked credentials."""
        default = (active or current["provider"]) if current["provider"] != "none" else None
        references = list(profiles)
        if default and default not in profiles:
            references.append(default)
        references.extend(
            choice.get("deployment") or choice["provider"]
            for choice in assignments["agents"].values()
            if choice["provider"] != "none"
        )
        results = []
        for reference in dict.fromkeys(references):
            if reference == "none":
                continue
            config = self.config(reference, profiles)
            if reference == default:
                config["model"] = current["model"]
            saved = profiles.get(reference, {})
            provider = config["provider"]
            legacy = reference in PROVIDERS
            source = (
                safe_profiles[provider]["key_source"]
                if legacy
                else ("saved" if config["api_key"] else "none")
            )
            key = config["api_key"] if source == "saved" else ""
            results.append(
                {
                    "id": reference,
                    "provider": provider,
                    "name": saved.get("name") or self.name(provider, set()),
                    "model": config["model"],
                    "legacy_models": safe_profiles[provider]["models"] if legacy else [],
                    "base_url": config["base_url"],
                    "context_window": config.get("context_window"),
                    "key_source": source,
                    "key_preview": self.preview(key),
                    "default": reference == default,
                    "agents": [
                        agent
                        for agent, choice in assignments["agents"].items()
                        if (choice.get("deployment") or choice["provider"]) == reference
                    ],
                    "reason": readiness(config),
                    "removable": reference in profiles,
                }
            )
        return results

    @staticmethod
    def preview(key: str) -> str:
        """Mask short keys entirely and show only the ends of longer ones."""
        return f"{key[:3]}••••••{key[-4:]}" if len(key) >= 15 else "••••••" if key else ""

    def save(self, body: "DeploymentRequest", reference: str | None = None) -> dict:
        """Create a separate credential or edit the named connection by identity."""
        with self.owner._lock, self.store.vault.lock:
            _, _, profiles, _ = self.store.model_snapshot()
            existing = profiles.get(reference, {}) if reference else {}
            if reference and self.lookup(reference, profiles)["provider"] != body.provider:
                raise ValueError("Choose the original provider when editing a deployment.")
            keys = self.owner.public()["deployments"]
            used = {
                row["name"].casefold()
                for row in keys
                if row["id"] != reference and row["provider"] == body.provider
            }
            name = body.name or existing.get("name") or self.name(body.provider, used)
            if name.casefold() in used:
                raise ModelConflict("A deployment already uses this name.")
            definition = PROVIDERS[body.provider]
            key = body.api_key.get_secret_value() if body.api_key else existing.get("api_key", "")
            if definition.requires_key and not (
                key or (reference in PROVIDERS and self.owner._environment_key(body.provider))
            ):
                raise ValueError("Add an API key for this deployment.")
            identity = reference or uuid4().hex
            result = {
                **existing,
                "provider": body.provider,
                "name": name,
                "model": self.model_id(body.provider, body.model)
                if not reference
                else self.read(reference)["model"],
                "base_url": body.base_url or definition.base_url,
                "api_key": key,
            }
            if body.provider == "ollama":
                result["context_window"] = (
                    body.context_window
                    or existing.get("context_window")
                    or self.owner._provider("ollama", {})["context_window"]
                )
            self.store.save_model_profile(identity, result, activate=False)
            return self.owner.public()

    @staticmethod
    def model_id(provider: str, model: str) -> str:
        if model and provider == "llama.cpp-local":
            path = Path(model).expanduser()
            if path.suffix.lower() != ".gguf" or not path.is_file():
                raise ValueError("Choose an existing GGUF file on the Python server.")
            return str(path.resolve())
        return model

    def set_model(self, reference: str, model: str) -> dict:
        """Set the deployment's model for future requests that reference it."""
        with self.owner._lock, self.store.vault.lock:
            active, _, profiles, _ = self.store.model_snapshot()
            config = self.lookup(reference, profiles)
            model = self.model_id(config["provider"], model)
            if not model:
                raise ValueError("Choose a model or enter a custom model ID.")
            profile = {**profiles.get(reference, {}), "model": model}
            if reference not in profiles:
                profile["base_url"] = config["base_url"]
            self.store.save_model_profile(
                reference,
                profile,
                activate=reference == (active or self.owner.settings.llm_provider),
            )
            return self.owner.public()

    def select(self, reference: str) -> dict:
        """Activate an existing deployment as the workspace default."""
        with self.owner._lock, self.store.vault.lock:
            config = self.read(reference)
            self.require_usable(config)
            self.store.select_default_model(reference, config["model"])
            return self.owner.public()

    def delete(self, reference: str) -> dict:
        """Delete only the named saved connection and reset its own assignments."""
        with self.owner._lock, self.store.vault.lock:
            active, _, profiles, _ = self.store.model_snapshot()
            if reference not in profiles or reference == "none":
                raise LookupError("Saved model deployment not found.")
            self.store.delete_model_profile(
                reference,
                is_default=reference == (active or self.owner.settings.llm_provider),
            )
            return self.owner.public()
