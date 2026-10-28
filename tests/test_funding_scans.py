"""Rolling native history reads and observed source corrections remain bounded and explicit."""

import json
import time
from contextlib import contextmanager
from types import SimpleNamespace

import ccxt
import pytest

from sibyl.accounting.funding.versions import FundingVersions
from sibyl.exchanges.funding import DAY, FundingPage
from sibyl.models import ConnectionCreate
from sibyl.services.funding.contracts import FundingRefreshConflict, RefreshFunding, ScanFunding, scan_streams
from sibyl.services.funding.scans import FundingScans
from sibyl.services.funding_ledger import funding_event, write_event
from sibyl.services.funding_sync import FundingSync
from sibyl.services.market import Market


@pytest.fixture
def workspace(settings, store, monkeypatch):
    account = store.add_connection(
        ConnectionCreate(
            exchange="binance", label="Offline Binance", api_key="fake-key", secret="fake-secret"
        )
    )
    market = Market(settings, store)
    sync = FundingSync(market, store)
    clock = SimpleNamespace(value=time.time())
    monkeypatch.setattr(time, "time", lambda: clock.value)
    w = SimpleNamespace(
        store=store,
        account=account,
        market=market,
        sync=sync,
        scans=sync.scans,
        clock=clock,
        calls=[],
        fetch=None,
    )

    @contextmanager
    def adapter(connection):
        def fetch(stream, cursor, limit):
            w.calls.append((connection.id, stream, dict(cursor), limit))
            assert w.fetch is not None, "Unconfigured test provider"
            return w.fetch(stream, cursor, limit)

        yield SimpleNamespace(fetch_funding_page=fetch)

    monkeypatch.setattr(market, "adapter", adapter)
    yield w
    sync.close()
    market.close()


def raw(w, identity="native-1", **changes):
    return {
        "native_id": identity,
        "reference": None,
        "timestamp_ms": int(w.clock.value * 1000) - 3600000,
        "asset": "BTC",
        "quantity": 1,
        "kind": "withdrawal",
        "direction": "out",
        "status": "completed",
        "posted_ms": int(w.clock.value * 1000) - 3500000,
        "fee": {"currency": "BTC", "cost": 0.01},
        "internal": False,
        "amount_basis": "provider_reported",
        "wallet_scope": "configured",
        **changes,
    }


def seed(w, row=None, account=None, origin="history_import"):
    account = account or w.account
    row = row or raw(w)
    event = funding_event(
        row,
        dict(
            account_id=account.id,
            account=account.label,
            exchange=account.exchange,
            environment="production",
            stream=row["kind"],
            start_ms=1,
            end_ms=int(w.clock.value * 1000),
        ),
    )
    with w.store.db() as db:
        write_event(db, event, "2026-01-01T00:00:00+00:00", origin=origin)
    return event


def policy(w):
    return next((row for row in w.scans.ledger.snapshot() if row["account_id"] == w.account.id), None)


def enable(w, **changes):
    state = policy(w)
    body = {"enabled": True, "replace_revision": state["revision"] if state else None, **changes}
    w.scans.configure(w.account, "withdrawal", ScanFunding(**body))


def read(w, event_id):
    with w.store.db() as db:
        return json.loads(
            db.execute("SELECT payload FROM funding_events WHERE id=?", (event_id,)).fetchone()[0]
        )


def step(w, seconds=10):
    w.clock.value += seconds
    w.scans.tick()


def test_default_off_and_first_window_are_explicit_and_bounded(workspace):
    w = workspace
    w.scans.tick()
    assert not w.calls and policy(w) is None
    row = raw(w)
    w.fetch = lambda _s, cursor, _n: FundingPage([row], cursor, True)
    now = w.clock.value
    enable(w, lookback_days=7)
    w.scans.tick()
    cursor = w.calls[0][2]
    assert cursor == {"start": int(now * 1000) - 60000 - 7 * DAY, "end": int(now * 1000) - 60000}
    state = policy(w)
    assert state["inserted"] == 1 and state["passes"] == 1
    assert not state["last_report"]["complete_history"] and not state["last_report"]["settlement_final"]
    with w.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM funding_sync").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM funding_scan_sources").fetchone()[0] == 0
    step(w)
    assert len(w.calls) == 1


def test_repeated_window_discovers_late_record_and_completed_fee_correction_with_audit(workspace):
    w = workspace
    original = raw(w)
    event = seed(w, original)
    w.fetch = lambda _s, cursor, _n: FundingPage([original], cursor, True)
    enable(w)
    w.scans.tick()
    later = {**original, "native_id": "late-record"}
    corrected = {**original, "fee": {"currency": "BTC", "cost": 0.02}}
    w.fetch = lambda _s, cursor, _n: FundingPage([corrected, later], cursor, True)
    enable(w, check_now=True)
    step(w)
    assert policy(w)["last_report"]["inserted"] == 1 and policy(w)["last_report"]["updated"] == 1
    assert read(w, event["id"])["fee"]["cost"] == 0.02
    history = FundingVersions(w.store).history(event["id"])
    assert history["total"] == 2 and history["entries"][0]["origin"] == "recent_sync"
    assert history["entries"][0]["changes"] == [
        {
            "field": "fee",
            "before": {"currency": "BTC", "cost": 0.01},
            "after": {"currency": "BTC", "cost": 0.02},
        }
    ]
    assert history["entries"][1]["first_observation"]


def test_repeated_identical_reads_and_label_changes_do_not_fabricate_revisions(workspace):
    w = workspace
    row = seed(w)
    seed(w)
    with w.store.db() as db:
        write_event(db, {**row, "account": "Renamed"}, "2026-02-01T00:00:00+00:00")
    assert FundingVersions(w.store).history(row["id"])["total"] == 1


def test_native_reference_correction_has_an_observed_revision(workspace):
    w = workspace
    original = raw(w)
    event = seed(w, original)
    seed(w, {**original, "reference": "changed-reference"})
    assert FundingVersions(w.store).history(event["id"])["entries"][0]["changes"] == [
        {"field": "reference", "before": None, "after": "changed-reference"}
    ]


def test_missing_completed_record_is_retained_and_reported_without_inventing_cancellation(workspace):
    w = workspace
    row = seed(w)
    w.fetch = lambda _s, cursor, _n: FundingPage([], cursor, True)
    enable(w)
    w.scans.tick()
    report = policy(w)["last_report"]
    assert report["not_returned"] == 1 and report["not_returned_preview"][0]["id"] == row["id"]
    assert read(w, row["id"])["status"] == "completed"
    assert FundingVersions(w.store).history(row["id"])["total"] == 1


@pytest.mark.parametrize("action", ["manual_update", "manual_insert", "deleted"])
def test_concurrent_native_facts_win_over_snapshot_response(workspace, action):
    w = workspace
    original = raw(w)
    event = seed(w, original) if action != "manual_insert" else None

    def fetch(_s, cursor, _n):
        if action == "deleted":
            with w.store.db() as db:
                db.execute("DELETE FROM funding_events WHERE id=?", (event["id"],))
        else:
            seed(w, {**original, "reference": "manual-correction"})
        return FundingPage([original], cursor, True)

    w.fetch = fetch
    enable(w)
    w.scans.tick()
    assert policy(w)["last_report"]["concurrent_changes"] == 1
    with w.store.db() as db:
        sources = db.execute("SELECT payload FROM funding_events").fetchall()
    if action == "deleted":
        assert not sources
    else:
        assert json.loads(sources[0][0])["reference"] == "manual-correction"


def test_restart_resumes_frozen_cursor_and_versions(workspace):
    w = workspace
    source = raw(w)
    first = {**source, "native_id": "page-one"}
    second = {**source, "native_id": "page-two"}
    w.fetch = lambda _s, cursor, _n: (
        FundingPage([first], {**cursor, "page": "private-token"}, False)
        if not cursor.get("page")
        else FundingPage([second], cursor, True)
    )
    enable(w)
    w.scans.tick()
    with w.store.db() as db:
        saved = w.scans.ledger.read_job(db, w.account.id, "withdrawal")
        start = saved["start_ms"]
        saved["status"] = "running"
        w.scans.ledger.write_job(db, saved)
    restarted = FundingScans(w.market, w.store)
    w.clock.value += 10
    restarted.tick()
    assert w.calls[-1][2]["page"] == "private-token" and w.calls[-1][2]["start"] == start
    assert policy(w)["inserted"] == 2 and policy(w)["passes"] == 1
    assert "private-token" not in json.dumps(policy(w))
    restarted.close()


@pytest.mark.parametrize("action", ["disable", "configure", "deactivate", "credentials", "disconnect"])
def test_inflight_scope_or_control_change_discards_page_and_audit(workspace, action):
    w = workspace
    source = raw(w)
    enable(w)

    def fetch(_s, cursor, _n):
        if action == "disable":
            enable(w, enabled=False)
        elif action == "configure":
            enable(w, lookback_days=1)
        elif action == "deactivate":
            w.store.activate_account(w.account.id, False)
        elif action == "credentials":
            with w.store.db() as db:
                db.execute(
                    "UPDATE connections SET credentials=? WHERE id=?", (b"changed-encrypted", w.account.id)
                )
        else:
            with w.store.db() as db:
                db.execute("DELETE FROM connections WHERE id=?", (w.account.id,))
        return FundingPage([source], cursor, True)

    w.fetch = fetch
    w.scans.tick()
    with w.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM funding_events").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM funding_versions").fetchone()[0] == 0
    assert policy(w)["passes"] == 0


def test_control_revision_is_stable_through_pass_and_old_saves_conflict(workspace):
    w = workspace
    enable(w)
    revision = policy(w)["revision"]
    w.fetch = lambda _s, cursor, _n: FundingPage([], cursor, True)
    w.scans.tick()
    assert policy(w)["revision"] == revision
    with pytest.raises(FundingRefreshConflict):
        w.scans.configure(w.account, "withdrawal", ScanFunding(enabled=False))


def test_old_failure_cannot_change_new_window(workspace):
    w = workspace
    enable(w)
    w.scans.ledger.schedule(w.clock.value)
    with w.store.db() as db:
        old = w.scans.ledger.read_job(db, w.account.id, "withdrawal")
    enable(w, lookback_days=1)
    w.scans._failure(old, ccxt.NetworkError("PRIVATE"))
    assert policy(w)["status"] == "idle" and policy(w)["error"] is None


def test_old_preflight_cannot_disable_new_account_controls(workspace):
    w = workspace
    enable(w)
    w.scans.ledger.schedule(w.clock.value)
    with w.store.db() as db:
        old = w.scans.ledger.read_job(db, w.account.id, "withdrawal")
        db.execute("UPDATE connections SET credentials=? WHERE id=?", (b"new-encrypted", w.account.id))
    enable(w)
    with pytest.raises(ValueError):
        w.scans.read_page(SimpleNamespace(), old)
    assert policy(w)["enabled"]


def test_page_validation_and_duplicate_pages_do_not_partially_commit(workspace):
    w = workspace
    source = raw(w)
    w.fetch = lambda _s, cursor, _n: FundingPage(
        [source, {**source, "native_id": "bad", "quantity": float("nan")}], cursor, True
    )
    enable(w)
    w.scans.tick()
    assert policy(w)["status"] == "error"
    with w.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM funding_events").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM funding_versions").fetchone()[0] == 0
    w.fetch = lambda _s, cursor, _n: FundingPage(
        [source], {**cursor, "offset": cursor.get("offset", 0) + 50}, False
    )
    enable(w, check_now=True)
    step(w)
    step(w)
    assert policy(w)["status"] == "error" and policy(w)["passes"] == 0


def test_scan_page_budget_stops_without_another_native_request(workspace):
    w = workspace
    enable(w)
    w.scans.ledger.schedule(w.clock.value)
    with w.store.db() as db:
        job = w.scans.ledger.read_job(db, w.account.id, "withdrawal")
        job["pages"] = 200
        w.scans.ledger.write_job(db, job)
    w.scans.tick()
    assert not w.calls and policy(w)["status"] == "error"


def test_oversize_snapshot_stops_without_native_reads(workspace, monkeypatch):
    import sibyl.services.funding.scan_journal as journal

    w = workspace
    seed(w, raw(w, identity="one"))
    seed(w, raw(w, identity="two"))
    monkeypatch.setattr(journal, "SCAN_SOURCE_LIMIT", 1)
    enable(w)
    w.scans.tick()
    assert policy(w)["status"] == "error" and not w.calls


def test_pending_and_recent_workers_share_persisted_read_floor_and_fairness(workspace):
    w = workspace
    source = raw(w, status="pending", posted_ms=None)
    seed(w, source)
    w.fetch = lambda _s, cursor, _n: FundingPage([source], cursor, True)
    w.sync.refresh.configure(w.account, "withdrawal", RefreshFunding(enabled=True))
    enable(w)
    w.sync.refresh.tick()
    w.scans.tick()
    assert len(w.calls) == 1
    w.clock.value += 10
    w.sync.refresh.tick()
    w.scans.tick()
    assert len(w.calls) == 2 and policy(w)["passes"] == 1


def test_downtime_outside_lookback_is_an_explicit_coverage_gap(workspace):
    w = workspace
    w.fetch = lambda _s, cursor, _n: FundingPage([], cursor, True)
    enable(w, lookback_days=1)
    w.scans.tick()
    previous_end = policy(w)["covered_end_ms"]
    step(w, 3 * 86400)
    report = policy(w)["last_report"]
    assert report["gap"]["start_ms"] == previous_end + 1
    assert report["gap"]["end_ms"] == report["start_ms"] - 1


def test_scan_reports_and_observed_versions_have_bounded_reads(workspace):
    w = workspace
    source = raw(w)
    event = seed(w, source)
    w.fetch = lambda _s, cursor, _n: FundingPage([], cursor, True)
    enable(w)
    for index in range(23):
        seed(w, {**source, "fee": {"currency": "BTC", "cost": index + 1}})
        step(w, 3601)
    history = w.scans.ledger.history(w.account.id, "withdrawal")
    assert len(history["items"]) == history["limit"] == 20
    versions = FundingVersions(w.store).history(event["id"])
    assert versions["total"] == 24 and len(versions["entries"]) == 20
    assert "history" not in policy(w)


@pytest.mark.parametrize(
    "provider,sandbox,streams",
    [
        ("binance", False, ["deposit", "withdrawal"]),
        ("kraken", False, ["deposit", "withdrawal", "transfer"]),
        ("bybit", False, ["withdrawal"]),
        ("binance", True, []),
        ("binance-testnet", True, []),
        ("demo", False, []),
        ("coinbase", False, []),
    ],
)
def test_support_matches_implemented_native_adapters(provider, sandbox, streams):
    assert scan_streams(SimpleNamespace(exchange=provider, sandbox=sandbox)) == streams


def test_pause_close_and_scope_privacy(workspace, monkeypatch):
    w = workspace
    monkeypatch.setattr(w.store, "credentials", lambda *_: pytest.fail("Controls decrypted credentials"))
    enable(w)
    w.sync.pause(w.account.id)
    assert not policy(w)["enabled"]
    enable(w)
    w.scans.close()
    w.scans.tick()
    assert not w.calls
    public = json.dumps(w.sync.snapshot())
    assert "fake-secret" not in public and "account_version" not in public
    assert '"cursor"' not in public and '"run_id"' not in public


def test_read_only_http_versions_and_controls(client, monkeypatch):
    s = client.app.state.services
    # These assertions exercise HTTP acceptance, independently of the background scheduler.
    monkeypatch.setattr(s.funding_sync, "tick", lambda: None)
    monkeypatch.setattr(s.market, "adapter", lambda *_: pytest.fail("Control save contacted exchange"))
    account = s.store.add_connection(
        ConnectionCreate(exchange="binance", label="Offline", api_key="fake", secret="fake")
    )
    monkeypatch.setattr(s.store, "credentials", lambda *_: pytest.fail("Unexpected credential read"))
    endpoint = f"/api/v1/connections/{account.id}/funding-scans/withdrawal"
    response = client.post(endpoint, json={"enabled": True})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert client.post(endpoint, json={"enabled": False}).status_code == 409
    assert client.post(endpoint, json={"enabled": True, "lookback_days": 90}).status_code == 422
    assert (
        client.post("/api/v1/connections/demo/funding-scans/deposit", json={"enabled": True}).status_code
        == 400
    )
    assert client.get(endpoint + "/reports").json()["items"] == []
    assert client.get("/api/v1/account-ledger/funding/missing/versions").status_code == 404


def test_unfetched_intervals_remain_visible_after_subsequent_scans_and_manual_backfill_closes_them(workspace):
    from datetime import UTC, datetime

    from sibyl.services.funding_sync import FundingSyncRequest
    from sibyl.services.import_worker import ImportWorker

    w = workspace
    w.clock.value -= 10 * 86400
    w.fetch = lambda _s, cursor, _n: FundingPage([], cursor, True)
    enable(w, lookback_days=1)
    w.scans.tick()
    step(w, 3 * 86400)
    gap = policy(w)["uncovered_gaps"][0]
    step(w, 3601)
    assert policy(w)["last_report"]["gap"] is None
    assert policy(w)["uncovered_gap_count"] == 1 and policy(w)["uncovered_gaps"][0] == gap
    w.sync.enqueue(
        w.account,
        FundingSyncRequest(
            streams=["withdrawal"],
            start=datetime.fromtimestamp(gap["start_ms"] / 1000, UTC),
            end=datetime.fromtimestamp(gap["end_ms"] / 1000, UTC),
        ),
    )
    ImportWorker.tick(w.sync)
    assert policy(w)["uncovered_gap_count"] == 0


def test_partial_available_range_splits_unfetched_interval_without_claiming_settlement(workspace):
    from sibyl.services.funding.coverage import cover_gaps

    w = workspace
    with w.store.db() as db:
        db.execute(
            "INSERT INTO funding_coverage_gaps VALUES(?,?,?,?)", (w.account.id, "withdrawal", 100, 300)
        )
        cover_gaps(db, w.account.id, "withdrawal", 150, 200)
        rows = list(db.execute("SELECT start_ms,end_ms FROM funding_coverage_gaps ORDER BY start_ms"))
    assert [tuple(row) for row in rows] == [(100, 149), (201, 300)]


def test_local_audit_preserves_prior_facts_when_feature_starts_after_an_existing_record(workspace):
    w = workspace
    event = seed(w)
    with w.store.db() as db:
        db.execute("DELETE FROM funding_versions")
        write_event(
            db,
            {**event, "fee": {"currency": "BTC", "cost": 0.02}},
            "2026-02-01T00:00:00+00:00",
            origin="recent_sync",
        )
    history = FundingVersions(w.store).history(event["id"])
    assert history["total"] == 1 and not history["entries"][0]["first_observation"]
    assert history["entries"][0]["changes"][0]["before"] == {"currency": "BTC", "cost": 0.01}


def test_native_accountant_receives_scoped_recent_controls_and_observed_changes_without_secrets(
    client, monkeypatch
):
    from protolink import Task

    s = client.app.state.services
    # Keep enabled-policy evidence while preventing an unrelated automatic read in this test.
    monkeypatch.setattr(s.funding_sync, "tick", lambda: None)
    account = s.store.add_connection(
        ConnectionCreate(exchange="binance", label="Offline", api_key="test-key", secret="test-secret")
    )
    s.funding_sync.scans.configure(account, "withdrawal", ScanFunding(enabled=True))
    stamp = int(time.time() * 1000) - 100000
    event = funding_event(
        {
            "native_id": "native-agent",
            "reference": None,
            "timestamp_ms": stamp,
            "posted_ms": stamp + 1000,
            "asset": "BTC",
            "quantity": 1,
            "kind": "withdrawal",
            "direction": "out",
            "status": "completed",
            "internal": False,
            "amount_basis": "provider_reported",
            "fee": {"currency": "BTC", "cost": 0.01},
            "wallet_scope": "configured",
        },
        {
            "account_id": account.id,
            "account": account.label,
            "exchange": "binance",
            "environment": "production",
            "stream": "withdrawal",
            "start_ms": 1,
            "end_ms": stamp + 10000,
        },
    )
    with s.store.db() as db:
        write_event(db, event, "2026-01-01T00:00:00+00:00")
        write_event(
            db,
            {**event, "fee": {"currency": "BTC", "cost": 0.02}},
            "2026-02-01T00:00:00+00:00",
            origin="recent_sync",
        )
    monkeypatch.setattr(s.store, "credentials", lambda *_: pytest.fail("Agent accessed credentials"))
    monkeypatch.setattr(s.market, "adapter", lambda *_: pytest.fail("Agent contacted exchange"))
    network = s.agents.network

    def query(account_id):
        response = client.portal.call(
            network.client.send_task,
            network.cards["accountant"].url,
            Task.create_tool_call("accountant_snapshot", {"funding_view": True, "account_id": account_id}),
        )
        response.raise_for_status()
        return response.get_last_item().parts[-1].as_tool_output().result

    evidence = query(account.id)
    assert evidence["recent_sync"][0]["lookback_days"] == 7
    assert "revision" not in evidence["recent_sync"][0]
    assert evidence["items"][0]["last_observed_change"]["changes"][0]["field"] == "fee"
    assert "test-secret" not in json.dumps(evidence)
    assert query("another-account")["recent_sync"] == []


def test_versions_http_is_read_only_and_excludes_private_raw_metadata(client, monkeypatch):
    s = client.app.state.services
    account = s.store.connections()[0]
    event = {
        "id": "b" * 64,
        "account_id": account.id,
        "account": "Offline",
        "exchange": "demo",
        "environment": "demo",
        "native_id": "native-http",
        "reference": None,
        "asset": "BTC",
        "kind": "deposit",
        "timestamp_ms": 1,
        "posted_ms": 1,
        "direction": "in",
        "quantity": 1,
        "status": "completed",
        "fee": {"currency": "BTC", "cost": 0},
        "fee_known": True,
        "internal": False,
        "amount_basis": "provider_reported",
        "wallet_scope": "configured",
        "created_at": "1970-01-01T00:00:00Z",
    }
    with s.store.db() as db:
        write_event(db, event, "2026-01-01T00:00:00Z")
    monkeypatch.setattr(s.store, "credentials", lambda *_: pytest.fail("History decrypted credentials"))
    monkeypatch.setattr(s.market, "adapter", lambda *_: pytest.fail("History contacted exchange"))
    response = client.get(f"/api/v1/account-ledger/funding/{event['id']}/versions")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert response.json()["total"] == 1
    assert "after_payload" not in response.text and "source_version" not in response.text


def test_numeric_representation_alone_is_not_an_observed_financial_change(workspace):
    w = workspace
    event = seed(w)
    with w.store.db() as db:
        write_event(db, {**event, "quantity": 1}, "2026-02-01T00:00:00Z")
    assert FundingVersions(w.store).history(event["id"])["total"] == 1
