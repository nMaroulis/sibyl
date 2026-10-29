"""Chronos research acceptance: causality, independent evaluation and durable native-agent evidence."""

import copy
import json
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from pydantic import ValidationError

from sibyl.forecasting.contracts import ForecastRequest, TrainForecast
from sibyl.forecasting.engine import features, fingerprint, predict, train
from sibyl.forecasting.service import ForecastModels


def candles(count=720, *, flat=False, timeframe="1d"):
    rng = np.random.default_rng(172)
    returns = np.zeros(count)
    for index in range(1, count):
        returns[index] = 0.7 * returns[index - 1] + rng.normal(0, 0.008)
    close = np.full(count, 100.0) if flat else 100 * np.exp(np.cumsum(returns))
    step = timedelta(days=1) if timeframe == "1d" else timedelta(hours=1)
    start = datetime(2020, 1, 1, tzinfo=UTC)
    return [
        {
            "timestamp": (start + index * step).isoformat(),
            "open": float(price),
            "high": float(price * 1.01),
            "low": float(price * 0.99),
            "close": float(price),
            "volume": 1000.0,
        }
        for index, price in enumerate(close)
    ]


@pytest.fixture
def model_input(client):
    service = client.app.state.services.forecasts
    data = candles()
    metadata = {"source": "demo", "source_label": "Demo", "environment": "demo"}
    service.market.archive.capture(metadata, "BTC/USDT", "1d", data)
    end = (datetime.fromisoformat(data[-1]["timestamp"]) + timedelta(days=1)).isoformat()
    dataset = service.market.archive.snapshot(metadata, "BTC/USDT", "1d", data[0]["timestamp"], end)
    body = TrainForecast(input_kind="saved_dataset", dataset_id=dataset["id"], max_horizon=14)
    return service, data, dataset, body


def test_exact_fit_is_reproducible_and_coefficients_learn_causal_return_structure():
    data = candles()
    body = TrainForecast(max_horizon=7)
    first, second = train(data, body), train(data, body)
    assert fingerprint(first) == fingerprint(second)
    one_day = first["models"][0]
    # Coefficients are stored in training-standardized units; recover raw lag sensitivity.
    sensitivity = one_day["coefficients"][0] / one_day["scale"][0]
    assert 0.4 < sensitivity < 0.95
    assert one_day["training_samples"] == int(720 * 0.6) - body.lags - 1
    assert one_day["calibration_samples"] == int(720 * 0.8) - int(720 * 0.6) - 1
    assert all(np.isfinite(item["model"]["rmse"]) for item in first["evaluation"])


def test_causal_features_never_read_prices_after_their_origin():
    original = np.log([row["close"] for row in candles(360)])
    changed = original.copy()
    changed[200:] += 0.4
    np.testing.assert_array_equal(features(original, 14)[:186], features(changed, 14)[:186])


def test_test_prices_cannot_change_training_scalers_coefficients_or_calibration():
    data = candles()
    changed = copy.deepcopy(data)
    for index in range(576, 720):
        changed[index]["close"] = float(changed[index]["close"] * np.exp((index - 575) * 0.005))
    first, second = train(data, TrainForecast()), train(changed, TrainForecast())
    assert first["models"] == second["models"]
    assert first["evaluation"] != second["evaluation"]


def test_calibration_prices_change_band_but_never_training_coefficients():
    data = candles()
    changed = copy.deepcopy(data)
    for index in range(432, 576):
        changed[index]["close"] *= 1.5
    first, second = train(data, TrainForecast()), train(changed, TrainForecast())
    for a, b in zip(first["models"], second["models"], strict=True):
        assert {k: v for k, v in a.items() if k != "radius"} == {k: v for k, v in b.items() if k != "radius"}
    assert any(a["radius"] != b["radius"] for a, b in zip(first["models"], second["models"], strict=True))


def test_evaluation_metrics_match_complete_trace_and_purged_date_partitions():
    result = train(candles(), TrainForecast())
    for score in result["evaluation"]:
        trace = score["trace"]
        actual = np.array([p["actual"] for p in trace])
        predicted = np.array([p["predicted"] for p in trace])
        assert score["samples"] == 720 - 576 - score["horizon"] == len(trace)
        assert score["model"]["mae"] == pytest.approx(float(np.mean(np.abs(actual - predicted))))
        assert all(
            result["partitions"]["test"]["start"]
            <= p["origin"]
            < p["timestamp"]
            <= result["partitions"]["test"]["end"]
            for p in trace
        )
        coverage = sum(p["lower"] <= p["actual"] <= p["upper"] for p in trace) / len(trace) * 100
        assert score["coverage_pct"] == pytest.approx(coverage)
        assert all(p["naive"] == pytest.approx(candles()[576 + i]["close"]) for i, p in enumerate(trace))


def test_constant_prices_remain_finite_with_undefined_benchmark_skill():
    data = candles(360, flat=True)
    artifact = train(data, TrainForecast())
    result = predict(artifact, data[-90:], 30)
    assert all(point["value"] == pytest.approx(100) for point in result["points"])
    assert all(point["lower"] <= point["value"] <= point["upper"] for point in result["points"])
    assert all(item["mae_skill_vs_naive_pct"] is None for item in artifact["evaluation"])
    assert result["shift"]["outside_training_range"] == 0


@pytest.mark.parametrize(
    "kind", ["gap", "duplicate", "reverse", "zero", "negative", "bool", "nan", "future", "short"]
)
def test_invalid_daily_inputs_fail_explicitly(kind):
    data = candles(360)
    if kind == "gap":
        data.pop(55)
    elif kind == "duplicate":
        data[50] = data[49]
    elif kind == "reverse":
        data.reverse()
    elif kind == "future":
        delta = datetime.now(UTC) + timedelta(days=2) - datetime.fromisoformat(data[-1]["timestamp"])
        for row in data:
            row["timestamp"] = (datetime.fromisoformat(row["timestamp"]) + delta).isoformat()
    elif kind == "short":
        data = data[:100]
    else:
        data[50]["close"] = {"zero": 0, "negative": -1, "bool": True, "nan": float("nan")}[kind]
    with pytest.raises(ValueError):
        train(data, TrainForecast())


@pytest.mark.parametrize(
    "changes",
    [
        {"alpha": True},
        {"alpha": 0},
        {"alpha": float("nan")},
        {"lags": 20},
        {"max_horizon": 31},
        {"candles": True},
        {"candles": 721},
        {"input_kind": "saved_dataset"},
        {"dataset_id": "a" * 64},
        {"symbol": "ETH/USD/XYZ"},
        {"label": "bad\nlabel"},
    ],
)
def test_request_limits_reject_ambiguous_or_unbounded_training(changes):
    with pytest.raises(ValidationError):
        TrainForecast(**changes)


def test_offline_model_registry_rerun_and_forecast_survive_restart(model_input, monkeypatch):
    service, data, dataset, body = model_input
    monkeypatch.setattr(
        service.market, "candles", lambda *a, **k: pytest.fail("Saved research attempted a provider read")
    )
    first = service.train(body)
    identity = first["model"]["id"]
    assert first["model"]["dataset"]["digest"] == dataset["digest"]
    assert first["model"]["environment"] == "demo"
    rerun = service.rerun(identity)
    assert rerun["model"]["series_id"] == first["model"]["series_id"]
    assert rerun["model"]["version"] == 2 and rerun["model"]["parent_id"] == identity
    assert rerun["model"]["fingerprint"] == first["model"]["fingerprint"]
    forecast = service.forecast(identity, ForecastRequest(horizon=7))
    assert forecast["stale"] and forecast["input_kind"] == "saved_input"
    assert forecast["points"] == predict(service.export(identity)["artifact"], data[-90:], 7)["points"]
    reopened = ForecastModels(service.market, service.store)
    assert reopened.output(forecast["id"]) == forecast
    assert reopened.detail(identity)["outputs"][0]["id"] == forecast["id"]
    assert len(reopened.list()["items"]) == 2


def test_failed_training_saves_no_partial_version_and_releases_admission(model_input, monkeypatch):
    service, _, _, body = model_input
    original = np.linalg.solve
    monkeypatch.setattr(
        np.linalg, "solve", lambda *a: (_ for _ in ()).throw(ValueError("Controlled fit failure"))
    )
    with pytest.raises(ValueError):
        service.train(body)
    assert not service.list()["items"]
    monkeypatch.setattr(np.linalg, "solve", original)
    assert service.train(body)["model"]["version"] == 1
    service._training.acquire()
    try:
        with pytest.raises(ValueError, match="already training"):
            service.train(body)
    finally:
        service._training.release()


def test_models_are_bounded_and_have_no_automatic_training_or_provider_fallback(client, monkeypatch):
    service = client.app.state.services.forecasts
    assert service.list()["items"] == []
    monkeypatch.setattr(service.market, "candles", lambda *a, **k: [])
    with pytest.raises(ValueError, match="fewer than 360"):
        service.train(TrainForecast())
    assert not service.list()["items"]
    for name in ("forecast_models", "forecast_outputs"):
        with service.store.db() as db:
            assert db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] == 0


def test_forecasts_retain_twenty_per_model_and_reject_foreign_saved_output(model_input):
    service, _, _, body = model_input
    first = service.train(body)["model"]
    other = service.train(body)["model"]
    initial = service.forecast(first["id"], ForecastRequest(horizon=7))
    for _ in range(21):
        service.forecast(first["id"], ForecastRequest(horizon=7))
    assert len(service.outputs(first["id"])) == 20
    with pytest.raises(LookupError):
        service.output(initial["id"])
    recent = service.outputs(first["id"])[0]
    view = service.preview(first["id"], 3, run_id=recent["id"])
    assert len(view["points"]) == view["horizon"] == 3
    assert view["saved_horizon"] == 7 and "result_fingerprint" not in view
    assert view["saved_result_fingerprint"] == service.output(recent["id"])["result_fingerprint"]
    with pytest.raises(ValueError, match="does not belong"):
        service.preview(other["id"], 7, run_id=recent["id"])
    with pytest.raises(ValueError, match="does not include"):
        service.preview(first["id"], 14, run_id=recent["id"])


@pytest.mark.parametrize("field", ["coefficients", "source", "parameters"])
def test_model_integrity_covers_weights_provenance_and_displayed_parameters(model_input, field):
    service, _, _, body = model_input
    model = service.train(body)["model"]
    with service.store.db() as db:
        raw = json.loads(
            db.execute("SELECT payload FROM forecast_models WHERE id=?", (model["id"],)).fetchone()[0]
        )
        if field == "coefficients":
            raw["artifact"]["models"][0]["coefficients"][0] += 1
        elif field == "source":
            raw["metadata"]["source"] = "other-source"
        else:
            raw["metadata"]["parameters"]["lags"] = 5
        db.execute("UPDATE forecast_models SET payload=? WHERE id=?", (json.dumps(raw), model["id"]))
    with pytest.raises(ValueError, match="check failed"):
        service.detail(model["id"])


def test_output_corruption_is_detected_without_a_provider_read(model_input):
    service, _, _, body = model_input
    model = service.train(body)["model"]
    result = service.forecast(model["id"], ForecastRequest(horizon=7))
    result["points"][0]["value"] += 1
    with service.store.db() as db:
        db.execute("UPDATE forecast_outputs SET payload=? WHERE id=?", (json.dumps(result), result["id"]))
    with pytest.raises(ValueError, match="integrity"):
        service.output(result["id"])


def test_http_training_offline_evidence_and_native_chronos_are_scoped(client, model_input, monkeypatch):
    service, _, _, body = model_input
    monkeypatch.setattr(service.market, "candles", lambda *a, **k: pytest.fail("Unexpected network read"))
    response = client.post("/api/v1/forecast-models", json=body.model_dump())
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    identity = response.json()["model"]["id"]
    response = client.post(f"/api/v1/forecast-models/{identity}/forecasts", json={"horizon": 7})
    assert response.status_code == 201
    result = response.json()
    assert client.get(f"/api/v1/forecast-models/outputs/{result['id']}").json()["points"] == result["points"]
    count = len(service.outputs(identity))
    reply = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "chronos",
            "message": "Explain this forecast",
            "context": {
                "symbol": "BTC/USDT",
                "horizon": 7,
                "forecast_model_id": identity,
                "forecast_run_id": result["id"],
            },
        },
    )
    assert reply.status_code == 200, reply.text
    assert reply.json()["evidence"]["model_id"] == identity
    assert "Trained research model" in reply.json()["answer"]
    assert len(service.outputs(identity)) == count
    assert client.get(f"/api/v1/forecast-models/{identity}/export").json()["artifact"]["models"]
    assert client.get("/api/v1/forecast-models/missing").status_code == 404
    assert client.post("/api/v1/forecast-models", json={"api_key": "do-not-reflect"}).status_code == 422


def test_current_forecast_is_pinned_to_original_source_and_never_refits(model_input, monkeypatch):
    service, data, _, body = model_input
    model = service.train(body)["model"]
    before = service.export(model["id"])
    seen = []
    original = service.market.candles

    def observe(symbol, limit, timeframe):
        seen.append((service.market.metadata()["source"], symbol, limit, timeframe))
        return data[-90:]

    monkeypatch.setattr(service.market, "candles", observe)
    output = service.forecast(model["id"], ForecastRequest(input_kind="current_feed", horizon=7))
    assert seen == [("demo", "BTC/USDT", 90, "1d")]
    assert output["input_kind"] == "current_feed"
    assert service.export(model["id"]) == before
    monkeypatch.setattr(service.market, "candles", lambda *a: data[:90])
    with pytest.raises(ValueError, match="predate"):
        service.forecast(model["id"], ForecastRequest(input_kind="current_feed", horizon=7))
    monkeypatch.setattr(service.market, "candles", original)


def test_forecast_dates_are_future_target_closes_not_already_observed_open_labels():
    data = candles(360)
    artifact = train(data, TrainForecast(max_horizon=7))
    result = predict(artifact, data[-90:], 7)
    last_open = datetime.fromisoformat(data[-1]["timestamp"])
    origin = datetime.fromisoformat(result["origin"])
    assert origin == last_open + timedelta(days=1)
    assert datetime.fromisoformat(result["points"][0]["timestamp"]) == origin + timedelta(days=1)
    assert datetime.fromisoformat(result["points"][-1]["timestamp"]) == origin + timedelta(days=7)


def test_registry_budget_rejects_training_before_reading_a_source(client, monkeypatch):
    service = client.app.state.services.forecasts
    with service.store.db() as db:
        db.executemany(
            "INSERT INTO forecast_models VALUES(?,?,?,?,?)",
            [(f"{i:032x}", f"{i:032x}", 1, "{}", "{}") for i in range(100)],
        )
    monkeypatch.setattr(service, "_input", lambda *a: pytest.fail("Budget checked after source read"))
    with pytest.raises(ValueError, match="budget"):
        service.train(TrainForecast())


def test_saved_training_rejects_wrong_market_and_unavailable_horizon(model_input):
    service, _, _, body = model_input
    with pytest.raises(ValueError, match="exact selected"):
        service.train(body.model_copy(update={"symbol": "ETH/USDT"}))
    model = service.train(body.model_copy(update={"max_horizon": 7}))["model"]
    with pytest.raises(ValueError, match="horizon"):
        service.forecast(model["id"], ForecastRequest(horizon=8))
    with pytest.raises(ValueError, match="horizon"):
        service.detail(model["id"], 8)
    assert service.outputs(model["id"]) == []


def test_forecast_from_latest_feed_never_falls_back_after_source_failure(model_input, monkeypatch):
    service, _, _, body = model_input
    model = service.train(body)["model"]

    def unavailable(*args, **kwargs):
        raise ValueError("Controlled unavailable source")

    monkeypatch.setattr(service.market, "candles", unavailable)
    with pytest.raises(ValueError, match="unavailable"):
        service.forecast(model["id"], ForecastRequest(input_kind="current_feed", horizon=7))
    assert service.outputs(model["id"]) == []
    assert service.forecast(model["id"], ForecastRequest(horizon=7))["input_kind"] == "saved_input"


def test_native_chronos_can_discover_and_inspect_a_version_without_page_context(client, model_input):

    from protolink import Task

    service, _, _, body = model_input
    model = service.train(body.model_copy(update={"max_horizon": 7}))["model"]
    owner = client.app.state.services.agents

    async def read():
        url = owner.agents["chronos"].card.url
        registry = await owner.network.client.send_task(url, Task.create_tool_call("trained_models", {}))
        report = await owner.network.client.send_task(
            url, Task.create_tool_call("model_report", {"model_id": model["id"]})
        )
        forecast = await owner.network.client.send_task(
            url, Task.create_tool_call("price_forecast", {"model_id": model["id"]})
        )
        return registry, report, forecast

    # Execute on the application's own native runtime loop.
    responses = client.portal.call(read)
    for response in responses:
        response.raise_for_status()
    results = [response.get_last_item().parts[-1].as_tool_output().result for response in responses]
    assert model["id"] in json.dumps(results[0])
    assert "evaluation" in results[1]
    assert results[2]["trained"] and results[2]["horizon"] == 7
    assert service.outputs(model["id"]) == []
