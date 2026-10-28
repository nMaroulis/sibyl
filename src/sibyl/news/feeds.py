"""Bounded RSS/Atom adapters for an explicit catalog of public publisher feeds."""

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from xml.etree import ElementTree

import httpx

MAX_BYTES = 2_000_000


@dataclass(frozen=True)
class FeedSource:
    """A reviewed publisher endpoint; URLs cannot be supplied by API callers."""

    id: str
    name: str
    url: str
    website: str


SOURCES = (
    FeedSource(
        "coindesk", "CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss", "https://www.coindesk.com"
    ),
    FeedSource(
        "cointelegraph", "Cointelegraph", "https://cointelegraph.com/rss", "https://cointelegraph.com"
    ),
    FeedSource("decrypt", "Decrypt", "https://decrypt.co/feed", "https://decrypt.co"),
    FeedSource("theblock", "The Block", "https://www.theblock.co/rss.xml", "https://www.theblock.co"),
    FeedSource("cryptoslate", "CryptoSlate", "https://cryptoslate.com/feed/", "https://cryptoslate.com"),
)


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        elif tag in {"p", "br", "div", "li"}:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "br", "div", "li"}:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain_text(value: str, limit: int = 700) -> str:
    """Remove markup, active content, and excessive whitespace from publisher text."""
    parser = _PlainText()
    parser.feed(value[:20_000])
    return " ".join("".join(parser.parts).split())[:limit]


def canonical_url(value: str, source: FeedSource) -> str | None:
    """Accept publisher-owned HTTPS article links and remove only tracking parameters."""
    try:
        parts = urlsplit(value.strip())
        host = parts.hostname or ""
        domain = urlsplit(source.website).hostname.removeprefix("www.")
        if (
            parts.scheme != "https"
            or parts.username
            or parts.password
            or parts.port not in (None, 443)
            or not (host == domain or host.endswith("." + domain))
        ):
            return None
        query = [
            (k, v)
            for k, v in parse_qsl(parts.query)
            if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}
        ]
        return urlunsplit(("https", host.removeprefix("www."), parts.path or "/", urlencode(query), ""))
    except ValueError:
        return None


def published_date(value: str, now: datetime) -> str | None:
    """Normalize RSS or Atom dates to UTC; reject unparseable and far-future timestamps."""
    try:
        try:
            parsed = parsedate_to_datetime(value)
        except (ValueError, TypeError):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        parsed = parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
        return parsed.isoformat() if parsed <= now + timedelta(minutes=10) else None
    except (ValueError, TypeError, OverflowError):
        return None


def parse_feed(content: bytes, source: FeedSource, now: datetime) -> list[dict]:
    """Parse up to 60 RSS/Atom excerpts, rejecting DTDs and entity declarations."""
    if len(content) > MAX_BYTES:
        raise ValueError("Feed exceeds the 2 MB limit.")
    xml = content.decode("utf-8-sig")
    if "\x00" in xml or re.search(r"<!\s*(DOCTYPE|ENTITY)", xml, re.I):
        raise ValueError("Feed contains unsupported XML declarations.")
    root = ElementTree.fromstring(xml)

    def local(tag):
        return tag.rsplit("}", 1)[-1]

    if local(root.tag) not in {"rss", "feed", "RDF"}:
        raise ValueError("Response is not an RSS or Atom feed.")
    items = []
    for node in [n for n in root.iter() if local(n.tag) in {"item", "entry"}][:60]:

        def value(*names, children=tuple(node)):
            for name in names:
                for child in children:
                    if local(child.tag) == name:
                        text = "".join(child.itertext()).strip()
                        if text:
                            return text
            return ""

        link = value("link")
        for child in node:
            if local(child.tag) == "link" and child.get("rel", "alternate") == "alternate":
                link = child.get("href") or link
        url = canonical_url(link, source)
        title = plain_text(value("title"), 300)
        if not url or not title:
            continue
        category = next((child for child in node if local(child.tag) == "category"), None)
        excerpt = plain_text(value("description", "summary", "encoded", "content"), 2000)
        if source.id == "cryptoslate":
            # This publisher appends its source link and newsletter CTA to every excerpt.
            excerpt = excerpt.split("Read the full story on CryptoSlate", 1)[0].strip()
        items.append(
            {
                "id": hashlib.sha256(url.encode()).hexdigest()[:24],
                "source_id": source.id,
                "publisher": source.name,
                "title": title,
                "summary": excerpt[:700],
                "category": plain_text(category.get("term") or value("category"), 80)
                if category is not None
                else "Markets",
                "published_at": published_date(value("pubDate", "published", "date", "updated"), now),
                "url": url,
            }
        )
    if not items:
        raise ValueError("Feed contained no supported publisher article links.")
    return items


@dataclass
class FeedResult:
    """A modified feed or HTTP 304 with conditional request validators."""

    items: list[dict] | None
    etag: str | None = None
    modified: str | None = None


class NewsProvider(ABC):
    """Implement a publisher transport independently of persistence and analysis."""

    source: FeedSource
    cache_version = "1"

    @abstractmethod
    def fetch(self, state: dict, now: datetime) -> FeedResult:
        """Fetch new excerpts, or return ``items=None`` when unchanged."""


class RSSProvider(NewsProvider):
    """Read an allowlisted public endpoint with conditional requests and bounded bodies."""

    def __init__(self, source: FeedSource, transport: httpx.BaseTransport | None = None):
        self.source = source
        self.transport = transport

    def fetch(self, state: dict, now: datetime) -> FeedResult:
        headers = {
            "User-Agent": "Sibyl/0.2 (local research dashboard)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml",
        }
        if state.get("etag"):
            headers["If-None-Match"] = state["etag"]
        if state.get("modified"):
            headers["If-Modified-Since"] = state["modified"]
        # Redirects deliberately require a catalog update, rather than following arbitrary destinations.
        with httpx.Client(timeout=12, follow_redirects=False, transport=self.transport) as client:
            with client.stream("GET", self.source.url, headers=headers) as response:
                if response.status_code == 304:
                    if not state.get("last_success"):
                        raise ValueError("Publisher returned 304 before a successful collection.")
                    return FeedResult(None, state.get("etag"), state.get("modified"))
                response.raise_for_status()
                if response.is_redirect:
                    raise ValueError("Publisher moved its feed endpoint.")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise ValueError("Feed exceeds the 2 MB limit.")
                return FeedResult(
                    parse_feed(bytes(body), self.source, now),
                    response.headers.get("etag", "")[:500],
                    response.headers.get("last-modified", "")[:500],
                )
