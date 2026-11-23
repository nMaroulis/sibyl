"""Offline drift and candidate lifecycle; no model is promoted or provider contacted."""

import copy
import json
from datetime import datetime

import numpy as np
import pytest
from test_forecasting import candles

from sibyl.forecasting.contracts import TrainForecast
from sibyl.forecasting.drift import CONFIRMATION, DriftPolicy, Recalibrate, divergence
from sibyl.forecasting.service import ForecastModels


@pytest.fixture
def drift_input(client, monkeypatch):
    owner = client.app.state.services.forecasts
    metadata = dict(source="binance", source_label="Isolated observed series", environment="production")
    data = candles(900)
    for i in range(720, 900):
        price = data[719]["close"] * np.exp((i - 719) * 0.025)
        data[i].update(
            open=float(price), close=float(price), high=float(price * 1.01), low=float(price * 0.99)
        )
    clock = int(datetime.fromisoformat(data[-1]["timestamp"]).timestamp() * 1000) + 86_400_000
    monkeypatch.setattr("sibyl.forecasting.drift.now_ms", lambda: clock)
    owner.market.archive.capture(metadata, "BTC/USDT", "1d", data[:720])
    dataset = owner.market.archive.snapshot(
        metadata, "BTC/USDT", "1d", data[0]["timestamp"], data[720]["timestamp"]
    )
    model = owner.train(TrainForecast(input_kind="saved_dataset", dataset_id=dataset["id"], max_horizon=7))[
        "model"
    ]
    return owner, model, metadata, data


def save(owner, model, **overrides):
    policy = dict(
        revision=owner.drift.state(model["id"])["revision"],
        enabled=True,
        recent_days=30,
        divergence_threshold=0.001,
        min_new_days=30,
        cooldown_days=30,
        confirmation=CONFIRMATION,
    )
    return owner.drift.save(model["id"], DriftPolicy(**(policy | overrides)))


def test_divergence_is_bounded_and_uses_reference_bins_only():
    values = np.linspace(-0.01, 0.01, 100)
    same = divergence(values, values)
    shifted = divergence(values, values + 0.1)
    assert same["js_divergence"] == pytest.approx(0)
    assert 0 < shifted["js_divergence"] < np.log(2)
    assert same["bins"] == shifted["bins"]
    assert sum(shifted["recent_probabilities"]) == pytest.approx(1)
    flat = divergence(np.zeros(100), np.ones(100))
    assert flat["volatility_ratio"] is None and flat["mean_shift_in_reference_std"] is None
    with pytest.raises(ValueError):
        divergence([float("nan")] * 30, values)


def test_model_input_days_are_never_reused_as_recent_evidence(drift_input):
    owner, model, meta, data = drift_input
    initial = owner.drift.check(model["id"])
    assert initial["revision"] == 0 and not initial["policy"]["enabled"]
    assert initial["assessment"]["status"] == "insufficient"
    assert initial["assessment"]["new_candles"] == 0
    owner.market.archive.capture(meta, "BTC/USDT", "1d", data[720:750])
    state = save(owner, model)
    result = owner.drift.check(model["id"])
    assert result["assessment"]["new_candles"] == 30
    assert result["assessment"]["required_candles"] == 31
    assert result["revision"] == state["revision"]


def test_source_environment_gaps_and_corrections_are_explicit(drift_input):
    owner, model, meta, data = drift_input
    owner.market.archive.capture(meta | dict(source="kraken"), "BTC/USDT", "1d", data)
    assert owner.drift.check(model["id"])["assessment"]["new_candles"] == 0
    owner.market.archive.capture(meta, "BTC/USDT", "1d", data[720:])
    save(owner, model)
    first = owner.drift.check(model["id"])["assessment"]
    assert first["status"] == "shift" and first["recent_start"] >= model["dataset"]["end"]
    changed = copy.deepcopy(data[-1])
    changed.update(open=200.0, close=200.0, high=202.0, low=198.0)
    owner.market.archive.capture(meta, "BTC/USDT", "1d", [changed])
    corrected = owner.drift.check(model["id"])["assessment"]
    assert corrected["input_fingerprint"] != first["input_fingerprint"]
    with owner.store.db() as db:
        db.execute(
            "DELETE FROM candle_rows WHERE timestamp=? AND series_id=(SELECT id FROM candle_series WHERE json_extract(metadata,'$.source')='binance')",
            (int(datetime.fromisoformat(data[-3]["timestamp"]).timestamp() * 1000),),
        )
    with pytest.raises(ValueError, match="consecutive"):
        owner.drift.check(model["id"])


def test_candidate_fit_is_pinned_idempotent_versioned_and_does_not_change_parent(drift_input):
    owner, model, meta, data = drift_input
    original = owner.export(model["id"])
    owner.market.archive.capture(meta, "BTC/USDT", "1d", data[720:])
    state = save(owner, model)
    body = Recalibrate(model_id=model["id"], revision=state["revision"])
    result = owner.drift.recalibrate(body)
    assert result["status"] == "completed"
    assert result["candidate_version"] == 2 and result["candidate_id"] != model["id"]
    candidate = owner.export(result["candidate_id"])
    assert candidate["metadata"]["parent_id"] == model["id"]
    assert candidate["metadata"]["source"] == model["source"]
    assert candidate["metadata"]["dataset"]["end"] > model["dataset"]["end"]
    assert candidate["metadata"]["dataset"]["count"] == model["dataset"]["count"]
    assert len(result["evaluation"]) == 7
    assert owner.export(model["id"]) == original
    assert owner.drift.recalibrate(body) == result
    assert len(owner.list()["items"]) == 2
    # A new policy revision can examine the same data but still respects cooldown.
    new = save(owner, model)
    assert (
        owner.drift.recalibrate(Recalibrate(model_id=model["id"], revision=new["revision"]))["status"]
        == "cooldown"
    )


def test_policy_revision_disabled_demo_and_archival_guards(drift_input, client):
    owner, model, meta, data = drift_input
    owner.market.archive.capture(meta, "BTC/USDT", "1d", data[720:])
    state = save(owner, model)
    with pytest.raises(ValueError, match="policy changed"):
        save(owner, model, revision=0)
    with pytest.raises(ValueError, match="current explicitly enabled"):
        owner.drift.recalibrate(Recalibrate(model_id=model["id"], revision=state["revision"] + 1))
    owner.archive(model["id"], True, 0)
    with pytest.raises(ValueError, match="Restore"):
        owner.drift.recalibrate(Recalibrate(model_id=model["id"], revision=state["revision"]))
    response = client.get(f"/api/v1/forecast-models/{model['id']}/drift")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert "coefficients" not in response.text


def test_failure_is_retained_and_is_not_replayed_on_restart(drift_input, monkeypatch):
    owner, model, meta, data = drift_input
    owner.market.archive.capture(meta, "BTC/USDT", "1d", data[720:])
    state = save(owner, model)
    calls = []

    def failure(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("PRIVATE PROVIDER DETAIL")

    monkeypatch.setattr(owner, "train", failure)
    body = Recalibrate(model_id=model["id"], revision=state["revision"])
    with pytest.raises(RuntimeError):
        owner.drift.recalibrate(body)
    result = owner.drift.recalibrate(body)
    assert result["status"] == "failed" and len(calls) == 1
    assert "PRIVATE" not in json.dumps(owner.drift.state(model["id"]))
    restored = ForecastModels(owner.market, owner.store)
    assert restored.drift.state(model["id"])["history"][0]["status"] == "failed"
