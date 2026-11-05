"""Controlled embedding transport acceptance; these vectors test contracts, not model quality."""

import json
from datetime import UTC, datetime

import httpx
import pytest
from protolink import Task
from pydantic import ValidationError
from test_research_library import library as library

from sibyl.research_library.semantic.contracts import (
    IndexBatch,
    LocalEndpoint,
    SemanticNotReady,
    SemanticSettings,
)
from sibyl.research_library.semantic.provider import OllamaEmbeddings
from sibyl.research_library.service import ResearchLibrary

MODEL = "embeddinggemma:latest"
DIGEST = "a" * 64


class EmbeddingServer:
    """Fake native HTTP responses with independently specified topic vectors and visible request receipts."""

    def __init__(self):
        self.calls = []
        self.digest = DIGEST
        self.version = "0.12.0"
        self.capabilities = ["embedding"]
        self.remote = False
        self.override = None

    def client(self):
        return httpx.Client(transport=httpx.MockTransport(self.respond))

    def respond(self, request):
        assert request.url.host == "127.0.0.1" and request.url.port == 11434
        assert not request.headers.get("authorization") and not request.url.query
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, body))
        if self.override:
            response = self.override(request, body)
            if response is not None:
                return response
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": self.version})
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": MODEL,
                            "digest": self.digest,
                            "remote_host": "https://cloud.example" if self.remote else "",
                        }
                    ]
                },
            )
        if request.url.path == "/api/show":
            return httpx.Response(
                200,
                json={
                    "capabilities": self.capabilities,
                    "remote_host": "https://cloud.example" if self.remote else "",
                },
            )
        assert request.url.path == "/api/embed" and request.method == "POST"
        assert body["model"] == MODEL and body["truncate"] is False
        vectors = []
        for text in body["input"]:
            if "custodian" in text.lower() or text == "safekeeping secrets":
                vectors.append([1.0, 0.0, 0.0])
            elif "collateral" in text.lower():
                vectors.append([0.0, 1.0, 0.0])
            elif "momentum" in text.lower():
                vectors.append([0.0, 0.0, 1.0])
            else:
                vectors.append([1.0, 1.0, 1.0])
        return httpx.Response(200, json={"model": MODEL, "embeddings": vectors})


@pytest.fixture
def semantic(library):
    server = EmbeddingServer()
    library.semantic.provider = OllamaEmbeddings(server.client)
    return library, server


def configure(library):
    return library.semantic.configure(
        SemanticSettings(model=MODEL, revision=library.semantic.status()["revision"])
    )


def sources(library):
    return [
        library.import_document("custody.txt", b"The custodian safeguards private keys."),
        library.import_document("loans.txt", b"Collateral backs the lending agreement."),
        library.import_document("rsi.txt", b"Momentum measures price acceleration."),
    ]


def index(library, **kwargs):
    return library.semantic.build(IndexBatch(revision=library.semantic.status()["revision"], **kwargs))


def test_optional_status_and_keyword_search_do_not_contact_or_construct_a_model(semantic):
    library, server = semantic
    sources(library)
    assert not library.semantic.status()["configured"] and library.search("custodian")["items"]
    assert server.calls == []
    with pytest.raises(SemanticNotReady):
        library.search("custodian", method="semantic")
    assert server.calls == []


def test_semantic_related_wording_returns_exact_sources_and_hybrid_fuses_ranks(semantic):
    library, server = semantic
    docs = sources(library)
    configure(library)
    assert all(
        c[2]["input"] == ["Sibyl embedding model compatibility check."]
        for c in server.calls
        if c[1] == "/api/embed"
    )
    assert index(library)["added"] == 3
    assert not library.search("safekeeping secrets")["items"]
    result = library.search("safekeeping secrets", method="semantic")
    first = result["items"][0]
    assert first["document_id"] == docs[0]["id"] and first["text"] == "The custodian safeguards private keys."
    assert first["similarity"] == pytest.approx(1) and first["url"] == docs[0]["passages"][0]["url"]
    assert result["semantic"]["model_digest"] == DIGEST and not result["semantic"]["coverage"]["partial"]
    hybrid = library.search("collateral", method="hybrid")
    assert hybrid["items"][0]["document_id"] == docs[1]["id"]
    assert hybrid["items"][0]["fusion_score"] == pytest.approx(2 / 61)
    assert "confidence" in hybrid["note"]
    assert index(library)["added"] == 0


def test_partial_index_coverage_and_filters_are_honest(semantic):
    library, _ = semantic
    sources(library)
    configure(library)
    assert index(library, limit=1)["added"] == 1
    result = library.search("safekeeping secrets", method="hybrid")
    assert result["semantic"]["coverage"] == {"total": 3, "indexed": 1, "missing": 2, "partial": True}
    with pytest.raises(SemanticNotReady):
        library.search("query", kind="news", method="semantic")
    assert not library.search("query", kind="news")["items"]


def test_delete_and_reindex_invalidate_vectors_without_reassigning_citations(semantic):
    library, _ = semantic
    docs = sources(library)
    configure(library)
    index(library)
    library.reindex(docs[0]["id"])
    assert library.semantic.status()["coverage"]["all"]["indexed"] == 2
    library.delete(docs[1]["id"])
    status = library.semantic.status()
    assert status["coverage"]["all"]["indexed"] == 1 and status["coverage"]["all"]["total"] == 2
    assert all(
        item["document_id"] != docs[1]["id"] for item in library.search("query", method="hybrid")["items"]
    )


def test_expired_news_loses_its_vectors_and_does_not_mix_with_upload_scope(semantic):
    library, _ = semantic
    now = datetime.now(UTC)
    library.news.save(
        "publisher",
        {},
        [
            {
                "id": "retained",
                "source_id": "publisher",
                "title": "Collateral release",
                "summary": "Collateral reduces lending exposure.",
                "url": "https://example.com/story",
                "publisher": "Example",
                "published_at": now.isoformat(),
            }
        ],
        now,
        30,
    )
    library.synchronize_news()
    configure(library)
    assert index(library, kind="document")["added"] == 0
    assert index(library, kind="news")["added"] == 1
    assert library.search("collateral", kind="news", method="semantic")["items"][0]["kind"] == "news"
    with library.news.connect() as db:
        db.execute("DELETE FROM articles")
    library.synchronize_news()
    assert library.semantic.status()["coverage"]["news"]["indexed"] == 0


def test_reopened_index_is_persistent_and_startup_is_passive(semantic):
    library, _ = semantic
    sources(library)
    configure(library)
    index(library)
    reopened = ResearchLibrary(library.path.parent, library.news)
    assert (
        reopened.semantic.status()["configured"]
        and reopened.semantic.status()["coverage"]["all"]["indexed"] == 3
    )
    reopened.semantic.provider = OllamaEmbeddings(lambda: pytest.fail("Keyword retrieval contacted Ollama"))
    assert reopened.search("custodian")["items"]


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://127.0.0.1:11434",
        "http://example.com:11434",
        "http://169.254.169.254",
        "http://127.0.0.1:0",
        "http://127.0.0.1:70000",
        "http://user:PRIVATE@localhost:11434",
        "http://:PRIVATE@localhost:11434",
        "http://127.0.0.1:11434/secret",
        "http://127.0.0.1:11434?key=PRIVATE",
        "http://127.0.0.1:11434#fragment",
    ],
)
def test_nonlocal_or_credential_bearing_endpoints_are_rejected(endpoint):
    with pytest.raises(ValidationError):
        LocalEndpoint(endpoint=endpoint)
    assert LocalEndpoint(endpoint="http://localhost:11434/").endpoint == "http://127.0.0.1:11434"


@pytest.mark.parametrize("cloud", [True, False])
def test_remote_or_chat_models_are_rejected_before_document_embedding(semantic, cloud):
    library, server = semantic
    sources(library)
    server.remote = cloud
    server.capabilities = ["completion"] if not cloud else ["embedding"]
    with pytest.raises(SemanticNotReady):
        configure(library)
    assert not any(path == "/api/embed" for _, path, _ in server.calls)
    assert not library.semantic.status()["configured"]


@pytest.mark.parametrize("change", ["digest", "version", "dimensions"])
def test_changed_vector_space_never_mixes_old_and_new_embeddings(semantic, change):
    library, server = semantic
    sources(library)
    configure(library)
    index(library)
    calls = len(server.calls)
    if change == "digest":
        server.digest = "b" * 64
    elif change == "version":
        server.version = "0.13.0"
    else:
        server.override = lambda request, body: (
            httpx.Response(
                200, json={"model": MODEL, "embeddings": [[1.0, 0.0, 0.0, 0.0] for _ in body["input"]]}
            )
            if request.url.path == "/api/embed"
            else None
        )
    with pytest.raises(SemanticNotReady):
        library.search("query", method="semantic")
    if change != "dimensions":
        assert not any(path == "/api/embed" for _, path, _ in server.calls[calls:])
    assert library.search("custodian")["items"]


def test_model_change_during_embedding_discards_batch(semantic):
    library, server = semantic
    sources(library)
    configure(library)

    def change(request, body):
        if request.url.path == "/api/embed":
            server.digest = "b" * 64
        return None

    server.override = change
    with pytest.raises(SemanticNotReady):
        index(library)
    assert library.semantic.status()["coverage"]["all"]["indexed"] == 0


@pytest.mark.parametrize(
    "vectors",
    [
        [[0.0, 0.0, 0.0]],
        [[True, 0.0, 1.0]],
        [[float("nan"), 0.0, 1.0]],
        [[float("inf"), 0.0, 1.0]],
        [[1e300, 0.0, 0.0]],
        [[1.0] * 4097],
        [],
        [[1.0, 0.0], [1.0, 0.0]],
    ],
)
def test_invalid_or_incomplete_embedding_responses_publish_no_vectors(semantic, vectors):
    library, server = semantic
    library.import_document("memo.txt", b"The custodian safeguards private keys.")
    configure(library)
    server.override = lambda request, body: (
        httpx.Response(200, text=json.dumps({"model": MODEL, "embeddings": vectors}))
        if request.url.path == "/api/embed"
        else None
    )
    with pytest.raises(ValueError):
        index(library)
    assert library.semantic.status()["coverage"]["all"]["indexed"] == 0


def test_stale_revision_and_deleted_source_responses_cannot_resurrect_data(semantic, monkeypatch):
    library, _ = semantic
    docs = sources(library)
    configure(library)
    original = library.semantic.provider.embed

    def remove(profile, texts):
        result = original(profile, texts)
        for doc in docs:
            library.delete(doc["id"])
        return result

    monkeypatch.setattr(library.semantic.provider, "embed", remove)
    result = index(library)
    assert result["added"] == 0 and result["skipped_changed"] == 3
    assert not library.semantic.status()["indexing"]
    sources(library)

    def clear(profile, texts):
        result = original(profile, texts)
        library.semantic.clear(library.semantic.status()["revision"])
        return result

    monkeypatch.setattr(library.semantic.provider, "embed", clear)
    with pytest.raises(SemanticNotReady):
        index(library)
    assert library.semantic.status()["coverage"]["all"]["indexed"] == 0


def test_config_change_during_search_discards_results_and_preserves_keyword_search(semantic, monkeypatch):
    library, _ = semantic
    sources(library)
    configure(library)
    index(library)
    original = library.semantic.provider.embed

    def clear(profile, texts):
        result = original(profile, texts)
        library.semantic.clear(library.semantic.status()["revision"])
        return result

    monkeypatch.setattr(library.semantic.provider, "embed", clear)
    with pytest.raises(SemanticNotReady):
        library.search("query", method="hybrid")
    assert library.search("custodian")["items"]


def test_budget_and_corruption_are_explicit_without_keyword_fallback(semantic, monkeypatch):
    library, _ = semantic
    sources(library)
    configure(library)
    monkeypatch.setattr("sibyl.research_library.semantic.service.MAX_PASSAGES", 2)
    result = index(library)
    assert result["added"] == 2 and result["status"]["coverage"]["all"]["missing"] == 1
    with pytest.raises(ValueError, match="budget"):
        index(library)
    with library.db() as db:
        db.execute("UPDATE semantic_vectors SET vector=?", (b"invalid",))
    with pytest.raises(ValueError, match="invalid"):
        library.search("query", method="semantic")
    assert library.search("custodian")["items"]


def test_clear_and_disable_invalidate_inflight_revision_and_keep_sources(semantic):
    library, _ = semantic
    sources(library)
    status = configure(library)
    index(library)
    cleared = library.semantic.clear(status["revision"])
    assert cleared["configured"] and cleared["coverage"]["all"]["indexed"] == 0
    with pytest.raises(SemanticNotReady):
        library.semantic.build(IndexBatch(revision=status["revision"]))
    disabled = library.semantic.clear(cleared["revision"], disable=True)
    assert not disabled["configured"] and library.search("custodian")["items"]


@pytest.mark.parametrize("status", [302, 400, 429, 500])
def test_provider_errors_do_not_echo_documents_or_credentials(semantic, status):
    library, server = semantic
    server.override = lambda request, body: httpx.Response(
        status, text="PRIVATE-PROVIDER-TEXT", headers={"Location": "https://example.com/PRIVATE"}
    )
    with pytest.raises(ValueError) as error:
        configure(library)
    assert "PRIVATE" not in str(error.value) and not library.semantic.status()["configured"]


def test_http_and_native_retrieval_preserve_exact_citations_and_scope(client, monkeypatch):
    library = client.app.state.services.library
    server = EmbeddingServer()
    library.semantic.provider = OllamaEmbeddings(server.client)
    docs = sources(library)
    response = client.post("/api/v1/library/semantic/settings", json={"model": MODEL, "revision": 0})
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    assert (
        client.post("/api/v1/library/semantic/index", json={"revision": response.json()["revision"]}).json()[
            "added"
        ]
        == 3
    )
    response = client.get(
        "/api/v1/library/search", params={"query": "safekeeping secrets", "method": "hybrid"}
    )
    assert response.status_code == 200 and response.json()["items"][0]["document_id"] == docs[0]["id"]
    reply = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "wiki",
            "message": "Explain this search",
            "context": {"library_query": "safekeeping secrets", "library_search_method": "semantic"},
        },
    )
    assert reply.status_code == 200, reply.text
    assert (
        reply.json()["tool"] == "search_research"
        and reply.json()["evidence"]["items"][0]["document_id"] == docs[0]["id"]
    )
    assert "source text" in reply.json()["answer"]
    # A selected source scope must not broaden to the indexed upload corpus.
    scoped = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "wiki",
            "message": "Show news for this search",
            "context": {
                "library_query": "safekeeping secrets",
                "library_search_method": "semantic",
                "library_source_type": "news",
            },
        },
    )
    assert scoped.status_code == 400, scoped.text
    network = client.app.state.services.agents.network
    result = client.portal.call(
        network.client.send_task,
        network.cards["reporter"].url,
        Task.create_tool_call("search_research", {"query": "safekeeping secrets", "method": "semantic"}),
    )
    result.raise_for_status()
    assert (
        result.get_last_item().parts[-1].as_tool_output().result["items"][0]["document_id"] == docs[0]["id"]
    )
    assert (
        client.post("/api/v1/library/semantic/settings", json={"model": MODEL, "revision": 0}).status_code
        == 400
    )
    assert client.post("/api/v1/library/semantic/index", json={"revision": True}).status_code == 422
    assert (
        client.post(
            "/api/v1/library/semantic/settings",
            json={"model": MODEL, "revision": 1, "endpoint": "https://PRIVATE.example"},
        ).status_code
        == 422
    )
    assert (
        client.get("/api/v1/library/search", params={"query": "test", "method": "guess"}).status_code == 400
    )


def test_no_model_semantic_setup_rejection_is_actionable(client):
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "wiki",
            "message": "Explain this topic",
            "context": {"library_query": "custody", "library_search_method": "semantic"},
        },
    )
    assert response.status_code == 400, response.text
    assert "Semantic search" in response.json()["detail"]
    assert "Keyword" in response.json()["detail"]
