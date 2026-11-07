"""Native tool contracts: bounded inputs, isolated defaults and responsive help."""

import asyncio
import json
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from protolink import RunHandle, Task, create_llm, request_context
from protolink.core.events import RunEvent

from sibyl.agents.utils.presentation import RunPresentation


@pytest.mark.parametrize("module", ["wiki", "reporter"])
@pytest.mark.parametrize(
    "tool,args",
    [
        ("search_research", {"query": "research", "limit": 0}),
        ("search_research", {"query": "research", "limit": 13}),
        ("search_research", {"query": "x" * 301}),
        ("read_research_document", {"document_id": "unknown", "offset": -1}),
        ("read_research_document", {"document_id": "unknown", "offset": 10001}),
    ],
)
def test_native_schema_rejects_bad_inputs_before_a_library_read_and_inference_can_correct(
    client, monkeypatch, module, tool, args
):
    library = client.app.state.services.library

    def forbidden(*_args, **_kwargs):
        pytest.fail("Invalid arguments reached the domain service")

    monkeypatch.setattr(library, "search", forbidden)
    monkeypatch.setattr(library, "document", forbidden)
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    monkeypatch.setattr(
        "sibyl.agents.utils.registry.create_llm",
        lambda *_a, **_kw: create_llm(
            "mock",
            sequential_responses=[
                {"type": "tool_call", "tool": tool, "args": args},
                {"type": "tool_call", "tool": "page_help", "args": {"topic": "overview"}},
                "The request was corrected using the page instructions.",
            ],
        ),
    )
    response = client.post("/api/v1/agents/ask", json={"module": module, "message": "Help with my research"})
    assert response.status_code == 200, response.text
    report = client.app.state.services.agents.network.run_store.get_report(response.json()["run_id"])
    assert any(item.tool_name == tool and item.outcome == "rejected" for item in report.tool_evidence)
    assert any(item.tool_name == "page_help" and item.outcome == "completed" for item in report.tool_evidence)


def test_shared_research_tools_keep_concurrent_page_defaults_private_and_independent(client, monkeypatch):
    network = client.app.state.services.agents.network
    barrier = threading.Barrier(2)

    def search(query, kind, limit, method):
        barrier.wait(timeout=3)
        return {"query": query, "kind": kind, "method": method, "limit": limit, "items": []}

    monkeypatch.setattr(client.app.state.services.library, "search", search)

    async def ask(module, query, kind):
        with request_context({"page": {"library_query": query, "library_source_type": kind}}):
            result = await network.send(module, Task.create_tool_call("search_research"))
        return result.output

    async def both():
        return await asyncio.gather(
            ask("wiki", "ridge uncertainty", "document"), ask("reporter", "exchange coverage", "news")
        )

    wiki, reporter = client.portal.call(both)
    assert wiki == {
        "query": "ridge uncertainty",
        "kind": "document",
        "method": "keyword",
        "limit": 6,
        "items": [],
    }
    assert reporter == {
        "query": "exchange coverage",
        "kind": "news",
        "method": "keyword",
        "limit": 6,
        "items": [],
    }


def test_native_inline_help_is_responsive_when_all_evidence_workers_are_occupied(client, monkeypatch):
    network = client.app.state.services.agents.network
    condition, release = threading.Condition(), threading.Event()
    started = 0

    def blocked(**_kwargs):
        nonlocal started
        with condition:
            started += 1
            condition.notify_all()
        assert release.wait(timeout=10)
        return {"mode": "demo", "items": []}

    monkeypatch.setattr(client.app.state.services.research, "news", blocked)

    async def start():
        return [
            RunHandle.start(
                network.agents["reporter"], Task.create_tool_call("news_briefing", {"mode": "demo"})
            )
            for _ in range(4)
        ]

    handles = client.portal.call(start)
    try:
        with condition:
            assert condition.wait_for(lambda: started == 4, timeout=3)

        async def help():
            return await asyncio.wait_for(
                network.client.send_task(
                    network.cards["reporter"].url, Task.create_tool_call("page_help", {"topic": "sources"})
                ),
                timeout=2,
            )

        result = client.portal.call(help)
        result.raise_for_status()
        assert result.get_last_item().parts[-1].as_tool_output().result["url"] == "/settings?tab=news"
        assert not release.is_set()
    finally:
        release.set()

        async def drain():
            await asyncio.gather(*(handle.result() for handle in handles))

        client.portal.call(drain)


@pytest.mark.parametrize("module", ["wiki", "reporter"])
def test_a_missing_selected_retrieval_report_can_be_corrected_by_listing_actual_ids(
    client, monkeypatch, module
):
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    monkeypatch.setattr(
        "sibyl.agents.utils.registry.create_llm",
        lambda *_a, **_kw: create_llm(
            "mock",
            sequential_responses=[
                {"type": "tool_call", "tool": "retrieval_evaluation", "args": {}},
                {"type": "tool_call", "tool": "retrieval_evaluation", "args": {"evaluation_id": ""}},
                "The selected report is missing; the actual retained list is empty.",
            ],
        ),
    )
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": module,
            "message": "Explain this report",
            "context": {"retrieval_evaluation_id": "f" * 32},
        },
    )
    assert response.status_code == 200, response.text
    report = client.app.state.services.agents.network.run_store.get_report(response.json()["run_id"])
    evidence = report.tool_evidence
    assert evidence[0].outcome == "rejected" and evidence[0].error["code"] == "retrieval_evaluation_not_found"
    assert evidence[1].outcome == "completed" and evidence[1].result["items"] == []


def test_missing_retrieval_report_in_factual_mode_stays_not_found(client):
    response = client.post(
        "/api/v1/agents/ask",
        json={"module": "wiki", "message": "Explain", "context": {"retrieval_evaluation_id": "f" * 32}},
    )
    assert response.status_code == 404
    assert client.get("/api/v1/runs?kind=agent").json() == []


def test_consultation_cards_ignore_raw_chunks_and_follow_native_cancellation():
    requests, record = Mock(), Mock()
    network = SimpleNamespace(
        requests=requests,
        roles={"reporter": ("Reporter",)},
        owner=SimpleNamespace(store=SimpleNamespace(record=record)),
    )
    view = RunPresentation(
        network, SimpleNamespace(task=SimpleNamespace(id="root")), {}, SimpleNamespace(request_id="request")
    )
    view.consume(
        RunEvent(
            type="action.started",
            task_id="root",
            run_id="run",
            action_id="consult",
            payload={
                "llm_event_type": "agent_call_start",
                "agent": "sibyl-reporter",
                "action": "infer",
                "payload": {"prompt": "Explain news"},
            },
        )
    )
    assert requests.update.call_count == 1
    requests.update.reset_mock()
    for _ in range(100):
        view.consume(
            RunEvent(
                type="llm.stream",
                task_id="child",
                run_id="child-run",
                delegation_id="consult",
                payload={"llm_event_type": "llm_chunk", "content": "PRIVATE ACTION FRAGMENT"},
            )
        )
    requests.update.assert_not_called()
    assert "PRIVATE" not in json.dumps(view.rows)
    view.consume(
        RunEvent(
            type="action.canceled",
            task_id="root",
            run_id="run",
            action_id="consult",
            payload={"action": {"kind": "agent.call", "name": "sibyl-reporter"}},
        )
    )
    assert view.rows["consult"]["status"] == "cancelled"
    record.assert_not_called()
