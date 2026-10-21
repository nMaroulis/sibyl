"""Local price alerts use controlled feeds and disposable databases; no external delivery."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event

import ccxt
import pytest
from pydantic import ValidationError

from sibyl.models import ConnectionCreate
from sibyl.services.alerts import PriceAlertCreate, PriceAlerts, fresh_quote
from sibyl.services.data_settings import DataSettings
from sibyl.services.market import Market
from sibyl.storage import Store


class Feed:
    """Small explicit source contract with a quote read counter and failure controls."""

    def __init__(self):
        self.source = "demo"
        self.price = 100.0
        self.timestamp = time.time() * 1000
        self.reads = 0
        self.failure = None
        self.seen = []

    @contextmanager
    def snapshot(self, source=None):
        self.source = source or self.source
        yield self

    def metadata(self):
        return {
            "source": self.source,
            "source_label": self.source,
            "environment": "demo" if self.source == "demo" else "production",
        }

    def symbols(self):
        return {"items": [{"symbol": "BTC/USDT"}]}

    def valuation_ticker(self, symbol):
        assert symbol == "BTC/USDT"
        self.reads += 1
        self.seen.append(self.source)
        if self.failure:
            raise self.failure
        return {"price": self.price, "timestamp": self.timestamp}


@pytest.fixture
def setup(store):
    feed = Feed()
    return PriceAlerts(feed, store), feed


def request(**changes):
    return PriceAlertCreate(
        **{"source": "demo", "symbol": "BTC/USDT", "condition": "above", "threshold": 100, **changes}
    )


def due(service, rule):
    with service.store.db() as db:
        current = service._read(db, rule["id"])
        current["next_check"] = 0
        service._write(db, current)


@pytest.mark.parametrize(
    "changes",
    [
        {"source": "https://bad.example"},
        {"source": "unknown space"},
        {"symbol": "BTC"},
        {"threshold": 0},
        {"threshold": float("nan")},
        {"threshold": float("inf")},
        {"condition": "equals"},
        {"label": "name\nsecret"},
    ],
)
def test_invalid_rule_shapes(changes):
    with pytest.raises(ValidationError):
        request(**changes)


def test_create_only_reads_catalog_and_list_reads_are_passive(setup):
    alerts, feed = setup
    rule = alerts.create(request(symbol=" btc/usdt ", label=" Watch this "))
    assert rule["symbol"] == "BTC/USDT" and rule["label"] == "Watch this"
    assert rule["status"] == "armed" and feed.reads == 0
    assert alerts.rules()["count"] == 1 and alerts.inbox()["unread"] == 0
    assert feed.reads == 0
    with pytest.raises(ValueError, match="exact spot pair"):
        alerts.create(request(symbol="BTC/USD"))


@pytest.mark.parametrize(
    "condition,threshold,price,matched",
    [
        ("above", 100, 100, True),
        ("above", 100, 99, False),
        ("below", 100, 100, True),
        ("below", 100, 101, False),
    ],
)
def test_inclusive_one_shot_thresholds(setup, condition, threshold, price, matched):
    alerts, feed = setup
    feed.price = price
    rule = alerts.create(request(condition=condition, threshold=threshold))
    result = alerts.check(rule["id"])
    assert result["status"] == ("triggered" if matched else "armed")
    assert alerts.inbox()["total"] == int(matched)
    alerts.tick()
    alerts.check(rule["id"])
    assert feed.reads == 1  # terminal state or persisted cooldown
    if matched:
        notification = alerts.inbox()["items"][0]
        assert notification["price"] == price and notification["source"] == "demo"
        assert notification["threshold"] == threshold and notification["environment"] == "demo"
        assert notification["read_at"] is None


def test_trigger_and_unread_state_survive_restart(setup):
    alerts, feed = setup
    alerts.create(request())
    alerts.tick()
    reopened = PriceAlerts(feed, Store(alerts.store.path.parent))
    reopened.tick()
    assert reopened.inbox()["total"] == 1 and feed.reads == 1
    identity = reopened.inbox()["items"][0]["id"]
    read_time = reopened.mark_read(identity)["items"][0]["read_at"]
    assert read_time and reopened.mark_read(identity)["items"][0]["read_at"] == read_time
    assert reopened.inbox()["unread"] == 0
    assert reopened.rules()["items"][0]["status"] == "triggered"


def test_saved_source_is_independent_of_new_default(setup):
    alerts, feed = setup
    rule = alerts.create(request(source="kraken"))
    feed.source = "binance"
    alerts.tick()
    assert feed.seen == ["kraken"]
    assert alerts.inbox()["items"][0]["source"] == "kraken"
    assert rule["environment"] == "production"


@pytest.mark.parametrize(
    "change",
    [
        {"price": None},
        {"price": float("nan")},
        {"price": -1},
        {"price": True},
        {"timestamp": None},
        {"timestamp": 0},
        {"timestamp": float("inf")},
        {"timestamp": True},
        {"timestamp": (time.time() - 301) * 1000},
        {"timestamp": (time.time() + 120) * 1000},
    ],
)
def test_stale_undated_invalid_or_future_quotes_never_trigger(setup, change):
    alerts, feed = setup
    for key, value in change.items():
        setattr(feed, key, value)
    rule = alerts.create(request())
    result = alerts.check(rule["id"])
    assert result["status"] == "armed" and result["error"]
    assert result["failures"] == 1 and result["next_check"] > time.time() + 50
    assert alerts.inbox()["total"] == 0
    alerts.check(rule["id"])
    assert feed.reads == 1  # manual checks do not bypass provider backoff


def test_staleness_rechecked_even_if_same_cached_timestamp(setup):
    alerts, feed = setup
    feed.price = 99
    rule = alerts.create(request())
    alerts.check(rule["id"])
    feed.price = 101
    feed.timestamp = (time.time() - 301) * 1000
    due(alerts, rule)
    alerts.tick()
    assert alerts.rules()["items"][0]["error"]
    assert alerts.inbox()["total"] == 0


def test_provider_failures_are_sanitized_and_recover_with_backoff(setup):
    alerts, feed = setup
    feed.failure = ccxt.AuthenticationError("PRIVATE apiKey=secret https://host/key")
    rule = alerts.create(request())
    alerts.tick()
    result = alerts.rules()["items"][0]
    assert "PRIVATE" not in json.dumps(result) and "secret" not in json.dumps(result)
    assert result["status"] == "armed" and result["failures"] == 1
    feed.failure = None
    due(alerts, rule)
    alerts.tick()
    assert alerts.rules()["items"][0]["status"] == "triggered"
    assert alerts.inbox()["total"] == 1


def test_backoff_is_capped_and_worker_checks_only_one_due_rule(setup):
    alerts, feed = setup
    first = alerts.create(request())
    second = alerts.create(request())
    feed.failure = TimeoutError("private")
    alerts.tick()
    assert feed.reads == 1
    alerts.tick()
    assert feed.reads == 2
    for _ in range(12):
        due(alerts, first)
        alerts.check(first["id"])
    result = next(r for r in alerts.rules()["items"] if r["id"] == first["id"])
    assert result["failures"] == 10 and time.time() + 890 < result["next_check"] <= time.time() + 900
    assert next(r for r in alerts.rules()["items"] if r["id"] == second["id"])["failures"] == 1


def test_pause_archive_restore_and_explicit_rearm_cycle(setup):
    alerts, feed = setup
    rule = alerts.create(request())
    alerts.change(rule["id"], "pause")
    alerts.tick()
    assert feed.reads == 0
    alerts.change(rule["id"], "arm")
    alerts.tick()
    assert alerts.inbox()["total"] == 1
    alerts.change(rule["id"], "arm")
    alerts.tick()
    assert alerts.inbox()["total"] == 2
    assert {item["cycle"] for item in alerts.inbox()["items"]} == {2, 3}
    alerts.change(rule["id"], "archive")
    assert not alerts.rules()["items"] and alerts.rules()["count"] == 0
    assert alerts.rules(True)["items"][0]["status"] == "archived"
    assert alerts.inbox()["total"] == 2
    with pytest.raises(ValueError, match="Restore"):
        alerts.change(rule["id"], "arm")
    assert alerts.change(rule["id"], "restore")["status"] == "paused"
    alerts.tick()
    assert alerts.inbox()["total"] == 2


def test_concurrent_checks_emit_once(setup):
    alerts, feed = setup
    rule = alerts.create(request())
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: alerts.check(rule["id"]), range(16)))
    assert feed.reads == 1 and alerts.inbox()["total"] == 1


@pytest.mark.parametrize("action", ["pause", "archive", "arm"])
def test_delayed_quote_cannot_overwrite_a_rule_lifecycle_change(setup, action):
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
        alerts.change(rule["id"], "pause")
        if action != "pause":
            alerts.change(rule["id"], action)
        release.set()
        result = pending.result()
    assert result["status"] == {"pause": "paused", "archive": "archived", "arm": "armed"}[action]
    assert alerts.inbox()["total"] == 0


def test_budget_and_restore_do_not_exceed_rule_limit(setup):
    alerts, _ = setup
    alerts.limit = 2
    first = alerts.create(request())
    alerts.create(request())
    with pytest.raises(ValueError, match="at most 2"):
        alerts.create(request())
    alerts.change(first["id"], "archive")
    alerts.create(request())
    with pytest.raises(ValueError, match="Archive another"):
        alerts.change(first["id"], "restore")


def test_inbox_pagination_and_acknowledgment_do_not_delete_history(setup):
    alerts, _ = setup
    rule = alerts.create(request())
    for i in range(4):
        if i:
            alerts.change(rule["id"], "arm")
        alerts.tick()
    first = alerts.inbox(2, 0)
    second = alerts.inbox(2, 2)
    assert first["unread"] == 4 and second["total"] == 4
    assert not {n["id"] for n in first["items"]} & {n["id"] for n in second["items"]}
    assert alerts.mark_read()["unread"] == 0
    assert alerts.inbox()["total"] == 4
    with pytest.raises(LookupError):
        alerts.mark_read("not-a-notification")


def test_unknown_ids_and_closed_worker_do_not_read_providers(setup):
    alerts, feed = setup
    with pytest.raises(LookupError):
        alerts.change("unknown", "pause")
    alerts.create(request())
    alerts.close()
    alerts.tick()
    assert feed.reads == 0


def test_exact_demo_market_works_without_any_active_account(settings, store):
    with store.db() as db:
        db.execute("DELETE FROM active_accounts")
    market = Market(settings, store, DataSettings(settings, store))
    alerts = PriceAlerts(market, store)
    alerts.create(request(threshold=1))
    alerts.tick()
    assert alerts.inbox()["total"] == 1
    assert not store.connections()[0].active
    assert store.orders() == []


def test_connected_feed_inactivation_prevents_triggering(settings, store, monkeypatch):
    connection = store.add_connection(
        ConnectionCreate(exchange="binance-testnet", label="Test", api_key="fake", secret="fake")
    )
    data = DataSettings(settings, store)
    market = Market(settings, store, data)
    # Exact catalog validation without private network access.
    monkeypatch.setattr(market, "symbols", lambda: {"items": [{"symbol": "BTC/USDT"}]})
    alerts = PriceAlerts(market, store)
    rule = alerts.create(request(source=f"connection:{connection.id}"))
    store.activate_account(connection.id, False)
    result = alerts.check(rule["id"])
    assert result["error"] and result["status"] == "armed" and alerts.inbox()["total"] == 0
    assert result["environment"] == "test"


def test_http_example_is_isolated_and_rules_inbox_are_durable(client):
    service = client.app.state.services.alerts
    service.close()  # Control manual evaluation while testing the HTTP contract.
    sample = client.get("/api/v1/alerts/example")
    assert sample.status_code == 200 and sample.json()["illustrative"]
    assert service.rules()["count"] == 0 and service.inbox()["total"] == 0
    assert sample.headers["cache-control"] == "no-store"
    created = client.post("/api/v1/alerts", json=request(threshold=1).model_dump())
    assert created.status_code == 201
    rule = created.json()
    checked = client.post(f"/api/v1/alerts/{rule['id']}/check")
    assert checked.status_code == 200 and checked.json()["status"] == "triggered"
    inbox = client.get("/api/v1/notifications?limit=1").json()
    assert inbox["unread"] == 1
    assert client.post(f"/api/v1/notifications/{inbox['items'][0]['id']}/read").json()["unread"] == 0
    assert client.post("/api/v1/notifications/read-all").status_code == 200
    assert client.post(f"/api/v1/alerts/{rule['id']}/action", json={"action": "archive"}).status_code == 200
    assert client.get("/api/v1/alerts").json()["items"] == []
    assert client.get("/api/v1/alerts?include_archived=true").json()["items"][0]["status"] == "archived"
    assert client.post(f"/api/v1/alerts/{rule['id']}/action", json={"action": "trade"}).status_code == 422
    assert client.get("/api/v1/notifications?limit=1000").status_code == 422
    roadmap = client.get("/api/v1/roadmap").json()
    assert len(roadmap["areas"]) == 12
    assert next(a for a in roadmap["areas"] if a["id"] == "multi-user")["status"] == "deferred"
    assert client.app.state.services.store.orders() == []


def test_credentials_never_enter_alert_or_notification_payloads(client):
    response = client.post(
        "/api/v1/alerts",
        json={
            "source": "coingecko",
            "symbol": "BTC/USD",
            "condition": "above",
            "threshold": 1,
            "api_key": "SECRET",
        },
    )
    assert response.status_code == 422 and "SECRET" not in response.text
    assert client.get("/api/v1/alerts").json()["count"] == 0


def test_freshness_uses_provider_time_not_receipt_time():
    with pytest.raises(ValueError, match="no provider timestamp"):
        fresh_quote({"price": 100, "received_at": "2026-10-21T10:00:00+00:00"}, time.time())


def test_older_archived_rules_remain_paged_and_restorable(setup):
    alerts, _ = setup
    first = None
    for _ in range(52):
        rule = alerts.create(request())
        first = first or rule
        alerts.change(rule["id"], "archive")
    first_page, second_page = alerts.rules(True), alerts.rules(True, 50)
    assert len(first_page["items"]) == 50 and len(second_page["items"]) == 2
    assert first_page["total"] == 52 and first_page["count"] == 0
    assert second_page["items"][-1]["id"] == first["id"]
    assert alerts.change(first["id"], "restore")["status"] == "paused"
    assert alerts.rules()["count"] == 1
