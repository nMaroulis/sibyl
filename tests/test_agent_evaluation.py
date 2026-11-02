"""Execute native evaluation/checks with real tools and controlled model responses."""

import argparse
import json
import os
import socket
from dataclasses import replace
from uuid import uuid4

import pytest
from protolink import Agent, AgentGroup, EvaluationCase, compare_evaluations, create_llm, evaluate

from scripts.agent_evaluation.checks import checks_for, compatible_cases, restore_scores
from scripts.agent_evaluation.runner import (
    local_only,
    main,
    read_baseline,
    run_cases,
    selected_cases,
    validate_tools,
)


def case():
    return EvaluationCase(
        "market",
        "Analyze ETH",
        metadata={
            "module": "analyst",
            "required": [
                {
                    "agent": "analyst",
                    "tool": "market_analysis",
                    "result": {"symbol": "ETH/USDT", "source": "demo"},
                }
            ],
            "scope": [
                {
                    "agent": "analyst",
                    "tool": "market_analysis",
                    "result": {"symbol": "ETH/USDT", "source": "demo"},
                }
            ],
            "numbers": [{"agent": "analyst", "tool": "market_analysis", "path": "rsi", "decimals": 1}],
            "answer_any": [["eth"], ["demo"]],
        },
    )


async def native_report(steps, selected=None, name="analyst", repetitions=1):
    def market_analysis(symbol: str = "BTC/USDT") -> dict:
        """Return an explicitly synthetic market observation for native evaluator tests."""
        return {"symbol": symbol, "source": "demo", "rsi": 60.5, "url": "/markets"}

    agent = Agent(
        name="sibyl-" + name,
        transport="runtime",
        url=f"runtime://eval-{uuid4().hex}",
        tools=[market_analysis],
        llm_factory=lambda: create_llm("mock", sequential_responses=steps),
        expose_tool_results=True,
        verbosity=0,
    )
    selected = selected or case()
    async with AgentGroup([agent]):
        return await evaluate(agent, [selected], checks=checks_for(selected), repetitions=repetitions)


async def test_native_evaluation_records_true_tools_repeats_and_portable_scores(tmp_path):
    steps = [
        {"type": "tool_call", "tool": "market_analysis", "args": {"symbol": "ETH/USDT"}},
        "ETH/USDT RSI 60.5 · Demo [Markets](/markets)",
    ]
    report = await native_report(steps, repetitions=2)
    assert report.passed and len(report.samples) == 2
    assert all(sample.report.tool_evidence[0].result["symbol"] == "ETH/USDT" for sample in report.samples)
    assert report.samples[0].report.context.session_id != report.samples[1].report.context.session_id
    path = tmp_path / "report.json"
    report.save(path)
    restored = restore_scores(json.loads(path.read_text()))
    assert restored.passed and compatible_cases(restored, [case()])
    assert not compatible_cases(restored, [replace(case(), prompt="A different question")])
    assert read_baseline(path, [case()]).passed
    with pytest.raises(ValueError, match="differ"):
        read_baseline(path, [replace(case(), prompt="Changed")])


async def test_numeric_check_accepts_sentence_punctuation_and_native_comparison_detects_regression():
    call = {"type": "tool_call", "tool": "market_analysis", "args": {"symbol": "ETH/USDT"}}
    baseline = await native_report([call, "Demo ETH/USDT RSI is 60.5."])
    assert baseline.passed
    candidate = await native_report([call, "Demo ETH/USDT RSI is 10.0."])
    comparison = compare_evaluations(baseline, candidate)
    assert not comparison["passed"]


async def test_one_correct_tool_cannot_hide_an_extra_wrong_market_read():
    report = await native_report(
        [
            {"type": "tool_call", "tool": "market_analysis", "args": {"symbol": "BTC/USDT"}},
            {"type": "tool_call", "tool": "market_analysis", "args": {"symbol": "ETH/USDT"}},
            "ETH/USDT RSI 60.5 · Demo",
        ]
    )
    scores = {score.name: score.value for score in report.samples[0].scores}
    assert scores["required_evidence"] == 1 and scores["selection_scope"] == 0
    assert not report.passed


@pytest.mark.parametrize(
    "owner,answer,failed",
    [
        ("technician", "ETH/USDT RSI 60.5 · Demo", "required_evidence"),
        ("analyst", "ETH/USDT RSI 20.0 · Demo", "numeric_grounding"),
        ("analyst", "ETH/USDT RSI 60.5 · Demo [Settings](/invented-page)", "returned_links"),
        ("analyst", "ETH/USDT RSI 60.5 · current exchange data", "answer_markers"),
        ("analyst", '{"type":"tool_call","tool":"market_analysis"}', "answer_present"),
    ],
)
async def test_checks_reject_wrong_owner_numbers_links_disclosures_and_action_json(owner, answer, failed):
    report = await native_report(
        [{"type": "tool_call", "tool": "market_analysis", "args": {"symbol": "ETH/USDT"}}, answer], name=owner
    )
    assert not report.passed
    assert any(score.name == failed and score.value == 0 for score in report.samples[0].scores)


async def test_instruction_case_flags_unnecessary_reads_and_does_not_inflate_other_metrics():
    selected = EvaluationCase(
        "help", "Explain the controls", metadata={"module": "analyst", "forbidden_tools": ["market_analysis"]}
    )
    report = await native_report(
        [{"type": "tool_call", "tool": "market_analysis", "args": {}}, "Instructions"], selected
    )
    scores = {score.name: score.value for score in report.samples[0].scores}
    assert scores["unwanted_reads"] == 0
    assert "numeric_grounding" not in scores and "selection_scope" not in scores
    assert not report.passed


def test_case_catalog_matches_real_native_tools_and_validated_page_contracts(client):
    cases = selected_cases()
    assert len(cases) == 15
    validate_tools(cases, client.app.state.services.agents)
    with pytest.raises(ValueError, match="Unknown cases"):
        selected_cases(["invented"])
    assert main(["--list-cases", "--case", "no_connected_accounts"]) == 0


def test_network_guard_blocks_external_and_other_local_ports_and_hides_environment_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "EVALUATION-PRIVATE")
    monkeypatch.setenv("OLLAMA_API_KEY", "LOCAL-PRIVATE")
    called = []
    monkeypatch.setattr(socket.socket, "connect", lambda sock, address: called.append(address))
    monkeypatch.setattr(socket.socket, "connect_ex", lambda sock, address: called.append(address) or 0)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [("local fixture",)])
    with local_only(11435):
        assert os.environ["OPENAI_API_KEY"] == "" and os.environ["OLLAMA_API_KEY"] == ""
        assert socket.getaddrinfo("localhost", 11435) == [("local fixture",)]
        with pytest.raises(OSError):
            socket.getaddrinfo("external.example", 443)
        with socket.socket() as channel:
            channel.connect(("127.0.0.1", 11435))
            assert channel.connect_ex(("::1", 11435)) == 0
            for address in [("example.com", 443), ("127.0.0.1", 8000), ("127.0.0.2", 11435)]:
                with pytest.raises(OSError):
                    channel.connect(address)
                with pytest.raises(OSError):
                    channel.connect_ex(address)
    assert os.environ["OPENAI_API_KEY"] == "EVALUATION-PRIVATE"
    assert len(called) == 2


@pytest.mark.parametrize(
    "url",
    [
        "https://remote.example",
        "http://user:secret@127.0.0.1:11434",
        "http://127.0.0.1:11434/path",
        "http://127.0.0.1:11434?token=secret",
    ],
)
def test_cli_refuses_nonlocal_or_credentialled_endpoints_before_network(url, tmp_path):
    with pytest.raises(SystemExit) as error:
        main(["--model", "mock", "--url", url, "--output", str(tmp_path / "out.json")])
    assert error.value.code == 2


async def test_native_application_evaluation_uses_real_discovery_context_fixture_and_reports(
    tmp_path, monkeypatch
):
    from protolink import current_request_context

    def factory(provider, **kwargs):
        module = current_request_context().get("agent_id")
        steps = {
            "broker": [
                {"type": "tool_call", "tool": "trade_help", "args": {"topic": "history"}},
                "Open /trade?tab=history.",
            ],
            "reporter": [
                {
                    "type": "tool_call",
                    "tool": "read_article",
                    "args": {"article_id": "evaluation-injection-71"},
                },
                "The synthetic excerpt discusses Ethereum activity and market-volume comparisons.",
            ],
            "sibyl": [
                {
                    "type": "agent_call",
                    "agent": "sibyl-technician",
                    "action": "tool_call",
                    "tool": "exchange_setup",
                    "args": {"exchange": "binance"},
                },
                "Technician explains how to connect Binance in /settings?tab=exchanges.",
            ],
        }[module]
        return create_llm("mock", sequential_responses=steps)

    monkeypatch.setattr("sibyl.agents.utils.registry.create_llm", factory)
    args = argparse.Namespace(
        timeout=30,
        model="controlled-model",
        url="http://127.0.0.1:11435",
        context_window=32768,
        repetitions=2,
        output=tmp_path / "report.json",
        include_reports=True,
    )
    selected = selected_cases(["trade_history_help", "sibyl_setup", "untrusted_news_excerpt"])
    result = await run_cases(args, selected)
    assert result == 0
    report = restore_scores(json.loads(args.output.read_text()))
    assert report.passed and len(report.samples) == 6
    provenance = json.loads(args.output.with_suffix(".provenance.json").read_text())
    assert provenance["no_trading_side_effects"]
    assert provenance["agent_source_sha256"]
    assert provenance["evaluation_source_sha256"]
    if os.name == "posix":
        assert not (args.output.stat().st_mode & 0o077)
    args.output = tmp_path / "candidate.json"
    assert await run_cases(args, selected, baseline=report) == 0
    compared = json.loads(args.output.with_suffix(".provenance.json").read_text())
    assert compared["comparison"]["passed"]
