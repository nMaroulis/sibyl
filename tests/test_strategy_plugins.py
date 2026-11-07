"""Actual installed-entry-point metadata with trusted local fixtures and real simulations."""

import importlib.metadata as metadata
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_agent_guidance import tool_call

from sibyl.api.app import create_app
from sibyl.strategies.plugins.registry import PluginRegistry

SOURCE = """from sibyl.strategies.plugins import StrategyPlugin, PluginSpec, Parameter
class Example(StrategyPlugin):
    @property
    def spec(self):
        return PluginSpec(name="Fixture momentum",description="Inspectable prefix decisions.",warmup=30,parameters={"period":Parameter(label="Period",minimum=2,maximum=20,default=5)})
    def signal(self,candles,parameters):
        try: candles[-1]["close"] = 0
        except TypeError: pass
        else: raise ValueError("Mutable input")
        return 1 if (len(candles)//parameters["period"])%2 else -1
"""


@pytest.fixture
def installed(tmp_path, monkeypatch):
    name = "plugin_fixture_" + uuid4().hex
    module = tmp_path / (name + ".py")
    module.write_text(SOURCE)
    info = tmp_path / (name + "-0.1.dist-info")
    info.mkdir()
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: 0.1\n")
    (info / "entry_points.txt").write_text(f"[sibyl.strategies]\nfixture-momentum = {name}:Example\n")
    (info / "RECORD").write_text(f"{name}.py,,\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    assert any(p.name == "fixture-momentum" for p in metadata.entry_points(group="sibyl.strategies"))
    return module, name


@pytest.fixture
def custom(settings, installed):
    settings.strategy_plugins = ["fixture-momentum"]
    with TestClient(create_app(settings)) as client:
        client.portal.call(client.app.state.services.workers.close)
        yield client


def request(client, **changes):
    item = next(
        p for p in client.get("/api/v1/strategies/plugins").json()["items"] if p["id"] == "fixture-momentum"
    )
    return (
        dict(
            plugin_id=item["id"],
            revision=item["revision"],
            input_kind="demo",
            candles=180,
            values={"period": 5},
        )
        | changes
    )


def run(client, **changes):
    response = client.post("/api/v1/strategies/plugins/backtests", json=request(client, **changes))
    assert response.status_code == 201, response.text
    return response.json()


def test_disabled_entry_point_is_not_imported(installed):
    import sys

    module, name = installed
    catalog = PluginRegistry().catalog()
    assert next(p for p in catalog["items"] if p["id"] == "fixture-momentum")["status"] == "disabled"
    assert name not in sys.modules
    registry = PluginRegistry(["fixture-momentum"])
    assert registry.catalog()["items"][0]["status"] == "ready"
    assert name in sys.modules


def test_actual_prefix_fills_costs_rerun_and_native_broker(custom, monkeypatch):
    before = custom.app.state.services.data_settings.public_market()
    first = run(custom)
    assert first["source"] == "demo" and first["environment"] == "demo" and first["trades"] > 0
    assert first["summary"]["warmup_bars"] == 30
    assert first["fees"] > 0 and first["summary"]["net_profit"] == pytest.approx(
        sum(t["pnl"] for t in first["round_trips"])
    )
    prices = {c["timestamp"]: c for c in first["price_series"]}
    for fill in first["fills"][:-1]:
        assert fill["price"] == pytest.approx(
            prices[fill["timestamp"]]["open"] * (1.0005 if fill["side"] == "buy" else 0.9995)
        )
    market = custom.app.state.services.market
    monkeypatch.setattr(market, "client", lambda *a: pytest.fail("Replay used a provider"))
    response = custom.post("/api/v1/strategies/plugins/backtests/" + first["id"] + "/rerun", json={})
    assert response.status_code == 201, response.text
    replay = response.json()
    assert replay["signal_fingerprint"] == first["signal_fingerprint"] and replay["fills"] == first["fills"]
    assert replay["rerun_of"] == first["id"]
    evidence = tool_call(custom, "broker", "backtest_report", run_id=first["id"])
    assert evidence["plugin"]["revision"] == first["plugin"]["revision"] and "plugin_signals" not in evidence
    assert custom.app.state.services.data_settings.public_market() == before
    assert not custom.app.state.services.strategies.jobs()
    assert (
        custom.post("/api/v1/strategies/jobs/demo", json={"strategy": "plugin:fixture-momentum"}).status_code
        == 422
    )
    assert custom.delete("/api/v1/strategies/plugins/backtests/" + first["id"]).status_code == 204
    assert custom.get("/api/v1/strategies/plugins/backtests/" + first["id"]).status_code == 404


def test_changed_code_rejects_rerun_but_old_evidence_remains_readable(custom, installed):
    first = run(custom)
    module, _ = installed
    module.write_text(module.read_text() + "\n# changed implementation\n")
    response = custom.post("/api/v1/strategies/plugins/backtests/" + first["id"] + "/rerun", json={})
    assert response.status_code == 400 and "implementation changed" in response.text
    assert custom.get("/api/v1/strategies/plugins/backtests/" + first["id"]).json()["fills"] == first["fills"]


@pytest.mark.parametrize(
    "values", [{"period": True}, {"period": "5"}, {"period": 1}, {"period": 5.5}, {"unknown": 2}]
)
def test_parameter_contract_rejects_unknown_or_invalid_values(custom, values):
    response = custom.post("/api/v1/strategies/plugins/backtests", json=request(custom, values=values))
    assert response.status_code in {400, 422}
    assert custom.get("/api/v1/strategies/plugins/backtests").json()["items"] == []


def test_stale_revision_and_missing_plugin_cannot_run(custom):
    for changes in ({"revision": "0" * 64}, {"plugin_id": "not-enabled"}):
        assert (
            custom.post("/api/v1/strategies/plugins/backtests", json=request(custom, **changes)).status_code
            == 400
        )


def test_invalid_signal_is_sanitized_and_saves_no_success(custom, monkeypatch):
    owner = custom.app.state.services.strategies.plugins
    factory = owner.registry.ready["fixture-momentum"][0]
    monkeypatch.setattr(factory, "signal", lambda *a: True)
    response = custom.post("/api/v1/strategies/plugins/backtests", json=request(custom))
    assert response.status_code == 400 and "invalid signal" in response.text
    assert custom.get("/api/v1/strategies/plugins/backtests").json()["items"] == []


def test_factual_dialog_reads_recorded_custom_backtest_without_an_llm(custom, monkeypatch):
    saved = run(custom)
    monkeypatch.setattr(
        custom.app.state.services.market, "client", lambda *a: pytest.fail("Agent read a provider")
    )
    response = custom.post(
        "/api/v1/agents/ask",
        json={
            "module": "broker",
            "message": "Explain this custom backtest",
            "context": {"backtest_id": saved["id"]},
        },
    )
    assert response.status_code == 200, response.text
    assert "Fixture momentum" in response.json()["answer"]
    assert "simulated round trips" in response.json()["answer"]
