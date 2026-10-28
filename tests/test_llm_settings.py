"""Provider coverage, write-only credentials, persistence, and actual agent wiring."""

import inspect
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from protolink import create_llm
from protolink.llms.factory import LLMFactory, LLMProvider

from sibyl.agents.providers import PROVIDERS
from sibyl.api.app import create_app
from sibyl.config import Settings
from sibyl.services.llm_settings import ModelSettings, ModelSettingsRequest


@pytest.fixture(autouse=True)
def isolated_keys(monkeypatch):
    """Never read the developer's provider tokens or selected environment model."""
    for provider in PROVIDERS.values():
        for name in provider.key_env:
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SIBYL_LLM_PROVIDER", "none")


def save(client, provider="openai", **changes):
    return client.post(
        "/api/v1/settings/llm",
        json={
            "provider": provider,
            "model": "custom-model",
            **changes,
        },
    )


def test_catalog_covers_every_installed_protolink_provider(client):
    result = client.get("/api/v1/settings/llm")
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    catalog = result.json()
    assert {p["id"] for p in catalog["providers"]} - {"none"} == {p.value for p in LLMProvider}
    assert catalog["active_provider"] == "none"
    assert {p["kind"] for p in catalog["providers"]} == {"tools", "local", "api"}


def test_saved_keys_are_encrypted_write_only_and_survive_restart(client, settings):
    response = save(client, api_key="provider-secret-sentinel")
    assert response.status_code == 200, response.text
    profile = response.json()["profiles"]["openai"]
    assert profile["has_api_key"] and profile["key_source"] == "saved"
    assert "sentinel" not in response.text
    assert "sentinel" not in client.get("/api/v1/settings/llm").text
    assert "sentinel" not in client.get("/api/v1/system").text
    assert b"provider-secret-sentinel" not in client.app.state.services.store.path.read_bytes()
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get("/api/v1/system").json()["llm_provider"] == "openai"
        assert restarted.app.state.services.agents.models.resolve()["api_key"] == "provider-secret-sentinel"
        assert "sentinel" not in restarted.get("/api/v1/agents").text


def test_provider_switch_and_model_edits_preserve_the_correct_key(client):
    assert save(client, api_key="openai-secret").status_code == 200
    assert save(client, "anthropic", model="claude-custom", api_key="anthropic-secret").status_code == 200
    assert save(client, model="different-custom-model").status_code == 200
    resolved = client.app.state.services.agents.models.resolve()
    assert resolved == {
        "provider": "openai",
        "model": "different-custom-model",
        "base_url": "",
        "api_key": "openai-secret",
    }
    assert save(client, api_key="replacement-secret").status_code == 200
    assert client.app.state.services.agents.models.resolve()["api_key"] == "replacement-secret"
    assert save(client, "anthropic", model="claude-custom").status_code == 200
    assert client.app.state.services.agents.models.resolve()["api_key"] == "anthropic-secret"


def test_save_does_not_contact_a_provider_and_agent_uses_saved_credentials(client, monkeypatch):
    # This tests native MockLLM wiring, independently of optional SDK installation.
    monkeypatch.setattr("sibyl.agents.providers.find_spec", lambda _: object())
    calls = []

    def factory(provider, **kwargs):
        calls.append((provider, kwargs))
        return create_llm("mock", default_response="A controlled model response.")

    monkeypatch.setattr("sibyl.agents.registry.create_llm", factory)
    assert save(client, api_key="only-adapter-sees-this").status_code == 200
    assert calls == []
    response = client.post(
        "/api/v1/agents/ask", json={"module": "wiki", "message": "What is diversification?"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["provider"] == "openai" and response.json()["mode"] == "llm"
    assert calls == [("openai", {"model": "custom-model", "api_key": "only-adapter-sees-this"})]
    assert "only-adapter-sees-this" not in response.text
    assert "only-adapter-sees-this" not in client.get("/api/v1/runs").text


def test_inflight_agent_keeps_its_provider_snapshot_when_settings_change(client, monkeypatch):
    # The provider factory below is scripted; CI need not install hosted SDKs.
    monkeypatch.setattr("sibyl.agents.providers.find_spec", lambda _: object())
    save(client, api_key="first-key")
    calls = []

    def factory(provider, **kwargs):
        calls.append((provider, kwargs))
        client.app.state.services.agents.models.save(
            ModelSettingsRequest(provider="anthropic", model="next-model", api_key="second-key")
        )
        return create_llm("mock", default_response="Snapshot preserved.")

    monkeypatch.setattr("sibyl.agents.registry.create_llm", factory)
    response = client.post("/api/v1/agents/ask", json={"module": "wiki", "message": "What is RSI?"})
    assert response.status_code == 200, response.text
    assert response.json()["provider"] == "openai"
    assert calls == [("openai", {"model": "custom-model", "api_key": "first-key"})]
    assert client.get("/api/v1/system").json()["llm_provider"] == "anthropic"


def test_removing_active_required_key_falls_back_to_tools(client):
    save(client, api_key="removed-key")
    result = client.delete("/api/v1/settings/llm/openai/key")
    assert result.status_code == 200
    assert result.json()["active_provider"] == "none"
    assert not result.json()["profiles"]["openai"]["has_api_key"]
    assert client.app.state.services.agents.models.resolve()["api_key"] == ""
    assert client.get("/api/v1/agents").json()[0]["mode"] == "tools"


def test_environment_fallback_and_saved_key_removal_do_not_mutate_environment(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "environment-only")
    result = save(client)
    assert result.status_code == 200
    assert result.json()["profiles"]["openai"]["key_source"] == "environment"
    save(client, api_key="workspace-key")
    result = client.delete("/api/v1/settings/llm/openai/key").json()
    assert result["active_provider"] == "openai"
    assert result["profiles"]["openai"]["key_source"] == "environment"
    assert client.app.state.services.agents.models.resolve()["api_key"] == "environment-only"


def test_model_save_does_not_change_unrelated_settings(client):
    before = client.get("/api/v1/system").json()
    assert save(client, "ollama", model="custom:tag", base_url="http://localhost:11435").status_code == 200
    after = client.get("/api/v1/system").json()
    assert after == {**before, "llm_provider": "ollama", "llm_model": "custom:tag"}
    assert save(client, "none", model="").status_code == 200
    assert client.get("/api/v1/settings/llm").json()["profiles"]["ollama"]["saved"]


@pytest.mark.parametrize("provider", [p for p in PROVIDERS if p != "none"])
def test_configuration_matches_actual_protolink_constructor_signature(client, tmp_path, provider):
    definition = PROVIDERS[provider]
    model = definition.models[0] if definition.models else "custom-model"
    if provider == "llama.cpp-local":
        path = tmp_path / "example.gguf"
        path.write_bytes(b"fixture, never loaded")
        model = str(path)
    payload = {"model": model, "base_url": definition.base_url}
    if provider not in {"mock", "llama.cpp-local"}:
        payload["api_key"] = "constructor-test-key"
    response = save(client, provider, **payload)
    assert response.status_code == 200, response.text
    resolved = client.app.state.services.agents.models.resolve()
    selected, kwargs = ModelSettings.constructor(resolved)
    assert selected == provider
    if provider == "ollama":
        assert kwargs["tool_calling"] == "auto"
    inspect.signature(LLMFactory._resolve_client(selected)).bind(**kwargs)
    if provider in {"ollama", "llama.cpp-server"}:
        assert kwargs["headers"] == {"Authorization": "Bearer constructor-test-key"}
    elif provider not in {"mock", "llama.cpp-local"}:
        assert kwargs["api_key"] == "constructor-test-key"


@pytest.mark.parametrize(
    "body",
    [
        {"provider": "unknown", "api_key": "secret-sentinel"},
        {"provider": "ollama", "model": "", "api_key": "secret-sentinel"},
        {"provider": "ollama", "model": "safe", "api_key": "secret-sentinel\r\nHeader: x"},
        {"provider": "ollama", "model": "safe", "base_url": "file:///private/tmp/secret-sentinel"},
        {"provider": "ollama", "model": "safe", "base_url": "https://secret-sentinel@host"},
        {"provider": "openai", "model": "safe", "base_url": "https://host?key=secret-sentinel"},
        {"provider": "none", "api_key": "secret-sentinel"},
    ],
)
def test_invalid_model_settings_never_reflect_secret_input(client, body):
    response = client.post("/api/v1/settings/llm", json=body)
    assert response.status_code == 422, response.text
    assert "secret-sentinel" not in response.text
    assert client.get("/api/v1/system").json()["llm_provider"] == "none"


def test_required_key_and_missing_gguf_are_rejected_without_changing_active(client):
    assert save(client).status_code == 400
    assert save(client, "llama.cpp-local", model="/missing/example.gguf").status_code == 400
    assert client.get("/api/v1/system").json()["llm_provider"] == "none"


def test_profile_and_activation_are_atomic_on_write_failure(store, settings):
    with store.db() as db:
        db.execute(
            "CREATE TRIGGER reject_selection BEFORE INSERT ON workspace_settings "
            "BEGIN SELECT RAISE(ABORT, 'test failure'); END;"
        )
    service = ModelSettings(settings, store)
    with pytest.raises(sqlite3.IntegrityError):
        service.save(ModelSettingsRequest(provider="openai", model="custom", api_key="atomic-key"))
    assert store.model_profiles() == (None, {})


def test_environment_defaults_use_the_right_local_endpoint(settings, store):
    for provider in ("vllm", "lmstudio", "llama.cpp-server"):
        config = Settings(
            data_dir=settings.data_dir, llm_provider=provider, llm_model="local", _env_file=None
        )
        service = ModelSettings(config, store)
        assert service.resolve()["base_url"] == PROVIDERS[provider].base_url


def test_model_settings_require_workspace_access(tmp_path):
    config = Settings(data_dir=tmp_path, api_token="test-access-token", _env_file=None)
    with TestClient(create_app(config)) as client:
        assert client.get("/api/v1/settings/llm").status_code == 401
        assert save(client, api_key="should-not-save").status_code == 401
        assert client.delete("/api/v1/settings/llm/openai/key").status_code == 401
        result = client.get("/api/v1/settings/llm", headers={"Authorization": "Bearer test-access-token"})
        assert result.status_code == 200
        assert "should-not-save" not in json.dumps(result.json())


def test_malformed_url_does_not_echo_credentials(client):
    response = save(client, "ollama", model="local", base_url="https://secret-sentinel＠host")
    assert response.status_code == 422
    assert "secret-sentinel" not in response.text


def test_ollama_context_is_persisted_and_shared_with_native_budget(client, settings, monkeypatch):
    state = save(client, "ollama", model="local-model", context_window=24576).json()
    assert state["profiles"]["ollama"]["context_window"] == 24576
    created, arguments = [], []

    def factory(provider, **kwargs):
        arguments.append((provider, kwargs))
        model = create_llm("mock", default_response="A real native runtime with scripted inference.")
        created.append(model)
        return model

    monkeypatch.setattr("sibyl.agents.registry.create_llm", factory)
    response = client.post("/api/v1/agents/ask", json={"module": "wiki", "message": "Hello"})
    assert response.status_code == 200
    assert arguments[0][0] == "ollama"
    assert arguments[0][1]["tool_calling"] == "auto"
    assert arguments[0][1]["model_params"] == {"num_ctx": 24576, "num_predict": 2048}
    assert created[0].metrics_profile.context_window == 24576
    # Older clients omitting the field preserve a deliberate saved value.
    assert (
        save(client, "ollama", model="renamed-model").json()["profiles"]["ollama"]["context_window"] == 24576
    )
    with TestClient(create_app(settings)) as restarted:
        assert restarted.app.state.services.agents.models.resolve()["context_window"] == 24576


def test_small_ollama_context_rejects_coordinator_before_model_call(client, monkeypatch):
    save(client, "ollama", model="small-window", context_window=4096)

    def factory(*_a, **_kw):
        return create_llm(
            "mock", response_callback=lambda *_: pytest.fail("Oversized input reached the model")
        )

    monkeypatch.setattr("sibyl.agents.registry.create_llm", factory)
    response = client.post("/api/v1/sibyl/ask", json={"message": "How do I see account history?"})
    assert response.status_code == 409, response.text
    assert "context window" in response.json()["detail"]
    assert (
        client.app.state.services.agents.network.conversations.get(
            client.app.state.services.agents.network.conversations.list()[0]["id"]
        )["turns"]
        == []
    )


@pytest.mark.parametrize("value", [True, 4095, 131073, "32768", 3.5])
def test_ollama_context_rejects_invalid_limits(client, value):
    assert save(client, "ollama", context_window=value).status_code == 422


@pytest.mark.parametrize("value", [32768, None])
def test_other_providers_do_not_accept_ollama_context_option(client, value):
    assert save(client, "mock", context_window=value).status_code == 422
