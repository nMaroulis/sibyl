"""Read deployment-attributed native reports without exposing chat or credentials."""

import pytest
from protolink import ContextLimitError, ContextPolicy, create_llm, request_context

from sibyl.agents.utils.conversations import SibylRequest

ROOT = "/api/v1/settings/llm/deployments"


def add(client, label, credential):
    response = client.post(
        ROOT,
        json={"provider": "openai", "name": label, "model": "gpt-6.1-sol", "api_key": credential},
    )
    assert response.status_code == 201, response.text
    return response.json()["deployments"][-1]["id"]


def test_native_reports_are_scoped_by_deployment_even_for_the_same_model(client, monkeypatch):
    monkeypatch.setattr("sibyl.agents.utils.providers.find_spec", lambda _: object())
    monkeypatch.setattr(
        "sibyl.agents.utils.registry.create_llm",
        lambda *_args, **_kwargs: create_llm("mock", default_response="private model answer"),
    )
    first = add(client, "First", "first-workspace-secret-key")
    second = add(client, "Second", "second-workspace-secret-key")
    assert client.post(f"{ROOT}/{first}/default").is_success
    network = client.app.state.services.agents.network

    async def receive():
        with request_context({"request_source": "telegram"}):
            return await network.ask(SibylRequest(message="private Telegram question"))

    client.portal.call(receive)
    response = client.get(f"{ROOT}/{first}/activity")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    data = response.json()
    assert data["requests"] == 1
    assert data["failed"] == 0
    assert data["calls"] == 1
    assert data["context_window"] == 1_050_000
    assert data["recent"][0]["source"] == "telegram"
    assert data["recent"][0]["status"] == "completed"
    assert client.get(f"{ROOT}/{second}/activity").json()["requests"] == 0
    assert client.get(f"{ROOT}/missing/activity").status_code == 404
    assert all(
        secret not in response.text
        for secret in (
            "private Telegram question",
            "private model answer",
            "first-workspace-secret-key",
            "second-workspace-secret-key",
        )
    )


def test_openai_uses_its_context_profile_for_long_protected_input(client, monkeypatch):
    monkeypatch.setattr("sibyl.agents.utils.providers.find_spec", lambda _: object())
    monkeypatch.setattr(
        "sibyl.agents.utils.registry.create_llm",
        lambda *_args, **_kwargs: create_llm("mock", default_response="ready"),
    )
    registry = client.app.state.services.agents
    configuration = {"provider": "openai", "model": "gpt-6.1-sol", "base_url": "", "api_key": "test-key"}
    llm = registry.make_model(configuration)
    llm.history.add_user("x" * 128_100)
    policy = ContextPolicy(preserve_recent=6)

    with pytest.raises(ContextLimitError, match="29952"):
        policy.prepare(llm.history)
    prepared = policy.prepare(llm.history, context_window=llm.metrics_profile.context_window)
    assert prepared["after_tokens"] > 29_952
    assert prepared["prompt_allowance"] == 1_047_952


def test_api_context_override_and_reply_limit_persist_and_return_to_auto(client, monkeypatch):
    monkeypatch.setattr("sibyl.agents.utils.providers.find_spec", lambda _: object())
    monkeypatch.setattr(
        "sibyl.agents.utils.registry.create_llm",
        lambda *_args, **_kwargs: create_llm("mock", default_response="ready"),
    )
    deployment = add(client, "Advanced", "advanced-test-credential")
    path = f"{ROOT}/{deployment}"
    assert client.post(path + "/default").is_success
    default = client.get(path + "/activity").json()
    assert default["context_mode"] == "auto" and default["context_window"] == 1_050_000

    body = {"provider": "openai", "name": "Advanced", "context_window": 500_000, "max_output_tokens": 7_000}
    result = client.put(path, json=body)
    assert result.status_code == 200, result.text
    card = result.json()["deployments"][0]
    assert card["context_window"] == 500_000
    assert card["auto_context_window"] == 1_050_000
    assert card["max_output_tokens"] == 7_000

    registry = client.app.state.services.agents
    configuration = registry.models.resolve()
    assert registry.make_model(configuration).metrics_profile.context_window == 500_000
    _, adapter = registry.models.constructor(configuration)
    assert adapter["model_params"] == {"max_output_tokens": 7_000}
    override = client.get(path + "/activity").json()
    assert override["context_mode"] == "manual" and override["max_output_tokens"] == 7_000

    unchanged = client.put(path, json={"provider": "openai", "name": "Renamed"})
    assert unchanged.json()["deployments"][0]["max_output_tokens"] == 7_000
    reset = client.put(path, json={"provider": "openai", "context_window": None, "max_output_tokens": None})
    assert reset.status_code == 200, reset.text
    assert registry.make_model(registry.models.resolve()).metrics_profile.context_window == 1_050_000
    assert "model_params" not in registry.models.constructor(registry.models.resolve())[1]


@pytest.mark.parametrize(
    "provider, parameter",
    [
        ("openai", "max_output_tokens"),
        ("gemini", "max_output_tokens"),
        ("anthropic", "max_tokens"),
        ("deepseek", "max_tokens"),
        ("grok", "max_tokens"),
        ("openai-compatible", "max_tokens"),
    ],
)
def test_api_output_limits_follow_native_adapter_options(client, provider, parameter):
    result = client.post(
        ROOT,
        json={
            "provider": provider,
            "api_key": "fixture-key",
            "model": "test-model",
            "max_output_tokens": 256,
        },
    )
    assert result.status_code == 201, result.text
    deployment = result.json()["deployments"][0]["id"]
    model_settings = client.app.state.services.agents.models
    configured = model_settings.deployments.read(deployment)
    assert model_settings.constructor(configured)[1]["model_params"] == {parameter: 256}


def test_hugging_face_accepts_custom_context_but_rejects_unused_reply_option(client):
    body = {"provider": "huggingface", "api_key": "fixture-key", "model": "Qwen/Qwen3.6-35B-A3B"}
    assert client.post(ROOT, json={**body, "max_output_tokens": 256}).status_code == 422
    result = client.post(ROOT, json={**body, "context_window": 200_000})
    assert result.status_code == 201, result.text
    card = result.json()["deployments"][0]
    assert card["context_window"] == 200_000
    assert card["auto_context_window"] == 262_144
