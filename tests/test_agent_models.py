"""Per-agent inference, encrypted profiles and native delegation with no provider network I/O."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from agent_helpers import delegate
from fastapi.testclient import TestClient
from protolink import Task, create_llm, current_request_context

from sibyl.agents.model_selection import AGENT_NAMES, AgentModelRequest, ModelConflict
from sibyl.agents.providers import PROVIDERS
from sibyl.api.app import create_app
from sibyl.services.llm_settings import ModelSettingsRequest


@pytest.fixture(autouse=True)
def isolated_keys(monkeypatch):
    for provider in PROVIDERS.values():
        for name in provider.key_env:
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SIBYL_LLM_PROVIDER", "none")


def profile(client, provider="ollama", **changes):
    return client.post(
        "/api/v1/settings/llm",
        json={"provider": provider, "model": "profile-model", "activate": False, **changes},
    )


def assign(client, agent="reporter", provider="ollama", model="reporter-model", **changes):
    state = client.get("/api/v1/settings/llm").json()
    return client.post(
        f"/api/v1/settings/llm/agents/{agent}",
        json={"revision": state["agent_revision"], "provider": provider, "model": model, **changes},
    )


def agent_row(state, agent="reporter"):
    return next(row for row in state["agents"] if row["id"] == agent)


def test_profile_only_save_keeps_default_and_does_not_invoke_provider(client, monkeypatch):
    monkeypatch.setattr("sibyl.agents.registry.create_llm", lambda *a, **kw: pytest.fail("Provider called"))
    state = profile(client, "openai", api_key="PROFILE-SECRET-SENTINEL").json()
    assert state["active_provider"] == "none" and state["profiles"]["openai"]["saved"]
    assert all(row["inherited"] and row["provider"] == "none" for row in state["agents"])
    assert "SENTINEL" not in json.dumps(state)
    assert b"PROFILE-SECRET-SENTINEL" not in client.app.state.services.store.path.read_bytes()


def test_override_reuses_correct_encrypted_profile_and_does_not_activate_default(client):
    profile(client, base_url="http://localhost:11500", api_key="OLLAMA-PRIVATE")
    state = assign(client).json()
    assert state["active_provider"] == "none" and state["agent_revision"] == 1
    reporter = agent_row(state)
    assert not reporter["inherited"] and reporter["ready"]
    assert reporter["selection"] == {"provider": "ollama", "model": "reporter-model"}
    assert client.app.state.services.agents.models.resolve("reporter") == {
        "provider": "ollama",
        "model": "reporter-model",
        "base_url": "http://localhost:11500",
        "api_key": "OLLAMA-PRIVATE",
        "context_window": 32768,
    }
    assert all(row["provider"] == "none" for row in state["agents"] if row["id"] != "reporter")
    assert "OLLAMA-PRIVATE" not in json.dumps(state)


def test_default_changes_preserve_fixed_override_and_reset_follows_current_default(client):
    profile(client)
    assign(client)
    changed = profile(client, "mock", model="new-default", activate=True).json()
    assert agent_row(changed)["model"] == "reporter-model"
    assert agent_row(changed, "analyst")["provider"] == "mock"
    reset = assign(client, provider=None, model="").json()
    assert agent_row(reset)["inherited"] and agent_row(reset)["model"] == "new-default"
    changed = profile(client, "mock", model="later-default", activate=True).json()
    assert agent_row(changed)["model"] == "later-default"


def test_same_provider_can_use_different_models_without_duplicating_keys(client):
    profile(client, "openai", model="default-model", api_key="one-shared-key", activate=True)
    assert assign(client, provider="openai", model="reporter-specific").status_code == 200
    profile(client, "openai", model="new-profile-default", activate=True)
    models = client.app.state.services.agents.models
    assert models.resolve("reporter")["model"] == "reporter-specific"
    assert models.resolve("analyst")["model"] == "new-profile-default"
    assert models.resolve("reporter")["api_key"] == models.resolve("analyst")["api_key"] == "one-shared-key"
    with models.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM model_profiles WHERE provider='openai'").fetchone()[0] == 1


def test_assignment_persists_and_settings_changes_do_not_respawn_agents(client, settings):
    network = client.app.state.services.agents.network
    before = {key: (id(agent), agent.card.url) for key, agent in network.agents.items()}
    profile(client)
    assign(client)
    assert before == {key: (id(agent), agent.card.url) for key, agent in network.agents.items()}
    with TestClient(create_app(settings)) as restarted:
        state = restarted.get("/api/v1/settings/llm").json()
        assert agent_row(state)["model"] == "reporter-model" and state["agent_revision"] == 1
        assert state["active_provider"] == "none"


def test_stale_edit_cannot_overwrite_another_agent_assignment(client):
    profile(client)
    assert assign(client).status_code == 200
    stale = assign(client, "analyst", revision=0)
    assert stale.status_code == 409 and stale.headers["cache-control"] == "no-store"
    state = client.get("/api/v1/settings/llm").json()
    assert agent_row(state, "analyst")["inherited"] and not agent_row(state)["inherited"]


def test_concurrent_editors_claim_one_revision_only(client):
    owner = client.app.state.services.agents

    def write(agent):
        try:
            return owner.models.assign(agent, AgentModelRequest(revision=0, provider="mock"))
        except ModelConflict:
            return None

    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(write, ["reporter", "analyst", "broker", "sibyl"]))
    assert sum(item is not None for item in results) == 1
    assert owner.models.public()["agent_revision"] == 1
    assert sum(not row["inherited"] for row in owner.models.public()["agents"]) == 1


def test_assignment_write_failure_rolls_back_selection_and_revision(client):
    store = client.app.state.services.store
    with store.db() as db:
        db.execute(
            "CREATE TRIGGER reject_agent_model BEFORE INSERT ON workspace_settings WHEN NEW.key='data:agent-models' BEGIN SELECT RAISE(ABORT,'fixture failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        client.app.state.services.agents.models.assign(
            "reporter", AgentModelRequest(revision=0, provider="mock")
        )
    assert client.get("/api/v1/settings/llm").json()["agent_revision"] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"revision": True},
        {"revision": "0"},
        {"revision": -1},
        {"provider": "unknown"},
        {"model": "bad\nmodel"},
        {"provider": "none", "model": "not-empty"},
        {"provider": None, "model": "not-empty"},
        {"model": ""},
        {"api_key": "BODY-SECRET-SENTINEL"},
        {"base_url": "https://BODY-SECRET-SENTINEL.invalid"},
    ],
)
def test_invalid_assignment_never_reflects_credentials(client, changes):
    body = {"revision": 0, "provider": "ollama", "model": "custom", **changes}
    result = client.post("/api/v1/settings/llm/agents/reporter", json=body)
    assert result.status_code == 422 and "BODY-SECRET-SENTINEL" not in result.text
    assert client.get("/api/v1/settings/llm").json()["agent_revision"] == 0


def test_unknown_agents_and_missing_profiles_are_rejected_without_changes(client):
    assert assign(client, agent="invented").status_code == 422
    assert assign(client).status_code == 400
    profile(client, "openai", api_key="removed-key")
    client.delete("/api/v1/settings/llm/openai/key")
    assert assign(client, provider="openai").status_code == 400
    assert client.get("/api/v1/settings/llm").json()["agent_revision"] == 0


def test_sibyl_override_enables_coordinator_and_messaging_without_global_model(client):
    state = assign(client, "sibyl", "mock", "coordinator-model").json()
    assert state["active_provider"] == "none"
    status = client.get("/api/v1/sibyl").json()
    assert status["ready"] and status["provider"] == "mock" and status["model"] == "coordinator-model"
    assert client.get("/api/v1/settings/messaging").json()["telegram"]["llm_ready"]
    assert client.post("/api/v1/sibyl/ask", json={"message": "Hello"}).json()["model"] == "coordinator-model"
    assert assign(client, "sibyl", "none", "").status_code == 200
    assert not client.get("/api/v1/sibyl").json()["ready"]
    assert client.post("/api/v1/sibyl/ask", json={"message": "Hello"}).status_code == 409


def test_direct_module_request_and_native_client_use_same_override(client, monkeypatch):
    owner = client.app.state.services.agents
    profile(client, api_key="NATIVE-SECRET", base_url="http://localhost:11500")
    assign(client)
    calls = []

    def factory(provider, **kwargs):
        calls.append((current_request_context().get("agent_id", ""), provider, kwargs))
        return create_llm("mock", default_response="Controlled answer")

    monkeypatch.setattr("sibyl.agents.registry.create_llm", factory)
    first = client.post(
        "/api/v1/agents/ask", json={"module": "reporter", "message": "Explain the news"}
    ).json()
    assert first["provider"] == "ollama" and first["model"] == "reporter-model"
    assert first["model_selection"] == "override" and first["mode"] == "llm"
    network = owner.network
    second = client.portal.call(
        network.client.send_task, network.cards["reporter"].url, Task.create_infer("Hello")
    )
    second.raise_for_status()
    assert len(calls) == 2 and all(row[:2] == ("reporter", "ollama") for row in calls)
    assert calls[0][2]["headers"] == {"Authorization": "Bearer NATIVE-SECRET"}
    assert "NATIVE-SECRET" not in json.dumps(first)
    assert "NATIVE-SECRET" not in json.dumps(owner.store.runs())


def test_tool_only_override_keeps_direct_native_tools_available(client, monkeypatch):
    profile(client, "mock", activate=True)
    assign(client, provider="none", model="")
    monkeypatch.setattr("sibyl.agents.registry.create_llm", lambda *a, **kw: pytest.fail("Model called"))
    result = client.post(
        "/api/v1/agents/ask", json={"module": "reporter", "message": "News", "context": {"news_mode": "demo"}}
    )
    assert result.status_code == 200 and result.json()["mode"] == "tools"
    assert result.json()["provider"] == "none"
    network = client.app.state.services.agents.network
    direct = client.portal.call(
        network.client.send_task, network.cards["reporter"].url, Task.create_tool_call("news_sources", {})
    )
    direct.raise_for_status()


def test_removed_override_key_is_unavailable_and_does_not_fall_back_to_default(client, monkeypatch):
    profile(client, "mock", activate=True)
    profile(client, "openai", api_key="REMOVE-SENTINEL")
    assign(client, provider="openai")
    state = client.delete("/api/v1/settings/llm/openai/key").json()
    assert state["active_provider"] == "mock" and not agent_row(state)["ready"]
    assert agent_row(state)["provider"] == "openai" and "API key" in agent_row(state)["reason"]
    monkeypatch.setattr(
        "sibyl.agents.registry.create_llm", lambda *a, **kw: pytest.fail("Silently fell back")
    )
    response = client.post("/api/v1/agents/ask", json={"module": "reporter", "message": "Hello"})
    assert response.status_code == 502 and "REMOVE-SENTINEL" not in response.text
    catalog = client.get("/api/v1/agents").json()
    assert not next(row for row in catalog if row["id"] == "reporter")["model_ready"]


def test_native_delegation_uses_each_specialist_frozen_provider_model_and_key(client, monkeypatch):
    owner = client.app.state.services.agents
    profile(client, "mock", model="lead", activate=True)
    profile(client, model="profile", base_url="http://localhost:11500", api_key="OLD-PRIVATE-SENTINEL")
    assign(client, model="old-reporter")
    calls = []

    def factory(provider, **kwargs):
        module = current_request_context().get("agent_id", "")
        calls.append((module, provider, kwargs))
        if module == "sibyl":
            steps = [delegate("reporter", "News", {"news_mode": "demo"}), "A summary from Reporter."]

            def respond(history, prompt):
                if len(steps) == 2:
                    owner.models.save(
                        ModelSettingsRequest(
                            provider="ollama",
                            model="new-profile",
                            base_url="http://localhost:11600",
                            api_key="NEW-PRIVATE-SENTINEL",
                            activate=False,
                        )
                    )
                    revision = owner.models.public()["agent_revision"]
                    owner.models.assign(
                        "reporter",
                        AgentModelRequest(revision=revision, provider="ollama", model="new-reporter"),
                    )
                return steps.pop(0)

            return create_llm("mock", response_callback=respond)
        return create_llm(
            "mock",
            sequential_responses=[
                {"type": "tool_call", "tool": "news_sources", "args": {}},
                "The retained sources are available.",
            ],
        )

    monkeypatch.setattr("sibyl.agents.registry.create_llm", factory)
    result = client.post("/api/v1/sibyl/ask", json={"message": "Explain the news"})
    assert result.status_code == 200, result.text
    result = result.json()
    reporter = next(row for row in calls if row[0] == "reporter")
    assert reporter[1] == "ollama" and reporter[2]["model"] == "old-reporter"
    assert reporter[2]["base_url"] == "http://localhost:11500"
    assert reporter[2]["headers"] == {"Authorization": "Bearer OLD-PRIVATE-SENTINEL"}
    trace = result["delegations"][0]
    assert (
        trace["provider"] == "ollama"
        and trace["model"] == "old-reporter"
        and trace["model_selection"] == "override"
    )
    assert trace["evidence"] and result["model"] == "lead"
    assert "PRIVATE-SENTINEL" not in json.dumps(result)
    assert "PRIVATE-SENTINEL" not in json.dumps(owner.store.runs())
    later = client.post("/api/v1/agents/ask", json={"module": "reporter", "message": "News"})
    assert later.status_code == 200 and later.json()["model"] == "new-reporter"
    assert calls[-1][2]["headers"] == {"Authorization": "Bearer NEW-PRIVATE-SENTINEL"}


def test_assignments_do_not_leak_into_native_task_payloads(client, monkeypatch):
    owner = client.app.state.services.agents
    profile(client, api_key="TRANSPORT-SECRET-SENTINEL")
    assign(client)
    run = owner.network.group.run
    inspected = []

    def inspect_task(agent, task, **kwargs):
        inspected.append(task.id)
        assert "TRANSPORT-SECRET-SENTINEL" not in json.dumps(task.to_dict())
        assert "_agents" not in json.dumps(task.to_dict())
        return run(agent, task, **kwargs)

    monkeypatch.setattr(owner.network.group, "run", inspect_task)
    monkeypatch.setattr(
        "sibyl.agents.registry.create_llm",
        lambda *a, **kw: create_llm("mock", default_response="Safe response"),
    )
    assert (
        client.post("/api/v1/agents/ask", json={"module": "reporter", "message": "Hello"}).status_code == 200
    )
    assert len(inspected) == 1


def test_passive_metadata_and_registered_catalog_names_match(client, monkeypatch):
    monkeypatch.setattr("sibyl.agents.registry.create_llm", lambda *a, **kw: pytest.fail("Provider called"))
    state = client.get("/api/v1/settings/llm")
    assert state.headers["cache-control"] == "no-store"
    names = {row["id"]: row["name"] for row in state.json()["agents"]}
    assert names == AGENT_NAMES
    for row in client.get("/api/v1/agents").json():
        assert row["name"] == names[row["id"]]
        assert row["model_selection"] == "default" and row["mode"] == "tools"


def test_assignment_endpoint_respects_origin_and_workspace_access(client):
    path = "/api/v1/settings/llm/agents/reporter"
    body = {"provider": "mock", "revision": 0}
    assert client.post(path, json=body, headers={"Origin": "https://untrusted.invalid"}).status_code == 403
    from pydantic import SecretStr

    client.app.state.services.settings.api_token = SecretStr("workspace-access")
    assert client.post(path, json=body).status_code == 401
    assert (
        client.post(path, json=body, headers={"Authorization": "Bearer workspace-access"}).status_code == 200
    )


def test_tool_mode_default_preserves_explicit_model_overrides(client):
    profile(client)
    assign(client)
    state = profile(client, "none", model="", activate=True).json()
    assert state["active_provider"] == "none" and agent_row(state)["provider"] == "ollama"
    assert not agent_row(state)["inherited"] and agent_row(state)["ready"]


def test_missing_embedded_file_marks_saved_override_unavailable(client, tmp_path, monkeypatch):
    path = tmp_path / "fixture.gguf"
    path.write_bytes(b"not a real model, never loaded")
    profile(client, "llama.cpp-local", model=str(path))
    result = assign(client, provider="llama.cpp-local", model=str(path))
    assert result.status_code == 200
    path.unlink()
    monkeypatch.setattr("sibyl.agents.providers.find_spec", lambda _: object())
    row = agent_row(client.get("/api/v1/settings/llm").json())
    assert not row["ready"] and "GGUF file is missing" in row["reason"]


def test_environment_provider_can_be_assigned_and_key_fallback_is_provider_specific(client, monkeypatch):
    owner = client.app.state.services.agents
    owner.settings.llm_provider = "openai"
    owner.settings.llm_model = "environment-default"
    monkeypatch.setenv("OPENAI_API_KEY", "OPENAI-ENV-PRIVATE")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "OTHER-ENV-PRIVATE")
    assert assign(client, provider="openai", model="custom-environment-model").status_code == 200
    assert owner.models.resolve("reporter")["api_key"] == "OPENAI-ENV-PRIVATE"
    profile(client, "openai", api_key="SAVED-PRIVATE")
    state = client.delete("/api/v1/settings/llm/openai/key").json()
    assert agent_row(state)["ready"]
    assert owner.models.resolve("reporter")["api_key"] == "OPENAI-ENV-PRIVATE"
    assert "ENV-PRIVATE" not in json.dumps(state)


def test_agent_frozen_configuration_survives_provider_key_removal_until_next_turn(client):
    profile(client, "openai", api_key="BEFORE-REMOVAL")
    assign(client, provider="openai")
    models = client.app.state.services.agents.models
    frozen = models.for_turn("reporter")
    client.delete("/api/v1/settings/llm/openai/key")
    assert frozen["_agents"]["reporter"]["api_key"] == "BEFORE-REMOVAL"
    assert models.for_turn("reporter")["_agents"]["reporter"]["api_key"] == ""


def test_ollama_status_uses_its_saved_profile_even_when_not_workspace_default(client):
    profile(client, base_url="http://localhost:11500", api_key="STATUS-KEY")
    assert client.app.state.services.agents.models.resolve()["provider"] == "none"
    ollama = client.app.state.services.ollama
    assert ollama._headers("http://localhost:11500") == {"Authorization": "Bearer STATUS-KEY"}
    assert ollama._headers("http://localhost:11600") == {}


def test_profile_only_edit_of_active_provider_does_not_change_default_model(client):
    profile(client, model="workspace-fixed", activate=True)
    changed = profile(client, model="profile-suggestion", api_key="updated-optional-key").json()
    assert changed["active_provider"] == "ollama" and changed["active_model"] == "workspace-fixed"
    assert changed["profiles"]["ollama"]["model"] == "profile-suggestion"
    assert agent_row(changed)["model"] == "workspace-fixed"
    models = client.app.state.services.agents.models
    assert models.resolve()["api_key"] == "updated-optional-key"


def test_profile_only_edit_pins_legacy_active_model_before_replacing_profile(client):
    profile(client, model="legacy-selection", activate=True)
    with client.app.state.services.store.db() as db:
        db.execute("DELETE FROM workspace_settings WHERE key='llm_default_model'")
    state = profile(client, model="new-profile-only").json()
    assert state["active_model"] == "legacy-selection"
    assert state["profiles"]["ollama"]["model"] == "new-profile-only"


def test_profile_only_save_preserves_environment_model_default(client):
    settings = client.app.state.services.settings
    settings.llm_provider, settings.llm_model = "ollama", "environment-selection"
    state = profile(client, model="saved-profile-only").json()
    assert state["source"] == "environment" and state["active_model"] == "environment-selection"
    assert state["profiles"]["ollama"]["model"] == "saved-profile-only"
