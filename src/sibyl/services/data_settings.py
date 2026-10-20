"""Saved news-source choices and restart-bound public market configuration."""

import threading
from typing import Literal

from pydantic import Field, SecretStr, field_validator

from sibyl.config import Settings
from sibyl.exchanges.catalog import ExchangeId
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
    """Select an existing exchange adapter for public prices; never enable execution."""

    mode: Literal["demo", "live"]
    exchange: ExchangeId


class DataSettings:
    """Own encrypted profiles; news applies immediately and market changes apply on restart."""

    def __init__(self, settings: Settings, store: Store):
        self.settings, self.store = settings, store
        self._lock = threading.RLock()

    def apply_startup(self):
        """Load a coherent market selection before constructing clients or starting workers."""
        saved = self.store.data_profile("market")
        if saved:
            selection = MarketSettingsRequest.model_validate(saved)
            self.settings.mode, self.settings.market_exchange = selection.mode, selection.exchange

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

    def public_market(self) -> dict:
        """Distinguish saved restart preferences from the current running market source."""
        active = {"mode": self.settings.mode, "exchange": self.settings.market_exchange}
        saved = self.store.data_profile("market") or active
        return {"active": active, "saved": saved, "restart_required": saved != active}

    def save_market(self, request: MarketSettingsRequest) -> dict:
        """Save for restart so an in-flight quote cannot receive the wrong source label."""
        with self._lock:
            self.store.save_data_profile("market", request.model_dump())
            return self.public_market()
