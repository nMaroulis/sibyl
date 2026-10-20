"""Optional web and authenticated API collectors behind the common news interface."""

import hashlib
import ipaddress
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from sibyl.news.feeds import (
    MAX_BYTES,
    SOURCES,
    FeedResult,
    FeedSource,
    NewsProvider,
    canonical_url,
    plain_text,
    published_date,
)

USER_AGENT = "Sibyl/0.2 (local research dashboard)"
NEWSAPI = FeedSource("newsapi", "NewsAPI", "https://newsapi.org/v2/everything", "https://newsapi.org")


def read_public(
    url: str,
    *,
    headers: dict | None = None,
    params: dict | None = None,
    transport: httpx.BaseTransport | None = None,
) -> bytes:
    """Read a fixed provider endpoint without redirects, bounding the decoded response."""
    with httpx.Client(timeout=12, follow_redirects=False, transport=transport) as client:
        with client.stream(
            "GET", url, params=params, headers={"User-Agent": USER_AGENT, **(headers or {})}
        ) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > MAX_BYTES:
                    raise ValueError("Provider response exceeds the 2 MB limit.")
            return bytes(body)


class _ArticleCards(HTMLParser):
    """Extract semantic article cards, never fetching their full linked articles."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []
        self.current = None
        self.depth = 0
        self.heading = False
        self.paragraph = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "article":
            self.depth += 1
            if self.current is None:
                self.current = {"title": [], "summary": [], "url": "", "date": ""}
        if self.current is None:
            return
        if tag in {"h1", "h2", "h3"}:
            self.heading = True
        if tag == "p":
            self.paragraph = True
        if tag == "a" and self.heading:
            self.current["url"] = attrs.get("href", "")
        if tag == "time" and not self.current["date"]:
            self.current["date"] = attrs.get("datetime", "")

    def handle_data(self, data):
        if self.current is not None:
            if self.heading:
                self.current["title"].append(data)
            elif self.paragraph:
                self.current["summary"].append(data)

    def handle_endtag(self, tag):
        if tag in {"h1", "h2", "h3"}:
            self.heading = False
        if tag == "p":
            self.paragraph = False
        if tag == "article" and self.current is not None:
            self.depth -= 1
            if not self.depth:
                self.items.append(self.current)
                self.current = None


class CryptoSlateWebProvider(NewsProvider):
    """Collect public homepage article cards after honoring the site's robots.txt."""

    source = next(s for s in SOURCES if s.id == "cryptoslate")
    cache_version = "web-cards-1"

    def __init__(self, transport: httpx.BaseTransport | None = None):
        self.transport = transport

    def fetch(self, state: dict, now: datetime) -> FeedResult:
        robots = RobotFileParser()
        robots.parse(
            read_public("https://cryptoslate.com/robots.txt", transport=self.transport)
            .decode("utf-8")
            .splitlines()
        )
        if not robots.can_fetch(USER_AGENT, self.source.website + "/"):
            raise ValueError("Publisher does not permit this collection path.")
        parser = _ArticleCards()
        parser.feed(read_public(self.source.website + "/", transport=self.transport).decode("utf-8"))
        items = []
        for card in parser.items[:60]:
            url = canonical_url(card["url"], self.source)
            title = plain_text(" ".join(card["title"]), 300)
            if url and title:
                items.append(
                    {
                        "id": hashlib.sha256(url.encode()).hexdigest()[:24],
                        "source_id": self.source.id,
                        "publisher": self.source.name,
                        "title": title,
                        "summary": plain_text(" ".join(card["summary"])),
                        "category": "Markets",
                        "published_at": published_date(card["date"], now),
                        "url": url,
                    }
                )
        if not items:
            raise ValueError("Publisher layout did not contain supported article cards.")
        return FeedResult(items)


def external_article_url(value: str) -> str | None:
    """Normalize API-supplied links; these are displayed, never fetched by this adapter."""
    try:
        host = urlsplit(value).hostname or ""
        if "." not in host or host.endswith((".localhost", ".local", ".internal")):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            pass
        return canonical_url(value, FeedSource("link", "Publisher", "", f"https://{host}"))
    except ValueError:
        return None


class NewsAPIProvider(NewsProvider):
    """Search NewsAPI with a server-only header key and retain original publisher attribution."""

    source = NEWSAPI

    def __init__(self, api_key: str, query: str, transport: httpx.BaseTransport | None = None):
        self.api_key, self.query, self.transport = api_key, query, transport
        self.cache_version = "newsapi-1-" + hashlib.sha256(query.encode()).hexdigest()[:12]

    def fetch(self, state: dict, now: datetime) -> FeedResult:
        import json

        payload = json.loads(
            read_public(
                self.source.url,
                headers={"X-Api-Key": self.api_key},
                params={"q": self.query, "language": "en", "sortBy": "publishedAt", "pageSize": 50},
                transport=self.transport,
            )
        )
        if (
            not isinstance(payload, dict)
            or payload.get("status") != "ok"
            or not isinstance(payload.get("articles"), list)
        ):
            raise ValueError("NewsAPI returned an unsuccessful response.")
        items = []
        for article in payload["articles"][:50]:
            if not isinstance(article, dict):
                continue
            url = external_article_url(str(article.get("url") or ""))
            title = plain_text(str(article.get("title") or ""), 300)
            if not url or not title or title == "[Removed]":
                continue
            publisher = article.get("source") if isinstance(article.get("source"), dict) else {}
            items.append(
                {
                    "id": hashlib.sha256(url.encode()).hexdigest()[:24],
                    "source_id": self.source.id,
                    "publisher": plain_text(str(publisher.get("name") or urlsplit(url).hostname), 80),
                    "title": title,
                    "summary": plain_text(str(article.get("description") or "")),
                    "category": "Markets",
                    "published_at": published_date(str(article.get("publishedAt") or ""), now),
                    "url": url,
                }
            )
        return FeedResult(items)
