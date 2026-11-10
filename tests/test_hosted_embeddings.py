"""Actual native ProtoLink/SDK requests with mock HTTP only; no paid provider or private user text."""

import json

import httpx
import pytest
from pydantic import ValidationError
from test_research_library import library as library

from sibyl.credentials.rotation import CONFIRMATION, RotateVault, VaultRotation
from sibyl.research_library.evaluations.contracts import EvaluationRun, EvaluationSuite
from sibyl.research_library.semantic.contracts import HostedSemanticSettings, IndexBatch, SemanticNotReady
from sibyl.research_library.semantic.hosted import PROVIDERS
from sibyl.research_library.service import ResearchLibrary
from sibyl.storage import Store

SECRET = "HOSTED-EMBEDDING-PRIVATE-ONLY"


class HostedServer:
    """Capture the real AsyncOpenAI request, returning independently controlled topic vectors."""

    def __init__(self):
        self.calls = []
        self.options = []
        self.override = None

    def respond(self, request):
        body = json.loads(request.content)
        self.calls.append((request, body))
        assert request.method == "POST" and request.url.path == "/v1/embeddings"
        assert request.url.host in {"api.openai.com", "api.mistral.ai"}
        assert not request.url.query and body["encoding_format"] == "float"
        assert request.headers["authorization"] == "Bearer " + SECRET
        assert "OTHER-PRIVATE-ORG" not in str(request.headers)
        assert "OTHER-PRIVATE-PROJECT" not in str(request.headers)
        if self.override:
            value = self.override(request, body)
            if value is not None:
                return value
        data = []
        for index, text in enumerate(body["input"]):
            vector = (
                [1.0, 0.0, 0.0]
                if "custod" in text.lower() or text == "safekeeping secrets"
                else [0.0, 1.0, 0.0]
            )
            data.append({"object": "embedding", "index": index, "embedding": vector})
        return httpx.Response(
            200,
            json={
                "object": "list",
                "model": body["model"],
                "data": list(reversed(data)),
                "usage": {"prompt_tokens": 4, "total_tokens": 4},
            },
        )


@pytest.fixture
def server(monkeypatch):
    server = HostedServer()
    original = httpx.AsyncClient

    class OfflineClient(original):
        def __init__(self, **kwargs):
            server.options.append(kwargs.copy())
            super().__init__(transport=httpx.MockTransport(server.respond), **kwargs)

    monkeypatch.setattr("sibyl.research_library.semantic.hosted.httpx.AsyncClient", OfflineClient)
    monkeypatch.setenv("OPENAI_ORG_ID", "OTHER-PRIVATE-ORG")
    monkeypatch.setenv("OPENAI_PROJECT_ID", "OTHER-PRIVATE-PROJECT")
    return server


@pytest.fixture
def hosted(library, server):
    library.store = Store(library.path.parent)
    return library, server


def setup(owner, provider="openai", **overrides):
    values = dict(
        revision=owner.semantic.status()["revision"],
        provider=provider,
        model=PROVIDERS.get(provider, PROVIDERS["openai"])["models"][0],
        api_key=SECRET,
        remote_consent=True,
    )
    return owner.semantic.configure_hosted(HostedSemanticSettings(**(values | overrides)))


def sources(owner):
    return [
        owner.import_document("custody.txt", b"A custodian safeguards private keys."),
        owner.import_document("lending.txt", b"Collateral backs the lending agreement."),
    ]


def build(owner):
    return owner.semantic.build(IndexBatch(revision=owner.semantic.status()["revision"], kind="document"))


@pytest.mark.parametrize("provider", ["openai", "mistral"])
def test_real_sdk_and_native_protolink_preserve_ordered_cited_hosted_vectors(hosted, provider, monkeypatch):
    owner, remote = hosted
    docs = sources(owner)
    calls = []
    from protolink.rag import OpenAIEmbedder

    original = OpenAIEmbedder.embed_documents

    async def native(self, texts):
        calls.append(list(texts))
        return await original(self, texts)

    monkeypatch.setattr(OpenAIEmbedder, "embed_documents", native)
    state = setup(owner, provider)
    assert len(remote.calls) == 1 and remote.calls[0][1]["input"] == [
        "Sibyl embedding model compatibility check."
    ]
    assert state["profile"]["provider"] == provider and state["has_api_key"]
    assert "credential_ref" not in state["profile"] and "model_digest" not in state["profile"]
    assert remote.calls[0][0].url.host == ("api.openai.com" if provider == "openai" else "api.mistral.ai")
    assert remote.options[0]["follow_redirects"] is False and remote.options[0]["trust_env"] is False
    assert build(owner)["added"] == 2
    result = owner.search("safekeeping secrets", method="semantic")
    assert result["items"][0]["document_id"] == docs[0]["id"]
    assert result["semantic"]["provider"] == provider and result["semantic"]["model_digest"] is None
    assert "cannot" in state["note"] and calls
    assert owner.search("custodian", method="hybrid")["items"][0]["document_id"] == docs[0]["id"]
    assert SECRET not in json.dumps([state, result])


def test_keys_are_separate_encrypted_and_survive_native_vault_rotation(hosted):
    owner, remote = hosted
    owner.store.save_model_profile("openai", {"api_key": "CHAT-ONLY-PRIVATE", "model": "chat-model"})
    sources(owner)
    setup(owner)
    assert SECRET not in owner.path.read_bytes().decode(errors="ignore")
    assert SECRET not in owner.store.path.read_bytes().decode(errors="ignore")
    with owner.db() as db:
        profile = json.loads(db.execute("SELECT payload FROM semantic_settings").fetchone()[0])
    key_ref = profile["credential_ref"]
    assert owner.store.data_profile(key_ref)["api_key"] == SECRET
    rotation = VaultRotation(owner.store)
    rotation.rotate(RotateVault(key_id=rotation.state()["key_id"], confirmation=CONFIRMATION))
    assert owner.store.data_profile(key_ref)["api_key"] == SECRET
    assert owner.store.model_profiles()[1]["openai"]["api_key"] == "CHAT-ONLY-PRIVATE"
    assert build(owner)["added"] == 2
    assert len(remote.calls) == 2


def test_passive_startup_catalog_and_keyword_search_never_send_text(hosted):
    owner, remote = hosted
    sources(owner)
    assert not owner.semantic.status()["configured"] and remote.calls == []
    assert {r["id"] for r in owner.semantic.status()["hosted"]["items"]} == {"openai", "mistral"}
    setup(owner)
    build(owner)
    before = len(remote.calls)
    reopened = ResearchLibrary(owner.path.parent, owner.news, store=owner.store)
    assert reopened.semantic.status()["profile"]["provider"] == "openai"
    assert reopened.search("custodian")["items"] and len(remote.calls) == before


@pytest.mark.parametrize(
    "values",
    [
        {"remote_consent": False},
        {"remote_consent": "true"},
        {"provider": "custom"},
        {"model": "https://attacker.invalid/"},
        {"model": "chat-model"},
        {"api_key": ""},
        {"api_key": "PRIVATE\nVALUE"},
        {"endpoint": "http://attacker.invalid"},
    ],
)
def test_invalid_setup_or_missing_permission_cannot_send_any_text(hosted, values):
    owner, remote = hosted
    with pytest.raises((ValidationError, SemanticNotReady)):
        setup(owner, **values)
    assert remote.calls == [] and not owner.semantic.status()["configured"]


def test_missing_embedding_key_never_borrows_chat_or_environment_credentials(hosted, monkeypatch):
    owner, remote = hosted
    owner.store.save_model_profile("openai", {"api_key": "CHAT-ONLY-PRIVATE", "model": "chat"})
    monkeypatch.setenv("OPENAI_API_KEY", "ENV-ONLY-PRIVATE")
    with pytest.raises(SemanticNotReady, match="separate"):
        setup(owner, api_key=None)
    assert remote.calls == []


def test_missing_optional_sdk_is_actionable_before_any_request(hosted, monkeypatch):
    import builtins

    owner, remote = hosted
    original = builtins.__import__

    def missing(name, *args, **kwargs):
        if name == "openai":
            raise ImportError("offline optional dependency absent")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing)
    with pytest.raises(SemanticNotReady, match="dependency"):
        setup(owner)
    assert remote.calls == []


@pytest.mark.parametrize(
    "failure",
    [
        "duplicate",
        "model",
        "missing",
        "bool",
        "nan",
        "zero",
        "dimension",
        "large",
        "string",
        "boolean_index",
        "oversized",
    ],
)
def test_invalid_provider_identity_or_vectors_never_publish_a_partial_batch(hosted, failure):
    owner, remote = hosted
    sources(owner)
    setup(owner)

    def response(request, body):
        data = [{"index": i, "embedding": [1.0, 0.0, 0.0]} for i in range(len(body["input"]))]
        model = body["model"]
        if failure == "duplicate":
            data[-1]["index"] = 0
        if failure == "model":
            model = "another-model"
        if failure == "missing":
            data.pop()
        if failure == "bool":
            data[0]["embedding"] = [True, 0.0, 0.0]
        if failure == "nan":
            return httpx.Response(
                200,
                content=json.dumps(
                    {"data": [{"index": 0, "embedding": [float("nan"), 0, 0]}], "model": model}
                ),
            )
        if failure == "zero":
            data[0]["embedding"] = [0.0, 0.0, 0.0]
        if failure == "dimension":
            for row in data:
                row["embedding"] = [1.0, 0.0, 0.0, 0.0]
        if failure == "large":
            data[0]["embedding"] = [1.0] * 4097
        if failure == "string":
            data[0]["embedding"] = ["1.0", 0.0, 0.0]
        if failure == "boolean_index":
            data[0]["index"] = False
        if failure == "oversized":
            return httpx.Response(200, content=b" " * (8 * 1024 * 1024 + 1))
        return httpx.Response(
            200,
            json={
                "object": "list",
                "data": data,
                "model": model,
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            },
        )

    remote.override = response
    with pytest.raises(ValueError):
        build(owner)
    assert owner.semantic.status()["coverage"]["all"]["indexed"] == 0
    assert owner.search("custodian")["items"]


@pytest.mark.parametrize("failure", ["timeout", "unauthorized", "rate_limit", "redirect"])
def test_errors_are_safe_single_attempt_and_do_not_enable_a_failed_provider(hosted, failure):
    owner, remote = hosted

    def response(request, body):
        if failure == "timeout":
            raise httpx.ReadTimeout(SECRET + " PRIVATE INPUT", request=request)
        if failure == "redirect":
            return httpx.Response(307, headers={"location": "https://attacker.invalid"})
        return httpx.Response(
            401 if failure == "unauthorized" else 429,
            json={"error": {"message": SECRET + " PRIVATE INPUT", "type": "request_error"}},
        )

    remote.override = response
    with pytest.raises(ValueError) as error:
        setup(owner)
    assert SECRET not in str(error.value) and "PRIVATE INPUT" not in str(error.value)
    assert len(remote.calls) == 1 and not owner.semantic.status()["configured"]


def test_model_replacement_reuses_only_same_provider_key_and_clears_vectors(hosted):
    owner, remote = hosted
    sources(owner)
    setup(owner)
    build(owner)
    before = owner.semantic.status()
    with owner.db() as db:
        old_ref = owner.semantic.config(db)[1]["credential_ref"]
    second = setup(owner, model="text-embedding-3-large", api_key=None)
    assert second["revision"] == before["revision"] + 1 and second["coverage"]["all"]["indexed"] == 0
    assert owner.store.data_profile(old_ref) == {}
    with pytest.raises(SemanticNotReady):
        setup(owner, "mistral", api_key=None)
    assert remote.calls[-1][1]["model"] == "text-embedding-3-large"


def test_disable_fences_inflight_batch_and_removes_only_its_saved_key(hosted):
    owner, remote = hosted
    sources(owner)
    setup(owner)
    with owner.db() as db:
        old = owner.semantic.config(db)[1]

    def disable(request, body):
        owner.semantic.clear(owner.semantic.status()["revision"], disable=True)
        return None

    remote.override = disable
    with pytest.raises(SemanticNotReady, match="changed"):
        build(owner)
    assert (
        not owner.semantic.status()["configured"]
        and owner.semantic.status()["coverage"]["all"]["indexed"] == 0
    )
    assert owner.store.data_profile(old["credential_ref"]) == {}


def test_losing_setup_revision_cleans_staged_key_without_erasing_the_winning_model(hosted):
    owner, remote = hosted
    setup(owner)
    before = owner.semantic.status()

    def clear(request, body):
        owner.semantic.clear(before["revision"])
        return None

    remote.override = clear
    with pytest.raises(SemanticNotReady, match="changed"):
        setup(owner, model="text-embedding-3-large")
    assert owner.semantic.status()["profile"]["model"] == before["profile"]["model"]
    with owner.store.db() as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM workspace_settings WHERE key LIKE 'data:research-embedding:%'"
            ).fetchone()[0]
            == 1
        )


def test_http_setup_masks_credentials_and_honors_permission(client, server):
    owner = client.app.state.services.library
    endpoint = "/api/v1/library/semantic/hosted-settings"
    body = dict(
        revision=0, provider="openai", model="text-embedding-3-small", api_key=SECRET, remote_consent=True
    )
    response = client.post(endpoint, json=body)
    assert response.status_code == 200, response.text
    assert SECRET not in response.text and "credential_ref" not in response.text
    rejected = client.post(endpoint, json=body | {"api_key": SECRET + "\nPRIVATE", "remote_consent": False})
    assert rejected.status_code == 422 and SECRET not in rejected.text
    assert len(server.calls) == 1
    assert owner.semantic.status()["has_api_key"]


def test_native_research_tool_uses_hosted_search_without_exposing_key(client, server, monkeypatch):
    from protolink import create_llm

    owner = client.app.state.services.library
    docs = sources(owner)
    setup(owner)
    build(owner)
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    monkeypatch.setattr(
        "sibyl.agents.utils.registry.create_llm",
        lambda *a, **kw: create_llm(
            "mock",
            sequential_responses=[
                {
                    "type": "tool_call",
                    "tool": "search_research",
                    "args": {"query": "safekeeping secrets", "method": "semantic"},
                },
                "The cited custodian passage explains the safekeeping arrangement.",
            ],
        ),
    )
    response = client.post(
        "/api/v1/agents/ask", json={"module": "wiki", "message": "Find safekeeping research."}
    )
    assert response.status_code == 200, response.text
    assert SECRET not in response.text
    evidence = response.json()["evidence"]
    assert docs[0]["id"] in json.dumps(evidence) and "openai" in json.dumps(evidence)


def test_retrieval_evaluation_is_provider_pinned_and_revocation_prevents_queued_queries(hosted):
    owner, remote = hosted
    docs = sources(owner)
    setup(owner)
    build(owner)
    passage = owner.document(docs[0]["id"])["passages"][0]["id"]
    suite = owner.evaluations.save(
        EvaluationSuite(
            title="Controlled hosted retrieval",
            kind="document",
            cases=[{"query": "safekeeping secrets", "expected": [passage]}],
        )
    )
    run = owner.evaluations.start(suite["id"], EvaluationRun(methods=["semantic"], k=1))
    owner.evaluations.tick()
    saved = owner.evaluations.get(run["id"])
    assert saved["state"] == "completed" and saved["snapshot"]["provider"] == "openai"
    assert saved["summary"]["semantic"]["hit"] == 1 and SECRET not in json.dumps(saved)
    second = owner.evaluations.start(suite["id"], EvaluationRun(methods=["semantic"], k=1))
    owner.semantic.clear(owner.semantic.status()["revision"], disable=True)
    before = len(remote.calls)
    owner.evaluations.tick()
    assert owner.evaluations.get(second["id"])["state"] == "failed" and len(remote.calls) == before


def test_switching_to_local_deletes_hosted_key_and_never_sends_it_to_ollama(hosted):
    from test_semantic_research import MODEL, EmbeddingServer

    from sibyl.research_library.semantic.contracts import SemanticSettings
    from sibyl.research_library.semantic.provider import OllamaEmbeddings

    owner, remote = hosted
    sources(owner)
    setup(owner)
    with owner.db() as db:
        old_ref = owner.semantic.config(db)[1]["credential_ref"]
    local = EmbeddingServer()
    owner.semantic.provider = OllamaEmbeddings(local.client)
    result = owner.semantic.configure(
        SemanticSettings(model=MODEL, revision=owner.semantic.status()["revision"])
    )
    assert result["profile"]["model"] == MODEL and not result["has_api_key"]
    assert owner.store.data_profile(old_ref) == {}
    assert build(owner)["added"] == 2 and len(remote.calls) == 1
    assert local.calls and SECRET not in json.dumps(local.calls)
