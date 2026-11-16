"""Reviewed fee prices affect risk while native balances and orders remain unchanged."""

import math
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_strategy_execution import execution as execution
from test_strategy_execution import reconcile, submit

from sibyl.market_data.archive import iso
from sibyl.strategies import Strategies
from sibyl.strategies.execution import runner
from sibyl.strategies.execution.accounting import project
from sibyl.strategies.execution.risk.ledger import positions, totals
from sibyl.strategies.execution.venue import order_size


def priced_candle(strategies, job, native, price=500, **override):
    source = {"source": job["source"], "environment": job["environment"], "source_label": "Fixture"}
    row = {
        "timestamp": iso(int(native.fills[0]["timestamp"]) - 120_000),
        "open": price,
        "close": price,
        "low": price,
        "high": price,
        "volume": 100,
    }
    strategies.market.archive.capture({**source, **override}, "BNB/USDT", "1m", [row])


def paused_with_fee(execution, amount=0.01):
    strategies, trading, native, _ = execution
    job, order = submit(execution)
    native.settle(order["exchange_order_id"], currency="BNB", fee=amount)
    reconcile(trading, order["id"])
    strategies.tick()
    assert strategies.journal.job(job["id"])["status"] == "paused"
    return job, order


def test_review_affects_equity_and_shared_loss_without_moving_cash_or_resuming(execution):
    strategies, trading, native, _ = execution
    job, _ = paused_with_fee(execution)
    identity = job["id"]
    fee_reviews = strategies.execution.fee_reviews
    priced_candle(strategies, job, native, environment="production")
    priced_candle(strategies, job, native, source="binance")
    missing = fee_reviews.preview(identity)
    assert missing["pending_count"] == 1 and missing["review_id"] is None
    before = project(job, trading)
    with strategies.store.db() as db:
        with pytest.raises(ValueError, match="unvalued fees"):
            positions(db, trading, job["environment"])

    priced_candle(strategies, job, native)
    review = fee_reviews.preview(identity)
    assert review["batch_quote"] == 5
    assert review["rows"][0]["rows"][0]["legs"][0]["symbol"] == "BNB/USDT"
    fee_reviews.approve(identity, review["review_id"])
    strategies.tick()
    after = strategies.journal.job(identity)
    assert after["cash"] == before["cash"] and after["entry_cost"] == before["entry_cost"]
    assert after["foreign_fees_quote"] == after["foreign_fee_reserve"] == 5
    assert after["equity"] == pytest.approx(after["cash"] + after["quantity"] * 100 - 5)
    assert after["status"] == "paused" and not after["unvalued_fees"]
    with strategies.store.db() as db:
        rows = positions(db, trading, job["environment"])
    rates = {asset: {"price": value} for asset, value in [("BTC", 100), ("USDT", 1)]}
    assert totals(rows, rates)["runs"][0]["pnl"] == pytest.approx(-5)
    assert len(native.calls) == 1
    assert strategies.status(identity, "running")["status"] == "running" and len(native.calls) == 1


def test_price_revision_invalidates_preview_then_approval_pins_the_estimate(execution):
    strategies, trading, native, _ = execution
    job, _ = paused_with_fee(execution)
    identity = job["id"]
    fees = strategies.execution.fee_reviews
    priced_candle(strategies, job, native)
    before = fees.preview(identity)
    priced_candle(strategies, job, native, 600)
    with pytest.raises(ValueError, match="review changed"):
        fees.approve(identity, before["review_id"])
    review = fees.preview(identity)
    with ThreadPoolExecutor(2) as workers:
        results = list(workers.map(lambda _: fees.approve(identity, review["review_id"]), range(2)))
    assert all(response["saved"] for response in results)
    assert len(strategies.journal.events(identity, action="FEE_VALUATION")["items"]) == 1

    priced_candle(strategies, job, native, 900)
    restarted = Strategies(strategies.market, strategies.store)
    restarted.attach_execution(trading)
    assert project(job, trading)["foreign_fees_quote"] == 6
    assert restarted.execution.performance.report(identity)["fee_valuation"]["quote_total"] == 6
    receipt = restarted.execution.fee_reviews.receipt(identity, review["review_id"])
    assert receipt["rows"][0]["rows"][0]["quote_fee"] == 6
    assert len(native.calls) == 1


def test_new_native_fee_amount_requires_its_own_approval(execution):
    strategies, trading, native, _ = execution
    job, order = paused_with_fee(execution)
    priced_candle(strategies, job, native)
    fees = strategies.execution.fee_reviews
    review = fees.preview(job["id"])
    fees.approve(job["id"], review["review_id"])
    native.fills[0]["fees"][0]["cost"] = 0.02
    reconcile(trading, order["id"])
    snapshot = project(job, trading)
    assert snapshot["foreign_fees_quote"] == 0 and snapshot["unvalued_fees"] == {"BNB": 0.02}
    assert fees.receipt(job["id"], review["review_id"])["rows"][0]["rows"][0]["quote_fee"] == 5
    next_review = fees.preview(job["id"])
    assert next_review["review_id"] != review["review_id"] and next_review["batch_quote"] == 10
    with pytest.raises(ValueError, match="review other-asset fees"):
        strategies.status(job["id"], "running")
    assert len(native.calls) == 1


@pytest.mark.parametrize(("amount", "fee_quote", "reserve"), [(0.1, 50, 50), (-0.1, -50, 0)])
def test_positive_fees_reduce_entry_budget_and_rebates_never_increase_it(
    execution, amount, fee_quote, reserve
):
    strategies, trading, native, _ = execution
    job, _ = paused_with_fee(execution, amount)
    priced_candle(strategies, job, native)
    fees = strategies.execution.fee_reviews
    fees.approve(job["id"], fees.preview(job["id"])["review_id"])
    state = project(job, trading)
    assert state["foreign_fees_quote"] == fee_quote and state["foreign_fee_reserve"] == reserve
    risk = {**job["risk"], "max_order_quote": 10_000}
    values = {**job, **state, "quantity": 0, "risk": risk}
    quantity, price = order_size(native, values, {"ask": 100, "bid": 99}, "buy")
    assert math.isclose(
        quantity * price * (1 + risk["fee_reserve_bps"] / 10000), values["cash"] - reserve, abs_tol=0.02
    )


def test_corrected_foreign_fee_at_native_write_boundary_refuses_submission(execution, monkeypatch):
    strategies, trading, native, _ = execution
    job, order = paused_with_fee(execution)
    priced_candle(strategies, job, native)
    fees = strategies.execution.fee_reviews
    fees.approve(job["id"], fees.preview(job["id"])["review_id"])
    strategies.status(job["id"], "running")
    monkeypatch.setattr(runner, "signals", lambda frame, *args: frame["close"] * 0 - 1)
    execute = trading.execute

    def corrected(*args, **kwargs):
        native.fills[0]["fees"][0]["cost"] = 0.025
        reconcile(trading, order["id"])
        return execute(*args, **kwargs)

    monkeypatch.setattr(trading, "execute", corrected)
    native.clock += 60
    strategies.tick()
    saved = strategies.journal.job(job["id"])
    assert saved["status"] == "paused" and "accounting changed before submission" in saved["error"]
    assert len(native.calls) == 1


def test_http_fee_review_is_private_and_journal_receipt_is_addressable(manual_client, execution, monkeypatch):
    strategies, _, native, _ = execution
    job, _ = paused_with_fee(execution)
    priced_candle(strategies, job, native)
    monkeypatch.setattr(manual_client.app.state.services, "strategies", strategies)
    url = f"/api/v1/strategies/exchange/jobs/{job['id']}/fee-review"
    review = manual_client.get(url)
    assert review.status_code == 200 and review.headers["cache-control"] == "no-store"
    value = review.json()
    result = manual_client.post(url, json={"review_id": value["review_id"]})
    assert result.status_code == 200, result.text
    uri = f"/api/v1/strategies/jobs/{job['id']}/events?action=FEE_VALUATION"
    assert manual_client.get(uri).json()["items"][0]["fee_review_id"] == value["review_id"]
    receipt = manual_client.get(f"{url}/{value['review_id']}")
    assert receipt.status_code == 200 and receipt.headers["cache-control"] == "no-store"
    assert receipt.json()["rows"][0]["rows"][0]["quote_fee"] == 5
    assert "FAKE" not in review.text + receipt.text


def test_approved_fee_can_latch_the_per_run_loss_guard(execution):
    strategies, _, native, _ = execution
    job, _ = paused_with_fee(execution, 0.1)
    identity = job["id"]
    stopped = strategies.journal.job(identity)
    stopped["risk"]["max_loss_pct"] = 1
    strategies.journal.save(stopped)
    priced_candle(strategies, job, native)
    fees = strategies.execution.fee_reviews
    fees.approve(identity, fees.preview(identity)["review_id"])
    with pytest.raises(ValueError, match="Allocated loss guard reached"):
        strategies.status(identity, "running")
    saved = strategies.journal.job(identity)
    assert saved["risk_locked"] and saved["status"] == "paused"
    assert len(native.calls) == 1


def test_offsetting_native_amounts_still_need_fee_prices(execution):
    strategies, trading, native, _ = execution
    job, order = submit(execution)
    native_id = order["exchange_order_id"]
    quantity = order["request"]["quantity"]
    native.settle(native_id, quantity / 2, currency="BNB", fee=0.01, terminal=False)
    native.clock += 60
    native.settle(native_id, quantity / 2, currency="BNB", fee=-0.01)
    native.orders[native_id].update(filled=quantity, remaining=0, cost=quantity * 100)
    reconcile(trading, order["id"])
    strategies.tick()
    snapshot = strategies.journal.job(job["id"])
    assert snapshot["status"] == "paused" and snapshot["unvalued_fees"] == {"BNB": 0.0}
    assert strategies.execution.fee_reviews.preview(job["id"])["pending_count"] == 2
    assert len(native.calls) == 1
