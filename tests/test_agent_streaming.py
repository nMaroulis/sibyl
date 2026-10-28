"""Safe browser streaming/metrics over actual native handles; no live providers."""

import json
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from protolink import create_llm
from protolink.core.events import RunEvent
from pydantic import SecretStr

from sibyl.agents.reporting import run_details
from sibyl.agents.streaming import public_activity, stream_reply
from sibyl.api.app import create_app
from sibyl.models import AgentRequest


def test_module_ndjson_uses_native_activity_and_one_saved_reply(client):
    response = client.post("/api/v1/agents/ask/stream", json={"module": "reporter", "message": "Show news"})
    assert response.status_code == 200 and response.headers["content-type"].startswith("application/x-ndjson")
    frames = [json.loads(line) for line in response.text.splitlines()]
    assert frames[0] == {"type": "status", "status": "queued"}
    actions = [row for row in frames if row["type"] == "activity"]
    assert [row["status"] for row in actions] == ["running", "completed"]
    assert all(row["label"] == "news_briefing" for row in actions)
    assert all("result" not in row and "arguments" not in row for row in actions)
    assert frames[-1]["type"] == "reply" and frames[-1]["reply"]["mode"] == "tools"
    assert len(client.get("/api/v1/runs?kind=agent").json()) == 1


def test_sibyl_stream_propagates_native_consultations_and_only_returns_the_root_reply(client, monkeypatch):
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    monkeypatch.setattr(
        "sibyl.agents.registry.create_llm",
        lambda *_a, **_kw: create_llm(
            "mock",
            sequential_responses=[
                {
                    "type": "agent_call",
                    "agent": "sibyl-reporter",
                    "action": "tool_call",
                    "tool": "page_help",
                    "args": {"topic": "sources"},
                },
                "Root final answer",
            ],
        ),
    )
    response = client.post("/api/v1/sibyl/ask/stream", json={"message": "Help with news sources"})
    frames = [json.loads(line) for line in response.text.splitlines()]
    assert frames[-1]["reply"]["answer"] == "Root final answer"
    activities = [row for row in frames if row["type"] == "activity"]
    assert any(row["kind"] == "consultation" for row in activities)
    assert any(row["kind"] == "tool" and row["label"] == "page_help" for row in activities)
    assert len([row for row in frames if row["type"] == "reply"]) == 1
    reply = frames[-1]["reply"]
    summary = client.get(f"/api/v1/agents/runs/{reply['run_id']}/summary").json()
    assert summary["calls"] and summary["calls"][0]["provider"] == "mock"
    assert summary["tokens"]["total"] is None  # Native owned-subagent branch omits metrics in 0.8.3.
    assert all(row["cost"] is None for row in summary["calls"])
    assert all("arguments" not in row and "result" not in row for row in summary["tools"])


def test_direct_specialist_summary_keeps_native_estimated_token_labels(client, monkeypatch):
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    monkeypatch.setattr(
        "sibyl.agents.registry.create_llm",
        lambda *_a, **_kw: create_llm("mock", default_response="A simulated answer"),
    )
    response = client.post("/api/v1/agents/ask/stream", json={"module": "reporter", "message": "Hello"})
    reply = json.loads(response.text.splitlines()[-1])["reply"]
    summary = client.get(f"/api/v1/agents/runs/{reply['run_id']}/summary").json()
    assert summary["tokens"]["estimated"] and summary["tokens"]["total"] > 0
    assert all(row["source"] == "estimate" and row["cost"] is None for row in summary["calls"])


def test_stream_errors_remain_sanitized_and_validation_still_uses_http_status(client, monkeypatch):
    client.post("/api/v1/settings/llm", json={"provider": "mock"})

    def failure(*_a, **_kw):
        raise RuntimeError("PRIVATE-PROVIDER-ERROR")

    monkeypatch.setattr("sibyl.agents.registry.create_llm", failure)
    response = client.post("/api/v1/agents/ask/stream", json={"module": "reporter", "message": "Hello"})
    assert "PRIVATE" not in response.text
    assert json.loads(response.text.splitlines()[-1])["type"] == "error"
    assert (
        client.post("/api/v1/agents/ask/stream", json={"module": "invented", "message": "Hello"}).status_code
        == 422
    )


def test_live_activity_arrives_before_a_blocking_tool_and_disconnect_prevents_late_success(
    client, monkeypatch
):
    owner = client.app.state.services.agents
    entered, release = threading.Event(), threading.Event()
    original = owner.services.research.news

    def blocked(**kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return original(**kwargs)

    monkeypatch.setattr(owner.services.research, "news", blocked)

    async def start():
        return stream_reply(lambda: owner.ask(AgentRequest(module="reporter", message="News")))

    stream = client.portal.call(start)
    try:
        assert json.loads(client.portal.call(anext, stream))["status"] == "queued"
        action = json.loads(client.portal.call(anext, stream))
        assert action["type"] == "activity" and action["status"] == "running"
        assert entered.wait(timeout=2) and client.get("/health").status_code == 200
        client.portal.call(stream.aclose)
        records = owner.network.run_store.list_report_records()
        assert len(records) == 1
        report = owner.network.run_store.get_report(records[0].run_id)
        assert all(item.outcome != "completed" for item in report.tool_evidence)
    finally:
        release.set()
    assert client.get("/api/v1/runs?kind=agent").json() == []


def test_activity_projection_never_exposes_raw_chunks_prompts_errors_or_results():
    assert (
        public_activity(
            RunEvent(
                type="llm.stream",
                run_id="root",
                payload={"llm_event_type": "llm_chunk", "content": "PRIVATE ACTION JSON"},
            )
        )
        is None
    )
    event = RunEvent(
        type="action.failed",
        run_id="root",
        payload={
            "tool": "read_article",
            "args": {"secret": "PRIVATE"},
            "error": {"message": "PRIVATE"},
            "result": "PRIVATE",
        },
    )
    assert "PRIVATE" not in json.dumps(public_activity(event))


@pytest.mark.parametrize("value", [None, True, float("nan"), -1])
def test_metrics_keep_unknown_usage_and_cost_unavailable(value):
    event = RunEvent(
        type="llm.call.completed",
        run_id="root",
        payload={"metrics": {"usage": {"total_tokens": value}, "cost": {"total_cost": value}}},
    )
    summary = run_details(
        SimpleNamespace(events=[event], context=SimpleNamespace(run_id="root"), tool_evidence=[])
    )
    assert summary["tokens"]["total"] is None and summary["calls"][0]["cost"] is None


def test_metrics_do_not_duplicate_events_sum_currencies_or_hide_partial_coverage():
    def event(identity, tokens=None, currency="USD"):
        return RunEvent(
            event_id=identity,
            type="llm.call.completed",
            run_id="root",
            payload={
                "metrics": {
                    "usage": {"total_tokens": tokens, "estimated": False, "source": "provider"},
                    "cost": {"total_cost": 0, "currency": currency, "estimated": True},
                }
            },
        )

    first, second = event("first", 0), event("second", None, "EUR")
    summary = run_details(
        SimpleNamespace(
            events=[first, first, second], context=SimpleNamespace(run_id="root"), tool_evidence=[]
        )
    )
    assert len(summary["calls"]) == 2
    assert summary["tokens"] == {"total": 0, "known_calls": 1, "calls": 2, "estimated": False}
    assert [row["cost"]["currency"] for row in summary["calls"]] == ["USD", "EUR"]


def test_streams_and_summaries_require_workspace_authentication(settings):
    secured = settings.model_copy(update={"api_token": SecretStr("stream-test-token")})
    with TestClient(create_app(secured)) as client:
        for path in ("/api/v1/agents/ask/stream", "/api/v1/sibyl/ask/stream"):
            assert client.post(path, json={"module": "reporter", "message": "Hello"}).status_code == 401
        path = "/api/v1/agents/runs/missing/summary"
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"Authorization": "Bearer stream-test-token"}).status_code == 404
        assert client.app.state.services.agents.network.run_store.list_report_records() == []
