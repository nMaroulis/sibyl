"""Explicit local/hosted semantic indexing controls; chat-provider profiles stay separate."""

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator

from sibyl.models import Request


class SemanticNotReady(ValueError):
    """A user-correctable missing or changed embedding configuration."""


class LocalEndpoint(Request):
    """Allow only plain loopback Ollama origins, with no credentials, proxy or URL path."""

    endpoint: str = Field(default="http://127.0.0.1:11434", max_length=200)

    @field_validator("endpoint")
    @classmethod
    def loopback(cls, value):
        try:
            parsed = urlsplit(value)
            port = 11434 if parsed.port is None else parsed.port
            if (
                parsed.scheme != "http"
                or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
                or not 1 <= port <= 65535
            ):
                raise ValueError
        except ValueError:
            raise ValueError("Use a plain local HTTP origin such as http://127.0.0.1:11434.") from None
        host = "[::1]" if parsed.hostname == "::1" else "127.0.0.1"
        return f"http://{host}:{port}"


class SemanticSettings(LocalEndpoint):
    """Check an installed embedding model before selecting a new vector space."""

    revision: int = Field(ge=0, strict=True)
    model: str = Field(min_length=1, max_length=180, pattern=r"^[A-Za-z0-9][A-Za-z0-9_./:-]*$")


class SemanticRevision(Request):
    """Guard destructive index changes against another editor or in-flight indexing batch."""

    revision: int = Field(ge=0, strict=True)


class IndexBatch(SemanticRevision):
    """Embed at most thirty-two current passages, publishing one complete checked batch."""

    kind: Literal["all", "document", "news"] = "document"
    limit: int = Field(default=32, ge=1, le=32, strict=True)


class HostedSemanticSettings(Request):
    """Deliberately check hosted embeddings and authorize text processing independently of chat models."""

    revision: int = Field(ge=0, strict=True)
    provider: Literal["openai", "mistral"]
    model: str = Field(min_length=1, max_length=180)
    api_key: SecretStr | None = Field(default=None, max_length=4096)
    remote_consent: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def review(self):
        from sibyl.research_library.semantic.hosted import provider_spec

        provider_spec(self.provider, self.model)
        if not self.remote_consent:
            raise ValueError(
                "Explicit permission to send library passages and search queries to the provider is required."
            )
        if self.api_key is not None:
            key = self.api_key.get_secret_value()
            if not key.strip() or key != key.strip() or any(ord(c) < 33 or ord(c) == 127 for c in key):
                raise ValueError("Use a nonempty provider API key without whitespace or control characters.")
        return self
