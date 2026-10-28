"""Opt-in native status reads preserve evidence, scope, cursors and user control."""

import json
import time
from contextlib import contextmanager
from types import SimpleNamespace

import ccxt
import pytest

from sibyl.accounting.funding.rules import fingerprint
from sibyl.exchanges.funding import FundingPage
from sibyl.models import ConnectionCreate
from sibyl.services.funding.contracts import FundingRefreshConflict, RefreshFunding, refresh_streams
from sibyl.services.funding_ledger import funding_event, write_event
from sibyl.services.funding_sync import FundingSync
from sibyl.services.market import Market


@pytest.fixture
def workspace(settings, store, monkeypatch):
    account = store.add_connection(
        ConnectionCreate(exchange="binance", label="Offline Binance", api_key="test-only", secret="test-only")
    )
    market = Market(settings, store)
    sync = FundingSync(market, store)
    clock = SimpleNamespace(value=time.time())
    monkeypatch.setattr(time, "time", lambda: clock.value)
    value = SimpleNamespace(
        store=store,
        market=market,
        sync=sync,
        refresh=sync.refresh,
        account=account,
        clock=clock,
        calls=[],
        fetch=None,
    )

    @contextmanager
    def adapter(connection):
        def fetch(stream, cursor, limit):
            value.calls.append((connection.id, stream, dict(cursor), limit))
            assert value.fetch is not None, "No test provider response configured"
            return value.fetch(stream, cursor, limit)

        yield SimpleNamespace(fetch_funding_page=fetch)

    monkeypatch.setattr(market, "adapter", adapter)
    yield value
    sync.close()
    market.close()


def native(workspace, identity="pending-1", **changes):
    result = dict(
        native_id=identity,
        reference=None,
        timestamp_ms=int(workspace.clock.value * 1000) - 3_600_000,
        asset="BTC",
        quantity=1,
        kind="withdrawal",
        direction="out",
        status="pending",
        internal=False,
        amount_basis="provider_reported",
        fee={"currency": "BTC", "cost": 0.01},
        wallet_scope="configured",
    )
    return {**result, **changes}


def seed(w, row=None, account=None):
    account = account or w.account
    raw = row or native(w)
    event = funding_event(
        raw,
        dict(
            account_id=account.id,
            account=account.label,
            exchange=account.exchange,
            environment="production",
            stream=raw["kind"],
            start_ms=1,
            end_ms=int(w.clock.value * 1000),
        ),
    )
    with w.store.db() as db:
        write_event(db, event, "original")
    return event


def policy(w, account=None):
    return next(
        (row for row in w.refresh.ledger.snapshot() if row["account_id"] == (account or w.account).id), None
    )


def enable(w, **changes):
    current = policy(w)
    request = {"enabled": True, "replace_revision": current["revision"] if current else None, **changes}
    w.refresh.configure(w.account, "withdrawal", RefreshFunding(**request))


def read(w, event_id):
    with w.store.db() as db:
        return json.loads(
            db.execute("SELECT payload FROM funding_events WHERE id=?", (event_id,)).fetchone()[0]
        )


def step(w, seconds=10):
    w.clock.value += seconds
    w.refresh.tick()


def complete(w, raw=None):
    raw = raw or native(w)
    return {**raw, "status": "completed", "posted_ms": raw["timestamp_ms"] + 1000}


def test_default_off_and_enabled_without_pending_never_contacts_provider(workspace):
    w = workspace
    seed(w)
    w.refresh.tick()
    assert not w.calls and policy(w) is None
    with w.store.db() as db:
        db.execute("DELETE FROM funding_events")
    enable(w)
    w.refresh.tick()
    assert not w.calls and policy(w)["status"] == "idle"


def test_status_refresh_updates_only_original_identity_and_preserves_manual_checkpoint(workspace):
    w = workspace
    source = native(w)
    row = seed(w, source)
    with w.store.db() as db:
        before = list(db.execute("SELECT * FROM funding_sync"))
    w.fetch = lambda _s, cursor, _n: FundingPage(
        [complete(w, source), {**complete(w, source), "native_id": "unrequested-neighbour"}], cursor, True
    )
    enable(w)
    w.refresh.tick()
    updated = read(w, row["id"])
    assert updated["status"] == "completed" and updated["posted_ms"] == source["timestamp_ms"] + 1000
    assert fingerprint(updated) != fingerprint(row)
    assert policy(w)["pending_count"] == 0 and policy(w)["updated"] == 1 and policy(w)["checked"] == 1
    assert len(w.calls) == 1 and w.calls[0][-1] == 50
    assert 0 < w.calls[0][2]["end"] - w.calls[0][2]["start"] <= 62_000
    with w.store.db() as db:
        assert list(db.execute("SELECT * FROM funding_sync")) == before
        assert db.execute("SELECT COUNT(*) FROM funding_events").fetchone()[0] == 1
        assert db.execute("SELECT first_seen_at FROM funding_events").fetchone()[0] == "original"
    step(w, 3600)
    assert len(w.calls) == 1  # Completed records are not re-polled.


def test_unchanged_pending_read_waits_for_per_record_interval(workspace):
    w = workspace
    source = native(w)
    seed(w, source)
    w.fetch = lambda _s, cursor, _n: FundingPage([source], cursor, True)
    enable(w)
    w.refresh.tick()
    step(w, 10)
    assert len(w.calls) == 1
    step(w, 290)
    assert len(w.calls) == 1  # Idle scan was scheduled; source interval is observed conservatively.
    step(w, 10)
    assert len(w.calls) == 2
    assert policy(w)["updated"] == 0 and policy(w)["pending_count"] == 1


def test_missing_record_remains_pending_and_stops_after_five_exhausted_misses(workspace):
    w = workspace
    row = seed(w)
    w.fetch = lambda _s, cursor, _n: FundingPage([], cursor, True)
    enable(w)
    for _ in range(5):
        step(w, 301)
    state = policy(w)
    assert state["needs_review"] == 1 and state["attention"][0]["id"] == row["id"]
    assert read(w, row["id"])["status"] == "pending"
    step(w, 3600)
    assert len(w.calls) == 5
    enable(w, check_now=True)
    step(w, 10)
    assert len(w.calls) == 6 and policy(w)["needs_review"] == 0


def test_multi_page_pass_and_cursor_resume_after_restart(workspace):
    from sibyl.services.funding.refresh import FundingRefresh

    w = workspace
    source = native(w)
    seed(w, source)

    def fetch(_stream, cursor, _limit):
        return (
            FundingPage([], {**cursor, "page": "opaque-private"}, False)
            if not cursor.get("page")
            else FundingPage([complete(w, source)], cursor, True)
        )

    w.fetch = fetch
    enable(w)
    w.refresh.tick()
    assert policy(w)["status"] == "queued" and policy(w)["checked"] == 0
    restarted = FundingRefresh(w.market, w.store)
    w.clock.value += 10
    restarted.tick()
    assert w.calls[-1][2]["page"] == "opaque-private"
    assert policy(w)["status"] == "idle" and policy(w)["checked"] == 1
    assert "opaque-private" not in json.dumps(policy(w))
    restarted.close()


def test_restart_recovers_interrupted_running_page(workspace):
    from sibyl.services.funding.refresh import FundingRefresh

    w = workspace
    source = native(w)
    row = seed(w, source)
    enable(w)
    w.refresh.ledger.schedule(w.clock.value)
    with w.store.db() as db:
        job = w.refresh.ledger.read_job(db, w.account.id, "withdrawal")
        job["status"] = "running"
        w.refresh.ledger.write_job(db, job)
    w.fetch = lambda _s, cursor, _n: FundingPage([complete(w, source)], cursor, True)
    restarted = FundingRefresh(w.market, w.store)
    restarted.tick()
    assert read(w, row["id"])["status"] == "completed"
    restarted.close()


@pytest.mark.parametrize("action", ["disable", "deactivate", "disconnect", "credentials"])
def test_inflight_page_cannot_commit_after_account_or_controls_change(workspace, action):
    w = workspace
    source = native(w)
    row = seed(w, source)
    enable(w)

    def fetch(_stream, cursor, _limit):
        if action == "disable":
            enable(w, enabled=False)
        elif action == "deactivate":
            w.store.activate_account(w.account.id, False)
        elif action == "disconnect":
            with w.store.db() as db:
                db.execute("DELETE FROM connections WHERE id=?", (w.account.id,))
        else:
            with w.store.db() as db:
                db.execute(
                    "UPDATE connections SET credentials=? WHERE id=?", (b"new-encrypted-value", w.account.id)
                )
        return FundingPage([complete(w, source)], cursor, True)

    w.fetch = fetch
    w.refresh.tick()
    assert read(w, row["id"])["status"] == "pending"
    assert not policy(w)["enabled"]


def test_manual_source_correction_wins_over_older_inflight_response(workspace):
    w = workspace
    source = native(w)
    row = seed(w, source)
    enable(w)

    def fetch(_stream, cursor, _limit):
        seed(w, {**source, "status": "restricted"})
        return FundingPage([complete(w, source)], cursor, True)

    w.fetch = fetch
    w.refresh.tick()
    assert read(w, row["id"])["status"] == "restricted"
    with w.store.db() as db:
        assert db.execute("SELECT outcome FROM funding_rechecks").fetchone()[0] == "source_changed"


def test_disable_then_reenable_rejects_old_page_and_failure(workspace):
    w = workspace
    seed(w)
    enable(w)
    w.refresh.ledger.schedule(w.clock.value)
    with w.store.db() as db:
        old = w.refresh.ledger.read_job(db, w.account.id, "withdrawal")
    enable(w, enabled=False)
    enable(w)
    w.refresh._failure(old, ccxt.AuthenticationError("PRIVATE-NATIVE-ERROR"))
    assert policy(w)["status"] == "idle" and policy(w)["error"] is None


@pytest.mark.parametrize(
    "error,status",
    [
        (ccxt.AuthenticationError("PRIVATE-NATIVE-ERROR"), "error"),
        (ccxt.NetworkError("PRIVATE-NATIVE-ERROR"), "retrying"),
        (ccxt.NotSupported("PRIVATE-NATIVE-ERROR"), "error"),
    ],
)
def test_provider_errors_are_sanitized_and_checkpoint_preserved(workspace, error, status):
    w = workspace
    row = seed(w)

    def fetch(*_):
        raise error

    w.fetch = fetch
    enable(w)
    w.refresh.tick()
    assert policy(w)["status"] == status
    assert "PRIVATE-NATIVE-ERROR" not in json.dumps(policy(w))
    assert read(w, row["id"])["status"] == "pending"
    assert policy(w)["checked"] == 0


def test_repeated_page_and_page_budget_are_not_successful_checks(workspace):
    w = workspace
    source = native(w)
    seed(w, source)
    enable(w)
    w.fetch = lambda _s, cursor, _n: FundingPage(
        [source], {**cursor, "offset": cursor.get("offset", 0) + 50}, False
    )
    w.refresh.tick()
    step(w)
    assert policy(w)["status"] == "error" and policy(w)["checked"] == 0
    enable(w, check_now=True)
    w.refresh.ledger.schedule(w.clock.value)
    with w.store.db() as db:
        job = w.refresh.ledger.read_job(db, w.account.id, "withdrawal")
        job["pages"] = 20
        w.refresh.ledger.write_job(db, job)
    before = len(w.calls)
    step(w)
    assert policy(w)["status"] == "error" and len(w.calls) == before


def test_settings_revision_is_stable_during_background_pass_and_stale_writes_conflict(workspace):
    w = workspace
    source = native(w)
    seed(w, source)
    enable(w)
    revision = policy(w)["revision"]
    w.fetch = lambda _s, cursor, _n: FundingPage([source], cursor, True)
    w.refresh.tick()
    assert policy(w)["revision"] == revision
    with pytest.raises(FundingRefreshConflict):
        w.refresh.configure(w.account, "withdrawal", RefreshFunding(enabled=False))
    assert policy(w)["enabled"]


def test_manual_pause_and_deactivation_stop_pending_updates_even_if_range_was_caught_up(workspace):
    w = workspace
    enable(w)
    w.sync.pause(w.account.id)
    assert not policy(w)["enabled"]
    enable(w)
    w.store.activate_account(w.account.id, False)
    w.refresh.tick()
    assert not policy(w)["enabled"]
    with pytest.raises(ValueError, match="Activate"):
        enable(w)


@pytest.mark.parametrize(
    "provider,sandbox,stream,accepted",
    [
        ("binance", False, "deposit", True),
        ("binance", False, "withdrawal", True),
        ("bybit", False, "withdrawal", True),
        ("bybit", False, "deposit", False),
        ("kraken", False, "withdrawal", False),
        ("binance-testnet", True, "withdrawal", False),
        ("binance", True, "withdrawal", False),
        ("demo", False, "deposit", False),
    ],
)
def test_support_comes_from_actual_pending_sources(provider, sandbox, stream, accepted):
    assert (stream in refresh_streams(SimpleNamespace(exchange=provider, sandbox=sandbox))) == accepted


def test_controls_and_snapshot_never_require_decrypted_credentials(workspace, monkeypatch):
    w = workspace
    seed(w)
    monkeypatch.setattr(
        w.store, "credentials", lambda *_: pytest.fail("Controls must not decrypt credentials")
    )
    enable(w)
    result = w.sync.snapshot()
    public = json.dumps(result)
    assert "test-only" not in public and "account_version" not in public
    assert '"targets"' not in public and '"cursor"' not in public
    assert result["pending_updates"][0]["enabled"]


def test_closed_worker_never_queues_or_reads(workspace):
    w = workspace
    seed(w)
    enable(w)
    w.refresh.close()
    w.refresh.tick()
    assert not w.calls


def test_http_revision_controls_and_unsupported_sources(client):
    s = client.app.state.services
    account = s.store.add_connection(
        ConnectionCreate(exchange="binance", label="Offline account", api_key="test-only", secret="test-only")
    )
    endpoint = f"/api/v1/connections/{account.id}/funding-refresh/withdrawal"
    response = client.post(endpoint, json={"enabled": True})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert client.post(endpoint, json={"enabled": False}).status_code == 409
    assert client.post(endpoint, json={"enabled": True, "interval_minutes": 1}).status_code == 422
    assert (
        client.post("/api/v1/connections/demo/funding-refresh/deposit", json={"enabled": True}).status_code
        == 400
    )
    s.store.activate_account(account.id, False)
    current = response.json()[0]
    assert (
        client.post(endpoint, json={"enabled": True, "replace_revision": current["revision"]}).status_code
        == 400
    )


def test_global_read_floor_is_shared_by_accounts_and_fair(workspace):
    w = workspace
    first = native(w)
    seed(w, first)
    second = w.store.add_connection(
        ConnectionCreate(exchange="binance", label="Second offline", api_key="fake-key", secret="fake-secret")
    )
    seed(w, first, second)
    w.fetch = lambda _s, cursor, _n: FundingPage([first], cursor, True)
    enable(w)
    w.refresh.configure(second, "withdrawal", RefreshFunding(enabled=True))
    w.refresh.tick()
    w.refresh.tick()
    assert len(w.calls) == 1
    step(w, 9)
    assert len(w.calls) == 1
    step(w, 1)
    assert len(w.calls) == 2 and {call[0] for call in w.calls} == {w.account.id, second.id}


def test_provider_deferral_preserves_retry_budget_and_native_cursor(workspace):
    from sibyl.market_data.control import ProviderDeferred

    w = workspace
    seed(w)

    def deferred(*_args):
        raise ProviderDeferred(30)

    w.fetch = deferred
    enable(w)
    w.refresh.tick()
    state = policy(w)
    assert state["status"] == "retrying" and "cooldown" in state["error"]
    with w.store.db() as db:
        job = w.refresh.ledger.read_job(db, w.account.id, "withdrawal")
        assert job["retries"] == 0 and job["pages"] == 0 and "page" not in job["cursor"]
    step(w, 10)
    assert len(w.calls) == 1
    step(w, 20)
    assert len(w.calls) == 2


def test_transient_retry_budget_eventually_requires_explicit_retry(workspace):
    w = workspace
    seed(w)

    def failure(*_):
        raise ccxt.NetworkError("PRIVATE")

    w.fetch = failure
    enable(w)
    for _ in range(6):
        step(w, 400)
    assert policy(w)["status"] == "error"
    step(w, 3600)
    assert len(w.calls) == 6


def test_account_change_before_read_disables_without_native_access(workspace):
    w = workspace
    seed(w)
    enable(w)
    w.refresh.ledger.schedule(w.clock.value)
    with w.store.db() as db:
        db.execute(
            "UPDATE connections SET credentials=? WHERE id=?",
            (b"changed-encrypted-credentials", w.account.id),
        )
    w.refresh.tick()
    assert not w.calls and not policy(w)["enabled"]


def test_range_pausing_missing_job_does_not_change_pending_controls(workspace):
    w = workspace
    enable(w)
    with pytest.raises(LookupError):
        w.sync.pause(w.account.id, "withdrawal")
    assert policy(w)["enabled"]


def test_invalid_page_is_atomic_and_keeps_pending_status(workspace):
    w = workspace
    raw = native(w)
    row = seed(w, raw)
    w.fetch = lambda _s, cursor, _n: FundingPage(
        [complete(w, raw), {**complete(w, raw), "native_id": "bad", "quantity": float("nan")}], cursor, True
    )
    enable(w)
    w.refresh.tick()
    assert read(w, row["id"])["status"] == "pending"
    assert policy(w)["status"] == "error" and policy(w)["checked"] == 0


def test_overlapping_target_across_pages_fails_instead_of_double_counting(workspace):
    w = workspace
    raw = native(w)
    seed(w, raw)
    enable(w)

    def fetch(_s, cursor, _n):
        offset = cursor.get("offset", 0)
        return FundingPage(
            [raw, {**raw, "native_id": f"unrequested-{offset}"}], {**cursor, "offset": offset + 50}, False
        )

    w.fetch = fetch
    w.refresh.tick()
    step(w)
    assert policy(w)["status"] == "error" and policy(w)["checked"] == 0


def test_new_manual_range_does_not_forget_older_pending_record(workspace):
    from datetime import UTC, datetime

    from sibyl.services.funding_sync import FundingSyncRequest

    w = workspace
    raw = native(w)
    row = seed(w, raw)
    w.sync.enqueue(
        w.account,
        FundingSyncRequest(
            streams=["withdrawal"],
            start=datetime.fromtimestamp((raw["timestamp_ms"] + 10_000) / 1000, UTC),
            end=datetime.fromtimestamp((raw["timestamp_ms"] + 20_000) / 1000, UTC),
        ),
    )
    with w.store.db() as db:
        before = dict(db.execute("SELECT * FROM funding_sync").fetchone())
    w.fetch = lambda _s, cursor, _n: FundingPage([complete(w, raw)], cursor, True)
    enable(w)
    w.refresh.tick()
    assert read(w, row["id"])["status"] == "completed"
    with w.store.db() as db:
        assert dict(db.execute("SELECT * FROM funding_sync").fetchone()) == before


def test_attention_and_target_batches_are_bounded(workspace):
    w = workspace
    for index in range(1002):
        seed(w, native(w, identity=f"pending-{index}"))
    enable(w)
    w.refresh.ledger.schedule(w.clock.value)
    with w.store.db() as db:
        job = w.refresh.ledger.read_job(db, w.account.id, "withdrawal")
        assert len(job["targets"]) == 1000
        for event_id in job["targets"]:
            db.execute(
                "INSERT INTO funding_rechecks VALUES(?,?,?,?,?,?)",
                (event_id, 0, 5, "checked", None, "not_returned"),
            )
    state = policy(w)
    assert state["pending_count"] == 1002 and state["needs_review"] == 1000
    assert len(state["attention"]) == state["attention_limit"] == 10


def test_native_accountant_sees_read_only_pending_controls_without_scope_or_secret_leaks(client, monkeypatch):
    from protolink import Task

    s = client.app.state.services
    account = s.store.add_connection(
        ConnectionCreate(
            exchange="binance", label="Offline control", api_key="dummy-key", secret="dummy-secret"
        )
    )
    s.funding_sync.refresh.configure(account, "withdrawal", RefreshFunding(enabled=True))
    monkeypatch.setattr(s.store, "credentials", lambda *_: pytest.fail("Agent decrypted credentials"))
    monkeypatch.setattr(s.market, "adapter", lambda *_: pytest.fail("Agent contacted provider"))
    network = s.agents.network
    response = client.portal.call(
        network.client.send_task,
        network.cards["accountant"].url,
        Task.create_tool_call("accountant_snapshot", {"funding_view": True, "account_id": account.id}),
    )
    response.raise_for_status()
    result = response.get_last_item().parts[-1].as_tool_output().result
    assert result["pending_updates"][0]["enabled"]
    assert "revision" not in result["pending_updates"][0]
    assert "dummy-secret" not in json.dumps(result)
    response = client.portal.call(
        network.client.send_task,
        network.cards["accountant"].url,
        Task.create_tool_call("accountant_snapshot", {"funding_view": True, "account_id": "other"}),
    )
    response.raise_for_status()
    assert response.get_last_item().parts[-1].as_tool_output().result["pending_updates"] == []


def test_failure_after_account_rotation_stops_old_checks(workspace):
    w = workspace
    seed(w)
    enable(w)

    def fetch(*_):
        with w.store.db() as db:
            db.execute("UPDATE connections SET credentials=? WHERE id=?", (b"rotated-account", w.account.id))
        raise ccxt.NetworkError("PRIVATE")

    w.fetch = fetch
    w.refresh.tick()
    assert not policy(w)["enabled"] and policy(w)["status"] == "paused"
    assert "PRIVATE" not in json.dumps(policy(w))


def test_old_account_failure_cannot_disable_newly_reviewed_controls(workspace):
    w = workspace
    seed(w)
    enable(w)
    w.refresh.ledger.schedule(w.clock.value)
    with w.store.db() as db:
        old = w.refresh.ledger.read_job(db, w.account.id, "withdrawal")
        db.execute("UPDATE connections SET credentials=? WHERE id=?", (b"rotated-account", w.account.id))
    enable(w)
    revision = policy(w)["revision"]
    w.refresh._failure(old, ccxt.NetworkError("PRIVATE"))
    assert policy(w)["enabled"] and policy(w)["revision"] == revision and policy(w)["error"] is None
