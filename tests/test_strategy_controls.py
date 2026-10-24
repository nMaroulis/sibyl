"""Global admission controls with fake venues, races and durable recovery evidence."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError
from test_strategy_cancellation import approve_stop, expiring, retained
from test_strategy_closing import owned
from test_strategy_execution import execution as execution
from test_strategy_execution import reconcile, request, start, submit

from sibyl.models import BacktestRequest, ExchangeOrderRequest
from sibyl.strategies import Strategies
from sibyl.strategies.execution.contracts import ClosePositionRequest
from sibyl.strategies.execution.controls import RELEASE_CONFIRMATION, ControlAction, ControlConflict


def change(strategies, action="halt", **fields):
    controls = strategies.execution.controls
    return controls.change(
        ControlAction(
            action=action,
            revision=controls.state()["revision"],
            confirmation=RELEASE_CONFIRMATION if action == "release" else "",
            **fields,
        )
    )


def test_halt_atomically_pauses_only_running_exchange_jobs_and_journals_each(execution):
    strategies, _, native, _ = execution
    job, _ = start(execution)
    for identity, mode, status in (
        ("second-account", "exchange", "running"),
        ("already-paused", "exchange", "paused"),
        ("terminal", "exchange", "stopped"),
        ("paper", "paper", "running"),
    ):
        strategies.journal.save({**job, "id": identity, "mode": mode, "status": status})
    result = change(strategies, reason="Investigate provider health")
    assert result["halted"] and result["revision"] == 1
    assert result["history"][0]["paused_count"] == 2
    assert set(result["history"][0]["paused_job_ids"]) == {job["id"], "second-account"}
    for identity in (job["id"], "second-account"):
        paused = strategies.journal.job(identity)
        assert paused["status"] == "paused" and paused["halt_revision"] == 1
        event = strategies.journal.events(identity)["items"][0]
        assert event["action"] == "PAUSE" and event["control_revision"] == 1
    assert strategies.journal.job("paper")["status"] == "running"
    assert strategies.journal.job("terminal")["status"] == "stopped"
    assert strategies.journal.events("already-paused")["items"] == []
    assert not native.calls and not native.cancels


def test_failed_pause_transaction_does_not_partially_apply_halt(execution, monkeypatch):
    strategies, _, _, _ = execution
    job, _ = start(execution)

    def fail(*args, **kwargs):
        raise RuntimeError("Local failure")

    monkeypatch.setattr(strategies, "_event", fail)
    with pytest.raises(RuntimeError):
        change(strategies)
    assert not strategies.execution.controls.state()["halted"]
    assert strategies.journal.job(job["id"])["status"] == "running"
    assert not strategies.execution.controls.state()["history"]


def test_halt_needs_no_provider_access_and_blocks_start_preview_resume(execution, monkeypatch):
    strategies, _, native, connection = execution
    review = strategies.execution.preview(request(connection))

    def fail(*args, **kwargs):
        pytest.fail("Halt must not need provider availability")

    monkeypatch.setattr(native, "fetch_balance", fail)
    monkeypatch.setattr(native, "fetch_order_book", fail)
    state = change(strategies)
    assert state["halted"]
    for operation in (
        lambda: strategies.execution.preview(request(connection)),
        lambda: strategies.execution.start(review["id"], review["confirmation"]),
    ):
        with pytest.raises(ValueError, match="Global strategy halt"):
            operation()
    assert not native.calls


def test_release_requires_current_revision_and_exact_phrase_never_resumes(execution):
    strategies, _, native, _ = execution
    job, _ = start(execution)
    state = change(strategies)
    with pytest.raises(ValueError, match="Type RELEASE"):
        strategies.execution.controls.change(ControlAction(action="release", revision=1))
    with pytest.raises(ControlConflict):
        strategies.execution.controls.change(
            ControlAction(action="release", revision=0, confirmation=RELEASE_CONFIRMATION)
        )
    assert strategies.execution.controls.state()["halted"]
    with pytest.raises(ValueError, match="Global strategy halt"):
        strategies.status(job["id"], "running")
    released = change(strategies, "release")
    assert not released["halted"] and released["revision"] == state["revision"] + 1
    assert released["history"][0]["paused_count"] == 0
    native.clock += 120
    strategies.tick()
    assert not native.calls and strategies.journal.job(job["id"])["status"] == "paused"
    strategies.status(job["id"], "running")
    strategies.tick()
    assert not native.calls
    native.clock += 60
    strategies.tick()
    assert len(native.calls) == 1


def test_review_created_before_halt_cannot_start_after_release(execution):
    strategies, _, native, connection = execution
    review = strategies.execution.preview(request(connection))
    change(strategies)
    change(strategies, "release")
    with pytest.raises(ValueError, match="controls changed"):
        strategies.execution.start(review["id"], review["confirmation"])
    fresh = strategies.execution.preview(request(connection))
    strategies.execution.start(fresh["id"], fresh["confirmation"])
    assert not native.calls


def test_halt_and_epoch_survive_restart_and_server_flags_can_stay_disabled(execution):
    strategies, trading, _, _ = execution
    job, _ = start(execution)
    strategies.market.settings.allow_live_trading = strategies.market.settings.allow_strategy_execution = (
        False
    )
    change(strategies)
    restarted = Strategies(strategies.market, strategies.store)
    restarted.attach_execution(trading)
    state = restarted.execution.controls.state()
    assert state["halted"] and state["revision"] == 1 and not state["server_enabled"]
    change(restarted, "release")
    assert restarted.journal.job(job["id"])["status"] == "paused"
    with pytest.raises(ValueError, match="SIBYL_ALLOW_LIVE_TRADING"):
        restarted.status(job["id"], "running")


def test_repeat_and_stale_actions_never_release_a_later_halt(execution):
    strategies, _, _, _ = execution
    first = change(strategies)
    assert change(strategies)["revision"] == first["revision"]  # Idempotent same-state request.
    change(strategies, "release")
    third = change(strategies)
    assert third["revision"] == 3
    with pytest.raises(ControlConflict):
        strategies.execution.controls.change(
            ControlAction(action="release", revision=1, confirmation=RELEASE_CONFIRMATION)
        )
    assert strategies.execution.controls.state()["halted"]


def test_halt_during_unlocked_order_preview_discards_plan(execution, monkeypatch):
    strategies, trading, native, _ = execution
    start(execution)
    original = trading.preview

    def halt_before_preview(body):
        change(strategies)
        return original(body)

    monkeypatch.setattr(trading, "preview", halt_before_preview)
    native.clock += 60
    strategies.tick()
    intent = trading.list_orders()[0]
    assert not native.calls and intent["strategy_abandoned"] and not intent["tracking"]
    change(strategies, "release")
    with pytest.raises(ValueError, match="controls changed"):
        trading.execute(intent["id"], intent["confirmation"], strategy_job_id=intent["strategy_job_id"])


def test_submission_boundary_checks_latch_even_with_internal_owner_id(execution):
    strategies, trading, native, connection = execution
    job, _ = start(execution)
    intent = trading.preview(
        ExchangeOrderRequest(
            connection_id=connection.id,
            symbol="BTC/USDT",
            side="buy",
            quantity=1,
            order_type="limit",
            limit_price=100,
            idempotency_key="control-test-manual",
        )
    )
    with strategies.store.db() as db:
        intent.update(origin="strategy", strategy_job_id=job["id"], strategy_control_revision=0)
        trading.lifecycle.write(db, intent)
    change(strategies)
    with pytest.raises(ValueError, match="Global strategy halt"):
        trading.execute(intent["id"], intent["confirmation"], strategy_job_id=job["id"])
    assert retained(trading, intent["id"])["status"] == "preview" and not native.calls


def test_halt_during_observation_and_release_resume_cannot_use_old_evidence(execution, monkeypatch):
    strategies, _, native, _ = execution
    job, _ = start(execution)
    original = native.fetch_order_book

    def interrupted(*args, **kwargs):
        monkeypatch.setattr(native, "fetch_order_book", original)
        change(strategies)
        change(strategies, "release")
        strategies.status(job["id"], "running")
        return original(*args, **kwargs)

    monkeypatch.setattr(native, "fetch_order_book", interrupted)
    native.clock += 60
    strategies.tick()
    assert not native.calls
    assert strategies.journal.job(job["id"])["status"] == "paused"


def test_halt_serializes_with_an_admitted_native_request(execution, monkeypatch):
    strategies, _, native, _ = execution
    job, _ = start(execution)
    entered, finish, requested = threading.Event(), threading.Event(), threading.Event()
    original = native.create_order

    def slow(*args, **kwargs):
        entered.set()
        assert finish.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(native, "create_order", slow)
    native.clock += 60
    with ThreadPoolExecutor(2) as pool:
        tick = pool.submit(strategies.tick)
        assert entered.wait(5)

        def halt():
            requested.set()
            return change(strategies)

        stop = pool.submit(halt)
        assert requested.wait(5)
        assert not stop.done()
        finish.set()
        tick.result(timeout=5)
        assert stop.result(timeout=5)["halted"]
    assert len(native.calls) == 1
    assert strategies.journal.job(job["id"])["status"] == "paused"
    native.clock += 60
    strategies.tick()
    assert len(native.calls) == 1


def test_pending_orders_and_later_fills_remain_owned_without_auto_cancellation(execution):
    strategies, trading, native, _ = execution
    job, intent = submit(execution)
    change(strategies)
    assert not native.cancels
    native.settle(intent["exchange_order_id"], quantity=1, terminal=False)
    reconcile(trading, intent["id"])
    strategies.tick()
    current = strategies.journal.job(job["id"])
    assert current["quantity"] == 1 and current["status"] == "paused"
    assert len(native.calls) == 1 and not native.cancels


def test_approved_expiry_and_stop_cancel_continue_during_halt(execution):
    strategies, _, native, _ = execution
    job, _, deadline = expiring(execution)
    change(strategies)
    native.clock = deadline + 1
    strategies.tick()
    assert len(native.cancels) == 1
    assert strategies.journal.job(job["id"])["status"] == "paused"
    approve_stop(strategies, job["id"])
    assert strategies.journal.job(job["id"])["status"] == "stopped"


def test_separately_reviewed_owned_exit_remains_available(execution):
    strategies, _, native, _ = execution
    job, _ = owned(execution)
    change(strategies)
    review = strategies.execution.closing.preview(job["id"], ClosePositionRequest())
    strategies.execution.closing.confirm(review["id"], review["confirmation"])
    assert len(native.calls) == 2 and native.calls[-1][0] == "sell"
    assert strategies.execution.controls.state()["halted"]


def test_manual_order_and_paper_runs_are_unaffected(execution):
    strategies, trading, native, connection = execution
    change(strategies)
    paper = strategies.start(BacktestRequest(capital=1000), source="demo")
    strategies.tick()
    assert strategies.journal.job(paper["id"])["status"] == "running"
    intent = trading.preview(
        ExchangeOrderRequest(
            connection_id=connection.id,
            symbol="BTC/USDT",
            side="buy",
            quantity=1,
            order_type="limit",
            limit_price=100,
            idempotency_key="control-test-manual",
        )
    )
    trading.execute(intent["id"], intent["confirmation"])
    assert len(native.calls) == 1


@pytest.mark.parametrize(
    "fields",
    [
        {"revision": True},
        {"revision": "1"},
        {"revision": -1},
        {"action": "resume"},
        {"reason": "x" * 241},
        {"extra": True},
    ],
)
def test_control_contract_is_bounded_and_strict(fields):
    with pytest.raises(ValidationError):
        ControlAction(**({"action": "halt", "revision": 0} | fields))


def test_control_reads_are_passive_and_http_conflicts_are_not_cached(client):
    path = "/api/v1/strategies/exchange/controls"
    first = client.get(path)
    assert first.status_code == 200 and first.headers["cache-control"] == "no-store"
    assert first.json()["history"] == [] and first.json()["revision"] == 0
    halted = client.post(path, json={"action": "halt", "revision": 0})
    assert halted.status_code == 200 and halted.json()["halted"]
    stale = client.post(path, json={"action": "release", "revision": 0, "confirmation": RELEASE_CONFIRMATION})
    assert stale.status_code == 409 and stale.headers["cache-control"] == "no-store"
    assert client.post(path, json={"action": "release", "revision": 1}).status_code == 400
    assert client.post(path, json={"action": "halt", "revision": True}).status_code == 422
    assert client.get(path).json()["revision"] == 1
    options = client.get("/api/v1/strategies/exchange/options").json()
    assert not options["enabled"] and options["controls"]["halted"] and not options["server_enabled"]


def test_http_controls_use_existing_origin_and_workspace_token_boundaries(client):
    path = "/api/v1/strategies/exchange/controls"
    assert (
        client.post(
            path, json={"action": "halt", "revision": 0}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    from pydantic import SecretStr

    client.app.state.services.settings.api_token = SecretStr("local-test-token")
    assert client.get(path).status_code == 401
    assert client.post(path, json={"action": "halt", "revision": 0}).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer local-test-token"}).status_code == 200


def test_audit_is_bounded_and_reads_do_not_rewrite_history(execution):
    strategies, _, _, _ = execution
    for index in range(206):
        change(strategies, "halt" if index % 2 == 0 else "release")
    result = strategies.execution.controls.state()
    assert result["revision"] == 206 and len(result["history"]) == 20
    assert result["history"][0]["revision"] == 206
    with strategies.store.db() as db:
        count, oldest = db.execute("SELECT COUNT(*),MIN(revision) FROM strategy_control_events").fetchone()
        assert count == 200 and oldest == 7
    assert strategies.execution.controls.state() == result
