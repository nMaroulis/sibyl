"""Exercise the new HTTP contracts and actual ProtoLink module-tool execution."""

import json

import pytest
from fastapi.testclient import TestClient
from protolink import Agent, create_llm

from sibyl.agents.registry import ROLES
from sibyl.api.app import create_app
from sibyl.config import Settings


@pytest.mark.parametrize(
    "path",
    [
        "/health",
        "/api/v1/system",
        "/api/v1/portfolio",
        "/api/v1/markets",
        "/api/v1/markets/analysis",
        "/api/v1/markets/correlation",
        "/api/v1/forecast",
        "/api/v1/news",
        "/api/v1/knowledge",
        "/api/v1/blocks",
        "/api/v1/stocks/AAPL",
        "/api/v1/agents",
    ],
)
def test_demo_endpoints_are_valid_json(client, path):
    result = client.get(path)
    assert result.status_code == 200, result.text
    json.loads(result.content, parse_constant=lambda value: pytest.fail(f"Non-finite JSON: {value}"))


@pytest.mark.parametrize("module", ROLES)
def test_actual_protolink_tool_execution_for_every_module(client, module):
    response = client.post(
        "/api/v1/agents/ask", json={"module": module, "message": "Explain RSI and portfolio risk"}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["engine"] == "ProtoLink" and result["mode"] == "tools"
    assert result["answer"] and result["tool"] and result["id"]
    assert client.get("/api/v1/runs?kind=agent").json()[0]["payload"]["module"] == module


def test_model_path_uses_protolink_with_mock_provider(client, monkeypatch):
    registry = client.app.state.services.agents
    registry.settings.llm_provider = "ollama"
    native_compose = registry._compose

    def compose(module, *, inference=False, configuration=None):
        if not inference:
            return native_compose(module)
        return Agent(
            name="test-sibyl-model",
            llm=create_llm("mock", default_response="A controlled model response."),
            tools=[registry._tools[module]],
            verbosity=0,
        )

    monkeypatch.setattr(registry, "_compose", compose)
    response = client.post("/api/v1/agents/ask", json={"module": "oracle", "message": "Explain my holdings"})
    assert response.status_code == 200, response.text
    assert response.json()["mode"] == "llm"
    assert "controlled model response" in response.json()["answer"]


def test_validation_never_reflects_credentials(client):
    response = client.post(
        "/api/v1/connections",
        json={
            "exchange": "unsupported",
            "label": "x",
            "api_key": "PRIVATE-KEY-SENTINEL",
            "secret": "PRIVATE-SECRET-SENTINEL",
        },
    )
    assert response.status_code == 422
    assert "PRIVATE" not in response.text
    assert "input" not in response.json()["detail"][0]


def test_connection_metadata_and_agent_context_exclude_secrets(client):
    response = client.post(
        "/api/v1/connections",
        json={
            "exchange": "binance",
            "label": "Test account",
            "api_key": "KEY-SENTINEL",
            "secret": "SECRET-SENTINEL",
        },
    )
    assert response.status_code == 201
    result = client.post("/api/v1/agents/ask", json={"module": "technician", "message": "Status?"})
    assert "SENTINEL" not in result.text
    assert "SENTINEL" not in client.get("/api/v1/connections").text
    assert client.delete(f"/api/v1/connections/{response.json()['id']}").status_code == 204


def test_paper_review_does_not_mutate_then_confirm_is_idempotent(client):
    before = client.get("/api/v1/paper/balances").json()
    request = {"symbol": "BTC/USDT", "side": "buy", "quantity": 0.01, "idempotency_key": "api-order-id-1"}
    assert client.post("/api/v1/orders/preview", json=request).status_code == 200
    assert client.get("/api/v1/paper/balances").json() == before
    first = client.post("/api/v1/orders", json=request).json()
    second = client.post("/api/v1/orders", json=request).json()
    assert first["id"] == second["id"]
    assert len(client.get("/api/v1/orders").json()) == 1


def test_backtest_and_paper_job_contracts(client):
    request = {"strategy": "ema", "symbol": "BTC/USDT"}
    result = client.post("/api/v1/strategies/backtest", json=request)
    assert result.status_code == 200, result.text
    assert result.json()["curve"] and result.json()["source"] == "demo"
    job = client.post("/api/v1/strategies/jobs", json=request).json()
    assert client.post(f"/api/v1/strategies/jobs/{job['id']}/pause").json()["status"] == "paused"
    assert client.post(f"/api/v1/strategies/jobs/{job['id']}/resume").json()["status"] == "running"


def test_token_and_origin_restrictions(tmp_path):
    settings = Settings(data_dir=tmp_path, api_token="test-token", _env_file=None)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/system").status_code == 401
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/system", headers={"Authorization": "Bearer test-token"}).status_code == 200
        assert (
            client.get(
                "/api/v1/system",
                headers={"Authorization": "Bearer test-token", "Origin": "https://untrusted.example"},
            ).status_code
            == 403
        )


def test_public_bind_requires_token(tmp_path):
    with pytest.raises(ValueError, match="SIBYL_API_TOKEN"):
        create_app(Settings(host="0.0.0.0", data_dir=tmp_path, _env_file=None))


@pytest.mark.parametrize("quantity", [-1, 0, "NaN", "Infinity"])
def test_invalid_order_numbers_are_rejected(client, quantity):
    response = client.post(
        "/api/v1/orders", json={"side": "buy", "quantity": quantity, "idempotency_key": "invalid-number-test"}
    )
    assert response.status_code == 422


def test_exchange_execution_is_disabled_by_default(client):
    response = client.post(
        "/api/v1/exchange-orders/preview",
        json={
            "connection_id": "unknown",
            "side": "buy",
            "quantity": 0.01,
            "idempotency_key": "disabled-live-order",
        },
    )
    assert response.status_code == 400
    assert "disabled" in response.json()["detail"]


def test_agent_snapshot_uses_selected_market_and_horizon(client):
    analyst = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "analyst",
            "message": "Explain this market.",
            "context": {"symbol": "ETH/USDT"},
        },
    )
    assert analyst.status_code == 200, analyst.text
    assert analyst.json()["evidence"]["symbol"] == "ETH/USDT"
    assert "ETH/USDT" in analyst.json()["answer"]
    chronos = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "chronos",
            "message": "Explain the uncertainty.",
            "context": {"symbol": "SOL/USDT", "horizon": 7},
        },
    )
    assert chronos.status_code == 200, chronos.text
    assert chronos.json()["evidence"]["symbol"] == "SOL/USDT"
    assert chronos.json()["evidence"]["horizon"] == 7
    assert len(chronos.json()["evidence"]["points"]) == 7


def test_broker_reads_selected_parameters_without_running_strategy(client):
    parameters = {"strategy": "rsi", "symbol": "ETH/USDT", "capital": 2500, "window": 14}
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "broker",
            "message": "Explain these assumptions.",
            "context": {"parameters": parameters},
        },
    )
    assert response.status_code == 200, response.text
    selected = response.json()["evidence"]["selected_parameters"]
    assert all(selected[key] == value for key, value in parameters.items())
    assert client.get("/api/v1/strategies/jobs").json() == []
    assert client.get("/api/v1/runs?kind=backtest").json() == []


def test_reporter_and_equity_agents_use_selected_record(client):
    story = client.get("/api/v1/news").json()["items"][1]
    reporter = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "reporter",
            "message": "Explain this story.",
            "context": {"article_id": story["id"]},
        },
    )
    assert reporter.status_code == 200, reporter.text
    assert reporter.json()["evidence"]["selected_article"]["id"] == story["id"]
    assert story["title"] in reporter.json()["answer"]
    stock = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "stocks",
            "message": "Summarize this equity.",
            "context": {"equity_symbol": "MSFT"},
        },
    )
    assert stock.status_code == 200, stock.text
    assert stock.json()["evidence"]["symbol"] == "MSFT"


@pytest.mark.parametrize(
    "context",
    [
        {"symbol": "bad-market"},
        {"horizon": 31},
        {"equity_symbol": "../../secret"},
        {"api_key": "not-accepted"},
        {"parameters": {"strategy": "unknown"}},
    ],
)
def test_agent_context_rejects_invalid_or_unrecognized_fields(client, context):
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "analyst",
            "message": "Explain.",
            "context": context,
        },
    )
    assert response.status_code == 422
