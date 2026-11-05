"""Saved research through real ProtoLink execution, controlled only at provider I/O."""

import json
import threading
import time
from uuid import uuid4

import pytest
from agent_helpers import coordinator_factory, delegate
from fastapi.testclient import TestClient
from protolink import Task, create_llm, current_request_context

from sibyl.agents.utils import providers
from sibyl.api.app import create_app
from sibyl.investigations.contracts import InvestigationCreate, InvestigationRun
from sibyl.investigations.evidence import report_sources, source_links
from sibyl.investigations.repository import InvestigationConflict
from sibyl.services.workspace.llm_settings import ModelSettingsRequest


def create(client, **patch):
    body = {
        "title": "My market review",
        "question": "Review ETH markets and news.",
        "context": {"symbol": "ETH/USDT", "market_source": "demo", "news_mode": "demo"},
        **patch,
    }
    response = client.post("/api/v1/investigations", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def answer(sources=None, **patch):
    return json.dumps(
        {
            "summary": "A simulated research report.",
            "findings": [
                {
                    "title": "Observed market",
                    "detail": "The observations are synthetic Demo data, not live conditions.",
                    "sources": sources or [],
                }
            ],
            "uncertainties": ["Historical observations do not predict future returns."],
            "next_questions": ["Which timeframe should I compare?"],
            **patch,
        }
    )


def prepare(client, monkeypatch, actions=None):
    assert client.post("/api/v1/settings/llm", json={"provider": "mock"}).status_code == 200
    coordinator_factory(
        monkeypatch, lambda *a, **kw: create_llm("mock", sequential_responses=actions or [answer()])
    )


def start(client, definition, request_id=None):
    response = client.post(
        f"/api/v1/investigations/{definition['id']}/runs", json={"request_id": request_id or uuid4().hex}
    )
    assert response.status_code == 202, response.text
    return response.json()


def wait(client, definition, run):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/investigations/{definition['id']}/runs/{run['id']}")
        assert response.status_code == 200, response.text
        saved = response.json()
        if saved["status"] not in {"queued", "running", "cancelling"}:
            return saved
        time.sleep(0.01)
    pytest.fail("The bounded native report did not finish.")


def test_save_and_read_need_no_llm_but_start_explains_setup(client, monkeypatch):
    coordinator_factory(monkeypatch, lambda *a, **kw: pytest.fail("Unexpected provider request"))
    definition = create(client)
    assert client.get("/api/v1/investigations").json()[0]["id"] == definition["id"]
    assert client.get(f"/api/v1/investigations/{definition['id']}").json()["runs"] == []
    response = client.post(
        f"/api/v1/investigations/{definition['id']}/runs", json={"request_id": uuid4().hex}
    )
    assert response.status_code == 409 and "model" in response.text.lower()
    assert client.get("/api/v1/investigations").headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "patch",
    [
        {"title": " "},
        {"question": " "},
        {"context": {"symbol": "BTC"}},
        {"context": {"portfolio_scope": "all;DROP TABLE accounts"}},
        {"execute": True},
    ],
)
def test_invalid_research_is_rejected_without_storage(client, patch):
    response = client.post(
        "/api/v1/investigations", json={"title": "Review", "question": "What changed?", **patch}
    )
    assert response.status_code == 422
    assert client.get("/api/v1/investigations").json() == []


def test_native_delegation_retains_structured_report_and_correlated_sources(client, monkeypatch):
    prepare(
        client,
        monkeypatch,
        [
            delegate("analyst", "Analyze the selected market"),
            delegate("reporter", "Explain the selected news"),
            answer(["analyst.market_analysis", "reporter.news_briefing"]),
        ],
    )
    definition = create(client)
    saved = wait(client, definition, start(client, definition))
    assert saved["status"] == "completed", saved
    assert saved["report"]["summary"] == "A simulated research report."
    assert {row["key"] for row in saved["sources"]} == {"analyst.market_analysis", "reporter.news_briefing"}
    analyst = next(row for row in saved["sources"] if row["agent_id"] == "analyst")
    assert "ETH/USDT" in analyst["preview"] and "BTC/USDT" not in analyst["preview"]
    assert analyst["task_id"] and analyst["delegation_id"] and analyst["retrieved_at"]
    assert saved["native_run_id"] and saved["models"]["sibyl"]["provider"] == "mock"
    chat = client.get(f"/api/v1/sibyl/conversations/{saved['session_id']}").json()
    assert chat["turns"][0]["question"] == definition["question"]
    assert chat["turns"][0]["investigation_id"] == definition["id"]
    exported = client.get(f"/api/v1/investigations/{definition['id']}/runs/{saved['id']}/export")
    assert exported.status_code == 200 and exported.json()["run"]["sources"] == saved["sources"]
    assert "api_key" not in exported.text and "llm_chunk" not in exported.text


def test_rerun_is_a_new_version_with_new_context_and_old_reports_unchanged(client, monkeypatch):
    prepare(client, monkeypatch)
    definition = create(client)
    first = wait(client, definition, start(client, definition))
    second = wait(client, definition, start(client, definition))
    assert first["version"] == 1 and second["version"] == 2
    assert first["session_id"] != second["session_id"]
    assert first["native_run_id"] != second["native_run_id"]
    assert client.get(f"/api/v1/investigations/{definition['id']}/runs/{first['id']}").json() == first
    assert len(client.get(f"/api/v1/investigations/{definition['id']}").json()["runs"]) == 2


@pytest.mark.parametrize(
    "output", ["This is not JSON", answer(["broker.imaginary_tool"]), answer(summary="")]
)
def test_invalid_or_invented_report_sources_fail_explicitly(client, monkeypatch, output):
    prepare(client, monkeypatch, [delegate("wiki", "Explain RSI"), output])
    definition = create(client)
    saved = wait(client, definition, start(client, definition))
    assert saved["status"] == "failed" and saved["report"] is None
    assert saved["sources"][0]["key"] == "wiki.search_knowledge"
    assert saved["error"] and saved["session_id"]


def test_idempotent_submission_and_cross_investigation_lookup(client, monkeypatch):
    prepare(client, monkeypatch)
    definition, other = create(client), create(client, title="Other")
    run = start(client, definition)
    saved = wait(client, definition, run)
    assert start(client, definition, run["id"])["id"] == run["id"]
    assert len(client.get(f"/api/v1/investigations/{definition['id']}").json()["runs"]) == 1
    assert client.get(f"/api/v1/investigations/{other['id']}/runs/{run['id']}").status_code == 404
    assert (
        client.post(f"/api/v1/investigations/{other['id']}/runs", json={"request_id": run["id"]}).status_code
        == 409
    )
    assert (
        client.post(f"/api/v1/investigations/{definition['id']}/runs/{saved['id']}/cancel").status_code == 409
    )


def test_stop_during_provider_call_prevents_late_success_and_duplicate_runs(client, monkeypatch):
    prepare(client, monkeypatch)
    entered, release = threading.Event(), threading.Event()

    def factory(*args, **kwargs):
        def respond(history, prompt):
            entered.set()
            release.wait(timeout=5)
            return answer()

        return create_llm("mock", response_callback=respond)

    coordinator_factory(monkeypatch, factory)
    definition = create(client)
    run = start(client, definition)
    try:
        assert entered.wait(2)
        duplicate = client.post(
            f"/api/v1/investigations/{definition['id']}/runs", json={"request_id": uuid4().hex}
        )
        assert duplicate.status_code == 409
        assert client.delete(f"/api/v1/investigations/{definition['id']}").status_code == 409
        stopped = client.post(f"/api/v1/investigations/{definition['id']}/runs/{run['id']}/cancel")
        assert stopped.status_code == 202, stopped.text
        assert stopped.json()["status"] == "cancelled"
    finally:
        release.set()
    saved = wait(client, definition, run)
    assert saved["status"] == "cancelled" and saved["report"] is None


def test_model_choices_are_frozen_before_queue_and_profiles_remain_private(client, monkeypatch):
    prepare(client, monkeypatch)
    owner = client.app.state.services.agents
    seen = []

    def factory(provider, **kwargs):
        seen.append((provider, current_request_context()["models"]["_agents"]["reporter"]["provider"]))
        return create_llm("mock", default_response=answer())

    coordinator_factory(monkeypatch, factory)
    definition = create(client)

    async def queued():
        async with owner._semaphore:
            async with owner._semaphore:
                run = await client.app.state.services.investigations.start(
                    definition["id"], InvestigationRun(request_id=uuid4().hex)
                )
                owner.models.save(ModelSettingsRequest(provider="none"))
        return run

    run = client.portal.call(queued)
    saved = wait(client, definition, run)
    assert saved["status"] == "completed", saved
    assert seen == [("mock", "mock")]
    assert "api_key" not in json.dumps(saved)


def test_saved_reports_survive_restart_and_conversation_deletion(client, settings, monkeypatch):
    prepare(client, monkeypatch)
    definition = create(client)
    saved = wait(client, definition, start(client, definition))
    assert client.delete(f"/api/v1/sibyl/conversations/{saved['session_id']}").status_code == 204
    with TestClient(create_app(settings)) as restarted:
        loaded = restarted.get(f"/api/v1/investigations/{definition['id']}/runs/{saved['id']}")
        assert loaded.status_code == 200 and loaded.json()["report"] == saved["report"]
        assert loaded.json()["activity"] is None
        assert restarted.delete(f"/api/v1/investigations/{definition['id']}").status_code == 204


def test_interrupted_runs_are_not_replayed_and_repository_admission_is_bounded(client, monkeypatch):
    prepare(client, monkeypatch)
    definition = create(client)
    repo = client.app.state.services.investigations.repository
    model = {"sibyl": {"provider": "mock", "model": ""}}
    run, _ = repo.reserve(definition["id"], uuid4().hex, definition["context"], model)
    with pytest.raises(InvestigationConflict):
        repo.reserve(definition["id"], uuid4().hex, {}, model)
    repo.recover()
    assert repo.run(definition["id"], run["id"])["status"] == "interrupted"
    for _ in range(4):
        entry = repo.create(InvestigationCreate(title="Queued", question="Review"))
        repo.reserve(entry["id"], uuid4().hex, {}, model)
    with pytest.raises(InvestigationConflict, match="Four"):
        repo.reserve(definition["id"], uuid4().hex, {}, model)


def test_sibyl_reads_saved_versions_through_its_native_domain_tool(client, monkeypatch):
    prepare(client, monkeypatch)
    definition = create(client)
    saved = wait(client, definition, start(client, definition))
    network = client.app.state.services.agents.network
    task = Task.create_tool_call(
        "investigation_reports", {"investigation_id": definition["id"], "run_id": saved["id"]}
    )
    result = client.portal.call(network.client.send_task, network.cards["sibyl"].url, task)
    result.raise_for_status()
    evidence = result.get_last_item().parts[-1].as_tool_output().result
    assert evidence["run"]["report"] == saved["report"]
    assert f"run={saved['id']}" in evidence["url"]


def test_source_links_and_previews_do_not_invent_or_follow_urls():
    from types import SimpleNamespace

    data = {
        "url": "javascript:alert(1)",
        "items": [
            {"url": "https://example.com/story"},
            {"url": "https://secret:password@example.com"},
            {"url": "http://[malformed"},
            {"url": "/markets?asset=ETH"},
            {"url": "//evil.example"},
        ],
        "text": "x" * 20000,
    }
    assert source_links(data) == ["https://example.com/story", "/markets?asset=ETH"]
    receipt = SimpleNamespace(
        outcome="completed",
        result_omitted=False,
        result=data,
        agent_name="sibyl-reporter",
        action_id="action",
        tool_name="article",
        finished_at="2026-11-01T00:00:00Z",
        task_id="task",
        delegation_id="delegation",
    )
    sources = report_sources(SimpleNamespace(tool_evidence=[receipt]))
    assert len(sources[0]["preview"]) == 16000 and sources[0]["truncated"]
    assert len(sources[0]["fingerprint"]) == 64
    assert sources[0]["key"] == "reporter.article"
    receipt.result_omitted = True
    assert report_sources(SimpleNamespace(tool_evidence=[receipt])) == []


def test_provider_failures_do_not_leak_secrets_or_create_a_successful_report(client, monkeypatch):
    prepare(client, monkeypatch)

    def fail(*args, **kwargs):
        raise RuntimeError("PROVIDER-PRIVATE-SECRET")

    coordinator_factory(monkeypatch, fail)
    definition = create(client)
    saved = wait(client, definition, start(client, definition))
    assert saved["status"] == "failed" and saved["report"] is None
    assert "PRIVATE-SECRET" not in json.dumps(saved)


def test_cancelling_before_a_slot_is_available_never_calls_a_provider(client, monkeypatch):
    prepare(client, monkeypatch)
    coordinator_factory(monkeypatch, lambda *a, **kw: pytest.fail("Cancelled queue waiter called a model"))
    definition = create(client)
    service = client.app.state.services.investigations
    owner = client.app.state.services.agents

    async def stop_queued():
        async with owner._semaphore:
            async with owner._semaphore:
                run = await service.start(definition["id"], InvestigationRun(request_id=uuid4().hex))
                return await service.cancel(definition["id"], run["id"])

    saved = client.portal.call(stop_queued)
    assert saved["status"] == "cancelled" and saved["report"] is None
    assert not service._tasks


def test_saved_report_metadata_excludes_real_provider_credentials(client, monkeypatch):
    # This tests secret redaction with a controlled model, not optional-SDK installation.
    available = providers.find_spec
    monkeypatch.setattr(
        providers, "find_spec", lambda name: object() if name == "openai" else available(name)
    )
    assert (
        client.post(
            "/api/v1/settings/llm",
            json={
                "provider": "openai",
                "model": "controlled-test",
                "api_key": "INVESTIGATION-PROVIDER-SECRET",
            },
        ).status_code
        == 200
    )
    calls = []

    def factory(provider, **kwargs):
        calls.append(kwargs["api_key"])
        return create_llm("mock", default_response=answer())

    coordinator_factory(monkeypatch, factory)
    definition = create(client)
    saved = wait(client, definition, start(client, definition))
    assert saved["status"] == "completed", saved
    assert calls == ["INVESTIGATION-PROVIDER-SECRET"]
    exported = client.get(f"/api/v1/investigations/{definition['id']}/runs/{saved['id']}/export")
    assert "INVESTIGATION-PROVIDER-SECRET" not in exported.text and "api_key" not in exported.text


def test_missing_optional_provider_sdk_rejects_report_before_model_call(client, monkeypatch):
    available = providers.find_spec
    monkeypatch.setattr(providers, "find_spec", lambda name: None if name == "openai" else available(name))
    assert (
        client.post(
            "/api/v1/settings/llm",
            json={"provider": "openai", "model": "controlled-test", "api_key": "SDK-ABSENT-PRIVATE"},
        ).status_code
        == 200
    )
    coordinator_factory(monkeypatch, lambda *a, **kw: pytest.fail("Missing SDK passed report admission"))
    definition = create(client)
    response = client.post(
        f"/api/v1/investigations/{definition['id']}/runs", json={"request_id": uuid4().hex}
    )
    assert response.status_code == 409 and "dependency" in response.json()["detail"]
    assert "SDK-ABSENT-PRIVATE" not in response.text
    assert client.get(f"/api/v1/investigations/{definition['id']}").json()["runs"] == []
