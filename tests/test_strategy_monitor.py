"""Strategy monitor contract: durable audit events, atomic paper fills, and honest reads."""

import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import pytest
from pydantic import ValidationError

from sibyl.models import BacktestRequest
from sibyl.services.market import Market
from sibyl.services.strategies import Strategies, strategy_indicators


@pytest.fixture
def engine(settings, store, monkeypatch):
    """A controllable market emits deterministic closed candles without any network."""
    import sibyl.services.strategies as module

    market = Market(settings, store)
    history = market.candles(limit=100)
    quote, signal = [100.0], [1]
    monkeypatch.setattr(market, "candles", lambda *args: history)
    monkeypatch.setattr(market, "price", lambda symbol: quote[0])
    monkeypatch.setattr(module, "signals", lambda frame, *args: pd.Series([signal[0]] * len(frame)))
    return Strategies(market, store), history, quote, signal


def advance(history):
    history.append(
        {
            **history[-1],
            "timestamp": (pd.Timestamp(history[-1]["timestamp"]) + pd.Timedelta(days=1)).isoformat(),
        }
    )


def test_read_only_monitor_and_quote_updates_do_not_repeat_decisions(engine):
    service, history, quote, signal = engine
    job = service.start(BacktestRequest())
    assert service.journal.monitor(job["id"])["observations"] == []
    service.tick()
    first = service.journal.monitor(job["id"])
    assert first["event_count"] == 2
    assert first["markers"][0]["action"] == "BUY"
    assert first["markers"][0]["slippage_bps"] == pytest.approx(5)
    assert first["job"]["fees_paid"] == pytest.approx(first["markers"][0]["fee"])
    # Monitor reads and repeated quote ticks cannot execute a duplicate candle.
    service.journal.monitor(job["id"])
    quote[0] = 110
    service.tick()
    second = service.journal.monitor(job["id"])
    assert len(second["observations"]) == 2
    assert second["event_count"] == first["event_count"]
    assert len(second["job"]["fills"]) == 1
    assert second["job"]["equity"] == pytest.approx(second["job"]["quantity"] * 110)
    restarted = Strategies(service.market, service.store)
    restarted.tick()
    assert restarted.journal.monitor(job["id"])["event_count"] == 2


def test_journal_records_skips_holds_and_net_realized_pnl(engine):
    service, history, quote, signal = engine
    job = service.start(BacktestRequest(fee_bps=10, slippage_bps=5, max_trades=1))
    service.tick()
    advance(history)
    service.tick()
    assert service.journal.events(job["id"])["items"][0]["action"] == "SKIP_BUY"
    signal[0] = 0
    advance(history)
    service.tick()
    assert service.journal.events(job["id"])["items"][0]["action"] == "HOLD"
    signal[0], quote[0] = -1, 120
    advance(history)
    service.tick()
    result = service.journal.monitor(job["id"])
    assert result["job"]["status"] == "completed"
    assert result["job"]["realized_pnl"] == pytest.approx(result["job"]["cash"] - 10000)
    assert result["job"]["fees_paid"] == pytest.approx(sum(fill["fee"] for fill in result["job"]["fills"]))
    assert result["markers"][-1]["action"] == "SELL"
    assert result["markers"][-1]["slippage_bps"] == pytest.approx(-5)
    assert "limit" in result["markers"][-1]["reason"]


def test_stop_is_terminal_preserves_position_and_is_idempotent(engine):
    service, history, quote, signal = engine
    job = service.start(BacktestRequest())
    service.tick()
    before = service.journal.job(job["id"])
    stopped = service.status(job["id"], "stopped")
    assert stopped["quantity"] == before["quantity"]
    assert stopped["cash"] == before["cash"]
    assert stopped["stopped_at"]
    service.status(job["id"], "stopped")
    with pytest.raises(ValueError, match="completed or stopped"):
        service.status(job["id"], "running")
    with pytest.raises(ValueError):
        service.status(job["id"], "paused")
    quote[0] = 1
    advance(history)
    service.tick()
    assert service.journal.job(job["id"])["equity"] == before["equity"]
    assert len(service.journal.events(job["id"], action="STOP")["items"]) == 1


def test_pause_resume_and_source_change_are_recorded(engine):
    service, history, quote, signal = engine
    job = service.start(BacktestRequest())
    service.tick()
    service.status(job["id"], "paused")
    n = len(service.journal.monitor(job["id"])["observations"])
    service.tick()
    assert len(service.journal.monitor(job["id"])["observations"]) == n
    service.status(job["id"], "running")
    service.market.settings.mode = "live"
    service.tick()
    assert service.journal.job(job["id"])["status"] == "paused"
    assert service.journal.events(job["id"])["items"][0]["action"] == "PAUSE"
    with pytest.raises(ValueError, match="source changed"):
        service.status(job["id"], "running")


def test_failed_decision_does_not_persist_partial_balances_or_advance_cursor(engine, monkeypatch):
    service, history, quote, signal = engine
    job = service.start(BacktestRequest())
    original_decision = service._decision

    def fail_after_mutation(*args):
        original_decision(*args)
        raise RuntimeError("do not expose this provider secret")

    monkeypatch.setattr(service, "_decision", fail_after_mutation)
    service.tick()
    failed = service.journal.monitor(job["id"])
    assert failed["job"]["cash"] == 10000
    assert failed["job"]["quantity"] == 0
    assert failed["job"]["last_candle"] is None
    assert failed["observations"] == []
    assert failed["markers"][0]["action"] == "ERROR"
    assert "provider secret" not in json.dumps(failed)
    service.tick()
    assert len(service.journal.events(job["id"], action="ERROR")["items"]) == 1
    monkeypatch.setattr(service, "_decision", original_decision)
    service.tick()
    assert service.journal.job(job["id"])["quantity"] > 0
    assert service.journal.job(job["id"])["error"] is None


def test_event_cursors_and_export_include_full_history(engine):
    service, history, quote, signal = engine
    job = service.start(BacktestRequest())
    service.tick()
    advance(history)
    service.tick()
    page = service.journal.events(job["id"], limit=2)
    assert page["has_more"]
    older = service.journal.events(job["id"], limit=2, before=page["next_before"])
    assert older["items"][0]["action"] == "START"
    assert not set(e["id"] for e in page["items"]) & set(e["id"] for e in older["items"])
    rows = list(csv.DictReader(io.StringIO("".join(service.journal.export(job["id"])))))
    assert [row["action"] for row in rows] == ["START", "BUY", "SKIP_BUY"]
    fills = list(csv.DictReader(io.StringIO("".join(service.journal.export(job["id"], "fills")))))
    assert len(fills) == 1
    assert fills[0]["reference_price"] == "100.0"
    assert service.journal.events(job["id"], action="fills")["matching_count"] == 1


def test_csv_snapshot_and_formula_neutralization(engine):
    service, history, quote, signal = engine
    job = service.start(BacktestRequest())
    service.journal.save(job, service._event(job, "HOLD", "=formula()"))
    export = service.journal.export(job["id"])
    service.journal.save(job, service._event(job, "HOLD", "later"))
    rows = list(csv.DictReader(io.StringIO("".join(export))))
    assert rows[-1]["reason"] == "'=formula()"
    assert not any(row["reason"] == "later" for row in rows)


def test_observations_are_bounded_but_events_are_not(engine):
    service, history, quote, signal = engine
    job = service.start(BacktestRequest())
    # Insert enough samples together to exercise pruning on the next real atomic write.
    sample = json.dumps(
        {"timestamp": job["created_at"], "price": 100, "equity": 10000, "cash": 10000, "position": 0}
    )
    with service.store.db() as db:
        db.executemany(
            "INSERT INTO strategy_observations(job_id,payload) VALUES (?,?)", [(job["id"], sample)] * 2001
        )
    service.tick()
    assert len(service.journal.monitor(job["id"], 2000)["observations"]) == 2000
    assert service.journal.events(job["id"])["matching_count"] == 2


def test_earlier_runs_do_not_get_fabricated_history_or_lifetime_stats(engine):
    service, history, quote, signal = engine
    job = service.start(BacktestRequest())
    with service.store.db() as db:
        db.execute("DELETE FROM strategy_events WHERE job_id = ?", (job["id"],))
    for key in ["statistics_complete", "monitoring_since", "fees_paid", "realized_pnl"]:
        job.pop(key, None)
    job["fills"] = [{"side": "buy", "price": 90, "quantity": 1, "timestamp": job["created_at"]}]
    service._save(job)
    before = service.journal.monitor(job["id"])
    assert before["legacy_fills"] == job["fills"]
    assert before["observations"] == before["markers"] == []
    service.tick()
    after = service.journal.monitor(job["id"])
    assert not after["job"].get("statistics_complete")
    assert len(after["legacy_fills"]) == 1
    assert after["job"]["monitoring_since"]


def test_concurrent_worker_calls_cannot_double_fill(engine):
    service, history, quote, signal = engine
    job = service.start(BacktestRequest())
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: service.tick(), range(4)))
    assert len(service.journal.events(job["id"], action="fills")["items"]) == 1
    assert len(service.journal.monitor(job["id"])["observations"]) == 4


def test_custom_indicator_periods_change_outputs_without_future_dependence(settings, store):
    market = Market(settings, store)
    history = market.candles(limit=120)
    custom = BacktestRequest(
        macd_fast_period=5,
        macd_slow_period=17,
        macd_signal_period=4,
        atr_period=7,
        adx_period=8,
        cmf_period=9,
        tsi_short_period=6,
        tsi_long_period=16,
    )
    full = strategy_indicators(history, custom)
    default = strategy_indicators(history, BacktestRequest())
    prefix = strategy_indicators(history[:100], custom)
    for column in ["macd", "macd_signal", "atr", "adx", "cmf", "tsi"]:
        assert not full[column].equals(default[column])
        pd.testing.assert_series_equal(prefix[column], full[column].iloc[:100])


@pytest.mark.parametrize(
    "changes",
    [
        {"macd_fast_period": 30, "macd_slow_period": 20},
        {"tsi_short_period": 30, "tsi_long_period": 20},
        {"candles": 60, "adx_period": 60},
    ],
)
def test_advanced_period_validation(changes):
    with pytest.raises(ValidationError):
        BacktestRequest(**changes)


def test_monitor_routes_and_run_specific_broker_evidence(client):
    response = client.post("/api/v1/strategies/jobs", json={"symbol": "ETH/USDT"})
    assert response.status_code == 201
    job = response.json()
    detail = client.get(f"/api/v1/strategies/jobs/{job['id']}")
    assert detail.status_code == 200
    assert detail.json()["job"]["id"] == job["id"]
    journal = client.get(f"/api/v1/strategies/jobs/{job['id']}/events")
    assert journal.json()["items"][-1]["action"] == "START"
    csv_response = client.get(f"/api/v1/strategies/jobs/{job['id']}/events.csv")
    assert csv_response.headers["content-type"].startswith("text/csv")
    assert "START" in csv_response.text
    agent = client.post(
        "/api/v1/agents/ask",
        json={"module": "broker", "message": "Explain this run.", "context": {"job_id": job["id"]}},
    )
    assert agent.status_code == 200
    assert agent.json()["evidence"]["selected_run"]["id"] == job["id"]
    assert agent.json()["evidence"]["selected_parameters"]["symbol"] == "ETH/USDT"
    assert "paper execution" in agent.json()["answer"]
    assert client.post(f"/api/v1/strategies/jobs/{job['id']}/stop").json()["status"] == "stopped"
    assert client.post(f"/api/v1/strategies/jobs/{job['id']}/resume").status_code == 400
    assert client.get("/api/v1/strategies/jobs/missing").status_code == 404
    assert client.get(f"/api/v1/strategies/jobs/{job['id']}?limit=2001").status_code == 422


def test_truncated_risk_window_uses_the_prior_observed_equity_as_baseline(engine):
    service, history, quote, signal = engine
    job = service.start(BacktestRequest())
    signal[0] = 0
    job["curve"] = [{"timestamp": str(i), "value": 5000.0} for i in range(720)]
    job["cash"], job["equity"] = 5000.0, 5000.0
    service._save(job)
    service.tick()
    result = service.journal.job(job["id"])
    assert result["curve_baseline"] == 5000
    assert result["metrics"]["max_drawdown"] == 0
    assert len(result["curve"]) == 720


def test_legacy_sale_counts_a_round_trip_even_if_its_cost_basis_is_missing(engine):
    service, history, quote, signal = engine
    job = service.start(BacktestRequest(max_trades=1))
    job.update(cash=0, quantity=2, statistics_complete=False)
    service._save(job)
    signal[0] = -1
    service.tick()
    result = service.journal.job(job["id"])
    assert result["round_trips"] == 1
    assert result["status"] == "completed"
    assert result["completed_returns"] == []


@pytest.mark.parametrize("state", ["stopped", "paused"])
def test_lifecycle_controls_do_not_wait_for_a_slow_provider_and_prevent_pending_fills(
    engine, monkeypatch, state
):
    from threading import Event

    service, history, quote, signal = engine
    job = service.start(BacktestRequest())
    entered, release = Event(), Event()

    def slow_quote(symbol):
        entered.set()
        release.wait(3)
        return 100

    monkeypatch.setattr(service.market, "price", slow_quote)
    with ThreadPoolExecutor(max_workers=2) as pool:
        worker = pool.submit(service.tick)
        assert entered.wait(1)
        try:
            changed = pool.submit(service.status, job["id"], state).result(timeout=1)
            assert changed["status"] == state
        finally:
            release.set()
        worker.result(timeout=2)
    result = service.journal.monitor(job["id"])
    assert result["job"]["status"] == state
    assert result["job"]["fills"] == []
    assert result["observations"] == []
    assert result["job"]["cash"] == 10000
