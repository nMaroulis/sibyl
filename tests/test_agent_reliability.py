"""Native recovery from invalid read selections and truthful retained execution labels."""

import pytest
from protolink import create_llm

from sibyl.agents.utils.snapshots import snapshot_answer
from sibyl.investigations.contracts import InvestigationCreate
from sibyl.investigations.scheduling.contracts import CreateBriefing
from sibyl.models import BacktestRequest


def ask(client, monkeypatch, module, steps, context=None):
    client.post("/api/v1/settings/llm", json={"provider": "mock"}).raise_for_status()
    monkeypatch.setattr(
        "sibyl.agents.utils.registry.create_llm",
        lambda *a, **kw: create_llm("mock", sequential_responses=steps),
    )
    endpoint = "/api/v1/sibyl/ask" if module == "sibyl" else "/api/v1/agents/ask"
    body = {"message": "Inspect the requested saved evidence."}
    if module != "sibyl":
        body["module"] = module
        body["context"] = context or {}
    response = client.post(endpoint, json=body)
    assert response.status_code == 200, response.text
    reply = response.json()
    return reply, client.app.state.services.agents.network.run_store.get_report(reply["run_id"])


@pytest.mark.parametrize("tool", ["read_article", "news_briefing"])
def test_reporter_recovers_a_missing_story_through_native_tool_rejection(client, monkeypatch, tool):
    context = {"news_mode": "demo", "article_id": "removed-story"}
    args = {"article_id": "removed-story"} if tool == "read_article" else {}
    reply, report = ask(
        client,
        monkeypatch,
        "reporter",
        [
            {"type": "tool_call", "tool": tool, "args": args},
            {"type": "tool_call", "tool": "news_briefing", "args": {"article_id": ""}},
            "The selected story is missing. Other retained Demo headlines are available, without substituting them for that story.",
        ],
        context,
    )
    receipts = report.tool_evidence
    assert [item.outcome for item in receipts] == ["rejected", "completed"]
    assert receipts[1].result["mode"] == "demo" and receipts[1].result["items"]
    assert "selected_article" not in receipts[1].result
    assert [item["tool"] for item in reply["observations"]] == ["news_briefing"]


def test_nonselection_tool_failure_is_not_reclassified_as_correctable(client, monkeypatch):
    monkeypatch.setattr(
        client.app.state.services.research.news_service,
        "article",
        lambda *a: (_ for _ in ()).throw(RuntimeError("Controlled storage failure")),
    )
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    monkeypatch.setattr(
        "sibyl.agents.utils.registry.create_llm",
        lambda *a, **kw: create_llm(
            "mock",
            sequential_responses=[
                {"type": "tool_call", "tool": "read_article", "args": {"article_id": "saved-story"}},
                "Should not recover a storage failure.",
            ],
        ),
    )
    response = client.post(
        "/api/v1/agents/ask", json={"module": "reporter", "message": "Read my selected story"}
    )
    assert response.status_code == 502
    assert "Controlled storage failure" not in response.text


def test_chronos_missing_selected_model_never_silently_uses_the_baseline(client, monkeypatch):
    monkeypatch.setattr(
        client.app.state.services.market,
        "candles",
        lambda *a, **kw: pytest.fail("Selected trained model fell back to prices"),
    )
    reply, report = ask(
        client,
        monkeypatch,
        "chronos",
        [
            {"type": "tool_call", "tool": "price_forecast", "args": {}},
            {"type": "tool_call", "tool": "trained_models", "args": {}},
            "The selected trained model is missing and the registry is empty. Open Forecasting; no baseline was substituted.",
        ],
        {"forecast_model_id": "a" * 32},
    )
    assert [(item.tool_name, item.outcome) for item in report.tool_evidence] == [
        ("price_forecast", "rejected"),
        ("trained_models", "completed"),
    ]
    assert reply["observations"][0]["evidence"]["total"] == 0


def test_chronos_can_correct_a_missing_model_report_selection(client, monkeypatch):
    _, report = ask(
        client,
        monkeypatch,
        "chronos",
        [
            {"type": "tool_call", "tool": "model_report", "args": {"model_id": "a" * 32}},
            {"type": "tool_call", "tool": "trained_models", "args": {}},
            "No retained trained models are available.",
        ],
    )
    assert [item.outcome for item in report.tool_evidence] == ["rejected", "completed"]


@pytest.mark.parametrize("arguments", [{"investigation_id": "missing"}, {"run_id": "missing"}])
def test_sibyl_recovers_unknown_investigation_ids_using_its_native_tool(client, monkeypatch, arguments):
    reply, report = ask(
        client,
        monkeypatch,
        "sibyl",
        [
            {"type": "tool_call", "tool": "investigation_reports", "args": arguments},
            {"type": "tool_call", "tool": "investigation_reports", "args": {}},
            "No saved investigations were found. I did not reconstruct the missing report.",
        ],
    )
    assert [item.outcome for item in report.tool_evidence] == ["rejected", "completed"]
    assert report.tool_evidence[1].result["items"] == []
    assert reply["status"] == "completed"


def test_sibyl_will_not_read_another_investigations_schedule_by_mismatched_ids(client, monkeypatch):
    services = client.app.state.services
    first = services.investigations.repository.create(
        InvestigationCreate(title="First", question="What changed?")
    )
    second = services.investigations.repository.create(
        InvestigationCreate(title="Second", question="What changed?")
    )
    policy = services.briefings.create(second["id"], CreateBriefing(enabled=False))
    _, report = ask(
        client,
        monkeypatch,
        "sibyl",
        [
            {
                "type": "tool_call",
                "tool": "briefing_schedules",
                "args": {"investigation_id": first["id"], "schedule_id": policy["id"]},
            },
            {"type": "tool_call", "tool": "briefing_schedules", "args": {"investigation_id": first["id"]}},
            "This investigation has no schedule. The requested schedule belonged to a different investigation.",
        ],
    )
    assert [item.outcome for item in report.tool_evidence] == ["rejected", "completed"]
    assert report.tool_evidence[1].result["schedules"] == []


def test_broker_missing_run_uses_native_correction_without_launching_a_strategy(client, monkeypatch):
    _, report = ask(
        client,
        monkeypatch,
        "broker",
        [
            {"type": "tool_call", "tool": "strategy_context", "args": {}},
            {"type": "tool_call", "tool": "strategy_context", "args": {"job_id": ""}},
            "The selected strategy run is missing; there are no saved runs to substitute.",
        ],
        {"job_id": "a" * 32},
    )
    assert [item.outcome for item in report.tool_evidence] == ["rejected", "completed"]
    assert report.tool_evidence[1].result["strategy_jobs"] == []
    assert not client.app.state.services.strategies.jobs()


@pytest.mark.parametrize(
    "mode,environment,equity",
    [
        ("exchange", "test", None),
        ("exchange", "production", 1000),
        ("paper", "demo", 1000),
        ("unknown", "test", 1000),
    ],
)
def test_broker_summary_preserves_actual_run_mode_environment_and_missing_equity(mode, environment, equity):
    answer = snapshot_answer(
        "broker",
        {
            "selected_parameters": BacktestRequest().model_dump(),
            "selected_run": {
                "status": "paused",
                "mode": mode,
                "environment": environment,
                "equity": equity,
                "checked_at": None,
                "unvalued_fees": {"BNB": 0.001},
            },
            "recent_events": [],
        },
    )
    if mode == "exchange":
        assert "exchange execution" in answer and environment in answer and "paper execution" not in answer
        assert "not a fresh exchange balance" in answer and "unvalued" in answer
        if equity is None:
            assert "equity unavailable" in answer
    elif mode == "paper":
        assert "paper execution" in answer and "virtual equity" in answer
    else:
        assert "Execution mode is unavailable" in answer


def test_broker_catalog_summary_does_not_describe_all_saved_runs_as_paper():
    answer = snapshot_answer(
        "broker",
        {
            "selected_parameters": BacktestRequest().model_dump(),
            "catalog": [],
            "strategy_jobs": [{"mode": "paper"}, {"mode": "exchange", "environment": "test"}],
            "backtests": [],
        },
    )
    assert "2 saved strategy runs" in answer and "2 paper jobs" not in answer
