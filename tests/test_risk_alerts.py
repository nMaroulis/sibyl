"""Real account-risk transitions with isolated native-shaped balances and valuation quotes."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event
from types import SimpleNamespace

import ccxt
import pytest
from protolink import Task
from pydantic import SecretStr, ValidationError

from sibyl.alerts.contracts import AlertAction, AlertConflict
from sibyl.alerts.risk.contracts import RiskAlertCreate, RiskAlertUpdate
from sibyl.alerts.risk.service import RiskAlerts
from sibyl.exchanges.demo import DemoClient
from sibyl.market_data.control import ProviderDeferred
from sibyl.models import ConnectionCreate
from sibyl.services.data_settings import DataSettings, MarketSettingsRequest
from sibyl.services.market import Market


@pytest.fixture
def risk(settings, store, monkeypatch):
    wall = [time.time()]
    data = DataSettings(settings, store)
    data.save_market(MarketSettingsRequest(source="binance"))
    market = Market(settings, store, data)
    first = store.add_connection(
        ConnectionCreate(
            exchange="binance",
            label="Main desk",
            api_key=SecretStr("PRIVATE-KEY"),
            secret=SecretStr("PRIVATE-SECRET"),
        )
    )
    balances = {first.id: {"BTC": 1, "USDT": 100}}
    quotes = {"BTC/USDT": 100, "USDC/USDT": 0.9}
    calls = []
    hook = [None]

    class Time(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromtimestamp(wall[0], tz or UTC)

    monkeypatch.setattr("sibyl.services.valuation.datetime", Time)

    class Quotes(DemoClient):
        def load_markets(self):
            return {
                pair: dict(symbol=pair, base=pair.split("/")[0], quote=pair.split("/")[1]) for pair in quotes
            }

        def fetch_ticker(self, symbol):
            calls.append(("quote", symbol))
            value = quotes[symbol]
            if isinstance(value, Exception):
                raise value
            return value if isinstance(value, dict) else dict(last=value, timestamp=wall[0] * 1000)

        def fetch_ohlcv(self, *a, **kw):
            pytest.fail("Risk checks must not fetch chart history")

    class Account(Quotes):
        def __init__(self, identity):
            super().__init__(store)
            self.identity = identity

        def fetch_balance(self):
            calls.append(("balance", self.identity))
            if hook[0]:
                hook[0]()
            value = balances[self.identity]
            if isinstance(value, Exception):
                raise value
            return {"total": value}

    public = Quotes(store)
    monkeypatch.setattr(
        market, "client", lambda connection=None: Account(connection.id) if connection else public
    )
    alerts = RiskAlerts(market, store, clock=lambda: wall[0])
    result = SimpleNamespace(
        alerts=alerts,
        market=market,
        data=data,
        store=store,
        wall=wall,
        balances=balances,
        quotes=quotes,
        calls=calls,
        first=first,
        hook=hook,
    )
    yield result
    market.close()


def request(risk, **changes):
    return RiskAlertCreate(
        **(dict(account_ids=[risk.first.id], source="binance", metric="value_floor", threshold=200) | changes)
    )


def watch(risk, **changes):
    return risk.alerts.create(request(risk, **changes))


def current(risk, rule):
    return next(item for item in risk.alerts.rules(True)["items"] if item["id"] == rule["id"])


def check(risk, rule, seconds=61):
    risk.wall[0] += seconds
    risk.market._cache.clear()
    with risk.store.db() as db:
        saved = risk.alerts.journal.read(db, rule["id"])
        saved["next_check"] = 0
        risk.alerts.journal.write(db, saved)
    return risk.alerts.check(rule["id"])


def change(risk, rule, action):
    return risk.alerts.change(
        rule["id"], AlertAction(action=action, revision=current(risk, rule)["revision"])
    )


def test_source_pinned_value_floor_and_recovery_keep_exact_account_evidence(risk):
    rule = watch(risk, threshold=200, reset_threshold=205)
    assert not risk.calls  # Save/list are passive; the opt-in worker reads afterward.
    assert risk.alerts.rules()["count"] == 1
    first = check(risk, rule)
    assert first["in_breach"] and first["notifications"] == 1
    item = risk.alerts.inbox.page()["items"][0]
    assert item["kind"] == "risk" and item["action"] == "breached"
    assert item["total"] == 200 and item["currency"] == "USDT"
    assert item["account_ids"] == [risk.first.id] and item["environment"] == "production"
    risk.data.save_market(MarketSettingsRequest(source="demo"))
    risk.quotes["BTC/USDT"] = 102  # Recovery band has not cleared.
    assert check(risk, rule)["in_breach"]
    risk.quotes["BTC/USDT"] = 105
    assert not check(risk, rule)["in_breach"]
    notices = risk.alerts.inbox.page()["items"]
    assert [row["action"] for row in notices] == ["recovered", "breached"]
    assert all(row["source"] == "binance" for row in notices)
    evidence = risk.alerts.journal.evidence(rule["id"], item["sample_id"])
    assert evidence["sample"]["total"] == 200
    assert evidence["sample"]["holdings"][0]["path"] == ["BTC", "USDT"]
    assert "PRIVATE" not in json.dumps(notices) + json.dumps(evidence) + json.dumps(risk.alerts.rules())


def test_fixed_combined_accounts_never_include_new_connections(risk):
    second = risk.store.add_connection(
        ConnectionCreate(
            exchange="kraken", label="Second", api_key=SecretStr("key"), secret=SecretStr("secret")
        )
    )
    risk.balances[second.id] = {"BTC": 2, "USDT": 20}
    rule = watch(risk, account_ids=[risk.first.id, second.id], threshold=500)
    third = risk.store.add_connection(
        ConnectionCreate(
            exchange="coinbase", label="New", api_key=SecretStr("key"), secret=SecretStr("secret")
        )
    )
    risk.balances[third.id] = {"USDT": 1000000}
    result = check(risk, rule)
    assert result["last_observation"]["total"] == 420
    assert third.id not in {identity for kind, identity in risk.calls if kind == "balance"}
    assert result["account_ids"] == sorted([risk.first.id, second.id])


def test_concentration_uses_complete_total_and_an_absent_asset_is_zero(risk):
    rule = watch(risk, metric="concentration", asset="BTC", threshold=50, reset_threshold=45)
    assert check(risk, rule)["last_observation"]["metric_value"] == 50
    assert risk.alerts.inbox.page()["total"] == 1
    risk.balances[risk.first.id] = {"USDT": 100}
    assert check(risk, rule)["last_observation"]["metric_value"] == 0
    assert risk.alerts.inbox.page()["items"][0]["action"] == "recovered"


def test_observed_value_peak_survives_restart_and_zero_can_be_full_drawdown(risk):
    rule = watch(risk, metric="drawdown", threshold=20, reset_threshold=5)
    assert check(risk, rule)["peak"] == 200
    risk.balances[risk.first.id] = {"USDT": 250}  # Deposits affect this observed-value metric.
    assert check(risk, rule)["peak"] == 250
    restarted = RiskAlerts(risk.market, risk.store, clock=lambda: risk.wall[0])
    risk.alerts = restarted
    risk.balances[risk.first.id] = {"USDT": 200}
    assert check(risk, rule)["last_observation"]["metric_value"] == 20
    assert restarted.inbox.page()["total"] == 1
    risk.balances[risk.first.id] = {}
    assert check(risk, rule)["last_observation"]["metric_value"] == 100
    assert restarted.inbox.page()["total"] == 1
    risk.balances[risk.first.id] = {"USDT": 240}
    assert not check(risk, rule)["in_breach"]


@pytest.mark.parametrize("metric,asset", [("concentration", "BTC"), ("drawdown", "")])
def test_empty_valid_wallet_has_no_percentage_assessment(risk, metric, asset):
    risk.balances[risk.first.id] = {}
    rule = watch(risk, metric=metric, asset=asset, threshold=10)
    result = check(risk, rule)
    assert result["error"] is None and result["last_observation"]["metric_value"] is None
    assert result["evaluation_note"] and risk.alerts.inbox.page()["total"] == 0


def test_cooldown_requires_another_fresh_qualifying_sample_and_no_orphan_recovery(risk):
    rule = watch(risk, threshold=200, reset_threshold=210, cooldown_seconds=300)
    check(risk, rule)
    risk.quotes["BTC/USDT"] = 120
    recovered = check(risk, rule, 10)
    assert not recovered["in_breach"], (
        recovered["error"],
        recovered["last_observation"],
        recovered["checks"],
    )
    risk.quotes["BTC/USDT"] = 90
    suppressed = check(risk, rule, 10)
    assert suppressed["in_breach"] and not suppressed["incident_notified"]
    assert "cooldown" in suppressed["evaluation_note"]
    risk.quotes["BTC/USDT"] = 120
    check(risk, rule, 10)
    assert risk.alerts.inbox.page()["total"] == 2
    risk.quotes["BTC/USDT"] = 90
    check(risk, rule, 10)
    assert risk.alerts.inbox.page()["total"] == 2
    assert check(risk, rule, 301)["incident_notified"]
    assert risk.alerts.inbox.page()["total"] == 3


@pytest.mark.parametrize(
    "ticker",
    [{"last": 100}, {"last": 100, "timestamp": 1}, {"last": float("nan")}, {"last": True}, {"last": -1}],
)
def test_partial_or_untrusted_quotes_never_trigger_or_resolve_risk(risk, ticker):
    rule = watch(risk, threshold=200)
    check(risk, rule)
    previous = current(risk, rule)["last_observation"]
    risk.quotes["BTC/USDT"] = ticker
    result = check(risk, rule)
    assert result["error"] and result["last_observation"] == previous
    assert result["in_breach"] and risk.alerts.inbox.page()["total"] == 1
    assert len(risk.alerts.journal.evidence(rule["id"])["samples"]) == 1


def test_unknown_holding_stops_all_or_nothing_value_not_a_false_floor(risk):
    rule = watch(risk, threshold=10000)
    risk.balances[risk.first.id]["UNKNOWN"] = 20
    result = check(risk, rule)
    assert result["last_observation"] is None and result["error"]
    assert risk.alerts.inbox.page()["total"] == 0


@pytest.mark.parametrize("quantity", [None, True, -1, float("inf"), "invalid"])
def test_invalid_balance_quantity_is_not_silently_dropped(risk, quantity):
    rule = watch(risk)
    risk.balances[risk.first.id] = {"BTC": quantity, "USDT": 100}
    assert check(risk, rule)["error"]
    assert risk.alerts.inbox.page()["total"] == 0


def test_feed_failures_and_deferrals_have_sanitized_backoff_not_recovery(risk):
    rule = watch(risk)
    check(risk, rule)
    risk.balances[risk.first.id] = ccxt.AuthenticationError("PRIVATE-URL?key=SECRET")
    failure = check(risk, rule)
    assert failure["failures"] == 1 and failure["next_check"] == risk.wall[0] + 60
    assert "PRIVATE" not in json.dumps(failure) and "SECRET" not in json.dumps(failure)
    risk.balances[risk.first.id] = ProviderDeferred(12)
    deferred = check(risk, rule)
    assert deferred["failures"] == 1 and deferred["next_check"] == risk.wall[0] + 12
    assert risk.alerts.inbox.page()["total"] == 1


@pytest.mark.parametrize("change_kind", ["inactive", "deleted", "profile", "slow", "stale"])
def test_inflight_config_and_age_changes_cannot_commit_a_snapshot(risk, change_kind, monkeypatch):
    rule = watch(risk)
    original = risk.alerts.reader.read

    def delayed(rule):
        sample, guard = original(rule)
        if change_kind == "inactive":
            risk.store.activate_account(risk.first.id, False)
        elif change_kind == "deleted":
            risk.store.delete_connection(risk.first.id)
        elif change_kind == "profile":
            risk.data.save_market(MarketSettingsRequest(source="kraken"))
        elif change_kind == "slow":
            risk.wall[0] += 46
        else:
            sample["holdings"][0]["observed_at"] = datetime.fromtimestamp(risk.wall[0] - 301, UTC).isoformat()
        return sample, guard

    monkeypatch.setattr(risk.alerts.reader, "read", delayed)
    result = check(risk, rule)
    assert result["error"] and result["last_observation"] is None
    assert risk.alerts.inbox.page()["total"] == 0


def test_deactivation_and_activation_preserve_fixed_scope_without_zero_fallback(risk):
    rule = watch(risk)
    risk.store.activate_account(risk.first.id, False)
    assert check(risk, rule)["error"]
    assert not risk.calls
    risk.store.activate_account(risk.first.id, True)
    assert check(risk, rule)["last_observation"]["total"] == 200


def test_demo_and_test_environments_are_explicit_and_never_mix(risk):
    with pytest.raises(ValueError):
        watch(risk, source="demo")
    test = risk.store.add_connection(
        ConnectionCreate(
            exchange="binance-testnet", label="Test", api_key=SecretStr("key"), secret=SecretStr("secret")
        )
    )
    with pytest.raises(ValueError):
        watch(risk, account_ids=[risk.first.id, test.id])
    risk.balances[test.id] = {"USDT": 10}
    rule = watch(risk, account_ids=[test.id], threshold=20)
    check(risk, rule)
    notice = risk.alerts.inbox.page()["items"][0]
    assert notice["environment"] == "test" and notice["pricing_environment"] == "production"
    risk.store.activate_account(risk.first.id, False)
    risk.store.activate_account(test.id, False)
    risk.store.activate_account("demo", True)
    with pytest.raises(ValueError):
        watch(risk, account_ids=["demo"])
    risk.balances["demo"] = {"USDT": 10}
    demo = watch(risk, account_ids=["demo"], source="demo", threshold=20)
    check(risk, demo)
    assert risk.alerts.inbox.page()["items"][0]["environment"] == "demo"


def test_pause_during_read_cannot_be_overwritten_and_sample_notification_rollback_together(risk, monkeypatch):
    rule = watch(risk)
    entered, release = Event(), Event()
    risk.hook[0] = lambda: (entered.set(), release.wait(3))
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(lambda: check(risk, rule))
        assert entered.wait(2)
        change(risk, rule, "pause")
        release.set()
        assert running.result()["status"] == "paused"
    assert risk.alerts.inbox.page()["total"] == 0
    risk.hook[0] = None
    change(risk, rule, "arm")
    original = risk.alerts.journal.write
    monkeypatch.setattr(risk.alerts.journal, "write", lambda *_: (_ for _ in ()).throw(RuntimeError("crash")))
    with pytest.raises(RuntimeError):
        check(risk, rule)
    assert risk.alerts.inbox.page()["total"] == 0
    assert not risk.alerts.journal.evidence(rule["id"])["samples"]
    monkeypatch.setattr(risk.alerts.journal, "write", original)
    check(risk, rule)
    assert risk.alerts.inbox.page()["total"] == 1


def test_revision_checked_edit_archive_restore_and_new_peak_window(risk):
    rule = watch(risk, metric="drawdown", threshold=10)
    check(risk, rule)
    old_sample = current(risk, rule)["last_sample_id"]
    old_peak = current(risk, rule)["peak"]
    updated = risk.alerts.edit(
        rule["id"], RiskAlertUpdate(**request(risk, metric="drawdown", threshold=5).model_dump(), revision=1)
    )
    assert updated["status"] == "paused" and updated["peak"] is None
    assert risk.alerts.journal.evidence(rule["id"], old_sample)["sample"]["peak"] == old_peak
    with pytest.raises(AlertConflict):
        risk.alerts.change(rule["id"], AlertAction(action="arm", revision=1))
    change(risk, rule, "arm")
    risk.balances[risk.first.id] = {"USDT": 150}
    assert check(risk, rule)["peak"] == 150
    change(risk, rule, "archive")
    assert risk.alerts.rules()["count"] == 0
    assert change(risk, rule, "restore")["status"] == "paused"
    assert risk.alerts.rules(True)["total"] == 1
    risk.alerts.limit = 1
    with pytest.raises(ValueError):
        watch(risk)


def test_retained_sample_caps_do_not_remove_original_inbox_evidence(risk, monkeypatch):
    monkeypatch.setattr("sibyl.alerts.risk.journal.SAMPLES_PER_RULE", 2)
    monkeypatch.setattr("sibyl.alerts.risk.journal.MAX_SAMPLES", 3)
    rule = watch(risk)
    check(risk, rule)
    notice = risk.alerts.inbox.page()["items"][0]
    for _ in range(4):
        check(risk, rule)
    evidence = risk.alerts.journal.evidence(rule["id"], notice["sample_id"])
    assert evidence["sample"] is None and len(evidence["samples"]) == 2
    assert risk.alerts.inbox.page()["items"][0] == notice
    risk.alerts.close()
    old_calls = list(risk.calls)
    risk.alerts.tick()
    assert old_calls == risk.calls


@pytest.mark.parametrize(
    "fields",
    [
        {"threshold": True},
        {"threshold": float("nan")},
        {"threshold": 0},
        {"metric": "drawdown", "threshold": 101},
        {"metric": "concentration", "asset": ""},
        {"asset": "BTC"},
        {"reset_threshold": 100},
        {"cooldown_seconds": True},
        {"notify_recovery": "true"},
        {"label": "two\nlines"},
        {"extra": 1},
    ],
)
def test_invalid_limits_and_unknown_fields_are_rejected(risk, fields):
    with pytest.raises(ValidationError):
        request(risk, **fields)


def test_http_evidence_and_native_accountant_tool_are_passive(client, monkeypatch):
    service = client.app.state.services.portfolio.risk_alerts
    service.close()  # Isolate passive HTTP reads from the independently authorized background watcher.
    monkeypatch.setattr(service.market, "client", lambda *_: pytest.fail("Passive endpoint fetched balances"))
    response = client.post(
        "/api/v1/risk-alerts", json=dict(account_ids=["demo"], source="demo", metric="drawdown", threshold=10)
    )
    assert response.status_code == 201 and response.headers["cache-control"] == "no-store"
    rule = response.json()
    assert client.get("/api/v1/risk-alerts").json()["count"] == 1
    assert client.get(f"/api/v1/risk-alerts/{rule['id']}/evidence").json()["sample"] is None
    assert client.get("/api/v1/risk-alerts/example").json()["inbox"]["items"][0]["kind"] == "risk"
    assert (
        client.post(
            f"/api/v1/risk-alerts/{rule['id']}/action", json=dict(action="pause", revision=99)
        ).status_code
        == 409
    )
    network = client.app.state.services.agents.network
    result = client.portal.call(
        network.client.send_task, network.cards["accountant"].url, Task.create_tool_call("risk_alerts", {})
    )
    result.raise_for_status()
    evidence = result.get_last_item().parts[-1].as_tool_output().result
    assert evidence["rules"]["items"][0]["id"] == rule["id"]


def test_stablecoin_depeg_and_inverse_routes_use_observed_rates(risk):
    risk.balances[risk.first.id] = {"USDC": 100, "USDT": 10}
    rule = watch(risk, threshold=100)
    assert check(risk, rule)["last_observation"]["total"] == 100
    risk.quotes.clear()
    risk.quotes["USDT/USDC"] = 2
    assert check(risk, rule)["last_observation"]["total"] == 60
    sample = risk.alerts.journal.evidence(rule["id"])["sample"]
    assert sample["holdings"][0]["path"] == ["USDC", "USDT"]


def test_database_commit_does_not_reenter_settings_or_market_locks(risk, monkeypatch):
    rule = watch(risk)
    original = risk.alerts.reader.read

    def read_before_settings_change(rule):
        sample, guard = original(rule)
        monkeypatch.setattr(
            risk.data, "resolve_market", lambda *_: pytest.fail("Settings lock under SQLite write")
        )
        return sample, guard

    monkeypatch.setattr(risk.alerts.reader, "read", read_before_settings_change)
    assert check(risk, rule)["notifications"] == 1


def test_concurrent_consumers_cannot_duplicate_or_overwrite_a_newer_check(risk, monkeypatch):
    from threading import Barrier

    rule = watch(risk)
    barrier = Barrier(2)
    other = RiskAlerts(risk.market, risk.store, clock=lambda: risk.wall[0])
    for service in (risk.alerts, other):
        original = service.reader.read

        def synchronized(rule, original=original):
            result = original(rule)
            barrier.wait(timeout=3)
            return result

        monkeypatch.setattr(service.reader, "read", synchronized)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda service: service.tick(), [risk.alerts, other]))
    assert risk.alerts.inbox.page()["total"] == 1
    assert current(risk, rule)["checks"] == 1
    assert len(risk.alerts.journal.evidence(rule["id"])["samples"]) == 1


def test_retained_revision_contains_the_original_metric_and_levels(risk):
    rule = watch(risk, threshold=200)
    check(risk, rule)
    sample_id = current(risk, rule)["last_sample_id"]
    risk.alerts.edit(
        rule["id"],
        RiskAlertUpdate(
            **request(risk, metric="concentration", asset="BTC", threshold=60).model_dump(), revision=1
        ),
    )
    sample = risk.alerts.journal.evidence(rule["id"], sample_id)["sample"]
    assert sample["revision"] == 1 and sample["policy"]["metric"] == "value_floor"
    assert sample["policy"]["threshold"] == 200
    assert risk.alerts.journal.evidence(rule["id"])["sample"] is None


def test_empty_spot_balance_is_zero_for_a_value_floor_and_sample_age_is_bounded(risk):
    rule = watch(risk, threshold=100)
    risk.balances[risk.first.id] = {}
    assert check(risk, rule)["last_observation"]["total"] == 0
    notice = risk.alerts.inbox.page()["items"][0]
    risk.wall[0] += 15 * 86400
    check(risk, rule)
    assert risk.alerts.journal.evidence(rule["id"], notice["sample_id"])["sample"] is None
    assert risk.alerts.inbox.page()["items"][0] == notice


def test_risk_endpoints_require_the_workspace_token(client):
    client.app.state.services.settings.api_token = SecretStr("workspace-token")
    assert client.get("/api/v1/risk-alerts").status_code == 401
    assert client.get("/api/v1/risk-alerts/example").status_code == 401
    assert (
        client.get("/api/v1/risk-alerts", headers={"Authorization": "Bearer workspace-token"}).status_code
        == 200
    )


def test_background_worker_retries_a_transient_storage_failure(client, monkeypatch):
    import sqlite3

    recovered = Event()
    calls = []

    def tick():
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.OperationalError("test-only storage contention")
        recovered.set()

    monkeypatch.setattr(client.app.state.services.portfolio.risk_alerts, "tick", tick)
    assert recovered.wait(5), "The dedicated watcher must survive transient SQLite errors."
    assert len(calls) >= 2


def test_passive_evidence_hides_expired_details_without_a_new_private_read(risk):
    rule = watch(risk)
    check(risk, rule)
    notice = risk.alerts.inbox.page()["items"][0]
    previous_calls = list(risk.calls)
    risk.wall[0] += 15 * 86400
    evidence = risk.alerts.journal.evidence(rule["id"], notice["sample_id"])
    assert evidence["sample"] is None and not evidence["samples"]
    assert risk.calls == previous_calls
    assert risk.alerts.inbox.page()["items"][0] == notice
