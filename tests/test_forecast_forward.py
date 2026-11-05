"""Prospective target eligibility, exact-source scoring, retained corrections and privacy."""

import json
from datetime import UTC, datetime

import pytest

from sibyl.forecasting.engine import fingerprint
from sibyl.forecasting.forward import ForwardAction
from sibyl.market_data.archive import iso, milliseconds, series_key, step_ms

DAY = step_ms("1d")


@pytest.fixture
def tracked(client):
    owner = client.app.state.services.forecasts
    now = milliseconds(datetime.now(UTC))
    origin = (now // DAY - 3) * DAY
    # A controlled saved output exercises real persistence/fingerprints without provider calls.
    output = dict(
        id="a" * 32,
        model_id="b" * 32,
        model_version=1,
        model_fingerprint="f" * 64,
        symbol="BTC/USDT",
        source="binance",
        environment="production",
        input_kind="current_feed",
        created_at=iso(origin + 1000),
        origin=iso(origin),
        last_price=100.0,
        points=[
            dict(timestamp=iso(origin + h * DAY), value=100 + h * 2, lower=90, upper=120) for h in range(1, 5)
        ],
        horizon=4,
        observations=dict(
            candles=[dict(timestamp=iso(origin - (90 - i) * DAY), close=100.0) for i in range(90)],
            source="binance",
            environment="production",
            symbol="BTC/USDT",
        ),
    )
    output["input_fingerprint"] = fingerprint(output["observations"])
    output["result_fingerprint"] = fingerprint(output)
    with owner.store.db() as db:
        db.execute(
            "INSERT INTO forecast_outputs VALUES(?,?,?)",
            (output["id"], output["model_id"], json.dumps(output)),
        )
    owner.forward.clock = lambda: now
    row = owner.forward.enroll(output["id"])
    return owner, row, output, now


def candle(owner, output, index, price, source=None):
    key = series_key(source or output["source"], output["environment"], output["symbol"], "1d")
    target = milliseconds(output["points"][index]["timestamp"])
    with owner.store.db() as db:
        db.execute(
            "INSERT OR REPLACE INTO candle_rows VALUES(?,?,?,?,?,?,?,?)",
            (key, target - DAY, price, price, price, price, 1000, iso(target + 1000)),
        )


def test_missing_prices_never_become_zero_and_other_sources_do_not_score(tracked):
    owner, row, output, now = tracked
    row = owner.forward.evaluate(row["id"])
    assert row["observed"] == 0 and row["metrics"] is None
    assert row["points"][-1]["state"] == "not_due"
    candle(owner, output, 0, 105, "kraken")
    assert owner.forward.evaluate(row["id"])["observed"] == 0
    candle(owner, output, 0, 105)
    row = owner.forward.evaluate(row["id"])
    assert row["observed"] == 1 and row["metrics"]["mae"] == 3 and row["naive"]["mae"] == 5
    assert row["coverage_pct"] == 100
    assert owner.forward.list(output["model_id"])["by_horizon"][0]["horizon"] == 1


def test_observation_corrections_do_not_rewrite_predictions(tracked):
    owner, row, output, now = tracked
    candle(owner, output, 0, 105)
    owner.forward.evaluate(row["id"])
    candle(owner, output, 0, 99)
    corrected = owner.forward.evaluate(row["id"])
    observation = corrected["points"][0]["observation"]
    assert observation["version"] == 2 and [r["actual"] for r in observation["history"]] == [105, 99]
    assert owner.output(output["id"]) == output
    assert owner.forward.evaluate(row["id"])["points"][0]["observation"]["version"] == 2


def test_pause_revision_and_explicit_refresh_are_separate(tracked, monkeypatch):
    owner, row, output, now = tracked
    monkeypatch.setattr(
        owner.market, "candles", lambda *args: pytest.fail("Passive scoring contacted provider")
    )
    owner.forward.evaluate(row["id"])
    paused = owner.forward.action(row["id"], ForwardAction(revision=row["revision"], action="pause"))
    with pytest.raises(ValueError, match="Resume"):
        owner.forward.evaluate(row["id"])
    with pytest.raises(ValueError, match="changed"):
        owner.forward.action(row["id"], ForwardAction(revision=1, action="resume"))
    owner.forward.action(row["id"], ForwardAction(revision=paused["revision"], action="resume"))
    owner.forward.evaluate(row["id"])


@pytest.mark.parametrize(
    "kind,source,created",
    [("saved_input", "binance", None), ("current_feed", "demo", None), ("current_feed", "binance", "late")],
)
def test_historical_and_demo_outputs_never_claim_live_performance(tracked, kind, source, created):
    owner, row, output, now = tracked
    output = {**output, "id": "c" * 32, "input_kind": kind, "source": source}
    if created:
        output["created_at"] = iso(now + 10 * DAY)
    output.pop("result_fingerprint")
    output["result_fingerprint"] = fingerprint(output)
    with owner.store.db() as db:
        db.execute(
            "INSERT INTO forecast_outputs VALUES(?,?,?)",
            (output["id"], output["model_id"], json.dumps(output)),
        )
    with pytest.raises(ValueError):
        owner.forward.enroll(output["id"])


def test_http_private_evidence_and_missing_records(tracked, client):
    owner, row, output, now = tracked
    response = client.get("/api/v1/forecast-models/outputs/" + output["id"] + "/tracking")
    assert response.status_code == 200 and response.headers["Cache-Control"] == "no-store"
    assert client.get("/api/v1/forecast-models/outputs/missing/tracking").status_code == 404
    assert (
        client.post(
            "/api/v1/forecast-models/outputs/" + output["id"] + "/tracking/action",
            json={"revision": True, "action": "pause"},
        ).status_code
        == 422
    )


def test_native_chronos_reads_selected_live_outcomes(tracked, client, monkeypatch):
    owner, row, output, now = tracked
    monkeypatch.setattr(owner.market, "candles", lambda *a: pytest.fail("Agent refreshed a provider"))
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "chronos",
            "message": "Explain the live scorecard",
            "context": {
                "forecast_model_id": output["model_id"],
                "forecast_run_id": output["id"],
                "forecast_tracking": True,
            },
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["tool"] == "forecast_outcomes"
    assert response.json()["evidence"]["id"] == output["id"]


def test_enrollment_is_idempotent_and_result_fingerprint_is_checked(tracked):
    owner, row, output, now = tracked
    assert owner.forward.enroll(row["id"])["id"] == row["id"]
    changed = {**output, "last_price": 999}
    with owner.store.db() as db:
        db.execute("UPDATE forecast_outputs SET payload=? WHERE id=?", (json.dumps(changed), row["id"]))
    with pytest.raises(ValueError, match="integrity"):
        owner.forward.evaluate(row["id"])


def test_duplicate_origin_saves_do_not_inflate_samples_and_tracking_can_be_removed(tracked):
    owner, row, output, now = tracked
    candle(owner, output, 0, 105)
    owner.forward.evaluate(row["id"])
    duplicate = {**output, "id": "d" * 32, "created_at": iso(milliseconds(output["created_at"]) + 1000)}
    duplicate.pop("result_fingerprint")
    duplicate["result_fingerprint"] = fingerprint(duplicate)
    with owner.store.db() as db:
        db.execute(
            "INSERT INTO forecast_outputs VALUES(?,?,?)",
            (duplicate["id"], duplicate["model_id"], json.dumps(duplicate)),
        )
    other = owner.forward.enroll(duplicate["id"])
    owner.forward.evaluate(other["id"])
    score = owner.forward.list(output["model_id"])["by_horizon"][0]
    assert score["samples"] == 1 and score["duplicate_origins_excluded"] == 1
    owner.forward.forget(other["id"], other["revision"])
    with pytest.raises(LookupError):
        owner.forward.detail(other["id"])
    assert owner.output(duplicate["id"])["result_fingerprint"] == duplicate["result_fingerprint"]


def test_worker_drains_a_bounded_batch_without_provider_reads(tracked, monkeypatch):
    owner, row, output, now = tracked
    monkeypatch.setattr(owner.market, "candles", lambda *a: pytest.fail("Worker contacted provider"))
    for index in range(1, 7):
        other = {**output, "id": str(index) * 32}
        other.pop("result_fingerprint")
        other["result_fingerprint"] = fingerprint(other)
        with owner.store.db() as db:
            db.execute(
                "INSERT INTO forecast_outputs VALUES(?,?,?)",
                (other["id"], other["model_id"], json.dumps(other)),
            )
        owner.forward.enroll(other["id"])
    owner.forward.tick()
    rows = owner.forward.list(output["model_id"])["items"]
    assert sum(item["checked_at"] is not None for item in rows) == 5
    owner.forward.tick()
    rows = owner.forward.list(output["model_id"])["items"]
    assert all(item["checked_at"] is not None for item in rows)


def test_restored_workspace_pauses_tracking_and_execution_subscriptions(tracked):
    from sibyl.alerts.orders.service import OrderAlertCreate, OrderAlerts
    from sibyl.operations.recovery import prepare_recovery

    owner, row, output, now = tracked
    alerts = OrderAlerts(owner.store)
    rule = alerts.create(OrderAlertCreate(account_id="demo"))
    prepare_recovery(owner.store, "controlled-backup")
    assert owner.forward.detail(row["id"])["status"] == "paused"
    assert alerts.rules()["items"][0]["status"] == "paused"
    assert alerts.rules()["items"][0]["id"] == rule["id"]
    assert owner.output(output["id"])["result_fingerprint"] == output["result_fingerprint"]
