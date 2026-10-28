"""Durable provider observations without external accounts, probes or execution."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import ccxt
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from sibyl.api.app import create_app
from sibyl.market_data.control import ProviderControl, ProviderDeferred
from sibyl.market_data.health_history import ProviderHistory


def source(identity="binance", environment="production"):
    return {
        "id": identity,
        "name": "PRIVATE-LABEL",
        "kind": "exchange",
        "provider": "binance",
        "environment": environment,
    }


def read(control, meta=None, failure=None):
    """Use the same operation/transport gate as native SDK reads, without network I/O."""

    def loader():
        if failure:
            raise failure
        return {"ok": True}

    with control.operation(meta or source(), "fetch_ticker", read=True):
        return control.transport(loader)


def test_hourly_history_is_durable_weighted_and_excludes_raw_context(store):
    now = datetime(2026, 10, 22, 12, 30, tzinfo=UTC)
    history = ProviderHistory(store, clock=lambda: now)
    history.record(source(), "old-profile", 100, None)
    history.record(source(), "new-profile", 200, "network")
    history.record(source(), "another-profile", 50, None)
    result = ProviderHistory(store, clock=lambda: now).read("binance")
    assert result["totals"]["requests"] == 3
    assert result["totals"]["success_rate"] == 66.67
    assert result["totals"]["mean_latency_ms"] == 116.7
    assert result["totals"]["max_latency_ms"] == 200
    assert len(result["series"]) == 24 and result["series"][-1]["requests"] == 3
    assert all(point["requests"] == 0 and point["mean_latency_ms"] is None for point in result["series"][:-1])
    assert result["recent_errors"][0]["kind"] == "network"
    with store.db() as db:
        saved = [dict(row) for row in db.execute("SELECT * FROM provider_read_hours")]
    assert "PRIVATE" not in json.dumps(saved)
    assert {row["environment"] for row in saved} == {"production"}


def test_environment_and_account_identities_do_not_merge(store):
    history = ProviderHistory(store)
    test_id = "connection:" + uuid4().hex
    history.record(source(), "prod", 10, None)
    history.record(source(test_id, "test"), "sandbox", 20, "authentication")
    assert history.read("binance")["totals"]["failures"] == 0
    assert history.read(test_id)["totals"]["failures"] == 1
    assert len(history.identities()) == 2


def test_parallel_observations_are_atomic_or_explicitly_reported_missing(store):
    history = ProviderHistory(store)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: history.record(source(), "profile", 10, None), range(32)))
    result = history.read("binance")
    assert result["totals"]["requests"] + history.recording()["dropped_observations"] == 32
    assert result["totals"]["failures"] == 0
    assert result["totals"]["mean_latency_ms"] == 10


def test_only_actual_completed_transport_reads_are_saved(store):
    history = ProviderHistory(store)
    control = ProviderControl(min_interval=0, max_wait=0.01, history=history)
    assert read(control) == {"ok": True}
    with pytest.raises(ccxt.AuthenticationError):
        read(control, failure=ccxt.AuthenticationError("PRIVATE-URL?key=SECRET"))
    control.cache_hit(source())
    with control.mutation():
        assert read(control) == {"ok": True}
    with control.operation(source(), "create_order", read=False):
        assert control.transport(lambda: {"ok": True})
    with control._condition:
        control._bucket(source())["cooldown"] = time.monotonic() + 60
    with pytest.raises(ProviderDeferred):
        read(control)
    history.record({**source(), "id": "demo", "provider": "demo"}, "demo", 1, None)
    result = history.read("binance")
    assert result["totals"]["requests"] == 2 and result["totals"]["failures"] == 1
    assert "PRIVATE" not in json.dumps(result) and "SECRET" not in json.dumps(result)
    assert history.read("demo")["totals"]["requests"] == 0


def test_database_contention_cannot_mask_or_retry_provider_results(store):
    history = ProviderHistory(store)
    control = ProviderControl(min_interval=0, history=history)
    with store.db() as locked:
        locked.execute("BEGIN IMMEDIATE")
        assert read(control) == {"ok": True}
        with pytest.raises(ccxt.AuthenticationError):
            read(control, failure=ccxt.AuthenticationError("PRIVATE"))
    assert history.recording()["dropped_observations"] == 2
    assert history.recording()["status"] == "partial"
    assert history.read("binance")["totals"]["requests"] == 0
    assert read(control) == {"ok": True}
    assert history.read("binance")["totals"]["requests"] == 1
    assert control.snapshot([source()], "binance")["items"][0]["requests"] == 3


def test_retention_bounds_hours_and_errors_without_inventing_missing_samples(store, monkeypatch):
    monkeypatch.setattr("sibyl.market_data.health_history.MAX_HOURS", 4)
    monkeypatch.setattr("sibyl.market_data.health_history.MAX_ERRORS", 3)
    now = datetime(2026, 10, 22, 0, tzinfo=UTC)
    history = ProviderHistory(store, clock=lambda: now)
    for _ in range(6):
        history.record(source(), "profile", 10, "network")
        now += timedelta(hours=1)
    result = history.read("binance")
    assert result["totals"]["requests"] == 4 and len(result["recent_errors"]) == 3
    assert len(history.read("binance", 168)["series"]) == 168
    now += timedelta(days=15)
    history.record(source(), "profile", 10, None)
    assert history.read("binance")["totals"]["requests"] == 1
    with store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM provider_read_hours").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM provider_read_errors").fetchone()[0] == 0


def test_restart_preserves_history_without_marking_current_credentials_checked(client, settings, monkeypatch):
    history = client.app.state.services.market.read_history
    history.record(source(), "previous", 25, None)
    old_id = "connection:" + uuid4().hex
    history.record({**source(old_id, "test"), "kind": "connection"}, "removed", 40, "authentication")
    with TestClient(create_app(settings)) as restarted:
        market = restarted.app.state.services.market
        monkeypatch.setattr(market, "client", lambda *_: pytest.fail("History must not probe a provider"))
        current = restarted.get("/api/v1/providers/health?source=binance").json()["items"][0]
        assert current["status"] == "not_checked" and current["requests"] == 0
        assert current["last_success_at"] is None and current["history_available"]
        removed = restarted.get(f"/api/v1/providers/health?source={old_id}").json()["items"][0]
        assert removed["status"] == "unavailable" and not removed["available"]
        for identity in ("binance", old_id):
            response = restarted.get(f"/api/v1/providers/health/history?source={identity}")
            assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
            assert response.json()["totals"]["requests"] == 1
        assert restarted.get("/api/v1/providers/health/history?source=unknown").status_code == 400
        assert restarted.get("/api/v1/providers/health/history?source=binance&window=bad").status_code == 422


def test_history_reads_are_local_and_do_not_add_observations(client, monkeypatch):
    market = client.app.state.services.market
    monkeypatch.setattr(market, "client", lambda *_: pytest.fail("Unexpected provider call"))
    for window in ("24h", "7d"):
        response = client.get(f"/api/v1/providers/health/history?source=demo&window={window}")
        assert response.status_code == 200
        assert response.json()["totals"]["requests"] == 0
        assert response.json()["totals"]["success_rate"] is None
    assert not market.read_history.identities()


def test_late_retired_profile_can_only_add_historical_evidence(store):
    history = ProviderHistory(store)
    control = ProviderControl(min_interval=0, history=history)
    old = source()
    old["_state"] = control.register(old)
    control.reset("binance")
    current = control.register(source())
    assert read(control, old) == {"ok": True}
    assert current["requests"] == 0
    assert control.snapshot([source()], "binance")["items"][0]["status"] == "not_checked"
    assert history.read("binance")["totals"]["requests"] == 1


def test_history_requires_workspace_token(settings):
    settings.api_token = SecretStr("workspace-token")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/providers/health/history?source=binance").status_code == 401
