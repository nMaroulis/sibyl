"""Native persistent agents, on-demand evidence, module tools and isolated contexts."""

import json
import threading
from uuid import uuid4

import pytest
from agent_helpers import coordinator_factory, delegate
from protolink import Task, create_llm

from sibyl.agents.common import current_turn
from sibyl.agents.conversations import SibylRequest
from sibyl.models import AgentRequest


def action(tool, **args):
    return {"type": "tool_call", "tool": tool, "args": args}


def use_model(client, monkeypatch, actions):
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    monkeypatch.setattr(
        "sibyl.agents.registry.create_llm", lambda *a, **kw: create_llm("mock", sequential_responses=actions)
    )


def test_same_agents_own_prompts_and_domain_tools_through_model_changes(client, monkeypatch):
    owner = client.app.state.services.agents
    before = {key: id(agent) for key, agent in owner.network.agents.items()}
    catalog = client.get("/api/v1/agents").json()
    assert all(item["url"].startswith(owner.network.namespace) for item in catalog)
    assert all("consult" not in item["tools"] for item in catalog)
    assert set(owner.agents["reporter"].tools) == {
        "news_briefing",
        "read_article",
        "news_sources",
        "fear_and_greed",
    }
    assert set(owner.agents["technician"].tools) == {"connection_status", "settings_guide", "exchange_setup"}
    use_model(client, monkeypatch, ["A general explanation without account reads."])
    monkeypatch.setattr(
        owner.services.portfolio, "overview", lambda *_: pytest.fail("Unrequested portfolio read")
    )
    result = client.post(
        "/api/v1/agents/ask", json={"module": "oracle", "message": "What is diversification?"}
    )
    assert result.status_code == 200, result.text
    assert result.json()["observations"] == [] and result.json()["evidence"] == {}
    client.post("/api/v1/settings/llm", json={"provider": "none"})
    assert before == {key: id(agent) for key, agent in owner.network.agents.items()}


def test_accountant_history_tool_reads_retained_facts_without_credentials_or_private_calls(
    client, monkeypatch
):
    owner = client.app.state.services.agents
    monkeypatch.setattr(owner.store, "credentials", lambda *_: pytest.fail("History help decrypted keys"))
    monkeypatch.setattr(
        owner.services.market, "adapter", lambda *_: pytest.fail("History help fetched private data")
    )
    network = owner.network
    result = client.portal.call(
        network.client.send_task,
        network.cards["accountant"].url,
        Task.create_tool_call("account_history", {"account_id": "demo", "symbol": "BTC/USDT"}),
    )
    result.raise_for_status()
    evidence = result.get_last_item().parts[-1].as_tool_output().result
    assert evidence["evidence_record_limit"] == 10 and evidence["complete_history"] is False
    assert evidence["provider_limits"][0]["account_id"] == "demo"
    assert "cursor" not in json.dumps(evidence) and "revision" not in json.dumps(evidence)


def test_new_history_tool_honors_the_selected_offline_example(client, monkeypatch):
    owner = client.app.state.services.agents
    monkeypatch.setattr(
        owner.services.account_sync.ledger,
        "fills",
        lambda **_: pytest.fail("Changed selected offline report"),
    )
    use_model(
        client,
        monkeypatch,
        [action("account_history", account_id="another-account"), "The selected example remains an example."],
    )
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "accountant",
            "message": "Explain these transfers",
            "context": {"transfer_view": True, "transfer_example": True},
        },
    )
    assert response.status_code == 200
    assert response.json()["evidence"]["view"] == "transfers" and response.json()["evidence"]["example"]


def test_reporter_selects_cached_tools_instead_of_preloaded_observations(client, monkeypatch):
    owner = client.app.state.services.agents
    research = owner.services.research
    article = research.news(mode="demo", refresh=False)["items"][0]
    calls, read = ([], research.news)

    def cached(**kwargs):
        calls.append(kwargs)
        return read(**kwargs)

    monkeypatch.setattr(research, "news", cached)
    monkeypatch.setattr(
        research.news_service, "refresh", lambda *_: pytest.fail("Reporter refreshed a publisher")
    )
    steps = [
        action("news_briefing"),
        action("read_article", article_id=article["id"]),
        action("news_sources"),
        action("fear_and_greed"),
        "A source-attributed summary of the illustrative briefing.",
    ]

    def factory(*args, **kwargs):

        def respond(history, prompt):
            encoded = json.dumps(history.messages)
            if not calls:
                assert article["title"] not in encoded
            return steps.pop(0)

        return create_llm("mock", response_callback=respond)

    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    monkeypatch.setattr("sibyl.agents.registry.create_llm", factory)
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "reporter",
            "message": "Explain the latest news",
            "context": {"news_mode": "demo", "news_days": 0},
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert calls == [
        {
            "refresh": False,
            "mode": "demo",
            "publisher": "",
            "asset": "",
            "sentiment": "",
            "q": "",
            "days": 0,
            "limit": 8,
        }
    ]
    assert [row["tool"] for row in result["observations"]] == [
        "news_briefing",
        "read_article",
        "news_sources",
        "fear_and_greed",
    ]
    assert result["observations"][1]["evidence"]["id"] == article["id"]
    assert result["evidence"]["mode"] == "demo"


def test_reporter_empty_live_archive_stays_live_and_never_fetches_or_substitutes_demo(client, monkeypatch):
    service = client.app.state.services.agents.services.research.news_service
    monkeypatch.setattr(service, "refresh", lambda *_: pytest.fail("Agent must only read the archive"))
    use_model(client, monkeypatch, [action("news_briefing"), "There are no retained live stories yet."])
    response = client.post(
        "/api/v1/agents/ask",
        json={"module": "reporter", "message": "Latest news", "context": {"news_mode": "live"}},
    )
    assert response.status_code == 200, response.text
    evidence = response.json()["evidence"]
    assert evidence["mode"] == "live" and evidence["items"] == []
    assert evidence["sources"] and evidence["source"] == "publisher feeds"


@pytest.mark.parametrize(
    "exchange,fields",
    [
        ("binance", ["label", "api_key", "secret"]),
        ("okx", ["label", "api_key", "secret", "passphrase"]),
        ("demo", ["label"]),
    ],
)
def test_technician_provides_provider_specific_setup_instructions_without_credentials(
    client, monkeypatch, exchange, fields
):
    owner = client.app.state.services.agents
    monkeypatch.setattr(
        owner.store, "credentials", lambda *_: pytest.fail("Help must not decrypt exchange keys")
    )
    use_model(
        client,
        monkeypatch,
        [
            action("exchange_setup", exchange=exchange),
            action("settings_guide", section="models"),
            "Open Settings and follow the returned connection steps. Never paste keys here.",
        ],
    )
    result = client.post(
        "/api/v1/agents/ask", json={"module": "technician", "message": f"How do I connect {exchange}?"}
    )
    assert result.status_code == 200, result.text
    reply = result.json()
    assert reply["tool"] == "exchange_setup"
    assert reply["evidence"]["exchange"]["support"]
    assert "locally and encrypted" in reply["evidence"]["key_storage"]
    assert reply["evidence"]["required_fields"] == fields
    assert reply["evidence"]["url"] == "/settings?tab=exchanges"
    assert len(reply["evidence"]["steps"]) >= 4
    assert reply["observations"][1]["evidence"]["url"] == "/settings?tab=models"


@pytest.mark.parametrize(
    "module,tool,args",
    [
        ("analyst", "analysis_help", {}),
        ("broker", "strategy_guide", {}),
        ("broker", "exchange_support", {"exchange": "gemini"}),
        ("chronos", "forecast_method", {}),
        ("wiki", "crypto_catalog", {}),
        ("explorer", "blockchain_help", {}),
        ("stocks", "equity_help", {}),
        ("technician", "settings_guide", {"section": "messaging"}),
    ],
)
def test_module_guides_are_real_tools_reachable_by_native_client(client, module, tool, args):
    network = client.app.state.services.agents.network
    result = client.portal.call(
        network.client.send_task, network.cards[module].url, Task.create_tool_call(tool, args)
    )
    result.raise_for_status()
    assert result.get_last_item().parts[-1].as_tool_output().result


def test_accountant_cannot_switch_selected_offline_report_into_private_balances(client, monkeypatch):
    owner = client.app.state.services.agents
    monkeypatch.setattr(
        owner.services.portfolio,
        "overview",
        lambda *_: pytest.fail("Private balance read from offline report"),
    )
    use_model(
        client,
        monkeypatch,
        [
            action(
                "accountant_snapshot",
                performance_view=False,
                funding_view=False,
                transfer_view=True,
                account_id="another-account",
                example=False,
            ),
            "The selected example remains provisional.",
        ],
    )
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "accountant",
            "message": "Explain this report",
            "context": {"performance_view": True, "performance_example": True},
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["evidence"]["view"] == "performance"
    assert response.json()["evidence"]["example"]


def test_concurrent_requests_to_same_agent_keep_history_and_page_defaults_isolated(client, monkeypatch):
    owner = client.app.state.services.agents
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    barrier = threading.Barrier(2)

    def factory(*args, **kwargs):
        turn = current_turn.get()
        other = "SOL/USDT" if turn.context["symbol"] == "ETH/USDT" else "ETH/USDT"
        steps = 0

        def respond(history, prompt):
            nonlocal steps
            assert other not in json.dumps(history.messages)
            steps += 1
            if steps == 1:
                barrier.wait(timeout=3)
                return action("market_analysis")
            assert turn.context["symbol"] in json.dumps(history.messages)
            return f"Observed {turn.context['symbol']} using its own selection."

        return create_llm("mock", response_callback=respond)

    monkeypatch.setattr("sibyl.agents.registry.create_llm", factory)
    eth = client.portal.start_task_soon(
        owner.ask,
        AgentRequest(
            module="analyst",
            message="Read this selection",
            session_id="same-browser",
            context={"symbol": "ETH/USDT", "market_source": "demo"},
        ),
    )
    sol = client.portal.start_task_soon(
        owner.ask,
        AgentRequest(
            module="analyst",
            message="Read this selection",
            session_id="same-browser",
            context={"symbol": "SOL/USDT", "market_source": "demo"},
        ),
    )
    eth_reply, sol_reply = eth.result(timeout=5), sol.result(timeout=5)
    assert eth_reply["evidence"]["symbol"] == "ETH/USDT"
    assert sol_reply["evidence"]["symbol"] == "SOL/USDT"
    assert eth_reply["answer"] == "Observed ETH/USDT using its own selection."
    assert sol_reply["answer"] == "Observed SOL/USDT using its own selection."


def test_stop_cancels_real_specialist_tool_and_prevents_late_evidence_commit(client, monkeypatch):
    owner = client.app.state.services.agents
    network = owner.network
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    session = network.conversations.create()["id"]
    started, release, finished = (threading.Event(), threading.Event(), threading.Event())
    read = owner.services.research.news

    def blocked(**kwargs):
        started.set()
        release.wait(timeout=4)
        try:
            return read(**kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(owner.services.research, "news", blocked)
    coordinator_factory(
        monkeypatch,
        lambda *a, **kw: create_llm(
            "mock",
            sequential_responses=[
                delegate("reporter", "Summarize the demo news", context={"news_mode": "demo"}),
                "Should never be saved.",
            ],
        ),
    )
    request_id = uuid4().hex
    future = client.portal.start_task_soon(
        network.ask, SibylRequest(session_id=session, request_id=request_id, message="News please")
    )
    try:
        assert started.wait(timeout=2)
        assert client.get("/health").status_code == 200
        stop = client.post(f"/api/v1/sibyl/conversations/{session}/cancel", json={"request_id": request_id})
        assert stop.status_code == 202, stop.text
        assert future.result(timeout=2)["status"] == "cancelled"
    finally:
        release.set()
    assert finished.wait(timeout=2)
    assert client.get("/api/v1/runs?kind=agent").json() == []
    assert client.get(f"/api/v1/sibyl/conversations/{session}").json()["turns"] == []
    assert (
        client.get(f"/api/v1/sibyl/conversations/{session}/activity").json()["delegations"][0]["status"]
        == "cancelled"
    )


def test_sibyl_automatically_sees_new_registry_agent_and_calls_its_advertised_tool(client, monkeypatch):
    """No MODULES entry, discovery tool, manual card injection or consultation wrapper is involved."""
    from protolink import Agent

    owner = client.app.state.services.agents
    network = owner.network

    def workspace_fact() -> dict:
        """Read a deterministic fact from a newly registered local agent."""
        return {"fact": "native-registry-evidence"}

    extra = Agent(
        name="additional-specialist",
        description="A newly registered test specialist.",
        transport="runtime",
        url=f"{network.namespace}/additional",
        registry=network.registry,
        tools=[workspace_fact],
        verbosity=0,
        expose_chat=False,
    )
    extra.card.capabilities.delegation = False
    extra.start(background=True)
    seen = []

    def factory(*args, **kwargs):
        def respond(history, prompt):
            advertised = json.dumps(history.messages)
            seen.append(advertised)
            assert "additional-specialist" in advertised
            assert "workspace_fact" in advertised
            if not any(m.get("role") == "assistant" for m in history.messages):
                return {
                    "type": "agent_call",
                    "agent": "additional-specialist",
                    "action": "tool_call",
                    "tool": "workspace_fact",
                    "args": {},
                }
            assert "native-registry-evidence" in json.dumps(history.messages)
            return "The new specialist returned native registry evidence."

        return create_llm("mock", response_callback=respond)

    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    monkeypatch.setattr("sibyl.agents.registry.create_llm", factory)
    try:
        response = client.post("/api/v1/sibyl/ask", json={"message": "Read the new specialist's fact"})
        assert response.status_code == 200, response.text
        assert "[MOCK ERROR]" not in response.text
        assert seen and network.agents["sibyl"].tools == {}
        assert response.json()["delegations"][0]["evidence"] == {"fact": "native-registry-evidence"}
    finally:
        extra.stop()


@pytest.mark.parametrize("module", ["analyst", "reporter", "technician"])
def test_specialists_never_discover_or_delegate_even_if_model_requests_it(client, monkeypatch, module):
    owner = client.app.state.services.agents

    async def forbidden(*args, **kwargs):
        pytest.fail("A specialist attempted agent discovery")

    monkeypatch.setattr(owner.agents[module], "discover_agents", forbidden)
    use_model(client, monkeypatch, [delegate("wiki", "Explain RSI"), "I can answer only with my own tools."])
    response = client.post("/api/v1/agents/ask", json={"module": module, "message": "Explain the module"})
    assert response.status_code == 200, response.text
    assert response.json()["observations"] == []
    assert len(client.get("/api/v1/runs?kind=agent").json()) == 1


def test_native_agent_client_inference_works_without_http_request_helpers(client, monkeypatch):
    """A registered agent owns its inference path; it does not need the app's Ask wrapper."""
    network = client.app.state.services.agents.network
    use_model(
        client,
        monkeypatch,
        [
            action("exchange_setup", exchange="binance"),
            "Open Settings → Exchanges and enter a dedicated read-only Binance key.",
        ],
    )
    task = Task.create_infer("How do I connect Binance?")
    response = client.portal.call(network.client.send_task, network.cards["technician"].url, task)
    response.raise_for_status()
    assert (
        response.get_last_part_content()
        == "Open Settings → Exchanges and enter a dedicated read-only Binance key."
    )
