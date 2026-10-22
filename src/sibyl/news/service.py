"""Coordinate publisher ingestion, a retained archive, and filtered sentiment evidence."""

from __future__ import annotations

import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Literal
from xml.etree.ElementTree import ParseError

import httpx

from sibyl.config import Settings
from sibyl.news.demo import demo_items
from sibyl.news.feeds import SOURCES, NewsProvider, RSSProvider
from sibyl.news.providers import CryptoSlateWebProvider, NewsAPIProvider
from sibyl.news.repository import NewsRepository
from sibyl.news.sentiment import ASSETS, analyze_article, extract_summary, sentiment_report

NewsMode = Literal["demo", "live"]

if TYPE_CHECKING:
    from sibyl.services.data_settings import DataSettings


class NewsService:
    """Collect public excerpts without exchange credentials, article crawling, or paid APIs.

    Live reads refresh due feeds, retain successful data through publisher outages, and
    never substitute samples. Background collection uses the same lock and cooldown.
    Demo stories are generated separately and cannot contaminate the live archive.
    """

    def __init__(
        self,
        settings: Settings,
        providers: list[NewsProvider] | None = None,
        data_settings: DataSettings | None = None,
    ):
        self.settings = settings
        self.data_settings = data_settings
        self.repository = NewsRepository(settings.data_dir)
        self.providers = providers if providers is not None else [RSSProvider(source) for source in SOURCES]
        self._refresh_lock = threading.Lock()

    @property
    def default_mode(self) -> NewsMode:
        """Resolve the news-specific setting without changing market or account mode."""
        mode = self.data_settings.news()["mode"] if self.data_settings else self.settings.news_mode
        return self.settings.mode if mode == "auto" else mode

    def configured_providers(self) -> list[NewsProvider]:
        """Snapshot enabled collectors and their server-only credentials for one operation."""
        if self.data_settings is None:
            return self.providers
        config = self.data_settings.news()
        providers = [
            CryptoSlateWebProvider()
            if p.source.id == "cryptoslate" and config["cryptoslate_method"] == "web"
            else p
            for p in self.providers
            if p.source.id in config["sources"]
        ]
        if "newsapi" in config["sources"] and config["api_key"]:
            providers.append(NewsAPIProvider(config["api_key"], config["query"]))
        return providers

    @staticmethod
    def _now() -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _elapsed(value: str | None, now: datetime) -> float:
        return (now - datetime.fromisoformat(value)).total_seconds() if value else float("inf")

    def refresh(self, force: bool = False) -> dict:
        """Collect due feeds concurrently; manual refreshes still obey a 60-second cooldown."""
        if not self._refresh_lock.acquire(blocking=False):
            return {"in_progress": True, "attempted": 0}
        try:
            now = self._now()
            states = self.repository.states()
            interval = 60 if force else self.settings.news_refresh_seconds
            due = [
                p
                for p in self.configured_providers()
                if self._elapsed(states.get(p.source.id, {}).get("last_attempt"), now) >= interval
                or states.get(p.source.id, {}).get(
                    "attempt_version", states.get(p.source.id, {}).get("version")
                )
                != p.cache_version
            ]

            def collect(provider):
                previous = states.get(provider.source.id, {})
                state = {
                    **previous,
                    "last_attempt": now.isoformat(),
                    "attempt_version": provider.cache_version,
                    "error": None,
                }
                items = []
                try:
                    # Parser upgrades must re-read excerpts even when the publisher's ETag is unchanged.
                    cached = previous if previous.get("version") == provider.cache_version else {}
                    result = provider.fetch(cached, now)
                    items = [analyze_article(item) for item in result.items or []]
                    state.update(
                        last_success=now.isoformat(),
                        etag=result.etag,
                        modified=result.modified,
                        version=provider.cache_version,
                    )
                except (httpx.HTTPError, ValueError, ParseError, UnicodeError) as exc:
                    state["error"] = (
                        f"Publisher request failed (HTTP {exc.response.status_code})."
                        if isinstance(exc, httpx.HTTPStatusError)
                        else "Publisher could not be reached."
                        if isinstance(exc, httpx.HTTPError)
                        else "Publisher returned an unsupported or invalid feed."
                    )
                self.repository.save(provider.source.id, state, items, now, self.settings.news_retention_days)

            if due:
                with ThreadPoolExecutor(
                    max_workers=min(5, len(due)), thread_name_prefix="sibyl-news"
                ) as pool:
                    list(pool.map(collect, due))
            return {"in_progress": False, "attempted": len(due)}
        finally:
            self._refresh_lock.release()

    def sources(self) -> list[dict]:
        """Report last success, request failures, and archived article counts per publisher."""
        states, now = self.repository.states(), self._now()
        counts = Counter(
            source for i in self._archive() for source in i.get("collector_ids", [i["source_id"]])
        )
        result = []
        for provider in self.configured_providers():
            source, state = provider.source, states.get(provider.source.id, {})
            stale = self._elapsed(state.get("last_success"), now) > self.settings.news_refresh_seconds * 2
            status = (
                "unavailable"
                if not state.get("last_success")
                else "stale"
                if state.get("error") or stale
                else "fresh"
            )
            result.append(
                {
                    "id": source.id,
                    "name": source.name,
                    "url": source.url,
                    "website": source.website,
                    "status": status if state else "not_fetched",
                    "last_attempt": state.get("last_attempt"),
                    "last_success": state.get("last_success"),
                    "error": state.get("error"),
                    "articles": counts[source.id],
                    "method": "web"
                    if isinstance(provider, CryptoSlateWebProvider)
                    else "api"
                    if isinstance(provider, NewsAPIProvider)
                    else "rss",
                }
            )
        return result

    def _archive(self) -> list[dict]:
        cutoff = (self._now() - timedelta(days=self.settings.news_retention_days)).isoformat()
        enabled = {p.source.id for p in self.configured_providers()}
        items = []
        for item in self.repository.items():
            collectors = set(item.get("collector_ids", [item["source_id"]])) & enabled
            if collectors and (item.get("published_at") or item["first_seen_at"]) >= cutoff:
                source = item["source_id"] if item["source_id"] in collectors else sorted(collectors)[0]
                items.append({**item, "source_id": source, "collector_ids": sorted(collectors)})
        return items

    def article(self, article_id: str, mode: NewsMode | None = None) -> dict:
        """Find a retained story outside the current page; missing IDs never select a different story."""
        resolved = mode or self.default_mode
        if resolved not in {"demo", "live"}:
            raise ValueError("Choose demo or live news.")
        items = demo_items(self._now()) if resolved == "demo" else self._archive()
        for item in items:
            if item["id"] == article_id:
                return item
        raise LookupError("Article is no longer in the news archive.")

    def query(
        self,
        summary: str = "excerpt",
        *,
        mode: NewsMode | None = None,
        publisher: str = "",
        asset: str = "",
        sentiment: str = "",
        q: str = "",
        days: int = 7,
        limit: int = 24,
        offset: int = 0,
        refresh: bool = True,
    ) -> dict:
        """Filter on the backend and aggregate the whole matching set before pagination.

        ``refresh=False`` reads only the retained archive, for read-only agent tools.
        A time window excludes undated articles; ``days=0`` includes all retained
        articles. Keyword search matches every whitespace-separated term literally.
        """
        resolved = mode or self.default_mode
        if resolved not in {"demo", "live"} or summary not in {"excerpt", "extractive"}:
            raise ValueError("Choose a supported news mode and summary method.")
        if sentiment not in {"", "positive", "neutral", "negative"}:
            raise ValueError("Choose a supported text polarity.")
        if not 0 <= days <= 365 or not 1 <= limit <= 100 or not 0 <= offset <= 5000 or len(q) > 200:
            raise ValueError("News query is outside supported bounds.")
        if asset and asset not in ASSETS:
            raise ValueError("Choose a supported news asset.")
        if publisher and publisher not in {p.source.id for p in self.providers} | {"demo", "newsapi"}:
            raise ValueError("Choose a supported news publisher.")
        if resolved == "live" and refresh:
            self.refresh()
        now = self._now()
        items = demo_items(now) if resolved == "demo" else self._archive()
        archive_count = len(items)
        cutoff = (now - timedelta(days=days)).isoformat() if days else None
        window = [i for i in items if cutoff is None or (i.get("published_at") or "") >= cutoff]
        terms = q.casefold().split()
        filtered = [
            i
            for i in window
            if (not publisher or publisher in i.get("collector_ids", [i["source_id"]]))
            and (not asset or asset in i["assets"])
            and (not sentiment or i["sentiment"]["label"] == sentiment)
            and all(term in (i["title"] + " " + i["summary"]).casefold() for term in terms)
        ]
        page = filtered[offset : offset + limit]
        return {
            "source": "demo" if resolved == "demo" else "publisher feeds",
            "mode": resolved,
            "default_mode": self.default_mode,
            "generated_at": now.isoformat(),
            "items": [
                {**i, "summary": extract_summary(i["summary"]) if summary == "extractive" else i["summary"]}
                for i in page
            ],
            "summary_method": summary,
            "total": len(filtered),
            "archive_count": archive_count,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < len(filtered),
            "sentiment": sentiment_report(filtered),
            "filters": {"publisher": publisher, "asset": asset, "sentiment": sentiment, "q": q, "days": days},
            "facets": {
                "assets": list(ASSETS),
                "publishers": [{"id": "demo", "name": "Sibyl sample briefing"}]
                if resolved == "demo"
                else [{"id": p.source.id, "name": p.source.name} for p in self.configured_providers()],
            },
            "sources": [] if resolved == "demo" else self.sources(),
            "collection": {
                "refresh_seconds": self.settings.news_refresh_seconds,
                "retention_days": self.settings.news_retention_days,
                "max_articles": 5000,
                "in_progress": self._refresh_lock.locked(),
            },
            "note": "Illustrative sample stories and dates; not current reporting."
            if resolved == "demo"
            else "Publisher headlines and bounded excerpts. Read the original source for full context.",
        }
