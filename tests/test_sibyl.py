"""Actual ProtoLink discovery, client tasks, bounded collaboration, and local chat settings."""

import pytest
from fastapi.testclient import TestClient
from protolink import create_llm
from protolink.transport.runtime_transport import RuntimeTransport
from pydantic import SecretStr

from sibyl.agents.registry import ROLES
from sibyl.api.app import create_app
from sibyl.services.llm_settings import ModelSettingsRequest


def model(client):
    assert client.post("/api/v1/settings/llm", json={"provider": "mock"}).status_code == 200


def tool(name, **args):
    return {"type": "tool_call", "tool": name, "args": args}


def script(monkeypatch, actions):
    """Replace only provider I/O; discovery, agents, transports and tools stay real."""
    monkeypatch.setattr(
        "sibyl.agents.network.create_llm", lambda *a, **kw: create_llm("mock", sequential_responses=actions)
    )


def test_agents_start_register_and_stop_with_each_app(client, settings):
    network = client.app.state.services.agents.network
    cards = client.portal.call(network.registry.client.discover)
    assert {c.name for c in cards} == {f"sibyl-{name}" for name in [*ROLES, "sibyl"]}
    assert all(RuntimeTransport.get_transport(c.url) for c in cards)
    assert len(client.portal.call(network.registry.client.discover, {"tags": "specialist"})) == 10
    assert client.get("/api/v1/system").json()["agents"] == 11
    assert all(item["registered"] for item in client.get("/api/v1/agents").json())
    with TestClient(create_app(settings)) as other:
        other_network = other.app.state.services.agents.network
        assert other_network.namespace != network.namespace
        other_urls = [c.url for c in other.portal.call(other_network.registry.client.discover)]
    assert not any(RuntimeTransport.get_transport(url) for url in other_urls)
    assert all(RuntimeTransport.get_transport(c.url) for c in cards)


def test_sibyl_requires_model_without_creating_chat_or_calling_provider(client, monkeypatch):
    monkeypatch.setattr("sibyl.agents.network.create_llm", lambda *a, **kw: pytest.fail("provider called"))
    state = client.get("/api/v1/sibyl").json()
    assert not state["ready"] and state["network_ready"] and "model" in state["reason"]
    assert state["settings_url"] == "/settings?tab=models"
    response = client.post("/api/v1/sibyl/ask", json={"message": "Hello"})
    assert response.status_code == 409
    assert client.get("/api/v1/sibyl/conversations").json() == []
    # Module factual snapshots continue to work without a model.
    assert (
        client.post("/api/v1/agents/ask", json={"module": "wiki", "message": "RSI"}).json()["mode"] == "tools"
    )


def test_missing_key_and_dependency_are_setup_states(client, monkeypatch):
    models = client.app.state.services.agents.models
    config = {"provider": "openai", "model": "test", "base_url": "", "api_key": ""}
    monkeypatch.setattr(models, "resolve", lambda: config)
    assert "API key" in client.get("/api/v1/sibyl").json()["reason"]
    config.update(provider="llama.cpp-local", model="/not/a/real/model.gguf")
    monkeypatch.setattr("sibyl.agents.providers.find_spec", lambda name: None)
    assert "dependency" in client.get("/api/v1/sibyl").json()["reason"]


def test_direct_ask_uses_agent_client_without_routing_through_sibyl(client, monkeypatch):
    network = client.app.state.services.agents.network
    calls, send = [], network.client.send_task

    async def capture(url, task, **kwargs):
        calls.append(url)
        return await send(url, task, **kwargs)

    monkeypatch.setattr(network.client, "send_task", capture)
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "analyst",
            "message": "Explain",
            "context": {"symbol": "ETH/USDT", "market_source": "demo"},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["evidence"]["symbol"] == "ETH/USDT"
    assert calls == [network.cards["analyst"].url]


def test_sibyl_discovers_and_consults_multiple_agents_over_real_clients(client, monkeypatch):
    model(client)
    script(
        monkeypatch,
        [
            tool("discover_agents"),
            tool(
                "ask_agent",
                agent_id="analyst",
                question="Explain ETH indicators",
                context={"symbol": "ETH/USDT", "market_source": "demo"},
            ),
            tool(
                "ask_agent",
                agent_id="broker",
                question="Explain paper strategies",
                context={"symbol": "ETH/USDT"},
            ),
            "I consulted Analyst and Broker. These observations use demo data and paper strategies.",
        ],
    )
    network = client.app.state.services.agents.network
    calls, send = [], network.client.send_task

    async def capture(url, task, **kwargs):
        calls.append(url)
        return await send(url, task, **kwargs)

    monkeypatch.setattr(network.client, "send_task", capture)
    response = client.post("/api/v1/sibyl/ask", json={"message": "Explain ETH and my strategies"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert [item["agent_id"] for item in result["delegations"]] == ["analyst", "broker"]
    assert all(item["status"] == "completed" for item in result["delegations"])
    assert result["delegations"][0]["evidence"]["symbol"] == "ETH/USDT"
    assert calls == [network.cards[key].url for key in ("sibyl", "analyst", "broker")]
    assert result["mode"] == "mock" and result["provider"] == "mock"
    assert client.get("/api/v1/strategies/jobs").json() == []
    assert client.get("/api/v1/orders").json() == []
    saved = client.get(f"/api/v1/sibyl/conversations/{result['session_id']}").json()
    assert saved["turns"] == [result]
    assert saved["title"] == "Explain ETH and my strategies"


def test_generic_question_can_be_answered_without_forced_delegation(client):
    model(client)
    response = client.post("/api/v1/sibyl/ask", json={"message": "Hello"})
    assert response.status_code == 200, response.text
    assert response.json()["delegations"] == []
    assert "simulated" in response.json()["answer"]


def test_unknown_recursive_and_external_targets_cannot_be_contacted(client, monkeypatch):
    model(client)
    script(
        monkeypatch,
        [
            tool("ask_agent", agent_id=target, question="Read data")
            for target in ("sibyl", "unknown", "https://example.com")
        ]
        + ["Those agents are unavailable."],
    )
    response = client.post("/api/v1/sibyl/ask", json={"message": "Check unavailable agents"})
    assert response.status_code == 200, response.text
    assert response.json()["delegations"] == []
    assert client.get("/api/v1/runs?kind=agent").json() == []


def test_consultation_budget_is_enforced(client, monkeypatch):
    model(client)
    script(
        monkeypatch,
        [tool("ask_agent", agent_id="wiki", question=f"Explain RSI, part {index}") for index in range(5)]
        + ["Done."],
    )
    response = client.post("/api/v1/sibyl/ask", json={"message": "Check RSI"})
    assert response.status_code == 200, response.text
    assert len(response.json()["delegations"]) == 4
    assert len(client.get("/api/v1/runs?kind=agent").json()) == 4


@pytest.mark.parametrize("context", [{"symbol": "ETH"}, {"api_key": "PRIVATE-SENTINEL"}])
def test_delegated_context_is_validated_and_not_reflected(client, monkeypatch, context):
    model(client)
    script(
        monkeypatch,
        [tool("ask_agent", agent_id="analyst", question="Read prices", context=context), "Missing evidence."],
    )
    response = client.post("/api/v1/sibyl/ask", json={"message": "Explain prices"})
    assert response.status_code == 200, response.text
    assert response.json()["delegations"][0]["status"] == "unavailable"
    assert "SENTINEL" not in response.text
    assert client.get("/api/v1/runs?kind=agent").json() == []


def test_provider_failures_do_not_expose_credentials(client, monkeypatch):
    model(client)

    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE-TOKEN-SENTINEL")

    monkeypatch.setattr("sibyl.agents.network.create_llm", fail)
    response = client.post("/api/v1/sibyl/ask", json={"message": "Hello"})
    assert response.status_code == 502
    assert "SENTINEL" not in response.text
    assert client.get("/api/v1/sibyl/conversations").json()[0]["title"] == "Hello"


def test_conversations_are_durable_separate_and_deletable(client, settings, monkeypatch):
    model(client)
    seen = []

    def factory(*a, **kw):
        def capture(history, system):
            seen.append(str(history.messages))
            return "A saved reply."

        return create_llm("mock", response_callback=capture)

    monkeypatch.setattr("sibyl.agents.network.create_llm", factory)
    first = client.post("/api/v1/sibyl/ask", json={"message": "unique-first-question"}).json()
    again = client.post("/api/v1/sibyl/ask", json={"message": "follow-up", "session_id": first["session_id"]})
    assert again.status_code == 200
    assert "unique-first-question" in seen[-1] and "A saved reply" in seen[-1]
    other = client.post("/api/v1/sibyl/ask", json={"message": "unrelated-chat"}).json()
    assert "unique-first-question" not in seen[-1]
    with TestClient(create_app(settings)) as restarted:
        assert len(restarted.get(f"/api/v1/sibyl/conversations/{first['session_id']}").json()["turns"]) == 2
        assert restarted.delete(f"/api/v1/sibyl/conversations/{first['session_id']}").status_code == 204
        assert restarted.get(f"/api/v1/sibyl/conversations/{first['session_id']}").status_code == 404
        assert restarted.get(f"/api/v1/sibyl/conversations/{other['session_id']}").status_code == 200


def test_snapshot_shared_by_sibyl_and_delegates_when_model_selection_changes(client, monkeypatch):
    model(client)

    def factory(*args, **kwargs):
        client.app.state.services.agents.models.save(ModelSettingsRequest(provider="none"))
        return create_llm(
            "mock", sequential_responses=[tool("ask_agent", agent_id="wiki", question="RSI"), "Done"]
        )

    monkeypatch.setattr("sibyl.agents.network.create_llm", factory)
    response = client.post("/api/v1/sibyl/ask", json={"message": "Explain RSI"})
    assert response.status_code == 200, response.text
    assert response.json()["provider"] == "mock"
    assert response.json()["delegations"][0]["provider"] == "mock"
    assert not client.get("/api/v1/sibyl").json()["ready"]


def test_messaging_describes_real_fields_but_never_exposes_old_drafts(client):
    store = client.app.state.services.store
    store.save_data_profile("messaging:telegram", {"label": "OLD-PRIVATE-DRAFT", "account": "OLD-ACCOUNT"})
    response = client.get("/api/v1/settings/messaging")
    assert response.status_code == 200
    channels = {item["id"]: item for item in response.json()["channels"]}
    assert set(channels) == {"whatsapp", "telegram", "discord", "slack"}
    assert all(not item["connected"] and item["status"] == "unavailable" for item in channels.values())
    assert "draft" not in response.text and "OLD-" not in response.text
    assert {f["id"] for f in channels["whatsapp"]["fields"]} == {
        "access_token",
        "phone_number_id",
        "app_secret",
        "verify_token",
        "allowed_phone_number",
    }
    assert {f["id"] for f in channels["telegram"]["fields"]} == {"bot_token", "allowed_user_id"}
    assert {f["id"] for f in channels["discord"]["fields"]} == {
        "bot_token",
        "application_id",
        "allowed_user_id",
    }
    assert {f["id"] for f in channels["slack"]["fields"]} == {"bot_token", "app_token", "allowed_user_id"}
    for channel in channels.values():
        assert channel["docs_url"].startswith("https://")
        assert all(
            field["type"] == "password"
            for field in channel["fields"]
            if "token" in field["id"] or "secret" in field["id"]
        )
        assert not any("value" in field for field in channel["fields"])


def test_unavailable_channels_accept_no_credentials_or_draft_writes(client):
    before = client.app.state.services.store.data_profile("messaging:whatsapp")
    for method in (client.put, client.post, client.delete):
        response = method("/api/v1/settings/messaging/whatsapp")
        assert response.status_code in {404, 405}
    assert client.app.state.services.store.data_profile("messaging:whatsapp") == before
    assert "/api/v1/settings/messaging/{channel}" not in client.get("/openapi.json").json()["paths"]


@pytest.mark.parametrize(
    "body",
    [
        {"message": ""},
        {"message": "   "},
        {"message": "x" * 4001},
        {"message": "Hello", "session_id": "bad"},
        {"message": "Hello", "context": {}},
    ],
)
def test_invalid_sibyl_requests_do_not_reach_model(client, body):
    assert client.post("/api/v1/sibyl/ask", json=body).status_code == 422


def test_sibyl_and_channel_endpoints_require_workspace_access(settings):
    settings.api_token = SecretStr("access-secret")
    with TestClient(create_app(settings)) as protected:
        for path in ("/sibyl", "/sibyl/conversations", "/settings/messaging"):
            assert protected.get("/api/v1" + path).status_code == 401
        assert protected.post("/api/v1/sibyl/ask", json={"message": "Hello"}).status_code == 401
        assert protected.put("/api/v1/settings/messaging/telegram", json={}).status_code == 401


def test_concurrent_turns_and_deletion_are_rejected_while_chat_is_running(client, monkeypatch):
    import asyncio

    from sibyl.agents.conversations import SibylRequest

    model(client)
    network = client.app.state.services.agents.network
    session = network.conversations.create()["id"]
    started, release = asyncio.Event(), asyncio.Event()

    async def waiting(request, configuration):
        started.set()
        await release.wait()
        return {"ok": True}

    monkeypatch.setattr(network, "_answer_sibyl", waiting)
    future = client.portal.start_task_soon(network.ask, SibylRequest(message="First", session_id=session))
    try:
        client.portal.call(started.wait)
        duplicate = client.post("/api/v1/sibyl/ask", json={"message": "Second", "session_id": session})
        assert duplicate.status_code == 409
        assert client.get(f"/api/v1/sibyl/conversations/{session}").json()["pending"]
        assert client.delete(f"/api/v1/sibyl/conversations/{session}").status_code == 409
    finally:
        client.portal.call(release.set)
        future.result(timeout=5)
    assert not network._chat_locks
    assert client.delete(f"/api/v1/sibyl/conversations/{session}").status_code == 204


def test_failed_specialist_is_reported_and_does_not_prevent_other_consultations(client, monkeypatch):
    model(client)
    owner = client.app.state.services.agents
    original = owner._answer

    async def answer(request, configuration):
        if request.module == "analyst":
            raise RuntimeError("PRIVATE-ERROR-SENTINEL")
        return await original(request, configuration)

    monkeypatch.setattr(owner, "_answer", answer)
    script(
        monkeypatch,
        [
            tool("ask_agent", agent_id="analyst", question="Prices"),
            tool("ask_agent", agent_id="wiki", question="Explain risk"),
            "Market data unavailable; Wiki helped explain risk.",
        ],
    )
    response = client.post("/api/v1/sibyl/ask", json={"message": "Help with risk"})
    assert response.status_code == 200, response.text
    assert [item["status"] for item in response.json()["delegations"]] == ["unavailable", "completed"]
    assert "SENTINEL" not in response.text


def test_native_agent_call_cannot_bypass_bounded_consultation_tools(client, monkeypatch):
    model(client)
    script(
        monkeypatch,
        [
            {"type": "agent_call", "agent": "sibyl-wiki", "action": "infer", "prompt": "RSI"},
            "Use the consultation tools instead.",
        ],
    )
    response = client.post("/api/v1/sibyl/ask", json={"message": "Explain RSI"})
    # Runtime capability enforcement blocks the alternate delegation path.
    assert response.status_code == 200, response.text
    assert client.get("/api/v1/runs?kind=agent").json() == []


def test_blocking_model_does_not_block_health_or_other_api_requests(client, monkeypatch):
    import threading
    import time

    from sibyl.agents.conversations import SibylRequest

    model(client)
    started, release = threading.Event(), threading.Event()

    def factory(*args, **kwargs):
        def response(history, system):
            started.set()
            release.wait(timeout=3)
            return "Completed the isolated test."

        return create_llm("mock", response_callback=response)

    monkeypatch.setattr("sibyl.agents.network.create_llm", factory)
    future = client.portal.start_task_soon(
        client.app.state.services.agents.network.ask, SibylRequest(message="Test a slow model")
    )
    try:
        assert started.wait(timeout=2)
        before = time.monotonic()
        assert client.get("/health").status_code == 200
        assert time.monotonic() - before < 0.5
    finally:
        release.set()
        future.result(timeout=5)
