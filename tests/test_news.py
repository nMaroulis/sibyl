"""News contracts use fixed excerpts and mocked HTTP; never contact publishers in CI."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event

import httpx
import pytest

from sibyl.config import Settings
from sibyl.news.feeds import (
    MAX_BYTES,
    SOURCES,
    FeedResult,
    NewsProvider,
    RSSProvider,
    canonical_url,
    parse_feed,
)
from sibyl.news.service import NewsService

NOW = datetime(2026, 10, 20, 12, tzinfo=UTC)
SOURCE = SOURCES[0]


def story(index=1, **changes):
    return {
        "id": f"story-{index}",
        "source_id": SOURCE.id,
        "publisher": SOURCE.name,
        "title": f"Bitcoin celebrates excellent growth {index}",
        "summary": "Strong growth brings great optimism. More detail follows. A final sentence.",
        "category": "Markets",
        "published_at": (NOW - timedelta(hours=index)).isoformat(),
        "url": f"https://coindesk.com/markets/story-{index}",
        **changes,
    }


class StubProvider(NewsProvider):
    source = SOURCE

    def __init__(self, items=None):
        self.items = items if items is not None else [story()]
        self.calls = 0
        self.error = False

    def fetch(self, state, now):
        self.calls += 1
        if self.error:
            raise httpx.ConnectError("sensitive transport diagnostics")
        return FeedResult(self.items, '"v1"', "Tue, 20 Oct 2026 11:00:00 GMT")


@pytest.fixture
def news(settings, monkeypatch):
    service = NewsService(settings, [StubProvider()])
    monkeypatch.setattr(service, "_now", lambda: NOW)
    return service


def test_rss_parser_sanitizes_and_preserves_provenance():
    xml = b"""<rss><channel><item><title>Bitcoin &amp; growth</title>
      <link>https://www.coindesk.com/markets/story?id=3&amp;utm_source=test#comments</link>
      <description><![CDATA[<p>Excellent <b>progress</b>.</p><script>ignored()</script>]]></description>
      <pubDate>Tue, 20 Oct 2026 11:00:00 GMT</pubDate><category>Markets</category>
      </item><item><title>Unsafe</title><link>javascript:alert(1)</link></item></channel></rss>"""
    items = parse_feed(xml, SOURCE, NOW)
    assert len(items) == 1
    item = items[0]
    assert item["url"] == "https://coindesk.com/markets/story?id=3"
    assert item["title"] == "Bitcoin & growth"
    assert item["summary"] == "Excellent progress."
    assert item["published_at"] == "2026-10-20T11:00:00+00:00"
    assert item["source_id"] == SOURCE.id


def test_atom_parser_and_missing_dates():
    xml = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Ethereum news</title>
      <link rel="self" href="https://coindesk.com/api/story"/>
      <link rel="alternate" href="https://coindesk.com/story"/>
      <summary>New protocol details.</summary><published>not-a-date</published>
      <category term="Technology"/></entry></feed>"""
    item = parse_feed(xml, SOURCE, NOW)[0]
    assert item["url"] == "https://coindesk.com/story"
    assert item["category"] == "Technology"
    assert item["published_at"] is None


def test_empty_namespaced_description_does_not_replace_rss_excerpt():
    xml = b"""<rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><item>
      <title>A Bitcoin update</title><link>https://coindesk.com/story</link>
      <description>The actual publisher excerpt.</description><dc:description/>
      </item></channel></rss>"""
    assert parse_feed(xml, SOURCE, NOW)[0]["summary"] == "The actual publisher excerpt."


def test_publisher_newsletter_boilerplate_is_excluded_from_analysis_input():
    xml = b"""<rss><channel><item><title>Bitcoin news</title><link>https://cryptoslate.com/story/</link>
      <description><![CDATA[<p>The actual news excerpt.</p><p>Read the full story on CryptoSlate</p>
      <p>Understand the stories that matter. Get The Catalyst in your inbox</p>]]></description>
      </item></channel></rss>"""
    assert parse_feed(xml, SOURCES[4], NOW)[0]["summary"] == "The actual news excerpt."


@pytest.mark.parametrize(
    "url",
    [
        "http://coindesk.com/a",
        "https://coindesk.com.evil.test/a",
        "https://user:password@coindesk.com/a",
        "https://127.0.0.1/a",
        "javascript:alert(1)",
        "https://coindesk.com:8443/a",
        "https://coindesk.com:bad/a",
    ],
)
def test_article_links_are_publisher_owned_https(url):
    assert canonical_url(url, SOURCE) is None


@pytest.mark.parametrize(
    "body",
    [
        b'<!DOCTYPE rss [<!ENTITY a "test">]><rss/>',
        '<!DOCTYPE rss [<!ENTITY a "test">]><rss/>'.encode("utf-16-le"),
        b"<html><body>Challenge</body></html>",
        b"<rss><channel/></rss>",
        b"x" * (MAX_BYTES + 1),
    ],
)
def test_untrusted_or_oversized_xml_is_rejected(body):
    with pytest.raises(ValueError):
        parse_feed(body, SOURCE, NOW)


def test_conditional_requests_and_no_redirects():
    def handler(request):
        assert request.url == SOURCE.url
        assert request.headers["If-None-Match"] == '"v1"'
        assert request.headers["If-Modified-Since"] == "yesterday"
        return httpx.Response(304)

    provider = RSSProvider(SOURCE, httpx.MockTransport(handler))
    result = provider.fetch({"etag": '"v1"', "modified": "yesterday", "last_success": NOW.isoformat()}, NOW)
    assert result.items is None
    assert result.etag == '"v1"'
    provider = RSSProvider(
        SOURCE,
        httpx.MockTransport(lambda _: httpx.Response(302, headers={"Location": "http://127.0.0.1/secret"})),
    )
    with pytest.raises(httpx.HTTPStatusError):
        provider.fetch({}, NOW)


def test_transport_rejects_oversized_body_before_parsing():
    provider = RSSProvider(
        SOURCE, httpx.MockTransport(lambda _: httpx.Response(200, content=b"x" * (MAX_BYTES + 1)))
    )
    with pytest.raises(ValueError, match="2 MB"):
        provider.fetch({}, NOW)


def test_live_archive_persists_and_never_contains_demo(news, settings, monkeypatch):
    result = news.query(mode="live")
    assert result["source"] == "publisher feeds"
    assert result["sources"][0]["status"] == "fresh"
    assert result["items"][0]["assets"] == ["BTC"]
    assert news.query(mode="demo")["source"] == "demo"
    assert len(news.repository.items()) == 1
    restarted = NewsService(settings, [StubProvider([])])
    monkeypatch.setattr(restarted, "_now", lambda: NOW)
    assert restarted.query(mode="live")["items"][0]["id"] == "story-1"
    assert restarted.providers[0].calls == 0


def test_failed_refresh_keeps_stale_archive_and_safe_error(news, monkeypatch):
    news.query(mode="live")
    news.providers[0].error = True
    monkeypatch.setattr(news, "_now", lambda: NOW + timedelta(minutes=11))
    result = news.query(mode="live")
    assert result["total"] == 1
    assert result["sources"][0]["status"] == "stale"
    assert result["sources"][0]["last_success"] == NOW.isoformat()
    assert "sensitive" not in json.dumps(result)
    assert news.article("story-1", "live")["id"] == "story-1"


def test_total_failure_returns_unavailable_without_sample_fallback(news):
    news.providers[0].error = True
    result = news.query(mode="live")
    assert result["items"] == []
    assert result["sentiment"]["compound"] is None
    assert result["sources"][0]["status"] == "unavailable"


def test_url_and_same_source_title_deduplication(news):
    news.providers[0].items = [
        story(),
        story(2, title=story()["title"], published_at=story()["published_at"]),
        story(),
    ]
    result = news.query(mode="live")
    assert result["total"] == 1
    assert result["items"][0]["id"] == "story-1"


def test_filters_and_sentiment_cover_matching_archive_before_pagination(news):
    news.providers[0].items = [story(i) for i in range(1, 7)] + [
        story(7, title="Ethereum suffers terrible losses", summary="A disastrous failure.")
    ]
    result = news.query(
        mode="live", asset="BTC", sentiment="positive", q="excellent growth", limit=2, offset=2
    )
    assert result["total"] == 6
    assert len(result["items"]) == 2
    assert result["has_more"] is True
    assert result["sentiment"]["count"] == result["sentiment"]["positive"] == 6
    assert sum(i["count"] for i in result["sentiment"]["timeline"]) == 6
    assert result["sentiment"]["assets"][0]["asset"] == "BTC"
    assert news.query(mode="live", asset="ETH")["total"] == 1
    assert news.query(mode="live", publisher="coindesk")["total"] == 7
    assert news.providers[0].calls == 1


def test_undated_and_retention_boundaries(news, monkeypatch):
    news.providers[0].items = [
        story(1, published_at=None),
        story(2, published_at=(NOW - timedelta(days=31)).isoformat()),
        story(3),
    ]
    assert news.query(mode="live")["total"] == 1
    all_items = news.query(mode="live", days=0)
    assert all_items["total"] == 2
    assert all_items["sentiment"]["undated"] == 1
    monkeypatch.setattr(news, "_now", lambda: NOW + timedelta(days=32))
    assert news._archive() == []


def test_manual_refresh_has_cooldown_and_304_keeps_articles(news, monkeypatch):
    news.refresh()
    assert news.refresh(force=True)["attempted"] == 0
    news.providers[0].items = None
    monkeypatch.setattr(news, "_now", lambda: NOW + timedelta(seconds=61))
    assert news.refresh(force=True)["attempted"] == 1
    assert len(news.repository.items()) == 1


def test_adapter_version_change_invalidates_http_validators(news, monkeypatch):
    seen = []

    def fetch(state, now):
        seen.append(state)
        return FeedResult([story()], etag='"cached"')

    monkeypatch.setattr(news.providers[0], "fetch", fetch)
    news.refresh()
    monkeypatch.setattr(news, "_now", lambda: NOW + timedelta(seconds=61))
    news.refresh(force=True)
    assert seen[-1]["etag"] == '"cached"'
    news.providers[0].cache_version = "2"
    monkeypatch.setattr(news, "_now", lambda: NOW + timedelta(seconds=122))
    news.refresh(force=True)
    assert seen[-1] == {}


def test_source_failures_are_isolated_from_successful_publishers(news):
    failed = StubProvider()
    failed.source = SOURCES[1]
    failed.error = True
    news.providers.append(failed)
    result = news.query(mode="live")
    assert result["total"] == 1
    assert [s["status"] for s in result["sources"]] == ["fresh", "unavailable"]


def test_reporter_can_open_archived_story_beyond_its_briefing_page(client, monkeypatch):
    service = client.app.state.services.research.news_service
    service.providers = [StubProvider([story(i) for i in range(1, 21)])]
    monkeypatch.setattr(service, "_now", lambda: NOW)
    service.refresh()  # Collection happens before Reporter reads the retained archive.
    result = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "reporter",
            "message": "Explain this story",
            "context": {"news_mode": "live", "article_id": "story-20"},
        },
    )
    assert result.status_code == 200
    evidence = result.json()["evidence"]
    assert len(evidence["items"]) == 8
    assert evidence["selected_article"]["id"] == "story-20"
    assert "growth 20" in result.json()["answer"]


def test_concurrent_refresh_is_single_flight(news, monkeypatch):
    entered, release = Event(), Event()

    def slow_fetch(state, now):
        entered.set()
        assert release.wait(5)
        return FeedResult([story()])

    monkeypatch.setattr(news.providers[0], "fetch", slow_fetch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        running = pool.submit(news.refresh)
        try:
            assert entered.wait(5)
            assert news.refresh() == {"in_progress": True, "attempted": 0}
        finally:
            release.set()
        assert running.result()["attempted"] == 1


def test_news_modes_and_query_bounds(client):
    result = client.get("/api/v1/news?asset=ETH&mode=demo").json()
    assert result["mode"] == "demo"
    assert result["total"] == 1
    article = result["items"][0]
    assert client.get(f"/api/v1/news/{article['id']}?mode=demo").json()["item"]["id"] == article["id"]
    assert client.get("/api/v1/news/missing?mode=demo").status_code == 404
    assert len(client.get("/api/v1/news/sources").json()["items"]) == 5
    for query in ("limit=0", "limit=101", "offset=-1", "days=366", "sentiment=bullish", "mode=no"):
        assert client.get(f"/api/v1/news?{query}").status_code == 422
    assert client.get("/api/v1/news?asset=FAKE").status_code == 400


def test_reporter_honors_selection_and_does_not_substitute_missing_article(client):
    result = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "reporter",
            "message": "Explain this selection",
            "context": {"news_mode": "demo", "news_asset": "ETH", "news_days": 7},
        },
    )
    assert result.status_code == 200
    evidence = result.json()["evidence"]
    assert evidence["total"] == 1
    assert evidence["filters"]["asset"] == "ETH"
    missing = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "reporter",
            "message": "Explain this story",
            "context": {"article_id": "missing", "news_mode": "demo"},
        },
    )
    assert missing.status_code == 404


def test_news_setting_can_use_public_news_with_demo_accounts(tmp_path):
    service = NewsService(Settings(data_dir=tmp_path, mode="demo", news_mode="live", _env_file=None), [])
    assert service.default_mode == "live"
    assert service.query()["mode"] == "live"
    assert service.settings.mode == "demo"
