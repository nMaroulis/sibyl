"""Actual strategy/fill/HTTP paths with controlled venues; no real account writes."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from test_strategy_execution import execution as execution
from test_strategy_execution import reconcile, request, start, submit

from sibyl.strategies import Strategies
from sibyl.strategies.execution import runner
from sibyl.strategies.execution.ownership.contracts import OwnershipReview
from sibyl.strategies.execution.risk.ledger import positions, totals


@pytest.fixture
def ownership(execution, monkeypatch):
    strategies, trading, native, connection = execution
    monkeypatch.setattr(
        native, "fetch_balance", lambda: {"total": dict(native.free), "free": dict(native.free)}
    )
    return strategies.execution.ownership


def held(execution):
    strategies, trading, native, _ = execution
    job, intent = submit(execution)
    native.settle(intent["exchange_order_id"])
    reconcile(trading, intent["id"])
    strategies.status(job["id"], "stopped")
    return strategies.journal.job(job["id"]), intent


def paused(execution):
    strategies, _, _, _ = execution
    job, _ = start(execution)
    strategies.status(job["id"], "paused")
    return strategies.journal.job(job["id"])


def adoption(ownership, job, **changes):
    return ownership.preview(
        job["id"],
        OwnershipReview(
            action="adopt", quantity=1.0, cost_basis=75.0, note="Manually acquired position", **changes
        ),
    )


def approve(ownership, review):
    return ownership.confirm(review["id"], review["confirmation"])


def test_native_check_is_on_demand_and_does_not_assign_manual_holdings(execution, ownership, monkeypatch):
    strategies, _, native, _ = execution
    job, _ = held(execution)
    calls = []
    fetch = native.fetch_balance
    monkeypatch.setattr(native, "fetch_balance", lambda: calls.append(True) or fetch())
    state = ownership.state(job["id"])
    assert state["check"] is None and not calls
    result = ownership.inspect(job["id"])
    check = result["check"]
    assert calls == [True]
    assert check["total"] == 50 and check["free"] == 50
    assert check["strategy_owned"] == job["quantity"]
    assert check["unassigned"] == pytest.approx(50 - job["quantity"])
    assert check["shortfall"] == 0 and check["current"]
    assert check["cost_min"] == 1 and check["amount_min"] == 0.0001
    assert not result["history"] and len(native.calls) == 1
    assert strategies.journal.job(job["id"])["quantity"] == job["quantity"]


@pytest.mark.parametrize("value", [None, True, float("nan"), -1])
def test_missing_invalid_native_total_remains_unknown(execution, ownership, monkeypatch, value):
    job = paused(execution)
    native = execution[2]
    monkeypatch.setattr(native, "fetch_balance", lambda: {"total": {"BTC": value}, "free": {"BTC": 1.0}})
    with pytest.raises(ValueError, match="finite native total"):
        ownership.inspect(job["id"])
    assert ownership.state(job["id"])["check"] is None


def test_adoption_has_asserted_basis_separate_flows_and_no_cash_or_native_trade(execution, ownership):
    strategies, _, native, _ = execution
    job = paused(execution)
    review = adoption(ownership, job)
    assert ownership.state(job["id"])["quantity"] == 0
    assert "evidence" not in json.dumps(review)
    state = approve(ownership, review)
    final = strategies.journal.job(job["id"])
    assert final["quantity"] == 1 and final["entry_cost"] == 75
    assert final["cash"] == 1000 and final["status"] == "paused"
    assert state["net_reference_flow"] == native.bid
    assert not final["statistics_complete"] and "metrics" not in final
    assert final["native_fill_count"] == 0 and final["realized_pnl"] == 0
    assert not native.calls and state["event_count"] == 1
    assert state["check"]["strategy_owned"] == 1 and state["check"]["current"]
    assert state["check"]["unassigned"] == 49 and not state["check"]["dust"]
    assert not approve(ownership, review)["stale"]
    assert ownership.state(job["id"])["event_count"] == 1
    assert (
        "OWNERSHIP" in strategies.journal.export(job["id"]).__next__()
        or strategies.journal.events(job["id"])["items"][0]["action"] == "OWNERSHIP"
    )


def test_adopted_units_participate_in_subsequent_actual_native_sell_accounting(
    execution, ownership, monkeypatch
):
    strategies, trading, native, _ = execution
    job = paused(execution)
    approve(ownership, adoption(ownership, job))
    strategies.status(job["id"], "running")
    monkeypatch.setattr(runner, "signals", lambda frame, *args: pd.Series([-1] * len(frame)))
    native.clock += 60
    strategies.tick()
    intent = strategies.execution._intent(strategies.journal.job(job["id"]))
    assert intent["request"]["side"] == "sell"
    native.settle(intent["exchange_order_id"], fee=0.1)
    reconcile(trading, intent["id"])
    strategies.tick()
    final = strategies.journal.job(job["id"])
    disposed = intent["request"]["quantity"]
    assert final["quantity"] == pytest.approx(1 - disposed)
    assert final["entry_cost"] == pytest.approx(75 * (1 - disposed))
    assert final["realized_pnl"] == pytest.approx(disposed * 25 - 0.1)
    assert final["native_fill_count"] == 1 and final["ownership_event_count"] == 1


def test_release_carries_basis_keeps_cash_and_does_not_claim_sale_proceeds(execution, ownership):
    strategies, _, native, _ = execution
    job, _ = held(execution)
    review = ownership.preview(
        job["id"],
        OwnershipReview(
            action="release", quantity=job["quantity"], note="Release retained dust to manual management"
        ),
    )
    result = approve(ownership, review)
    final = strategies.journal.job(job["id"])
    assert final["quantity"] == 0 and final["entry_cost"] == pytest.approx(0)
    assert final["cash"] == job["cash"] and final["realized_pnl"] == job["realized_pnl"]
    assert result["history"][0]["cost_basis"] == -job["entry_cost"]
    assert result["net_reference_flow"] == -job["quantity"] * native.bid
    assert len(native.calls) == 1
    # Released base units no longer block a fresh exact-account/pair approval.
    assert strategies.execution.preview(request(execution[3]))


@pytest.mark.parametrize(
    "cause",
    [
        "quantity",
        "status",
        "fees",
        "other_owner",
        "balance",
        "confirmation",
        "expiry",
        "correction",
        "credentials",
    ],
)
def test_review_rejects_ineligible_or_changed_evidence(execution, ownership, cause):
    strategies, trading, native, _ = execution
    if cause in {"fees", "correction"}:
        job, intent = held(execution)
        if cause == "fees":
            native.fills[0]["fees"] = []
            reconcile(trading, intent["id"])
            with pytest.raises(ValueError):
                ownership.preview(
                    job["id"], OwnershipReview(action="release", quantity=1.0, note="Check fees")
                )
            return
        review = ownership.preview(
            job["id"], OwnershipReview(action="release", quantity=1.0, note="Reviewed release")
        )
    else:
        job = paused(execution)
        if cause == "status":
            strategies.status(job["id"], "running")
            with pytest.raises(ValueError, match="Pause or stop"):
                adoption(ownership, job)
            return
        if cause == "quantity":
            native.free["BTC"] = 0.5
            with pytest.raises(ValueError, match="exceeds free"):
                adoption(ownership, job)
            return
        if cause == "other_owner":
            # A different quote pair still consumes the same base asset on this account.
            other = {**job, "id": "other-owner", "parameters": {**job["parameters"], "symbol": "BTC/USD"}}
            strategies.journal.save(other)
            native.markets["BTC/USD"] = native.markets["BTC/USDT"]
            approve(ownership, adoption(ownership, other))
            native.free["BTC"] = 1.5
            with pytest.raises(ValueError, match="exceeds free"):
                adoption(ownership, job)
            return
        review = adoption(ownership, job)
    if cause == "balance":
        native.free["BTC"] = 40
    elif cause == "expiry":
        with strategies.store.db() as db:
            raw = json.loads(
                db.execute(
                    "SELECT payload FROM strategy_ownership_reviews WHERE id=?", (review["id"],)
                ).fetchone()[0]
            )
            raw["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
            db.execute(
                "UPDATE strategy_ownership_reviews SET payload=? WHERE id=?", (json.dumps(raw), review["id"])
            )
    elif cause == "correction":
        native.fills[0]["fees"][0]["cost"] += 0.5
        reconcile(trading, intent["id"])
    elif cause == "credentials":
        with strategies.store.db() as db:
            db.execute(
                "UPDATE connections SET credentials=? WHERE id=?", (b"replacement", job["connection_id"])
            )
    with pytest.raises(ValueError):
        ownership.confirm(review["id"], "yes" if cause == "confirmation" else review["confirmation"])
    assert ownership.state(job["id"])["event_count"] == 0


def test_concurrent_confirmation_and_restart_are_idempotent(execution, ownership):
    strategies, trading, native, _ = execution
    job = paused(execution)
    review = adoption(ownership, job)
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: approve(ownership, review), range(4)))
    assert all(row["event_count"] == 1 for row in results)
    restarted = Strategies(strategies.market, strategies.store)
    restarted.attach_execution(trading)
    assert restarted.execution.ownership.confirm(review["id"], review["confirmation"])["event_count"] == 1
    restarted.tick()
    assert restarted.journal.job(job["id"])["quantity"] == 1 and not native.calls


def handoff(execution, ownership):
    strategies, _, _, connection = execution
    source, intent = held(execution)
    review = strategies.execution.preview(request(connection, handoff_from=source["id"]))
    target = strategies.execution.start(review["id"], review["confirmation"])
    return source, intent, review, target


def test_handoff_atomically_carries_basis_and_leaves_source_stopped(execution, ownership):
    strategies, _, native, _ = execution
    source, _, review, target = handoff(execution, ownership)
    old = strategies.journal.job(source["id"])
    assert old["quantity"] == 0 and old["status"] == "stopped" and old["cash"] == source["cash"]
    assert target["quantity"] == source["quantity"] and target["entry_cost"] == source["entry_cost"]
    assert target["cash"] == target["parameters"]["capital"]
    assert target["ownership_net_value"] == -old["ownership_net_value"]
    assert target["status"] == "running" and len(native.calls) == 1
    assert target["ownership_events"][0]["peer_id"] == source["id"]
    assert old["ownership_events"][0]["peer_id"] == target["id"]
    assert strategies.execution.start(review["id"], review["confirmation"])["id"] == target["id"]
    assert len(ownership.state(source["id"])["history"]) == 1
    assert not strategies.execution.options()["handoff_sources"]


def test_late_source_correction_invalidates_descendant_and_prevents_writes(execution, ownership):
    strategies, trading, native, _ = execution
    source, intent, _, target = handoff(execution, ownership)
    native.fills[0]["fees"][0]["cost"] += 0.5
    reconcile(trading, intent["id"])
    assert ownership.state(source["id"])["stale"]
    assert ownership.state(target["id"])["stale"]
    native.clock += 60
    strategies.tick()
    latest = strategies.journal.job(target["id"])
    assert latest["status"] == "paused" and latest["accounting_incomplete"]
    assert len(native.calls) == 1
    with pytest.raises(ValueError):
        strategies.status(target["id"], "running")


def test_handoff_competing_reviews_cannot_duplicate_position(execution, ownership):
    strategies, _, native, connection = execution
    source, _ = held(execution)
    first = strategies.execution.preview(request(connection, handoff_from=source["id"]))
    second = strategies.execution.preview(request(connection, handoff_from=source["id"]))
    strategies.execution.start(first["id"], first["confirmation"])
    with pytest.raises(ValueError):
        strategies.execution.start(second["id"], second["confirmation"])
    assert len(strategies.execution.jobs()) == 2 and len(native.calls) == 1


def test_reference_flows_do_not_create_shared_profit_or_double_exposure(execution, ownership):
    strategies, trading, _, _ = execution
    source, _, _, target = handoff(execution, ownership)
    rates = {"BTC": {"price": 100}, "USDT": {"price": 1}}
    with strategies.store.db() as db:
        values = totals(positions(db, trading, "test"), rates)
    assert values["position"] == pytest.approx(source["quantity"] * 100)
    assert sum(row["pnl"] for row in values["runs"]) == pytest.approx(
        source["cash"] + source["quantity"] * 100 - source["parameters"]["capital"]
    )
    assert values["allocated"] == pytest.approx(target["parameters"]["capital"] + source["quantity"] * 100)


def test_native_shortfall_blocks_attributed_resume_and_reports_deficit(execution, ownership):
    strategies, _, native, _ = execution
    job = paused(execution)
    approve(ownership, adoption(ownership, job))
    native.free["BTC"] = 0.25
    check = ownership.inspect(job["id"])["check"]
    assert check["shortfall"] == 0.75
    with pytest.raises(ValueError, match="no longer back"):
        strategies.status(job["id"], "running")
    assert not native.calls


def test_dust_uses_actual_native_minimums_and_precision(execution, ownership):
    job = paused(execution)
    review = ownership.preview(
        job["id"], OwnershipReview(action="adopt", quantity=0.00001, cost_basis=0.001, note="Retained dust")
    )
    approve(ownership, review)
    check = ownership.inspect(job["id"])["check"]
    assert check["dust"] and check["amount_min"] == 0.0001 and check["cost_min"] == 1


def test_http_reviews_project_safe_evidence(manual_client, execution, ownership, monkeypatch):
    strategies, _, _, _ = execution
    monkeypatch.setattr(manual_client.app.state.services, "strategies", strategies)
    job = paused(execution)
    base = f"/api/v1/strategies/exchange/jobs/{job['id']}/ownership"
    assert manual_client.get(base).json()["check"] is None
    assert manual_client.post(base + "/check").status_code == 200
    review = manual_client.post(
        base + "/preview",
        json={"action": "adopt", "quantity": 1.0, "cost_basis": 75.0, "note": "Reviewed external position"},
    )
    assert review.status_code == 200, review.text
    value = review.json()
    result = manual_client.post(
        f"/api/v1/strategies/exchange/ownership-reviews/{value['id']}/confirm",
        json={"confirmation": value["confirmation"]},
    )
    assert result.status_code == 200, result.text
    assert result.json()["quantity"] == 1
    journal_url = f"/api/v1/strategies/jobs/{job['id']}"
    events = manual_client.get(journal_url + "/events?action=OWNERSHIP")
    assert events.status_code == 200, events.text
    assert events.json()["items"][0]["action"] == "OWNERSHIP"
    export = manual_client.get(journal_url + "/events.csv?action=OWNERSHIP")
    assert export.status_code == 200, export.text
    assert "ownership_event_id" in export.text and "Manually" not in export.text
    public = result.text + review.text + manual_client.get(base).text
    assert all(
        secret not in public
        for secret in (
            "credential_version",
            '"pins"',
            '"digest"',
            '"evidence"',
            '"_native_fills"',
            '"api_key"',
        )
    )
    assert (
        manual_client.post(
            base + "/preview", json={"action": "adopt", "quantity": True, "cost_basis": 1, "note": "bad"}
        ).status_code
        == 422
    )


def test_broker_reads_ownership_through_native_protolink_without_checking_exchange(
    manual_client, monkeypatch
):
    from protolink import create_llm

    client = manual_client
    strategies = client.app.state.services.strategies
    # A paused run with no imported fills is enough to verify the native read tool.
    job = {
        "id": "native-ownership-read",
        "mode": "exchange",
        "connection_id": "nonexistent-read-only",
        "account": "Saved test",
        "exchange": "binance-testnet",
        "sandbox": True,
        "environment": "test",
        "parameters": {"symbol": "BTC/USDT", "capital": 1000},
        "status": "paused",
        "fills": [],
        "cash": 1000,
        "quantity": 0,
        "created_at": datetime.now(UTC).isoformat(),
        "source": "test",
    }
    strategies.journal.save(job)
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    monkeypatch.setattr(
        "sibyl.agents.utils.registry.create_llm",
        lambda *a, **kw: create_llm(
            "mock",
            sequential_responses=[
                {"type": "tool_call", "tool": "position_ownership", "args": {}},
                "This run has no assigned units. Check the account explicitly to inspect native balances.",
            ],
        ),
    )
    monkeypatch.setattr(
        strategies.execution.ownership,
        "inspect",
        lambda *a, **kw: pytest.fail("Agent performed an exchange check"),
    )
    response = client.post(
        "/api/v1/agents/ask",
        json={
            "module": "broker",
            "message": "Explain this position ownership",
            "context": {"job_id": job["id"]},
        },
    )
    assert response.status_code == 200, response.text
    evidence = response.json()["evidence"]
    assert evidence["job_id"] == job["id"] and evidence["quantity"] == 0 and evidence["check"] is None
    assert '"pins"' not in response.text and '"api_key"' not in response.text


def test_final_submission_rechecks_source_evidence_after_quote(execution, ownership, monkeypatch):
    strategies, trading, native, connection = execution
    source, entry = submit(execution)
    native.settle(entry["exchange_order_id"], quantity=1.0)
    reconcile(trading, entry["id"])
    strategies.status(source["id"], "stopped")
    review = strategies.execution.preview(request(connection, handoff_from=source["id"]))
    target = strategies.execution.start(review["id"], review["confirmation"])
    original = trading.execute

    def execute(*args, **kwargs):
        native.fills[0]["fees"][0]["cost"] += 0.5
        reconcile(trading, entry["id"])
        return original(*args, **kwargs)

    # The inherited one-unit residual is dust, but the next entry exceeds native minimums.
    native.markets["BTC/USDT"]["limits"]["amount"]["min"] = 2.0
    monkeypatch.setattr(trading, "execute", execute)
    native.clock += 60
    strategies.tick()
    assert len(native.calls) == 1  # Only the source's original buy.
    assert strategies.journal.job(target["id"])["status"] == "paused"
    assert ownership.state(target["id"])["stale"]


def test_unattributed_runs_do_not_add_private_balance_reads_to_idle_ticks(execution, ownership, monkeypatch):
    strategies, _, native, _ = execution
    job, _ = start(execution)
    calls = []
    original = native.fetch_balance
    monkeypatch.setattr(native, "fetch_balance", lambda: calls.append(True) or original())
    strategies.tick()  # Same candle: no new order or attribution needs a balance read.
    assert not calls and not ownership.needs_backing(job)
    strategies.status(job["id"], "paused")
    approve(ownership, adoption(ownership, job))
    assert ownership.needs_backing(job)
    calls.clear()
    strategies.status(job["id"], "running")
    assert calls == [True]
