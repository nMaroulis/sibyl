"""Fetch boundaries, attributed history, persistent caching, and contextual Wiki reads."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import httpx
import pytest

from sibyl.services.crypto_library import CryptoLibrary, CryptoSourceError, article_sections, safe_url


@pytest.fixture
def library(settings):
    return CryptoLibrary(settings.data_dir)


@pytest.fixture
def public_payloads():
    return {
        "profile": {
            "id": "btc-bitcoin",
            "description": "A <b>public</b> project description.",
            "started_at": "2009-01-03T00:00:00Z",
            "proof_type": "Proof of Work",
            "org_structure": "Decentralized",
            "open_source": True,
            "tags": [{"name": "Payments"}],
            "team": [{"name": "Satoshi Nakamoto", "position": "Creator"}],
            "links": {
                "website": ["https://bitcoin.org", "javascript:alert(1)"],
                "explorer": ["https://user:password@example.com"],
            },
            "whitepaper": {"link": "https://bitcoin.org/bitcoin.pdf"},
        },
        "market": {
            "id": "btc-bitcoin",
            "rank": 1,
            "circulating_supply": 20_000_000,
            "max_supply": 21_000_000,
            "quotes": {"USD": {"price": 100, "market_cap": 2_000_000_000, "percent_change_24h": -1.5}},
        },
        "history": {
            "query": {
                "pages": [
                    {
                        "title": "Bitcoin",
                        "lastrevid": 1234,
                        "fullurl": "https://en.wikipedia.org/wiki/Bitcoin",
                        "extract": "An encyclopedia introduction.\n\n== History ==\nEarly background.\n=== Creation ===\nIt started in 2009.\n=== Later years ===\nFurther developments.\n== Technology ==\nThis belongs outside the history section.",
                    }
                ]
            }
        },
    }


def wire(library, monkeypatch, payloads):
    calls = []

    def get(url, **params):
        calls.append((url, params))
        return payloads["history" if "wikipedia" in url else "market" if "/tickers/" in url else "profile"]

    monkeypatch.setattr(library, "_json", get)
    return calls


def test_catalog_is_twenty_unique_editorial_choices_and_does_not_fetch(client, monkeypatch):
    library = client.app.state.services.research.crypto
    monkeypatch.setattr(library, "_json", lambda *_args, **_kwargs: pytest.fail("Catalog fetched a profile"))
    response = client.get("/api/v1/research/crypto")
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == len({a["id"] for a in items}) == len({a["symbol"] for a in items}) == 20
    assert {"BTC", "ETH", "USDT", "XMR", "ETC"} <= {a["symbol"] for a in items}
    assert "not a live ranking" in response.json()["selection_note"]


def test_profile_fetches_three_sources_in_demo_mode_and_normalizes_fields(
    client, monkeypatch, public_payloads
):
    library = client.app.state.services.research.crypto
    calls = wire(library, monkeypatch, public_payloads)
    response = client.get("/api/v1/research/crypto/btc-bitcoin")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "ready" and len(calls) == 3
    assert result["profile"]["description"] == "A public project description."
    assert result["market"]["price"] == 100 and result["market"]["percent_change_24h"] == -1.5
    assert result["market"]["total_supply"] is None
    assert result["history"]["sections"][1] == {"title": "Creation", "text": "It started in 2009."}
    assert "Technology" not in json.dumps(result["history"]["sections"])
    assert result["history"]["license_url"].endswith("by-sa/4.0/") and result["history"]["revision"] == 1234
    assert all(source["as_of"] and source["url"].startswith("https://") for source in result["sources"])
    assert all(link["url"].startswith("https://bitcoin.org") for link in result["profile"]["links"])
    assert client.get("/api/v1/system").json()["mode"] == "demo"


def test_profile_cache_survives_service_restart(library, settings, monkeypatch, public_payloads):
    calls = wire(library, monkeypatch, public_payloads)
    first = library.profile("btc-bitcoin")
    assert len(calls) == 3
    restarted = CryptoLibrary(settings.data_dir)
    monkeypatch.setattr(restarted, "_json", lambda *_args, **_kwargs: pytest.fail("Cache was not reused"))
    second = restarted.profile("btc-bitcoin")
    assert first["profile"] == second["profile"] and first["history"] == second["history"]
    assert all(source["cached"] and not source["stale"] for source in second["sources"])


def test_parallel_requests_fetch_each_source_only_once(library, monkeypatch, public_payloads):
    calls = wire(library, monkeypatch, public_payloads)
    with ThreadPoolExecutor(max_workers=6) as pool:
        profiles = list(pool.map(lambda _: library.profile("btc-bitcoin"), range(6)))
    assert len(calls) == 3
    assert all(result["status"] == "ready" for result in profiles)


def test_market_failure_preserves_fetched_education_and_throttles_retry(
    library, monkeypatch, public_payloads
):
    calls = wire(library, monkeypatch, public_payloads)
    original = library._json

    def fail_market(url, **params):
        if "/tickers/" in url:
            calls.append((url, params))
            raise CryptoSourceError("Provider rate limit reached; retry after one minute.")
        return original(url, **params)

    monkeypatch.setattr(library, "_json", fail_market)
    result = library.profile("btc-bitcoin")
    assert result["status"] == "partial" and result["market"] is None
    assert result["profile"] and result["history"]
    assert result["sources"][2]["error"] and not result["sources"][2]["stale"]
    assert library.profile("btc-bitcoin")["market"] is None
    assert len(calls) == 3


def test_expired_observation_is_explicitly_stale_when_provider_fails(library, monkeypatch, public_payloads):
    wire(library, monkeypatch, public_payloads)
    before = library.profile("btc-bitcoin")
    path = library.directory / "btc-bitcoin-market.json"
    cached = json.loads(path.read_text())
    cached["checked_at"] = time.time() - 901
    path.write_text(json.dumps(cached))
    monkeypatch.setattr(
        library, "_fetch", lambda *_: (_ for _ in ()).throw(CryptoSourceError("Source unavailable."))
    )
    after = library.profile("btc-bitcoin")
    assert after["status"] == "partial"
    assert after["market"] == before["market"]
    source = next(s for s in after["sources"] if s["part"] == "market")
    assert source["stale"] and source["error"] == "Source unavailable."
    assert source["as_of"] == before["sources"][2]["as_of"]


def test_all_source_failure_is_not_replaced_with_fixtures(library, monkeypatch):
    monkeypatch.setattr(library, "_fetch", lambda *_: (_ for _ in ()).throw(CryptoSourceError("Offline.")))
    result = library.profile("btc-bitcoin")
    assert result["status"] == "unavailable"
    assert result["market"] is result["profile"] is result["history"] is None
    assert all(source["error"] == "Offline." for source in result["sources"])


@pytest.mark.parametrize("asset_id", ["unknown", "../../settings", "https://example.com", "BTC"])
def test_non_catalog_ids_never_cause_network_or_file_reads(library, monkeypatch, asset_id):
    monkeypatch.setattr(library, "_json", lambda *_args, **_kwargs: pytest.fail("Invalid asset fetched"))
    with pytest.raises(LookupError):
        library.profile(asset_id)


def test_api_unknown_id_returns_not_found(client):
    assert client.get("/api/v1/research/crypto/not-a-coin").status_code == 404


def test_wrong_provider_asset_and_missing_wikipedia_are_partial(library, monkeypatch, public_payloads):
    public_payloads["profile"]["id"] = "wrong-coin"
    public_payloads["history"] = {"query": {"pages": [{"missing": True}]}}
    wire(library, monkeypatch, public_payloads)
    result = library.profile("btc-bitcoin")
    assert result["profile"] is None and result["history"] is None
    assert result["market"] is not None and result["status"] == "partial"


def test_nonfinite_provider_market_values_are_missing(library, monkeypatch, public_payloads):
    public_payloads["market"]["quotes"]["USD"].update(price=float("nan"), market_cap=float("inf"))
    wire(library, monkeypatch, public_payloads)
    result = library.profile("btc-bitcoin")
    assert result["market"]["price"] is result["market"]["market_cap"] is None
    json.dumps(result, allow_nan=False)


def test_history_without_a_history_heading_does_not_invent_milestones():
    intro, sections = article_sections("An introduction.\n== Technology ==\nTechnical details.")
    assert intro == "An introduction." and sections == []


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://name:key@host",
        "https://host:bad",
        "https://bad host/path",
    ],
)
def test_source_urls_are_safe(url):
    assert safe_url(url) is None


def test_corrupt_cache_is_refetched(library, monkeypatch, public_payloads):
    library.directory.mkdir(parents=True)
    (library.directory / "btc-bitcoin-profile.json").write_text('{"version":1,"checked_at":"bad"}')
    calls = wire(library, monkeypatch, public_payloads)
    assert library.profile("btc-bitcoin")["status"] == "ready"
    assert len(calls) == 3


def test_http_provider_failures_are_safe_and_response_size_is_bounded(library, monkeypatch):
    @contextmanager
    def limited(*_args, **_kwargs):
        yield httpx.Response(
            429,
            text="Do not reflect provider response body",
            request=httpx.Request("GET", "https://api.coinpaprika.com"),
        )

    monkeypatch.setattr(httpx, "stream", limited)
    with pytest.raises(CryptoSourceError, match="rate limit"):
        library._json("https://api.coinpaprika.com")

    @contextmanager
    def oversized(*_args, **_kwargs):
        yield httpx.Response(
            200, content=b"x" * 1_000_001, request=httpx.Request("GET", "https://api.coinpaprika.com")
        )

    monkeypatch.setattr(httpx, "stream", oversized)
    with pytest.raises(CryptoSourceError, match="exceeded"):
        library._json("https://api.coinpaprika.com")


def test_wiki_reads_the_selected_fetched_profile(client, monkeypatch, public_payloads):
    library = client.app.state.services.research.crypto
    wire(library, monkeypatch, public_payloads)
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "wiki",
            "message": "Give me the background.",
            "context": {"crypto_id": "btc-bitcoin"},
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["evidence"]["asset"]["id"] == "btc-bitcoin"
    assert "public project description" in result["answer"]
    assert result["evidence"]["history"]["revision"] == 1234
    assert result["context"]["crypto_id"] == "btc-bitcoin"


def test_background_heading_is_included_as_historical_context():
    intro, sections = article_sections(
        "Introduction.\n== Background ==\nProject origins.\n== Privacy ==\nOther details."
    )
    assert sections == [{"title": "Background", "text": "Project origins."}]


def test_unreported_zero_maximum_supply_is_not_presented_as_zero_tokens(
    library, monkeypatch, public_payloads
):
    public_payloads["market"]["max_supply"] = 0
    wire(library, monkeypatch, public_payloads)
    assert library.profile("btc-bitcoin")["market"]["max_supply"] is None
    assert library.profile("btc-bitcoin")["market"]["max_supply"] is None
