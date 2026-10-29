"""Exercise advertised help and order evidence through real native agent clients.

Only model responses are scripted. No test uses a user's accounts, keys or model
provider; help must work without reading workspace funds or contacting providers.
"""

import copy
import inspect
import json

import pytest
from protolink import Task, create_llm

from sibyl.services.ledger import AccountLedger, now_iso
from sibyl.services.order_examples import order_examples


def tool_call(client, module, tool, **args):
    network = client.app.state.services.agents.network
    result = client.portal.call(
        network.client.send_task, network.cards[module].url, Task.create_tool_call(tool, args)
    )
    result.raise_for_status()
    return result.get_last_item().parts[-1].as_tool_output().result


def test_accountant_explains_saved_balance_checks_without_live_reads_or_mutations(client, monkeypatch):
    checks = client.app.state.services.balance_checks
    checkpoint = checks.capture("demo")["checkpoint"]["id"]
    saved = checks.check("demo", checkpoint)
    forbid_reads(client, monkeypatch)
    monkeypatch.setattr(checks, "capture", lambda *_: pytest.fail("Agent replaced a checkpoint"))
    monkeypatch.setattr(checks, "check", lambda *_: pytest.fail("Agent read live balances"))
    evidence = tool_call(client, "accountant", "balance_check_report", account_id="demo")
    assert evidence["report"]["id"] == saved["latest"]["id"]
    assert evidence["view"] == "balance_check"
    assert not evidence["report"]["coverage_complete"]
    asset = saved["latest"]["rows"][0]["asset"]
    selected = tool_call(client, "accountant", "balance_check_report", account_id="demo", asset=asset)
    assert selected["matching_rows"] == 1 and selected["report"]["rows"][0]["asset"] == asset
    missing = tool_call(client, "accountant", "balance_check_report", account_id="demo", asset="NOT_PRESENT")
    assert missing["report"]["rows"] == [] and missing["matching_rows"] == 0
    help = tool_call(client, "accountant", "page_help", topic="balance_checks")
    assert help["url"] == "/account"


def forbid_reads(client, monkeypatch):
    services = client.app.state.services

    def unexpected(*args, **kwargs):
        pytest.fail("Instructions must not read credentials, account funds or provider data")

    monkeypatch.setattr(services.store, "credentials", unexpected)
    monkeypatch.setattr(services.market, "adapter", unexpected)
    monkeypatch.setattr(services.market, "client", unexpected)
    monkeypatch.setattr(services.portfolio, "overview", unexpected)
    monkeypatch.setattr(services.research, "news", unexpected)
    monkeypatch.setattr(services.research, "stock", unexpected)
    monkeypatch.setattr(services.research, "blocks", unexpected)
    return services


@pytest.mark.parametrize(
    "module,tool,topic,url,phrase",
    [
        ("oracle", "page_help", "agents", "/sibyl", "ProtoLink"),
        ("accountant", "page_help", "performance", "/trade?tab=history", "Opening inventory"),
        ("analyst", "page_help", "chart", "/markets", "Shift+drag"),
        ("broker", "trade_help", "history", "/trade?tab=history", "Fills & imports"),
        ("broker", "strategy_help", "results", "/strategies", "Price & trades"),
        ("broker", "strategy_help", "limits", "/strategies", "SAVE STRATEGY LIMITS"),
        ("chronos", "page_help", "models", "/forecast?tab=models", "new numbered version"),
        ("reporter", "page_help", "articles", "/news", "Read full article"),
        ("wiki", "page_help", "profiles", "/research?tab=crypto", "Ask Wiki"),
        ("explorer", "page_help", "transactions", "/research?tab=explorer", "Inspect confirmations"),
        ("stocks", "page_help", "setup", "/research?tab=stocks", "uv sync --extra stocks"),
    ],
)
def test_specialists_have_actionable_help_without_domain_reads(
    client, monkeypatch, module, tool, topic, url, phrase
):
    forbid_reads(client, monkeypatch)
    result = tool_call(client, module, tool, topic=topic)
    assert result["kind"] == "page_help" and result["url"] == url
    assert result["topic"] == topic and phrase in " ".join(result["steps"])
    assert "overview" in {item["id"] for item in result["topics"]}


def test_technician_has_complete_settings_orientation_without_account_reads(client, monkeypatch):
    forbid_reads(client, monkeypatch)
    overview = tool_call(client, "technician", "settings_guide")
    assert overview["section"] == "overview" and overview["url"] == "/settings"
    assert set(overview["sections"]) >= {"exchanges", "models", "news", "market", "messaging", "workspace"}
    messaging = tool_call(client, "technician", "settings_guide", section="messaging")
    assert "Telegram is implemented" in messaging["steps"][0]
    assert "unavailable previews" in messaging["steps"][0]


def test_registry_advertises_actual_docstrings_and_typed_help_schemas(client):
    owner = client.app.state.services.agents
    for module, agent in owner.agents.items():
        assert agent.card.capabilities.delegation is False
        for skill in agent.card.skills:
            if skill.id == "read_context_artifact":
                continue  # SDK-provided bounded-context retrieval, not a Sibyl declaration.
            tool = agent.tools[skill.id]
            assert skill.description == tool.description == inspect.getdoc(tool.func)
            assert skill.input_schema == tool.input_schema
        help_name = (
            "trade_help"
            if module == "broker"
            else "settings_guide"
            if module == "technician"
            else "page_help"
        )
        schema = agent.tools[help_name].input_schema
        field = "section" if module == "technician" else "topic"
        assert "overview" in schema["properties"][field]["enum"]
        assert schema["additionalProperties"] is False
    description = owner.agents["reporter"].tools["fear_and_greed"].description
    assert "Bitcoin" in description and "publication date" in description
    assert "network refresh" not in description
    with pytest.raises(ValueError):
        owner.agents["broker"].tools["trade_help"].validate_args({"topic": "withdraw_money"})
    with pytest.raises(ValueError):
        owner.agents["analyst"].tools["market_analysis"].validate_args({"limit": 100000})


def test_broker_how_to_answer_uses_help_without_reading_account_history(client, monkeypatch):
    services = forbid_reads(client, monkeypatch)
    monkeypatch.setattr(services.account_sync.ledger, "fills", lambda **_: pytest.fail("Unneeded fill read"))
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    steps = [
        {"type": "tool_call", "tool": "trade_help", "args": {"topic": "history"}},
        "Open [Trade → Account history](/trade?tab=history), then Fills & imports and Sync market history.",
    ]
    monkeypatch.setattr(
        "sibyl.agents.registry.create_llm", lambda *a, **kw: create_llm("mock", sequential_responses=steps)
    )
    response = client.post(
        "/api/v1/agents/ask",
        json={"module": "broker", "message": "How can I see my account history?"},
    )
    assert response.status_code == 200, response.text
    reply = response.json()
    assert [row["tool"] for row in reply["observations"]] == ["trade_help"]
    assert reply["evidence"]["url"] == "/trade?tab=history"


def test_sibyl_can_call_discovered_help_using_native_delegation(client, monkeypatch):
    forbid_reads(client, monkeypatch)
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    steps = [
        {
            "type": "agent_call",
            "agent": "sibyl-reporter",
            "action": "tool_call",
            "tool": "page_help",
            "args": {"topic": "sources"},
        },
        "Reporter explains source configuration in [Settings → News](/settings?tab=news).",
    ]
    monkeypatch.setattr(
        "sibyl.agents.registry.create_llm", lambda *a, **kw: create_llm("mock", sequential_responses=steps)
    )
    response = client.post("/api/v1/sibyl/ask", json={"message": "How do I choose news sources?"})
    assert response.status_code == 200, response.text
    reply = response.json()
    assert len(reply["delegations"]) == 1
    consultation = reply["delegations"][0]
    assert consultation["agent_id"] == "reporter" and consultation["status"] == "completed"
    assert consultation["evidence"]["topic"] == "sources"
    assert consultation["evidence"]["url"] == "/settings?tab=news"


def test_explicit_glossary_query_does_not_fetch_the_page_selected_project(client, monkeypatch):
    research = client.app.state.services.research
    monkeypatch.setattr(
        research.crypto, "profile", lambda *_: pytest.fail("Ignored explicit glossary question")
    )
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    monkeypatch.setattr(
        "sibyl.agents.registry.create_llm",
        lambda *a, **kw: create_llm(
            "mock",
            sequential_responses=[
                {"type": "tool_call", "tool": "search_knowledge", "args": {"query": "RSI"}},
                "A sourced RSI definition.",
            ],
        ),
    )
    response = client.post(
        "/api/v1/agents/ask",
        json={"module": "wiki", "message": "What is RSI?", "context": {"crypto_id": "btc-bitcoin"}},
    )
    assert response.status_code == 200, response.text
    assert "RSI" in json.dumps(response.json()["evidence"])


def seed_orders(services, count=12):
    """Retain test observations only; no order preview/submission or external transport."""
    sample = order_examples()[0]
    with services.store.db() as db:
        for i in range(count):
            order = copy.deepcopy(sample["order"])
            order.update(id=f"retained-{i:02d}", created_at=now_iso(), environment="demo", origin="imported")
            order.update(
                refreshed_at=now_iso(),
                cancel_state="unknown",
                cancel_message="Inspect native status.",
                tracking=False,
                fill_tracking=False,
            )
            order["request"]["connection_id"] = "demo" if i != count - 1 else "other-account"
            order["exchange_order_id"] = f"native-{i}"
            order["status"] = "canceled" if i == count - 1 else "open"
            db.execute(
                "INSERT INTO exchange_orders VALUES(?,?,?)", (order["id"], order["id"], json.dumps(order))
            )
        fills = []
        for i in range(12):
            fill = copy.deepcopy(sample["fills"][0])
            fill.update(
                id=f"retained-fill-{i}",
                trade_id=f"native-fill-{i}",
                account_id="demo",
                order_id="native-0",
                environment="demo",
            )
            fills.append(fill)
        AccountLedger.upsert_fills(db, fills, now_iso())


def test_broker_order_evidence_is_filtered_bounded_and_has_no_provider_reads_or_writes(client, monkeypatch):
    services = client.app.state.services
    seed_orders(services)
    forbid_reads(client, monkeypatch)
    for name in ("preview", "execute", "refresh", "recover"):
        monkeypatch.setattr(
            services.trading, name, lambda *_a, **_kw: pytest.fail("Order tool mutated/refreshed")
        )
    with services.store.db() as db:
        before = list(db.iterdump())
    orders = tool_call(client, "broker", "recorded_orders", account_id="demo", status="active")
    assert orders["total"] == 11 and len(orders["items"]) == 10 and orders["has_more"]
    assert all(
        row["request"]["connection_id"] == "demo" and row["status"] == "open" for row in orders["items"]
    )
    detail = tool_call(client, "broker", "recorded_orders", account_id="demo", order_id="retained-00")
    assert detail["order"]["environment"] == "demo"
    assert detail["order"]["refreshed_at"] and detail["order"]["cancel_state"] == "unknown"
    assert detail["reconciliation"]["fill_count"] == 12
    assert len(detail["fills"]) == 10 and detail["has_more_fills"]
    assert detail["reconciliation"]["settlement_final"] is False
    assert "cursor" not in json.dumps(detail) and "request_key" not in json.dumps(detail)
    with services.store.db() as db:
        assert list(db.iterdump()) == before


def test_native_tool_rejection_allows_model_to_correct_an_unknown_order_id(client, monkeypatch):
    forbid_reads(client, monkeypatch)
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    steps = [
        {"type": "tool_call", "tool": "recorded_orders", "args": {"order_id": "invented"}},
        {"type": "tool_call", "tool": "recorded_orders", "args": {}},
        "There are no retained orders to inspect. Open Trade → Executions.",
    ]
    monkeypatch.setattr(
        "sibyl.agents.registry.create_llm", lambda *a, **kw: create_llm("mock", sequential_responses=steps)
    )
    response = client.post("/api/v1/agents/ask", json={"module": "broker", "message": "Check my order"})
    assert response.status_code == 200, response.text
    observations = response.json()["observations"]
    assert len(observations) == 1
    assert observations[0]["arguments"] == {"account_id": "", "status": "", "order_id": ""}
    assert observations[0]["evidence"]["items"] == []


def test_exchange_setup_keeps_actionable_guidance_in_native_bounded_context(client, monkeypatch):
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    step = []

    def respond(history, _prompt):
        step.append(True)
        if len(step) == 1:
            return {"type": "tool_call", "tool": "exchange_setup", "args": {"exchange": "binance"}}
        visible = json.dumps(history.messages)
        assert "context_artifact" in visible
        assert "/settings?tab=exchanges" in visible
        assert "Save the connection" in visible
        return "Use the supplied Exchanges settings link."

    monkeypatch.setattr(
        "sibyl.agents.registry.create_llm",
        lambda *_a, **_kw: create_llm("mock", response_callback=respond),
    )
    response = client.post("/api/v1/agents/ask", json={"module": "technician", "message": "Connect Binance"})
    assert response.status_code == 200, response.text
    assert len(step) == 2
    assert response.json()["evidence"]["exchange"]["support"]  # Full receipt survives the preview.
