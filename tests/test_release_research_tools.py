"""Acceptance for portable research, comparable benchmarks and bounded operation evidence."""

import copy
import json
from contextlib import nullcontext
from types import SimpleNamespace

import psutil
import pytest
from test_forecasting import candles
from test_provider_history import source

from sibyl.forecasting.contracts import ForecastRequest
from sibyl.forecasting.engine import fingerprint
from sibyl.forecasting.service import ForecastModels
from sibyl.market_data.health_history import ProviderHistory
from sibyl.models import BacktestRequest
from sibyl.operations.resources import ProcessResources
from sibyl.services.markets.service import Market
from sibyl.storage import Store
from sibyl.strategies.backtest import BacktestEngine
from sibyl.strategies.research.benchmarks import simulate


@pytest.fixture
def portable_model(client):
    from sibyl.forecasting.contracts import TrainForecast
    from sibyl.market_data.archive import iso, milliseconds, step_ms

    service = client.app.state.services.forecasts
    data = candles()
    source = {"source": "demo", "source_label": "Demo", "environment": "demo"}
    service.market.archive.capture(source, "BTC/USDT", "1d", data)
    dataset = service.market.archive.snapshot(
        source,
        "BTC/USDT",
        "1d",
        data[0]["timestamp"],
        iso(milliseconds(data[-1]["timestamp"]) + step_ms("1d")),
    )
    return (
        service,
        data,
        dataset,
        TrainForecast(input_kind="saved_dataset", dataset_id=dataset["id"], max_horizon=14),
    )


def test_reference_portfolios_use_exact_evaluation_window_and_leave_strategy_unchanged():
    data = candles(360)
    request = BacktestRequest(strategy="ema", candles=360, benchmark_interval=11)
    result = BacktestEngine().run(data, request)
    assert set(result["benchmarks"]) == {"buy_hold", "cash", "installments", "balanced"}
    assert result["benchmarks"]["buy_hold"]["return_pct"] == pytest.approx(result["benchmark_pct"])
    assert result["benchmarks"]["buy_hold"]["curve"] == result["benchmark_curve"]
    assert result["benchmarks"]["cash"]["sharpe"] is None
    for item in result["benchmarks"].values():
        assert item["curve"][0]["timestamp"] == result["curve"][0]["timestamp"]
        assert item["curve"][-1]["timestamp"] == result["curve"][-1]["timestamp"]
        assert item["fees"] == pytest.approx(sum(fill["fee"] for fill in item["fills"]))
    changed = BacktestEngine().run(data, request.model_copy(update={"benchmark_interval": 31}))
    for key in ("curve", "fills", "metrics", "final_equity", "benchmark_pct"):
        assert result[key] == changed[key]
    assert result["benchmarks"]["installments"] != changed["benchmarks"]["installments"]


@pytest.mark.parametrize("kind", ["installments", "balanced"])
def test_scheduled_references_charge_both_sides_and_cannot_see_future_opens(kind):
    data = candles(360, flat=True)
    body = BacktestRequest(candles=360, fee_bps=100, slippage_bps=100, benchmark_interval=20)
    result = simulate(data, body, kind)
    assert result["final_equity"] < body.capital
    assert result["fees"] > 0 and result["fills"][-1]["side"] == "sell"
    changed = copy.deepcopy(data)
    for row in changed[200:]:
        row.update(open=400.0, close=400.0)
    later = simulate(changed, body, kind)
    assert result["curve"][:200] == later["curve"][:200]
    zero = simulate(data, body.model_copy(update={"fee_bps": 0, "slippage_bps": 0}), kind)
    assert zero["final_equity"] == pytest.approx(body.capital)
    assert zero["return_pct"] == pytest.approx(0)


def test_bundle_roundtrip_refits_offline_in_unverified_namespace(portable_model, tmp_path, monkeypatch):
    service, _, _, body = portable_model
    original = service.train(body)["model"]
    document = service.bundles.export(original["id"])
    other_store = Store(tmp_path / "other")
    market = Market(service.market.settings, other_store)
    other = ForecastModels(market, other_store)
    monkeypatch.setattr(market, "candles", lambda *a, **k: pytest.fail("Import must be offline"))
    imported = other.bundles.import_bundle(json.dumps(document).encode())
    meta = imported["model"]
    assert meta["environment"] == "imported" and meta["source"].startswith("import:")
    assert not meta["imported_from"]["verified"] and meta["imported_from"]["recorded_fit_matches_local"]
    assert other.export(meta["id"])["artifact"] == document["model"]["artifact"]
    assert other.forecast(meta["id"], ForecastRequest(horizon=7))["environment"] == "imported"
    assert other.bundles.import_bundle(json.dumps(document).encode())["import_result"]["duplicate"]
    assert len(other.list()["items"]) == 1
    # Re-export/re-import remains unverified, including without original source archive access.
    assert other.bundles.export(meta["id"])["dataset"]["dataset"]["source_verified"] is False
    market.close()


@pytest.mark.parametrize("tamper", ["hash", "engine", "gap", "nan", "duplicate"])
def test_malformed_bundles_leave_no_partial_model_and_release_training_lock(portable_model, tamper):
    service, _, _, body = portable_model
    original = service.train(body)["model"]
    document = service.bundles.export(original["id"])
    if tamper == "hash":
        document["model"]["artifact"]["engine"] = "other"
    elif tamper == "engine":
        document["model"]["metadata"]["engine"] = "other"
    elif tamper == "gap":
        document["dataset"]["candles"][20]["timestamp"] = document["dataset"]["candles"][19]["timestamp"]
    elif tamper == "nan":
        document["dataset"]["candles"][20]["close"] = float("nan")
    if tamper not in {"nan", "hash"}:
        document["digest"] = fingerprint({k: v for k, v in document.items() if k != "digest"})
    content = json.dumps(document).encode()
    if tamper == "duplicate":
        content = content.replace(b'"schema": 1', b'"schema": 1, "schema": 1', 1)
    with pytest.raises(ValueError):
        service.bundles.import_bundle(content)
    assert not service._training.locked()
    assert len(service.list()["items"]) == 1


def test_import_never_trusts_uploaded_fit_even_with_valid_hashes(portable_model):
    service, _, _, body = portable_model
    document = service.bundles.export(service.train(body)["model"]["id"])
    document["model"]["artifact"]["evaluation"][0]["model"]["mae"] = 0
    document["model"]["metadata"]["fingerprint"] = fingerprint(
        {"dataset": document["dataset"]["dataset"], "artifact": document["model"]["artifact"]}
    )
    document["digest"] = fingerprint({k: v for k, v in document.items() if k != "digest"})
    result = service.bundles.import_bundle(json.dumps(document).encode())
    assert result["model"]["imported_from"]["recorded_fit_matches_local"] is False
    assert result["evaluation"][0]["model"]["mae"] > 0


def test_archive_preserves_outputs_and_requires_fresh_revision(portable_model):
    service, _, _, body = portable_model
    identity = service.train(body)["model"]["id"]
    output = service.forecast(identity, ForecastRequest(horizon=7))
    archived = service.archive(identity, True, 0)
    assert archived["model"]["archived"] and service.list()["items"] == []
    assert len(service.list(True)["items"]) == 1 and service.output(output["id"]) == output
    with pytest.raises(ValueError, match="archived"):
        service.forecast(identity, ForecastRequest())
    with pytest.raises(ValueError, match="changed"):
        service.archive(identity, False, 0)
    assert not service.archive(identity, False, 1)["model"]["archived"]
    assert len(service.list()["items"]) == 1


def test_latency_histogram_persists_upper_bounds_and_reports_legacy_coverage(store):
    history = ProviderHistory(store)
    for latency in [10, 11, 25, 26, 100, 60000]:
        history.record(source(), "profile", latency, None)
    result = ProviderHistory(store).read("binance")["latency_distribution"]
    assert result["samples"] == 6 and result["coverage_pct"] == 100
    assert result["p50_upper_ms"] == 25 and result["p95_upper_ms"] is None
    assert result["overflow_samples"] == 1
    with store.db() as db:
        db.execute("UPDATE provider_read_hours SET requests=requests+4,successes=successes+4")
    result = history.read("binance")["latency_distribution"]
    assert result["status"] == "partial" and result["coverage_pct"] == 60
    assert result["p50_upper_ms"] == 25


def test_resource_metrics_use_elapsed_process_cpu_and_cache_without_provider_reads(store, monkeypatch):
    clock, cpu = [0.0], [10.0]
    process = SimpleNamespace(
        oneshot=nullcontext,
        cpu_times=lambda: SimpleNamespace(user=cpu[0], system=2.0),
        memory_info=lambda: SimpleNamespace(rss=123456),
        num_threads=lambda: 3,
    )
    monitor = ProcessResources(store, process=process, clock=lambda: clock[0])
    first = monitor.snapshot()
    assert first["cpu_percent"] is None and first["rss_bytes"] == 123456
    clock[0], cpu[0] = 6.0, 13.0
    second = monitor.snapshot()
    assert second["cpu_percent"] == 50 and second["sample_seconds"] == 6
    clock[0], cpu[0] = 7.0, 100.0
    assert monitor.snapshot() == second
    monkeypatch.setattr(
        "sibyl.operations.resources.psutil.Process", lambda: (_ for _ in ()).throw(psutil.AccessDenied())
    )
    partial = ProcessResources(store).snapshot()
    assert partial["cpu_percent"] is None and partial["status"] == "partial"


def test_bundle_http_download_can_be_imported_unchanged_and_source_cannot_be_promoted(
    portable_model, client, monkeypatch
):
    service, _, _, body = portable_model
    identity = service.train(body)["model"]["id"]
    response = client.get(f"/api/v1/forecast-models/{identity}/bundle")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    imported = client.post(
        "/api/v1/forecast-models/import",
        content=response.content,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert imported.status_code == 201
    model = imported.json()["model"]
    monkeypatch.setattr(
        service.market, "snapshot", lambda *a, **k: pytest.fail("Unverified source cannot read a provider")
    )
    blocked = client.post(
        f"/api/v1/forecast-models/{model['id']}/forecasts", json={"input_kind": "current_feed"}
    )
    assert blocked.status_code == 400 and "unverified" in blocked.json()["detail"]
    saved = client.post(
        f"/api/v1/forecast-models/{model['id']}/forecasts", json={"input_kind": "saved_input", "horizon": 7}
    )
    assert saved.status_code == 201
    assert client.post(f"/api/v1/forecast-models/outputs/{saved.json()['id']}/track").status_code == 400
    monkeypatch.setattr("sibyl.api.forecasting.MAX_BUNDLE", 16)
    assert client.post("/api/v1/forecast-models/import", content=b" " * 17).status_code == 413


def test_bundle_budget_failure_is_atomic_and_fit_admission_is_shared(portable_model, monkeypatch):
    service, _, _, body = portable_model
    content = json.dumps(service.bundles.export(service.train(body)["model"]["id"])).encode()
    service._training.acquire()
    try:
        with pytest.raises(ValueError, match="already training"):
            service.bundles.import_bundle(content)
    finally:
        service._training.release()
    with service.store.db() as db:
        # Fill the dataset budget with existing evidence rows; importing must leave no orphan model/input.
        seed = ("{}", "[]")
        db.executemany(
            "INSERT INTO candle_datasets VALUES(?,?,?)",
            [(f"budget-{i}", seed[0], seed[1]) for i in range(999)],
        )
    with pytest.raises(ValueError, match="dataset budget"):
        service.bundles.import_bundle(content)
    assert len(service.list()["items"]) == 1 and not service._training.locked()
    with service.store.db() as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM candle_datasets WHERE json_extract(metadata,'$.environment')='imported'"
            ).fetchone()[0]
            == 0
        )


def test_native_specialists_explain_new_controls_and_read_recorded_status(client, monkeypatch):
    from test_agent_guidance import forbid_reads, tool_call

    forbid_reads(client, monkeypatch)
    assert tool_call(client, "broker", "strategy_help", topic="benchmarks")["url"] == "/strategies"
    assert tool_call(client, "chronos", "page_help", topic="portability")["url"] == "/forecast?tab=models"
    policy = tool_call(client, "technician", "notification_history")
    assert policy["policy"]["enabled"] is False and policy["url"] == "/alerts?tab=inbox"
    health = tool_call(client, "technician", "workspace_operations")["health"]
    assert "Current Python API process" in health["resources"]["scope"]
