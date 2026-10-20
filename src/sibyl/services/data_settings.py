"""Encrypted news and market-source profiles with write-only provider keys."""

import threading
from typing import Literal

from pydantic import Field, SecretStr, field_validator

from sibyl.config import Settings
from sibyl.market_data.catalog import API_PROVIDERS, source_catalog
from sibyl.models import Request
from sibyl.news.feeds import SOURCES
from sibyl.storage import Store

NewsSourceId = Literal["coindesk", "cointelegraph", "decrypt", "theblock", "cryptoslate", "newsapi"]


class NewsSettingsRequest(Request):
    """Replace source selections; an omitted API key preserves the encrypted saved key."""

    mode: Literal["auto", "demo", "live"] = "auto"
    sources: list[NewsSourceId] = Field(default_factory=lambda: [s.id for s in SOURCES], max_length=6)
    cryptoslate_method: Literal["rss", "web"] = "rss"
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=1024)
    clear_api_key: bool = False
    query: str = Field(default="bitcoin OR ethereum OR cryptocurrency", min_length=1, max_length=200)

    @field_validator("query")
    @classmethod
    def valid_query(cls, value: str) -> str:
        """Reject blank queries and control characters before calling a provider."""
        value = value.strip()
        if not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Enter a search query without control characters.")
        return value

    @field_validator("api_key")
    @classmethod
    def valid_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return value
        key = value.get_secret_value().strip()
        if not key or any(not 33 <= ord(c) <= 126 for c in key):
            raise ValueError("Enter an ASCII API key without whitespace or control characters.")
        return SecretStr(key)


class MarketSettingsRequest(Request):
    """Select one reference feed and optionally save that API provider's credential."""

    source: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9:-]+$")
    api_key: SecretStr | None = Field(default=None, min_length=1, max_length=1024)

    @field_validator("api_key")
    @classmethod
    def valid_key(cls, value: SecretStr | None) -> SecretStr | None:
        """Keep provider credentials out of URLs, response metadata and header injection."""
        return NewsSettingsRequest.valid_key(value)


class DataSettings:
    """Own encrypted profiles; changing feeds never changes account or execution mode."""

    def __init__(self, settings: Settings, store: Store):
        self.settings, self.store = settings, store
        self._lock = threading.RLock()

    def apply_startup(self):
        """Retained startup hook; reference choices now resolve independently per read."""
        return None

    def news(self) -> dict:
        """Read private collector configuration; callers must not return it in API responses."""
        with self._lock:
            config = {
                "mode": self.settings.news_mode,
                "sources": [s.id for s in SOURCES],
                "cryptoslate_method": "rss",
                "query": "bitcoin OR ethereum OR cryptocurrency",
                "api_key": "",
                **self.store.data_profile("news"),
            }
            if config["mode"] == "demo":
                config["sources"] = []
            return config

    def public_news(self) -> dict:
        """Return provider choices and key presence, with no credential values."""
        config = self.news()
        return {k: v for k, v in config.items() if k != "api_key"} | {
            "has_api_key": bool(config["api_key"]),
            "resolved_mode": self.settings.mode if config["mode"] == "auto" else config["mode"],
            "catalog": [
                {
                    "id": "demo",
                    "name": "Demo briefings",
                    "kind": "demo",
                    "website": None,
                    "description": "Offline sample reporting and a sample Fear & Greed index.",
                }
            ]
            + [
                {
                    "id": s.id,
                    "name": s.name,
                    "kind": "rss",
                    "website": s.website,
                    "description": "Public publisher headlines and excerpts. No API key required.",
                    "methods": ["rss", "web"] if s.id == "cryptoslate" else ["rss"],
                }
                for s in SOURCES
            ]
            + [
                {
                    "id": "newsapi",
                    "name": "NewsAPI",
                    "kind": "api",
                    "website": "https://newsapi.org",
                    "description": "Crypto keyword search across publishers. Requires your NewsAPI key and a suitable plan.",
                }
            ],
        }

    def save_news(self, request: NewsSettingsRequest) -> dict:
        """Atomically save validated choices; blank key inputs never erase a saved key."""
        with self._lock:
            previous = self.news()
            if request.clear_api_key and request.api_key is not None:
                raise ValueError("Save a new API key or remove the existing key, not both.")
            key = request.api_key.get_secret_value() if request.api_key is not None else previous["api_key"]
            if request.clear_api_key:
                key = ""
            sources = [] if request.mode == "demo" else list(dict.fromkeys(request.sources))
            if request.mode != "demo" and not sources:
                raise ValueError("Choose at least one public news source, or select Demo.")
            if "newsapi" in sources and not key:
                raise ValueError("Save a NewsAPI key before enabling that source.")
            payload = request.model_dump(exclude={"api_key", "clear_api_key"}) | {
                "sources": sources,
                "api_key": key,
            }
            self.store.save_data_profile("news", payload)
            return self.public_news()

    def market(self) -> dict:
        """Resolve private feed configuration; only adapters may read key values."""
        with self._lock:
            saved = self.store.data_profile("market")
            fallback = self.settings.market_exchange
            # Honor an earlier saved public reference without changing account mode.
            source = saved.get("source") or (
                saved.get("exchange", fallback) if saved.get("mode") == "live" else fallback
            )
            return {"source": source, "profiles": saved.get("profiles", {})}

    def public_market(self) -> dict:
        """Discover usable feeds and the workspace default, never returning API keys."""
        with self._lock:
            config = self.market()
            catalog = source_catalog(self.store.connections(), config["profiles"])
            active = next((row for row in catalog if row["id"] == config["source"]), None)
            return {
                "active": active
                or {
                    "id": config["source"],
                    "name": "Unavailable connected account",
                    "available": False,
                    "kind": "connection",
                    "provider": "",
                    "environment": "production",
                    "candles": False,
                    "order_book": False,
                    "requires_key": False,
                    "has_api_key": False,
                },
                "catalog": catalog,
                "restart_required": False,
                "account_mode": self.settings.mode,
            }

    def resolve_market(self, source: str | None = None) -> dict:
        """Freeze one validated selection and its secret for an in-flight reference read."""
        with self._lock:
            config = self.market()
            identity = source or config["source"]
            selected = next(
                (
                    row
                    for row in source_catalog(self.store.connections(), config["profiles"])
                    if row["id"] == identity
                ),
                None,
            )
            if selected is None:
                raise ValueError(
                    "This market source is unavailable. Choose a source in Settings → Market data."
                )
            if not selected["available"]:
                if selected["kind"] == "connection":
                    raise ValueError(
                        "This account is inactive. Activate it in Exchanges or choose a public market feed."
                    )
                raise ValueError("Save an API key for this market source in Settings → Market data.")
            return {**selected, "api_key": config["profiles"].get(identity, {}).get("api_key", "")}

    def save_market(self, request: MarketSettingsRequest) -> dict:
        """Save a default atomically; existing reads keep their own source snapshot."""
        with self._lock:
            config = self.market()
            if request.api_key is not None:
                if request.source not in API_PROVIDERS:
                    raise ValueError(
                        "Public exchange feeds use no API key. Manage account keys under Exchanges."
                    )
                config["profiles"][request.source] = {"api_key": request.api_key.get_secret_value()}
            catalog = source_catalog(self.store.connections(), config["profiles"])
            selected = next((row for row in catalog if row["id"] == request.source), None)
            if selected is None or not selected["available"]:
                raise ValueError("Choose an available source and supply its API key when required.")
            self.store.save_data_profile("market", {**config, "source": request.source})
            return self.public_market()

    def remove_market_key(self, provider: str) -> dict:
        """Remove a saved credential; an active key-required feed must be changed first."""
        if provider not in API_PROVIDERS:
            raise LookupError("Market API provider not found.")
        with self._lock:
            config = self.market()
            if config["source"] == provider and API_PROVIDERS[provider]["requires_key"]:
                raise ValueError("Choose another default source before removing this active provider's key.")
            config["profiles"].pop(provider, None)
            self.store.save_data_profile("market", config)
            return self.public_market()
