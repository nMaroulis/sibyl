"""Observed crossing, anti-noise recurrence and editable-rule race contracts."""

import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import ccxt
import pytest
from pydantic import ValidationError
from test_alerts import due, request
from test_alerts import setup as setup

from sibyl.services.alerts import AlertConflict, PriceAlerts, PriceAlertUpdate


@pytest.fixture
def clocked(setup, monkeypatch):
    alerts, feed = setup
    wall = [time.time()]
    monkeypatch.setattr("sibyl.services.alerts.time.time", lambda: wall[0])

    def observe(rule, price, seconds=31, timestamp=None):
        wall[0] += seconds
        feed.price, feed.timestamp = price, (wall[0] if timestamp is None else timestamp) * 1000
        due(alerts, rule)
        return alerts.check(rule["id"])

    return alerts, feed, wall, observe


def edit_request(rule, **changes):
    """Send complete reviewed configuration, retaining the editor's explicit revision."""
    return PriceAlertUpdate(
        **{
            key: rule[key]
            for key in (
                "source",
                "symbol",
                "label",
                "condition",
                "threshold",
                "repeat",
                "cooldown_seconds",
                "revision",
            )
        }
        | changes
    )


@pytest.mark.parametrize(
    "condition,prices", [("crosses_above", [101, 99, 100]), ("crosses_below", [99, 101, 100])]
)
def test_first_quote_is_only_a_baseline_then_a_strict_opposite_to_touch_crosses(clocked, condition, prices):
    alerts, _, _, observe = clocked
    rule = alerts.create(request(condition=condition))
    first = observe(rule, prices[0])
    assert first["status"] == "armed" and first["baseline_at"]
    assert alerts.inbox()["total"] == 0
    observe(rule, prices[1])
    assert alerts.inbox()["total"] == 0
    assert observe(rule, prices[2])["status"] == "triggered"
    notification = alerts.inbox()["items"][0]
    assert notification["condition"] == condition and notification["price"] == 100
    assert notification["rule_revision"] == rule["revision"]


def test_equality_alone_is_not_an_opposite_side_crossing(clocked):
    alerts, _, _, observe = clocked
    rule = alerts.create(request(condition="crosses_above"))
    observe(rule, 100)
    observe(rule, 101)
    observe(rule, 100)
    assert alerts.inbox()["total"] == 0
    observe(rule, 99)
    observe(rule, 100)
    assert alerts.inbox()["total"] == 1


@pytest.mark.parametrize(
    "condition,trigger,reset",
    [("above", 100, 99), ("below", 100, 101), ("crosses_above", 100, 99), ("crosses_below", 100, 101)],
)
def test_repeats_require_an_observed_reset_and_keep_unique_notification_cycles(
    clocked, condition, trigger, reset
):
    alerts, _, _, observe = clocked
    rule = alerts.create(request(condition=condition, repeat="after_reset", cooldown_seconds=60))
    if condition.startswith("crosses_"):
        observe(rule, reset)
    first = observe(rule, trigger)
    assert first["status"] == "armed" and first["waiting_reset"] and first["cycle"] == 1
    for _ in range(3):
        assert observe(rule, trigger)["waiting_reset"]
    assert alerts.inbox()["total"] == 1
    assert not observe(rule, reset)["waiting_reset"]
    second = observe(rule, trigger)
    assert second["cycle"] == 2 and second["waiting_reset"]
    assert {row["cycle"] for row in alerts.inbox()["items"]} == {1, 2}


def test_cooldown_crossings_are_skipped_not_delivered_late(clocked):
    alerts, _, _, observe = clocked
    rule = alerts.create(request(repeat="after_reset", cooldown_seconds=60))
    observe(rule, 101, 0)
    observe(rule, 99, 10)
    suppressed = observe(rule, 101, 10)
    assert suppressed["waiting_reset"]
    observe(rule, 101, 80)
    assert alerts.inbox()["total"] == 1
    observe(rule, 99, 31)
    observe(rule, 100, 31)
    assert alerts.inbox()["total"] == 2


def test_reset_during_cooldown_can_precede_a_new_crossing_after_cooldown(clocked):
    alerts, _, _, observe = clocked
    rule = alerts.create(request(repeat="after_reset", cooldown_seconds=60))
    observe(rule, 100, 0)
    observe(rule, 99, 31)
    observe(rule, 100, 31)
    assert alerts.inbox()["total"] == 2


@pytest.mark.parametrize("timestamp_delta", [0, -1])
def test_duplicate_and_out_of_order_quotes_cannot_create_crossings(clocked, timestamp_delta):
    alerts, _, wall, observe = clocked
    rule = alerts.create(request(condition="crosses_above"))
    initial = observe(rule, 99)
    previous = wall[0]
    result = observe(rule, 101, timestamp=previous + timestamp_delta)
    assert result["observed_at"] == initial["observed_at"] and result["last_price"] == 99
    assert "newer provider quote" in result["evaluation_note"]
    assert alerts.inbox()["total"] == 0
    observe(rule, 100)
    assert alerts.inbox()["total"] == 1


def test_large_observation_gap_cannot_reconstruct_a_crossing(clocked):
    alerts, _, _, observe = clocked
    rule = alerts.create(request(condition="crosses_above"))
    observe(rule, 99)
    result = observe(rule, 101, 301)
    assert result["status"] == "armed" and "baseline" in result["evaluation_note"]
    assert alerts.inbox()["total"] == 0
    observe(rule, 99)
    observe(rule, 100)
    assert alerts.inbox()["total"] == 1


def test_read_error_invalidates_crossing_baseline_without_erasing_displayed_evidence(clocked):
    alerts, feed, _, observe = clocked
    rule = alerts.create(request(condition="crosses_above"))
    observe(rule, 99)
    feed.failure = ccxt.RequestTimeout("PRIVATE")
    result = observe(rule, 101)
    assert result["baseline_at"] is None and result["last_price"] == 99
    feed.failure = None
    observe(rule, 101)
    assert alerts.inbox()["total"] == 0
    observe(rule, 99)
    observe(rule, 101)
    assert alerts.inbox()["total"] == 1


def test_restart_preserves_waiting_reset_cooldown_baseline_and_prior_notifications(clocked):
    alerts, feed, wall, observe = clocked
    rule = alerts.create(request(repeat="after_reset", cooldown_seconds=300))
    triggered = observe(rule, 100)
    reopened = PriceAlerts(feed, alerts.store)
    retained = reopened.rules()["items"][0]
    assert retained["waiting_reset"] and retained["cooldown_until"] == triggered["cooldown_until"]
    wall[0] += 31
    feed.price, feed.timestamp = 99, wall[0] * 1000
    due(reopened, rule)
    reopened.check(rule["id"])
    reopened = PriceAlerts(feed, alerts.store)
    wall[0] += 300
    feed.price, feed.timestamp = 100, wall[0] * 1000
    due(reopened, rule)
    result = reopened.check(rule["id"])
    assert result["cycle"] == 2 and reopened.inbox()["total"] == 2
    assert result["cooldown_until"] > wall[0]


def test_restarting_after_long_sleep_does_not_turn_reset_evidence_into_a_new_entry(clocked):
    alerts, feed, wall, observe = clocked
    rule = alerts.create(request(repeat="after_reset", cooldown_seconds=60))
    observe(rule, 100)
    observe(rule, 99)
    reopened = PriceAlerts(feed, alerts.store)
    wall[0] += 301
    feed.price, feed.timestamp = 101, wall[0] * 1000
    due(reopened, rule)
    assert reopened.check(rule["id"])["waiting_reset"]
    assert reopened.inbox()["total"] == 1


def test_edit_saves_paused_keeps_id_and_immutable_old_notifications(clocked):
    alerts, _, _, observe = clocked
    rule = alerts.create(request(label="Original", repeat="after_reset"))
    observe(rule, 100)
    old_notification = alerts.inbox()["items"][0]
    current = alerts.rules()["items"][0]
    edited = alerts.edit(
        rule["id"], edit_request(current, threshold=120, label="Updated", condition="crosses_below")
    )
    assert edited["id"] == rule["id"] and edited["status"] == "paused"
    assert edited["revision"] == rule["revision"] + 1 and edited["baseline_at"] is None
    assert edited["cooldown_until"] == 0 and edited["last_price"] is None
    assert alerts.inbox()["items"][0] == old_notification
    assert alerts.rules()["count"] == 1
    alerts.change(rule["id"], "arm")
    observe(rule, 130)
    observe(rule, 120)
    notification = alerts.inbox()["items"][0]
    assert notification["label"] == "Updated" and notification["threshold"] == 120
    assert notification["cycle"] > old_notification["cycle"]


def test_same_market_edit_does_not_need_a_working_feed(setup):
    alerts, feed = setup
    rule = alerts.create(request())
    feed.symbols = lambda: (_ for _ in ()).throw(RuntimeError("PRIVATE"))
    assert alerts.edit(rule["id"], edit_request(rule, label="Repair me"))["status"] == "paused"
    assert feed.reads == 0


def test_changed_pair_is_validated_and_source_metadata_is_updated(setup):
    alerts, feed = setup
    rule = alerts.create(request())
    with pytest.raises(ValueError, match="exact spot pair"):
        alerts.edit(rule["id"], edit_request(rule, symbol="BTC/USD"))
    assert alerts.rules()["items"][0]["status"] == "armed"
    changed = alerts.edit(rule["id"], edit_request(rule, source="kraken"))
    assert changed["source"] == "kraken" and changed["environment"] == "production"
    assert feed.reads == 0


def test_stale_editor_and_archived_rule_cannot_overwrite_newer_decisions(setup):
    alerts, _ = setup
    rule = alerts.create(request())
    alerts.change(rule["id"], "pause")
    with pytest.raises(AlertConflict, match="changed"):
        alerts.edit(rule["id"], edit_request(rule, threshold=105))
    archived = alerts.change(rule["id"], "archive")
    with pytest.raises(ValueError, match="Restore"):
        alerts.edit(rule["id"], edit_request(archived))
    with pytest.raises(LookupError):
        alerts.edit("unknown", edit_request(rule))


def test_concurrent_editors_cannot_lose_an_edit(setup):
    alerts, _ = setup
    rule = alerts.create(request())

    def save(value):
        try:
            return alerts.edit(rule["id"], edit_request(rule, threshold=value))
        except AlertConflict:
            return None

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(save, [110, 120]))
    assert sum(result is not None for result in results) == 1
    assert alerts.rules()["items"][0]["revision"] == 2


def test_delayed_quote_cannot_trigger_after_edit(setup):
    alerts, feed = setup
    rule = alerts.create(request())
    entered, release = Event(), Event()

    def delayed(_):
        entered.set()
        assert release.wait(3)
        return {"price": 100, "timestamp": time.time() * 1000}

    feed.valuation_ticker = delayed
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(alerts.check, rule["id"])
        assert entered.wait(3)
        edited = alerts.edit(rule["id"], edit_request(rule, threshold=110))
        release.set()
        result = pending.result()
    assert result == edited and alerts.inbox()["total"] == 0


def test_lifecycle_change_during_catalog_validation_rejects_the_old_editor(setup):
    alerts, feed = setup
    rule = alerts.create(request())
    entered, release = Event(), Event()

    def delayed():
        entered.set()
        assert release.wait(3)
        return {"items": [{"symbol": "BTC/USDT"}]}

    feed.symbols = delayed
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(alerts.edit, rule["id"], edit_request(rule, source="kraken"))
        assert entered.wait(3)
        alerts.change(rule["id"], "archive")
        release.set()
        with pytest.raises(AlertConflict):
            pending.result()
    retained = alerts.rules(True)["items"][0]
    assert retained["source"] == "demo" and retained["status"] == "archived"


def test_notification_and_recurrence_state_roll_back_together(clocked):
    alerts, _, _, observe = clocked
    rule = alerts.create(request(repeat="after_reset"))
    with alerts.store.db() as db:
        db.execute(
            "CREATE TRIGGER fail_notice BEFORE INSERT ON alert_notifications BEGIN SELECT RAISE(ABORT, 'test failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        observe(rule, 100)
    retained = alerts.rules()["items"][0]
    assert not retained["waiting_reset"] and retained["triggered_at"] is None and retained["cycle"] == 1
    assert alerts.inbox()["total"] == 0
    with alerts.store.db() as db:
        db.execute("DROP TRIGGER fail_notice")
    observe(rule, 100)
    assert alerts.inbox()["total"] == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"repeat": "every_second"},
        {"cooldown_seconds": 59},
        {"cooldown_seconds": 86401},
        {"cooldown_seconds": True},
        {"cooldown_seconds": 60.5},
        {"revision": 0},
        {"revision": True},
    ],
)
def test_invalid_edit_and_repeat_shapes_are_rejected(changes):
    payload = request().model_dump() | {"revision": 1} | changes
    with pytest.raises(ValidationError):
        PriceAlertUpdate(**payload)


def test_old_saved_rules_default_to_one_shot_without_mutating_passive_reads(setup):
    alerts, _ = setup
    rule = alerts.create(request())
    for key in (
        "repeat",
        "cooldown_seconds",
        "cooldown_until",
        "waiting_reset",
        "baseline_at",
        "baseline_price",
        "evaluation_note",
    ):
        rule.pop(key)
    with alerts.store.db() as db:
        db.execute("UPDATE price_alerts SET payload=? WHERE id=?", (json.dumps(rule), rule["id"]))
    assert alerts.rules()["items"][0]["repeat"] == "once"
    with alerts.store.db() as db:
        assert "repeat" not in json.loads(db.execute("SELECT payload FROM price_alerts").fetchone()[0])
    assert alerts.check(rule["id"])["status"] == "triggered"
    assert alerts.inbox()["total"] == 1


def test_http_edit_contract_revision_conflict_and_isolated_examples(client):
    service = client.app.state.services.alerts
    service.close()
    rule = client.post(
        "/api/v1/alerts", json=request(condition="crosses_above", repeat="after_reset").model_dump()
    ).json()
    response = client.post(
        f"/api/v1/alerts/{rule['id']}/edit", json=edit_request(rule, threshold=200).model_dump()
    )
    assert response.status_code == 200 and response.json()["status"] == "paused"
    assert response.headers["cache-control"] == "no-store"
    stale = client.post(f"/api/v1/alerts/{rule['id']}/edit", json=edit_request(rule).model_dump())
    assert stale.status_code == 409 and stale.headers["cache-control"] == "no-store"
    assert (
        client.post(
            f"/api/v1/alerts/{rule['id']}/edit", json=edit_request(rule).model_dump() | {"secret": "PRIVATE"}
        ).status_code
        == 422
    )
    sample = client.get("/api/v1/alerts/example").json()
    assert any(row["repeat"] == "after_reset" for row in sample["rules"]["items"])
    assert service.rules()["count"] == 1 and service.inbox()["total"] == 0
    assert client.app.state.services.store.orders() == []
