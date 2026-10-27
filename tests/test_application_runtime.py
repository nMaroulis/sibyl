"""Acceptance contracts for Sibyl's native ProtoLink 0.8.3 integration.

Use actual registry/handles, worker admission, context isolation and SQLite
history/reports. Only provider responses and blocking domain reads are scripted.
"""

import asyncio
import json
import threading

import pytest
from agent_helpers import delegate
from fastapi.testclient import TestClient
from protolink import Task, create_llm, current_request_context, request_context

from sibyl.agents.common import freeze
from sibyl.api.app import create_app
from sibyl.models import AgentRequest
from sibyl.services.llm_settings import ModelSettingsRequest


def test_native_factories_are_lazy_and_tools_remain_ordinary_functions(settings, monkeypatch):
    monkeypatch.setattr(
        "sibyl.agents.registry.create_llm", lambda *_a, **_kw: pytest.fail("Startup created a provider")
    )
    with TestClient(create_app(settings)) as client:
        network = client.app.state.services.agents.network
        assert network.database.stat().st_mode & 0o777 == 0o600
        for agent in network.agents.values():
            assert agent.llm is None and agent.llm_factory is not None
            assert agent.sync_execution == "thread"
            assert agent.expose_tool_results
            assert all(not hasattr(tool.func, "__wrapped__") for tool in agent.tools.values())
        assert network.agents["sibyl"].subagents
        assert all(not agent.subagents for key, agent in network.agents.items() if key != "sibyl")
        reply = client.post("/api/v1/agents/ask", json={"module": "reporter", "message": "Tool snapshot"})
        assert reply.status_code == 200 and reply.json()["mode"] == "tools"


def test_private_snapshot_is_immutable_and_not_inherited_across_runtime_transport(client, monkeypatch):
    owner = client.app.state.services.agents
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    calls = []

    def model(*_a, **kw):
        calls.append(kw.get("model"))
        return create_llm("mock", default_response="Native independent answer")

    monkeypatch.setattr("sibyl.agents.registry.create_llm", model)
    snapshot = freeze(owner.models.for_turn("reporter"))
    with pytest.raises(TypeError):
        snapshot["_agents"]["reporter"]["model"] = "mutated"

    async def send():
        # A client must not smuggle ambient application dependencies through runtime://.
        with request_context(
            {"models": {"_agents": {"reporter": {"model": "caller-private"}}}, "private": "SECRET"}
        ):
            result = await owner.network.client.send_task(
                owner.network.cards["reporter"].url, Task.create_infer("Hello")
            )
        result.raise_for_status()
        assert "caller-private" not in json.dumps(result.to_dict())

    client.portal.call(send)
    assert calls == [None]


def test_queued_request_keeps_the_accepted_team_configuration(client, monkeypatch):
    owner = client.app.state.services.agents
    owner.models.save(ModelSettingsRequest(provider="mock", model="accepted"))
    accepted = threading.Event()
    for_turn = owner.models.for_turn

    def snapshot(module):
        result = for_turn(module)
        accepted.set()
        return result

    monkeypatch.setattr(owner.models, "for_turn", snapshot)
    selected = []

    def model(*_a, **kw):
        selected.append((current_request_context()["agent_id"], kw["model"]))
        return create_llm("mock", default_response="The accepted model answered")

    monkeypatch.setattr("sibyl.agents.registry.create_llm", model)
    semaphore = owner._semaphore
    client.portal.call(semaphore.acquire)
    client.portal.call(semaphore.acquire)
    future = client.portal.start_task_soon(owner.ask, AgentRequest(module="reporter", message="Queued"))
    try:
        assert accepted.wait(timeout=2)
        owner.models.save(ModelSettingsRequest(provider="mock", model="later"))
    finally:
        client.portal.call(semaphore.release)
        client.portal.call(semaphore.release)
    assert future.result(timeout=3)["model"] == "accepted"
    assert selected == [("reporter", "accepted")]


def test_native_reports_keep_child_evidence_once_and_the_ui_uses_only_the_root_answer(client, monkeypatch):
    owner = client.app.state.services.agents
    client.post("/api/v1/settings/llm", json={"provider": "mock"})

    def model(*_a, **_kw):
        module = current_request_context()["agent_id"]
        actions = (
            [delegate("reporter", "Explain sources"), "Root final answer"]
            if module == "sibyl"
            else [
                {"type": "tool_call", "tool": "page_help", "args": {"topic": "sources"}},
                "Child final answer",
            ]
        )
        return create_llm("mock", sequential_responses=actions)

    monkeypatch.setattr("sibyl.agents.registry.create_llm", model)
    response = client.post("/api/v1/sibyl/ask", json={"message": "How do I change news sources?"})
    assert response.status_code == 200, response.text
    reply = response.json()
    assert reply["answer"] == "Root final answer"
    report = owner.network.run_store.get_report(reply["run_id"])
    assert report is not None
    evidence = report.tool_evidence
    assert len(evidence) == 1 and evidence[0].tool_name == "page_help"
    assert evidence[0].outcome == "completed" and evidence[0].result["topic"] == "sources"
    assert evidence[0].delegation_id == reply["delegations"][0]["action_id"]
    assert evidence[0].task_id == reply["delegations"][0]["task_id"]
    assert evidence[0].duration_seconds is not None
    public = client.get(f"/api/v1/agents/runs/{reply['run_id']}")
    assert public.status_code == 200 and public.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/agents/runs/missing").status_code == 404
    assert client.delete(f"/api/v1/sibyl/conversations/{reply['session_id']}").status_code == 204
    assert owner.network.run_store.get_report(reply["run_id"]) is None


def test_native_evidence_keeps_the_actual_tool_return_before_context_truncation(client, monkeypatch):
    owner = client.app.state.services.agents
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    actual = {"id": "retained-story", "excerpt": "Sourced text. " * 2000, "source": "test-fixture"}
    monkeypatch.setattr(owner.services.research.news_service, "article", lambda *_: actual.copy())
    monkeypatch.setattr(
        "sibyl.agents.registry.create_llm",
        lambda *_a, **_kw: create_llm(
            "mock",
            sequential_responses=[
                {"type": "tool_call", "tool": "read_article", "args": {"article_id": "retained-story"}},
                "A grounded summary.",
            ],
        ),
    )
    response = client.post("/api/v1/agents/ask", json={"module": "reporter", "message": "Explain this story"})
    assert response.status_code == 200, response.text
    reply = response.json()
    assert reply["evidence"] == actual
    assert owner.network.run_store.get_report(reply["run_id"]).tool_evidence[0].result == actual


def test_native_worker_capacity_remains_occupied_after_cancellation_without_late_success(client, monkeypatch):
    network = client.app.state.services.agents.network
    original = network.owner.services.research.news
    condition, release = threading.Condition(), threading.Event()
    started = []

    def blocking(**kwargs):
        with condition:
            started.append(len(started))
            condition.notify_all()
        assert release.wait(timeout=5)
        return original(**kwargs)

    monkeypatch.setattr(network.owner.services.research, "news", blocking)

    async def start():
        return [
            network.group.run(
                network.agents["reporter"], Task.create_tool_call("news_briefing", {"mode": "demo"})
            )
            for _ in range(5)
        ]

    handles = client.portal.call(start)
    try:
        with condition:
            assert condition.wait_for(lambda: len(started) == 4, timeout=2)
        assert client.get("/health").status_code == 200
        client.portal.call(handles[0].cancel)
        canceled = client.portal.call(handles[0].result)
        assert canceled.status == "canceled"
        assert len(started) == 4  # Cancellation has not freed an unfinished Python worker.
    finally:
        release.set()

    async def finish():
        return await asyncio.gather(*(handle.result() for handle in handles))

    results = client.portal.call(finish)
    assert [result.status for result in results] == ["canceled", *("completed" for _ in range(4))]
    assert all(item.outcome != "completed" for item in results[0].tool_evidence)


def test_group_shutdown_cancels_and_drains_its_native_handles(client, monkeypatch):
    network = client.app.state.services.agents.network
    entered, release = threading.Event(), threading.Event()
    original = network.owner.services.research.news

    def blocking(**kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return original(**kwargs)

    monkeypatch.setattr(network.owner.services.research, "news", blocking)

    async def start():
        return network.group.run(
            network.agents["reporter"], Task.create_tool_call("news_briefing", {"mode": "demo"})
        )

    handle = client.portal.call(start)
    try:
        assert entered.wait(timeout=2)
        client.portal.call(network.close)
        assert not network.ready and client.portal.call(handle.result).status == "canceled"
    finally:
        release.set()


def test_provider_credentials_are_redacted_from_native_reports(client, monkeypatch):
    secret = "actual-provider-secret-sentinel"
    client.post("/api/v1/settings/llm", json={"provider": "ollama", "model": "example", "api_key": secret})

    def failure(*_a, **_kw):
        raise RuntimeError("Provider rejected " + secret)

    monkeypatch.setattr("sibyl.agents.registry.create_llm", failure)
    response = client.post("/api/v1/agents/ask", json={"module": "reporter", "message": "Hello"})
    assert response.status_code == 502 and secret not in response.text
    network = client.app.state.services.agents.network
    reports = network.run_store.list_report_records()
    assert len(reports) == 1
    assert secret not in json.dumps(reports[0].to_dict())
    assert secret.encode() not in network.database.read_bytes()


def test_native_conversation_history_survives_restart_and_delete_clears_the_session(
    client, settings, monkeypatch
):
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    histories = []

    def model(*_a, **_kw):
        def answer(history, _prompt):
            histories.append(json.dumps(history.messages))
            return "Saved native answer"

        return create_llm("mock", response_callback=answer)

    monkeypatch.setattr("sibyl.agents.registry.create_llm", model)
    first = client.post("/api/v1/sibyl/ask", json={"message": "unique-native-first-turn"}).json()
    with TestClient(create_app(settings)) as restarted:
        second = restarted.post(
            "/api/v1/sibyl/ask", json={"session_id": first["session_id"], "message": "Continue"}
        )
        assert second.status_code == 200 and "unique-native-first-turn" in histories[-1]
        network = restarted.app.state.services.agents.network
        native_session = network.session_key("sibyl", first["session_id"], {})
        assert native_session in network.states["sibyl"].conversation.to_dict()
        assert restarted.delete(f"/api/v1/sibyl/conversations/{first['session_id']}").status_code == 204
        assert native_session not in network.states["sibyl"].conversation.to_dict()
