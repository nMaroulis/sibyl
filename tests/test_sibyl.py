"""Actual ProtoLink discovery, client tasks, bounded collaboration, and local chat settings."""

import pytest
from agent_helpers import coordinator_factory, delegate
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
    coordinator_factory(monkeypatch, lambda *a, **kw: create_llm("mock", sequential_responses=actions))


def test_agents_start_register_and_stop_with_each_app(client, settings):
    network = client.app.state.services.agents.network
    cards = client.portal.call(network.registry.client.discover)
    assert {c.name for c in cards} == {f"sibyl-{name}" for name in [*ROLES, "sibyl"]}
    assert all(RuntimeTransport.get_transport(c.url) for c in cards)
    assert len(client.portal.call(network.registry.client.discover, {"tags": "specialist"})) == 10
    assert client.get("/api/v1/system").json()["agents"] == 11
    assert all(item["registered"] for item in client.get("/api/v1/agents").json())
    assert all(
        {skill.id for skill in network.cards[key].skills} == set(agent.tools)
        for key, agent in network.agents.items()
    )
    with TestClient(create_app(settings)) as other:
        other_network = other.app.state.services.agents.network
        assert other_network.namespace != network.namespace
        other_urls = [c.url for c in other.portal.call(other_network.registry.client.discover)]
    assert not any(RuntimeTransport.get_transport(url) for url in other_urls)
    assert all(RuntimeTransport.get_transport(c.url) for c in cards)


def test_sibyl_requires_model_without_creating_chat_or_calling_provider(client, monkeypatch):
    coordinator_factory(monkeypatch, lambda *a, **kw: pytest.fail("provider called"))
    state = client.get("/api/v1/sibyl").json()
    assert not state["ready"] and state["network_ready"] and ("model" in state["reason"])
    assert state["settings_url"] == "/settings?tab=models"
    response = client.post("/api/v1/sibyl/ask", json={"message": "Hello"})
    assert response.status_code == 409
    assert client.get("/api/v1/sibyl/conversations").json() == []
    assert (
        client.post("/api/v1/agents/ask", json={"module": "wiki", "message": "RSI"}).json()["mode"] == "tools"
    )


def test_missing_key_and_dependency_are_setup_states(client, monkeypatch):
    models = client.app.state.services.agents.models
    config = {"provider": "openai", "model": "test", "base_url": "", "api_key": ""}
    monkeypatch.setattr(models, "resolve", lambda agent=None: config)
    assert "API key" in client.get("/api/v1/sibyl").json()["reason"]
    config.update(provider="llama.cpp-local", model="/not/a/real/model.gguf")
    monkeypatch.setattr("sibyl.agents.providers.find_spec", lambda name: None)
    assert "dependency" in client.get("/api/v1/sibyl").json()["reason"]


def test_direct_ask_uses_native_group_handle_without_routing_through_sibyl(client, monkeypatch):
    network = client.app.state.services.agents.network
    calls, run = ([], network.group.run)

    def capture(agent, task, **kwargs):
        calls.append(agent.card.url)
        return run(agent, task, **kwargs)

    monkeypatch.setattr(network.group, "run", capture)
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


def test_sibyl_discovers_and_consults_multiple_agents_through_native_delegation(client, monkeypatch):
    model(client)
    script(
        monkeypatch,
        [
            delegate(
                "analyst", "Explain ETH indicators", context={"symbol": "ETH/USDT", "market_source": "demo"}
            ),
            delegate("broker", "Explain paper strategies", context={"symbol": "ETH/USDT"}),
            "I consulted Analyst and Broker. These observations use demo data and paper strategies.",
        ],
    )
    network = client.app.state.services.agents.network
    calls, run = ([], network.group.run)

    def capture(agent, task, **kwargs):
        calls.append(agent.card.url)
        return run(agent, task, **kwargs)

    monkeypatch.setattr(network.group, "run", capture)
    response = client.post("/api/v1/sibyl/ask", json={"message": "Explain ETH and my strategies"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert [item["agent_id"] for item in result["delegations"]] == ["analyst", "broker"]
    assert all(item["status"] == "completed" for item in result["delegations"])
    assert result["delegations"][0]["evidence"]["symbol"] == "ETH/USDT"
    assert calls == [network.cards["sibyl"].url]
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


@pytest.mark.parametrize("target", ["sibyl-sibyl", "unknown", "https://example.com"])
def test_native_validation_rejects_cycles_unknown_agents_and_urls(client, monkeypatch, target):
    model(client)
    script(monkeypatch, [delegate(target, "Read data"), "That target is unavailable."])
    result = client.post("/api/v1/sibyl/ask", json={"message": "Check target"})
    assert result.status_code == 200, result.text
    assert result.json()["delegations"] == []
    assert client.get("/api/v1/runs?kind=agent").json() == []


def test_native_shared_budget_bounds_delegation(client, monkeypatch):
    model(client)
    script(monkeypatch, [delegate("wiki", f"Explain RSI, part {i}") for i in range(12)] + ["Done"])
    response = client.post("/api/v1/sibyl/ask", json={"message": "Bound this investigation"})
    assert response.status_code == 502
    saved = client.get("/api/v1/runs?kind=agent").json()
    assert 0 < len(saved) < 12
    session = client.get("/api/v1/sibyl/conversations").json()[0]["id"]
    assert client.get(f"/api/v1/sibyl/conversations/{session}/activity").json()["status"] == "failed"


def test_native_delegated_tool_arguments_are_validated_before_dispatch(client, monkeypatch):
    model(client)
    script(
        monkeypatch,
        [
            {
                "type": "agent_call",
                "agent": "sibyl-analyst",
                "action": "tool_call",
                "tool": "market_analysis",
                "args": {"api_key": "PRIVATE-SENTINEL"},
            },
            "The tool arguments were invalid.",
        ],
    )
    response = client.post("/api/v1/sibyl/ask", json={"message": "Explain prices"})
    assert response.status_code == 200, response.text
    assert response.json()["delegations"] == []
    assert "SENTINEL" not in response.text


def test_provider_failures_do_not_expose_credentials(client, monkeypatch):
    model(client)

    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE-TOKEN-SENTINEL")

    coordinator_factory(monkeypatch, fail)
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

    coordinator_factory(monkeypatch, factory)
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
        return create_llm("mock", sequential_responses=[delegate("wiki", "RSI"), "Done"])

    coordinator_factory(monkeypatch, factory)
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
    assert set(channels) == {"whatsapp", "telegram", "discord", "slack", "signal", "email"}
    assert all(not item["connected"] for item in channels.values())
    assert channels["telegram"]["status"] == "available"
    assert all(item["status"] == "unavailable" for key, item in channels.items() if key != "telegram")
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
    assert {f["id"] for f in channels["signal"]["fields"]} == {"bridge_url", "account", "allowed_sender_aci"}
    assert channels["signal"]["planned_transport"] == "signal_cli_jsonrpc"
    assert "unofficial" in channels["signal"]["setup_note"]
    email_fields = {field["id"]: field for field in channels["email"]["fields"]}
    assert set(email_fields) == {
        "email_address",
        "allowed_sender",
        "imap_host",
        "imap_port",
        "imap_security",
        "imap_username",
        "imap_password",
        "imap_folder",
        "smtp_host",
        "smtp_port",
        "smtp_security",
        "smtp_username",
        "smtp_password",
    }
    assert channels["email"]["planned_transport"] == "imap_smtp"
    for protocol in ("imap", "smtp"):
        assert email_fields[f"{protocol}_password"]["type"] == "password"
        assert set(email_fields[f"{protocol}_security"]["options"]) == {"TLS", "STARTTLS"}
    for channel in channels.values():
        assert channel["docs_url"].startswith("https://")
        assert all(
            field["type"] == "password"
            for field in channel["fields"]
            if "token" in field["id"] or "secret" in field["id"]
        )
        assert not any("value" in field for field in channel["fields"])


@pytest.mark.parametrize("channel", ["whatsapp", "discord", "slack", "signal", "email"])
def test_unavailable_channels_accept_no_credentials_or_draft_writes(client, channel):
    before = client.app.state.services.store.data_profile(f"messaging:{channel}")
    for method in (client.put, client.post, client.delete):
        response = method(f"/api/v1/settings/messaging/{channel}")
        assert response.status_code in {404, 405}
    assert client.app.state.services.store.data_profile(f"messaging:{channel}") == before
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
    started, release = (asyncio.Event(), asyncio.Event())

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


def test_native_failed_specialist_retains_prior_completed_consultations(client, monkeypatch):
    model(client)
    owner = client.app.state.services.agents
    monkeypatch.setattr(
        owner.services.market,
        "candles",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("PRIVATE-ERROR-SENTINEL")),
    )
    script(
        monkeypatch, [delegate("wiki", "Explain risk"), delegate("analyst", "Prices"), "Must not be saved"]
    )
    response = client.post("/api/v1/sibyl/ask", json={"message": "Help with risk"})
    assert response.status_code == 502 and "SENTINEL" not in response.text
    session = client.get("/api/v1/sibyl/conversations").json()[0]["id"]
    latest = client.get(f"/api/v1/sibyl/conversations/{session}/requests").json()[0]
    detail = client.get(f"/api/v1/sibyl/conversations/{session}/requests/{latest['id']}").json()
    assert [row["status"] for row in detail["delegations"]] == ["completed", "unavailable"]
    assert detail["delegations"][0]["evidence"]
    assert "SENTINEL" not in str(detail)


def test_native_agent_call_is_sibyls_only_delegation_path(client, monkeypatch):
    model(client)
    network = client.app.state.services.agents.network
    assert set(network.agents["sibyl"].tools) == {"read_context_artifact"}
    assert network.cards["sibyl"].capabilities.delegation
    assert all(not network.cards[key].capabilities.delegation for key in ROLES)
    script(monkeypatch, [delegate("wiki", "RSI"), "Wiki explained RSI."])
    response = client.post("/api/v1/sibyl/ask", json={"message": "Explain RSI"})
    assert response.status_code == 200, response.text
    assert response.json()["delegations"][0]["agent_id"] == "wiki"


def test_blocking_model_does_not_block_health_or_other_api_requests(client, monkeypatch):
    import threading
    import time

    from sibyl.agents.conversations import SibylRequest

    model(client)
    started, release = (threading.Event(), threading.Event())

    def factory(*args, **kwargs):

        def response(history, system):
            started.set()
            release.wait(timeout=3)
            return "Completed the isolated test."

        return create_llm("mock", response_callback=response)

    coordinator_factory(monkeypatch, factory)
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
