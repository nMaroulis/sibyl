"""Historical evidence, causal executions, exact reruns and explicit Demo isolation."""

import pytest


def test_demo_backtest_has_prices_trades_metrics_and_replays_without_provider_reads(client, monkeypatch):
    services = client.app.state.services
    before = services.data_settings.public_market()
    active = [c.id for c in services.store.connections() if c.active]
    response = client.post("/api/v1/strategies/backtest/demo", json={"strategy": "ema", "candles": 180})
    assert response.status_code == 200, response.text
    run = response.json()
    assert run["source"] == run["environment"] == "demo"
    assert len(run["price_series"]) == 180 and run["round_trips"]
    assert run["summary"]["net_profit"] == pytest.approx(sum(t["pnl"] for t in run["round_trips"]))
    assert run["summary"]["evaluated_bars"] + run["summary"]["warmup_bars"] == 180
    assert run["benchmark_curve"][-1]["value"] == pytest.approx(
        run["initial_capital"] * (1 + run["benchmark_pct"] / 100)
    )
    assert services.data_settings.public_market() == before
    assert [c.id for c in services.store.connections() if c.active] == active
    monkeypatch.setattr(services.market, "client", lambda *args: pytest.fail("Rerun fetched a provider"))
    replay = client.post(f"/api/v1/strategies/backtests/{run['id']}/rerun")
    assert replay.status_code == 200, replay.text
    repeated = replay.json()
    assert repeated["id"] != run["id"] and repeated["rerun_of"] == run["id"]
    for key in ("curve", "fills", "round_trips", "summary", "benchmark_curve", "price_series"):
        assert repeated[key] == run[key]
    assert repeated["dataset"]["digest"] == run["dataset"]["digest"]


def test_research_rejects_missing_saved_run(client):
    assert client.post("/api/v1/strategies/backtests/missing/rerun").status_code == 404


def test_demo_paper_run_is_source_pinned_without_changing_default_feed(client):
    services = client.app.state.services
    services.store.save_data_profile("market", {"source": "exchange:binance", "profiles": {}})
    before = services.store.data_profile("market")
    response = client.post("/api/v1/strategies/jobs/demo", json={"strategy": "ema"})
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["source"] == "demo" and job["source_pinned"]
    services.strategies.tick()
    observed = services.strategies.journal.monitor(job["id"], 100)
    assert observed["observations"] and observed["job"]["error"] is None
    assert services.store.data_profile("market") == before
