"""Provider selection, encrypted credentials, web collection and daily index contracts."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from sibyl.config import Settings
from sibyl.news.fear_greed import FearGreed
from sibyl.news.providers import CryptoSlateWebProvider, NewsAPIProvider
from sibyl.news.repository import NewsRepository
from sibyl.news.service import NewsService
from sibyl.services.data_settings import DataSettings, NewsSettingsRequest
from sibyl.storage import Store

NOW = datetime(2026, 10, 20, 12, tzinfo=UTC)


def test_news_settings_encrypt_keys_and_keep_omitted_credentials(client, settings):
    original = client.get("/api/v1/settings/news")
    assert original.status_code == 200
    assert original.headers["cache-control"] == "no-store"
    assert len(original.json()["catalog"]) == 7
    key = "private-news-key-72934"
    payload = {"mode": "demo", "sources": ["coindesk"], "api_key": key}
    saved = client.post("/api/v1/settings/news", json=payload)
    assert saved.status_code == 200
    assert saved.json()["has_api_key"] is True
    assert key not in saved.text
    assert key.encode() not in (settings.data_dir / "sibyl.db").read_bytes()
    assert key not in client.get("/api/v1/settings/news").text
    kept = client.post("/api/v1/settings/news", json={"mode": "demo", "sources": ["coindesk"]})
    assert kept.json()["has_api_key"] is True
    reopened = DataSettings(Settings(data_dir=settings.data_dir, _env_file=None), Store(settings.data_dir))
    assert reopened.news()["api_key"] == key
    removed = client.post(
        "/api/v1/settings/news", json={"mode": "demo", "sources": ["coindesk"], "clear_api_key": True}
    )
    assert removed.json()["has_api_key"] is False


@pytest.mark.parametrize(
    "payload,status",
    [
        ({"mode": "live", "sources": []}, 400),
        ({"mode": "live", "sources": ["newsapi"]}, 400),
        ({"mode": "demo", "sources": ["unknown"]}, 422),
        ({"mode": "demo", "api_key": "secret\nkey"}, 422),
        ({"mode": "demo", "api_key": "non-ascii-秘密"}, 422),
        ({"mode": "demo", "query": "\n"}, 422),
        ({"mode": "demo", "cryptoslate_method": "untrusted"}, 422),
        ({"mode": "demo", "api_key": "secret-key", "clear_api_key": True}, 400),
    ],
)
def test_news_settings_validate_before_persistence(client, payload, status):
    response = client.post("/api/v1/settings/news", json=payload)
    assert response.status_code == status
    assert "secret-key" not in response.text
    assert "secret\\nkey" not in response.text
    assert client.get("/api/v1/settings/news").json()["has_api_key"] is False


def test_source_selection_applies_immediately_and_archive_is_retained(settings, store):
    preferences = DataSettings(settings, store)
    service = NewsService(settings, data_settings=preferences)
    preferences.save_news(NewsSettingsRequest(mode="live", sources=["cryptoslate"], cryptoslate_method="web"))
    configured = service.configured_providers()
    assert len(configured) == 1
    assert isinstance(configured[0], CryptoSlateWebProvider)
    assert service.default_mode == "live"
    preferences.save_news(NewsSettingsRequest(mode="live", sources=["coindesk"]))
    assert [p.source.id for p in service.configured_providers()] == ["coindesk"]


def test_market_save_applies_immediately_without_changing_account_or_execution_mode(client, settings):
    saved = client.post("/api/v1/settings/market", json={"source": "kraken"})
    assert saved.status_code == 200
    assert saved.json()["restart_required"] is False
    assert saved.json()["active"]["id"] == "kraken"
    assert client.get("/api/v1/system").json()["mode"] == "demo"
    assert client.get("/api/v1/system").json()["allow_live_trading"] is False
    restarted_config = Settings(data_dir=settings.data_dir, news_mode="demo", _env_file=None)
    reopened = DataSettings(restarted_config, Store(settings.data_dir))
    reopened.apply_startup()
    assert restarted_config.mode == "demo"
    assert reopened.resolve_market()["id"] == "kraken"
    assert restarted_config.allow_live_trading is False
    assert client.post("/api/v1/settings/market", json={"source": "binance-testnet"}).status_code == 400


def test_demo_is_exclusive_and_keeps_unused_provider_credentials(settings, store):
    preferences = DataSettings(settings, store)
    service = NewsService(settings, data_settings=preferences)
    preferences.save_news(
        NewsSettingsRequest(mode="live", sources=["coindesk", "newsapi"], api_key="private-key")
    )
    assert len(service.configured_providers()) == 2
    saved = preferences.save_news(NewsSettingsRequest(mode="demo", sources=["coindesk", "newsapi"]))
    assert saved["sources"] == []
    assert saved["resolved_mode"] == "demo"
    assert saved["has_api_key"] is True
    assert service.configured_providers() == []
    assert service.default_mode == "demo"
    assert all(article["source_id"] == "demo" for article in service.query()["items"])
    preferences.save_news(NewsSettingsRequest(mode="live", sources=["coindesk"]))
    assert [provider.source.id for provider in service.configured_providers()] == ["coindesk"]
    store.save_data_profile("news", {**preferences.news(), "mode": "demo", "sources": ["coindesk"]})
    assert preferences.public_news()["sources"] == []
    assert service.configured_providers() == []


def test_web_collector_honors_robots_and_extracts_dated_article_cards():
    requested = []

    def handler(request):
        requested.append(str(request.url))
        assert request.url.host == "cryptoslate.com"
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
        return httpx.Response(
            200,
            text="""<main><article><h3><a href="https://cryptoslate.com/story/?utm_source=x">Bitcoin &amp; progress</a></h3><p>A useful excerpt.</p><time datetime="2026-10-20T10:00:00Z"></time></article><article><h3><a href="http://127.0.0.1/private">Unsafe</a></h3></article></main>""",
        )

    provider = CryptoSlateWebProvider(httpx.MockTransport(handler))
    result = provider.fetch({}, NOW)
    assert requested == ["https://cryptoslate.com/robots.txt", "https://cryptoslate.com/"]
    assert len(result.items) == 1
    assert result.items[0]["title"] == "Bitcoin & progress"
    assert result.items[0]["summary"] == "A useful excerpt."
    assert result.items[0]["url"] == "https://cryptoslate.com/story/"
    assert result.items[0]["published_at"] == "2026-10-20T10:00:00+00:00"


def test_web_collector_stops_when_robots_disallows_collection():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, text="User-agent: *\nDisallow: /\n")

    with pytest.raises(ValueError, match="does not permit"):
        CryptoSlateWebProvider(httpx.MockTransport(handler)).fetch({}, NOW)
    assert len(calls) == 1


def test_web_layout_change_is_explicit():
    provider = CryptoSlateWebProvider(
        httpx.MockTransport(
            lambda r: httpx.Response(
                200,
                text="User-agent: *\nAllow: /" if r.url.path == "/robots.txt" else "<html>No cards</html>",
            )
        )
    )
    with pytest.raises(ValueError, match="layout"):
        provider.fetch({}, NOW)


def test_newsapi_uses_header_key_and_preserves_original_publisher():
    def handler(request):
        assert request.url.host == "newsapi.org"
        assert request.headers["x-api-key"] == "private-key"
        assert "private-key" not in str(request.url)
        assert request.url.params["q"] == "bitcoin OR ethereum"
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "articles": [
                    {
                        "title": "Bitcoin grows",
                        "description": "<p>Strong growth.</p>",
                        "url": "https://publisher.example/news?utm_source=x",
                        "source": {"name": "Original publisher"},
                        "publishedAt": "2026-10-20T10:00:00Z",
                    },
                    {"title": "Unsafe", "url": "http://127.0.0.1/private"},
                ],
            },
        )

    result = NewsAPIProvider("private-key", "bitcoin OR ethereum", httpx.MockTransport(handler)).fetch(
        {}, NOW
    )
    assert len(result.items) == 1
    assert result.items[0]["publisher"] == "Original publisher"
    assert result.items[0]["source_id"] == "newsapi"
    assert result.items[0]["summary"] == "Strong growth."


def test_api_access_error_does_not_expose_provider_response():
    provider = NewsAPIProvider(
        "secret",
        "bitcoin",
        httpx.MockTransport(lambda _: httpx.Response(200, json={"status": "error", "message": "secret"})),
    )
    with pytest.raises(ValueError, match="unsuccessful") as exc:
        provider.fetch({}, NOW)
    assert "secret" not in str(exc.value)


def fng_payload():
    return {
        "metadata": {"error": None},
        "data": [
            {
                "value": str(55 - i % 10),
                "value_classification": "Greed" if i == 0 else "Neutral",
                "timestamp": str(int((NOW.replace(hour=0) - timedelta(days=i)).timestamp())),
            }
            for i in range(30)
        ],
    }


def test_fear_greed_cache_survives_restart_and_retains_stale_observations(tmp_path, monkeypatch):
    calls = []
    failed = False

    def handler(request):
        calls.append(str(request.url))
        assert request.url.host == "api.alternative.me"
        if failed:
            return httpx.Response(503)
        return httpx.Response(200, json=fng_payload())

    repository = NewsRepository(tmp_path)
    service = FearGreed(repository, httpx.MockTransport(handler))
    monkeypatch.setattr(service, "_now", lambda: NOW)
    first = service.read("live")
    assert first["current"]["value"] == 55
    assert first["status"] == "fresh"
    assert first["source"] == "Alternative.me"
    assert len(first["history"]) == 30
    assert first["comparisons"]["yesterday"]["value"] == 54
    assert first["comparisons"]["last_week"]["value"] == 48
    assert len(calls) == 1
    restarted = FearGreed(NewsRepository(tmp_path), httpx.MockTransport(handler))
    monkeypatch.setattr(restarted, "_now", lambda: NOW)
    assert restarted.read("live")["current"]["value"] == 55
    assert len(calls) == 1
    failed = True
    monkeypatch.setattr(restarted, "_now", lambda: NOW + timedelta(hours=2))
    stale = restarted.read("live")
    assert stale["status"] == "stale"
    assert stale["current"] == first["current"]
    assert stale["error"]


@pytest.mark.parametrize(
    "payload",
    [
        {"data": []},
        {"data": [{}]},
        {"data": [None]},
        {"data": [], "metadata": ["invalid"]},
        {"data": [{"value": "150", "value_classification": "Greed", "timestamp": str(int(NOW.timestamp()))}]},
        {"data": [{"value": True, "value_classification": "Greed", "timestamp": str(int(NOW.timestamp()))}]},
    ],
)
def test_invalid_index_never_falls_back_to_demo(tmp_path, monkeypatch, payload):
    service = FearGreed(
        NewsRepository(tmp_path), httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    )
    monkeypatch.setattr(service, "_now", lambda: NOW)
    result = service.read("live")
    assert result["status"] == "unavailable"
    assert result["current"] is None
    assert result["source"] == "Alternative.me"


def test_demo_index_and_briefing_are_backend_data(client):
    index = client.get("/api/v1/news/fear-greed?mode=demo")
    assert index.status_code == 200
    assert index.json()["mode"] == "demo"
    assert index.json()["current"]["value"] == 42
    story = client.get("/api/v1/news?mode=demo").json()["items"][0]
    assert "\n\n" in story["body"]
    assert "demo sample" in story["body"]


def test_aggregator_and_direct_provider_share_identity_and_keep_provenance(settings, store, monkeypatch):
    from sibyl.news.sentiment import analyze_article

    service = NewsService(settings, data_settings=DataSettings(settings, store))
    monkeypatch.setattr(service, "_now", lambda: NOW)
    item = analyze_article(
        {
            "id": "same-url",
            "source_id": "coindesk",
            "publisher": "CoinDesk",
            "title": "Bitcoin news",
            "summary": "The full publisher excerpt.",
            "published_at": NOW.isoformat(),
            "url": "https://coindesk.com/story",
        }
    )
    service.repository.save("coindesk", {}, [item], NOW, 30)
    service.repository.save(
        "newsapi", {}, [{**item, "source_id": "newsapi", "summary": "Short API excerpt."}], NOW, 30
    )
    assert len(service.repository.items()) == 1
    stored = service.repository.items()[0]
    assert stored["summary"] == "The full publisher excerpt."
    assert stored["collector_ids"] == ["coindesk", "newsapi"]
    service.data_settings.save_news(
        NewsSettingsRequest(mode="live", sources=["newsapi"], api_key="private-key")
    )
    monkeypatch.setattr(service, "refresh", lambda **kw: {})
    result = service.query(mode="live")
    assert result["total"] == 1
    assert result["items"][0]["source_id"] == "newsapi"
    assert result["items"][0]["publisher"] == "CoinDesk"
