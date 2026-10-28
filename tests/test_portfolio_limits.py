"""Shared strategy admission against isolated native-shaped venues; no private account use."""

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from test_strategy_execution import Venue, reconcile, request, start, submit
from test_strategy_execution import execution as execution

from sibyl.models import ConnectionCreate, ExchangeOrderRequest
from sibyl.strategies import Strategies
from sibyl.strategies.execution.contracts import ExecutionGuard
from sibyl.strategies.execution.controls import ControlConflict
from sibyl.strategies.execution.risk import prices
from sibyl.strategies.execution.risk.contracts import (
    RELEASE_CONFIRMATION,
    SAVE_CONFIRMATION,
    ReleaseLossLock,
    SaveLimits,
)


@pytest.fixture
def shared(execution, monkeypatch):
    strategies, _, _, _ = execution
    strategies.market.settings.mode = "live"
    clock = [datetime.now(UTC)]
    values = {"BTC": 100.0, "ETH": 10.0, "USDT": 1.0, "USD": 0.95}
    monkeypatch.setattr(prices, "utcnow", lambda: clock[0])

    def read(market, source, rows):
        assets = set()
        for row in rows:
            base, quote = row["symbol"].split("/")
            assets.add(quote)
            if row["retained"] or row.get("quantity", 0):
                assets.add(base)
        return {
            asset: {
                "price": values[asset],
                "status": "identity" if asset == "USDT" else "fresh",
                "observed_at": None if asset == "USDT" else clock[0].isoformat(),
                "path": [asset] if asset == "USDT" else [asset, "USDT"],
            }
            for asset in assets
        }, {"source": source, "source_label": "Isolated observed feed", "environment": "production"}

    monkeypatch.setattr(prices, "read", read)
    return strategies.execution.portfolio_limits, clock, values


def state(limits, environment="test"):
    return next(row for row in limits.state()["policies"] if row["environment"] == environment)


def enable(limits, environment="test", **changes):
    values = dict(enabled=True, max_allocated=5000, max_exposure=600, max_daily_loss=50, source="binance")
    values.update(changes)
    return limits.save(
        environment,
        SaveLimits(revision=state(limits, environment)["revision"], confirmation=SAVE_CONFIRMATION, **values),
    )


def second(execution):
    strategies, _, native, _ = execution
    connection = strategies.store.add_connection(
        ConnectionCreate(
            exchange="binance-testnet", label="Another exchange account", api_key="FAKE", secret="FAKE"
        )
    )
    other = Venue()
    other.clock = native.clock
    strategies.market._clients[connection.id] = other
    return connection, other


def test_default_policy_is_passive_and_does_not_enable_trading(client):
    response = client.get("/api/v1/strategies/exchange/limits")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert [row["environment"] for row in response.json()["policies"]] == ["production", "test"]
    assert all(not row["policy"]["enabled"] and not row["sample"] for row in response.json()["policies"])
    options = client.get("/api/v1/strategies/exchange/options").json()
    assert not options["server_enabled"]


def test_shared_allocations_span_accounts_and_reviews_reserve_nothing(execution, shared):
    strategies, _, native, connection = execution
    limits, _, _ = shared
    enable(limits, max_allocated=1500)
    first = strategies.execution.preview(request(connection))
    other, _ = second(execution)
    second_review = strategies.execution.preview(request(other))
    strategies.execution.start(first["id"], first["confirmation"])
    with pytest.raises(ExecutionGuard, match="capital limit"):
        strategies.execution.start(second_review["id"], second_review["confirmation"])
    assert not native.calls
    sample = state(limits)["sample"]
    assert sample["allocated"] == 1000 and sample["daily_loss"] == 0


def test_outstanding_buys_consume_exposure_across_accounts(execution, shared):
    strategies, _, native, connection = execution
    limits, _, _ = shared
    enable(limits)
    start(execution)
    other, other_venue = second(execution)
    review = strategies.execution.preview(request(other))
    strategies.execution.start(review["id"], review["confirmation"])
    native.clock += 60
    other_venue.clock += 60
    strategies.tick()
    assert len(native.calls) + len(other_venue.calls) == 1
    paused = [job for job in strategies.execution.jobs() if job["status"] == "paused"]
    assert len(paused) == 1 and "shared strategy exposure" in paused[0]["error"]
    limits.check("test")
    sample = state(limits)["sample"]
    assert sample["position"] == 0 and 490 < sample["pending_buys"] <= 500
    assert len(sample["runs"]) == 2


def test_partial_fills_count_held_units_and_only_unfilled_buy_remainder(execution, shared):
    strategies, trading, native, _ = execution
    limits, _, _ = shared
    enable(limits)
    _, intent = submit(execution)
    native.settle(intent["exchange_order_id"], quantity=1, fee=0, terminal=False)
    reconcile(trading, intent["id"])
    limits.check("test")
    sample = state(limits)["sample"]
    assert sample["position"] == 100
    assert sample["pending_buys"] == pytest.approx((intent["request"]["quantity"] - 1) * intent["price"])
    assert 490 < sample["exposure"] <= 500


def test_loss_lock_pauses_environment_retains_terminal_positions_and_survives_restart(execution, shared):
    strategies, trading, native, _ = execution
    limits, _, values = shared
    enable(limits)
    job, intent = submit(execution)
    native.settle(intent["exchange_order_id"], fee=0)
    reconcile(trading, intent["id"])
    # Stop does not release an owned position or its capital from shared controls.
    strategies.status(job["id"], "stopped")
    values["BTC"] = 80
    limits.check("test")
    current = state(limits)
    assert current["locked"] and current["sample"]["daily_loss"] > 90
    assert current["sample"]["allocated"] == 1000
    assert not native.cancels and len(native.calls) == 1
    restarted = Strategies(strategies.market, strategies.store)
    restarted.attach_execution(trading)
    assert state(restarted.execution.portfolio_limits)["locked"]
    assert not state(limits, "production")["locked"]
    assert current["history"][0]["action"] == "daily_loss_locked"


def test_late_fee_correction_trips_at_native_admission_and_commits_refusal(execution, shared):
    strategies, trading, native, connection = execution
    limits, _, _ = shared
    enable(limits, max_daily_loss=1)
    job, intent = submit(execution)
    native.settle(intent["exchange_order_id"], fee=0)
    reconcile(trading, intent["id"])
    limits.check("test")
    preview = trading.preview(
        ExchangeOrderRequest(
            connection_id=connection.id,
            symbol="BTC/USDT",
            side="sell",
            quantity=1,
            order_type="limit",
            limit_price=100,
            idempotency_key="late-fee-admission",
        ),
        strategy_job_id=job["id"],
    )
    with strategies.store.db() as db:
        preview["strategy_risk_revision"] = state(limits)["revision"]
        trading.lifecycle.write(db, preview)
    native.fills[0]["fees"] = [{"currency": "USDT", "cost": 2}]
    reconcile(trading, intent["id"])
    with pytest.raises(ExecutionGuard, match="daily-loss limit"):
        trading.execute(preview["id"], preview["confirmation"], strategy_job_id=job["id"])
    assert len(native.calls) == 1
    assert state(limits)["locked"]
    assert strategies.journal.job(job["id"])["status"] == "paused"
    with strategies.store.db() as db:
        assert trading.lifecycle.read(db, preview["id"])["strategy_abandoned"]


def test_latch_cannot_be_cleared_same_day_or_by_changing_limits(execution, shared):
    _, trading, native, _ = execution
    limits, clock, values = shared
    enable(limits)
    _, intent = submit(execution)
    native.settle(intent["exchange_order_id"], fee=0)
    reconcile(trading, intent["id"])
    values["BTC"] = 80
    limits.check("test")
    current = state(limits)
    release = ReleaseLossLock(revision=current["revision"], confirmation=RELEASE_CONFIRMATION)
    with pytest.raises(ExecutionGuard, match="next UTC day"):
        limits.release("test", release)
    enable(limits, max_daily_loss=1000)
    assert state(limits)["locked"]
    with pytest.raises(ExecutionGuard, match="before disabling"):
        enable(limits, enabled=False)
    clock[0] += timedelta(days=1)
    limits.release(
        "test", ReleaseLossLock(revision=state(limits)["revision"], confirmation=RELEASE_CONFIRMATION)
    )
    assert not state(limits)["locked"]
    assert state(limits)["sample"]["daily_loss"] == 0
    assert all(job["status"] != "running" for job in execution[0].execution.jobs())


def test_overnight_price_gap_counts_without_rebasing_away_loss(execution, shared):
    _, trading, native, _ = execution
    limits, clock, values = shared
    enable(limits)
    _, intent = submit(execution)
    native.settle(intent["exchange_order_id"], fee=0)
    reconcile(trading, intent["id"])
    limits.check("test")
    clock[0] += timedelta(days=1)
    values["BTC"] = 80
    limits.check("test")
    assert state(limits)["sample"]["daily_loss"] > 90
    assert state(limits)["locked"]


def test_incomplete_ledger_blocks_all_automatic_orders_without_clearing_baseline(execution, shared):
    strategies, trading, native, _ = execution
    limits, _, _ = shared
    enable(limits)
    job, intent = submit(execution)
    previous = state(limits)["period"]
    native.settle(intent["exchange_order_id"], fee=0)
    trading.lifecycle.refresh(intent["id"])
    with pytest.raises(ExecutionGuard, match="quantities.*differ"):
        limits.check("test")
    current = state(limits)
    assert current["period"] == previous
    assert current["error"] and not current["fresh"]
    assert strategies.journal.job(job["id"])["status"] == "paused"
    assert not current["locked"]  # Unknown evidence is not an invented loss breach.


def test_stale_assessment_is_rechecked_at_submission(execution, shared):
    strategies, trading, native, connection = execution
    limits, clock, _ = shared
    enable(limits)
    job, _ = start(execution)
    preview = trading.preview(
        ExchangeOrderRequest(
            connection_id=connection.id,
            symbol="BTC/USDT",
            side="buy",
            quantity=1,
            order_type="limit",
            limit_price=100,
            idempotency_key="stale-risk",
        ),
        strategy_job_id=job["id"],
    )
    with strategies.store.db() as db:
        preview["strategy_risk_revision"] = state(limits)["revision"]
        trading.lifecycle.write(db, preview)
    clock[0] += timedelta(seconds=61)
    with pytest.raises(ExecutionGuard, match="expired"):
        trading.execute(preview["id"], preview["confirmation"], strategy_job_id=job["id"])
    assert not native.calls


def test_concurrent_checks_cannot_overwrite_new_policy(execution, shared, monkeypatch):
    limits, _, _ = shared
    enable(limits)
    entered, proceed = threading.Event(), threading.Event()
    read = prices.read

    def slow(*args):
        entered.set()
        assert proceed.wait(5)
        return read(*args)

    monkeypatch.setattr(prices, "read", slow)
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(limits.check, "test")
        assert entered.wait(5)
        enable(limits, max_exposure=200)
        proceed.set()
        with pytest.raises(ControlConflict):
            result.result(5)
    assert state(limits)["sample"] is None
    assert state(limits)["policy"]["max_exposure"] == 200


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_allocated", True),
        ("max_exposure", -1),
        ("max_daily_loss", float("nan")),
        ("max_daily_loss", "50"),
        ("revision", True),
        ("source", "demo"),
        ("enabled", "true"),
        ("unexpected", 1),
    ],
)
def test_policy_contract_rejects_ambiguous_values(field, value):
    fields = dict(
        enabled=True,
        max_allocated=5000,
        max_exposure=500,
        max_daily_loss=50,
        revision=0,
        confirmation=SAVE_CONFIRMATION,
    )
    fields[field] = value
    with pytest.raises(ValidationError):
        SaveLimits(**fields)


def test_http_limits_require_revision_confirmation_and_workspace_access(client):
    path = "/api/v1/strategies/exchange/limits/test"
    body = dict(enabled=False, revision=0, confirmation=SAVE_CONFIRMATION, max_allocated=1000)
    assert client.post(path, json=body).status_code == 200
    stale = client.post(path, json=body)
    assert stale.status_code == 409 and stale.headers["cache-control"] == "no-store"
    assert client.post(path, json={**body, "revision": 1, "confirmation": ""}).status_code == 400
    assert client.post(path, json=body, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post(path.replace("test", "demo"), json=body).status_code == 422


def test_failed_trip_transaction_rolls_back_all_pauses(execution, shared, monkeypatch):
    strategies, trading, native, _ = execution
    limits, _, values = shared
    enable(limits)
    job, intent = submit(execution)
    native.settle(intent["exchange_order_id"], fee=0)
    reconcile(trading, intent["id"])
    values["BTC"] = 80
    original = limits._audit

    def fail(db, current, action, *args):
        if action == "daily_loss_locked":
            raise RuntimeError("Local audit storage unavailable")
        return original(db, current, action, *args)

    monkeypatch.setattr(limits, "_audit", fail)
    with pytest.raises(ExecutionGuard):
        limits.check("test")
    assert not state(limits)["locked"]
    assert strategies.journal.job(job["id"])["status"] == "paused"  # Separate fail-closed diagnostic.
    assert not any(item["action"] == "daily_loss_locked" for item in state(limits)["history"])
    assert len(native.calls) == 1


def test_two_native_writers_cannot_admit_the_same_exposure_headroom(execution, shared):
    strategies, trading, native, connection = execution
    limits, _, _ = shared
    enable(limits, max_exposure=600)
    first_job, _ = start(execution)
    other, other_venue = second(execution)
    review = strategies.execution.preview(request(other))
    other_job = strategies.execution.start(review["id"], review["confirmation"])
    intents = []
    for job, account in ((first_job, connection), (other_job, other)):
        intent = trading.preview(
            ExchangeOrderRequest(
                connection_id=account.id,
                symbol="BTC/USDT",
                side="buy",
                quantity=4,
                order_type="limit",
                limit_price=100,
                idempotency_key="competing-" + job["id"],
            ),
            strategy_job_id=job["id"],
        )
        intent["strategy_risk_revision"] = state(limits)["revision"]
        with strategies.store.db() as db:
            trading.lifecycle.write(db, intent)
        intents.append((job, intent))
    barrier = threading.Barrier(2)

    def write_one(pair):
        job, intent = pair
        barrier.wait(timeout=5)
        try:
            return trading.execute(intent["id"], intent["confirmation"], strategy_job_id=job["id"])
        except ExecutionGuard as error:
            return str(error)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(write_one, intents))
    assert len(native.calls) + len(other_venue.calls) == 1
    assert sum(isinstance(result, dict) for result in outcomes) == 1
    assert not state(limits)["locked"]


def test_new_capital_is_not_a_gain_and_released_budget_does_not_erase_loss(execution, shared):
    strategies, trading, native, _ = execution
    limits, _, _ = shared
    enable(limits, max_daily_loss=100)
    job, intent = submit(execution)
    native.settle(intent["exchange_order_id"], fee=2)
    reconcile(trading, intent["id"])
    limits.check("test")
    assert state(limits)["sample"]["daily_loss"] == pytest.approx(2)
    other, _ = second(execution)
    review = strategies.execution.preview(request(other))
    new_job = strategies.execution.start(review["id"], review["confirmation"])
    limits.check("test")
    assert state(limits)["sample"]["daily_loss"] == pytest.approx(2)
    strategies.status(new_job["id"], "stopped")
    limits.check("test")
    assert state(limits)["sample"]["allocated"] == 1000
    assert state(limits)["sample"]["daily_loss"] == pytest.approx(2)


def test_policy_change_invalidates_old_reviews_and_unsent_orders(execution, shared):
    strategies, trading, _, connection = execution
    limits, _, _ = shared
    review = strategies.execution.preview(request(connection))
    enable(limits)
    with pytest.raises(ExecutionGuard, match="limits changed"):
        strategies.execution.start(review["id"], review["confirmation"])
    job, _ = start(execution)
    intent = trading.preview(
        ExchangeOrderRequest(
            connection_id=connection.id,
            symbol="BTC/USDT",
            side="buy",
            quantity=1,
            order_type="limit",
            limit_price=100,
            idempotency_key="changed-limits",
        ),
        strategy_job_id=job["id"],
    )
    enable(limits, max_exposure=300)
    assert strategies.journal.job(job["id"])["status"] == "paused"
    with strategies.store.db() as db:
        assert trading.lifecycle.read(db, intent["id"])["strategy_abandoned"]


def test_loss_trip_leaves_manual_orders_and_separately_reviewed_closes_available(execution, shared):
    from sibyl.strategies.execution.contracts import ClosePositionRequest

    strategies, trading, native, connection = execution
    limits, _, values = shared
    enable(limits)
    job, intent = submit(execution)
    native.settle(intent["exchange_order_id"], fee=0)
    reconcile(trading, intent["id"])
    strategies.status(job["id"], "stopped")
    values["BTC"] = 80
    limits.check("test")
    assert state(limits)["locked"]
    exit_review = strategies.execution.closing.preview(job["id"], ClosePositionRequest())
    strategies.execution.closing.confirm(exit_review["id"], exit_review["confirmation"])
    manual = trading.preview(
        ExchangeOrderRequest(
            connection_id=connection.id,
            symbol="BTC/USDT",
            side="buy",
            quantity=1,
            order_type="limit",
            limit_price=100,
            idempotency_key="manual-during-shared-lock",
        )
    )
    trading.execute(manual["id"], manual["confirmation"])
    assert len(native.calls) == 3 and native.calls[1][0] == "sell"
    assert state(limits)["locked"]


def test_reference_conversion_is_actual_including_foreign_quote_and_pending_buys():
    from sibyl.strategies.execution.risk.ledger import totals

    rows = [
        dict(
            id="one",
            account="A",
            connection_id="a",
            symbol="BTC/USD",
            status="running",
            capital=1000,
            cash=800,
            quantity=2,
            retained=True,
            pending_buys=[dict(quantity=1, price=110)],
        ),
        dict(
            id="two",
            account="B",
            connection_id="b",
            symbol="ETH/USDT",
            status="stopped",
            capital=1000,
            cash=1050,
            quantity=0,
            retained=False,
            pending_buys=[],
        ),
    ]
    result = totals(rows, {"BTC": {"price": 100}, "USD": {"price": 0.9}, "USDT": {"price": 1}})
    assert result["allocated"] == 900
    assert result["position"] == 200
    assert result["pending_buys"] == 100  # Reference value exceeds 110 * 0.9 limit notional.
    assert [row["pnl"] for row in result["runs"]] == [20, 50]


def test_native_valuation_requires_dated_prices_and_preserves_observed_conversion(client, monkeypatch):
    from test_portfolio_valuation import feed

    market, _ = feed(client, monkeypatch, {"BTC/USDT": 100, "USD/USDT": 0.9})
    rows = [dict(symbol="BTC/USD", retained=True)]
    rates, _ = prices.read(market, "binance", rows)
    assert rates["USD"]["price"] == 0.9 and rates["BTC"]["price"] == 100
    market._cache.clear()
    market, _ = feed(client, monkeypatch, {"BTC/USDT": {"last": 100}, "USD/USDT": 0.9})
    with pytest.raises(ExecutionGuard, match="fresh dated"):
        prices.read(market, "binance", rows)


def test_public_evidence_omits_feed_fingerprints_and_credentials(execution, shared):
    limits, _, _ = shared
    enable(limits)
    start(execution)
    raw = limits.check("test")
    assert "configuration" in raw["sample"]
    public = limits.state()
    assert "configuration" not in state(limits)["sample"]
    assert raw["sample"]["configuration"] not in str(public)
    assert "FAKE" not in str(public)


def test_exposure_cap_does_not_block_a_reducing_automatic_sell(execution, shared):
    strategies, trading, native, connection = execution
    limits, _, values = shared
    enable(limits)
    job, intent = submit(execution)
    native.settle(intent["exchange_order_id"], fee=0)
    reconcile(trading, intent["id"])
    values["BTC"] = 200
    limits.check("test")
    assert state(limits)["sample"]["exposure"] > 600
    assert not state(limits)["locked"]
    sell = trading.preview(
        ExchangeOrderRequest(
            connection_id=connection.id,
            symbol="BTC/USDT",
            side="sell",
            quantity=1,
            order_type="limit",
            limit_price=100,
            idempotency_key="reducing-sell",
        ),
        strategy_job_id=job["id"],
    )
    sell["strategy_risk_revision"] = state(limits)["revision"]
    with strategies.store.db() as db:
        trading.lifecycle.write(db, sell)
    trading.execute(sell["id"], sell["confirmation"], strategy_job_id=job["id"])
    assert len(native.calls) == 2 and native.calls[-1][0] == "sell"
    limits.check("test")
    assert state(limits)["sample"]["exposure"] > 600  # A pending sell has not reduced owned units.


@pytest.mark.parametrize("currency", ["BNB", None])
def test_unvalued_or_missing_fees_fail_closed(execution, shared, currency):
    strategies, trading, native, _ = execution
    limits, _, _ = shared
    enable(limits)
    job, intent = submit(execution)
    native.settle(intent["exchange_order_id"], currency=currency)
    reconcile(trading, intent["id"])
    with pytest.raises(ExecutionGuard, match="missing costs or unvalued fees"):
        limits.check("test")
    assert strategies.journal.job(job["id"])["status"] == "paused"
    assert not state(limits)["locked"]


def test_feed_edit_invalidates_public_freshness_and_native_admission(execution, shared):
    strategies, trading, native, connection = execution
    limits, _, _ = shared
    enable(limits)
    job, _ = start(execution)
    intent = trading.preview(
        ExchangeOrderRequest(
            connection_id=connection.id,
            symbol="BTC/USDT",
            side="buy",
            quantity=1,
            order_type="limit",
            limit_price=100,
            idempotency_key="changed-reference-feed",
        ),
        strategy_job_id=job["id"],
    )
    intent["strategy_risk_revision"] = state(limits)["revision"]
    with strategies.store.db() as db:
        trading.lifecycle.write(db, intent)
    strategies.store.save_data_profile("market", {"source": "binance", "profiles": {}})
    assert not state(limits)["fresh"]
    with pytest.raises(ExecutionGuard, match="feed settings changed"):
        trading.execute(intent["id"], intent["confirmation"], strategy_job_id=job["id"])
    assert not native.calls


def test_older_completed_assessment_cannot_replace_newer_prices(execution, shared, monkeypatch):
    limits, clock, _ = shared
    enable(limits)
    entered, proceed = threading.Event(), threading.Event()
    original = prices.read

    def read(*args):
        if threading.current_thread().name.startswith("OlderAssessment"):
            entered.set()
            assert proceed.wait(5)
        return original(*args)

    monkeypatch.setattr(prices, "read", read)
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="OlderAssessment") as pool:
        older = pool.submit(limits.check, "test")
        assert entered.wait(5)
        clock[0] += timedelta(seconds=1)
        limits.check("test")
        latest = state(limits)["sample"]["as_of"]
        proceed.set()
        with pytest.raises(ControlConflict, match="newer shared assessment"):
            older.result(5)
    assert state(limits)["sample"]["as_of"] == latest
