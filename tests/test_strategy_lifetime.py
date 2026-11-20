"""Local run performance and archival remain independent of native execution."""

import time
from uuid import uuid4

import pytest
from test_strategy_execution import execution as execution
from test_strategy_execution import reconcile, start, submit
from test_strategy_ownership import adoption, approve, held, paused
from test_strategy_ownership import ownership as ownership

from sibyl.market_data.archive import iso
from sibyl.models import ExchangeOrderRequest
from sibyl.strategies import Strategies
from sibyl.strategies.execution.ownership.contracts import OwnershipReview
from sibyl.strategies.execution.ownership.service import unattributed_fill


def test_adoption_lifetime_reads_fresh_exact_mark_without_trading(execution, ownership):
    strategies, _, native, _ = execution
    job = paused(execution)
    performance = strategies.execution.performance
    approve(ownership, adoption(ownership, job))
    assert performance.report(job["id"])["metrics"] is None
    assert native.calls == []

    native.clock = time.time() + 1
    native.bid, native.ask = 109.95, 110.05
    previous = strategies.journal.job(job["id"])
    report = performance.refresh(job["id"])
    assert report["mark"]["kind"] == "reviewed_midpoint"
    metrics = report["metrics"]
    assert metrics["closing"] == 1110
    assert metrics["gain"] == pytest.approx(110 - 99.95)
    assert metrics["net_external_flow"] == pytest.approx(99.95)
    assert metrics["return_pct"] == pytest.approx(metrics["gain"] / metrics["weighted_capital"] * 100)
    assert strategies.journal.job(job["id"]) == previous and native.calls == []


def test_open_orders_withhold_returns_and_block_archive(execution):
    strategies, _, _, _ = execution
    job, _ = submit(execution)
    strategies.status(job["id"], "stopped")
    performance = strategies.execution.performance
    report = performance.report(job["id"])
    assert report["metrics"] is None and "uncertain orders" in report["reason"]
    with pytest.raises(ValueError, match="settled evidence"):
        performance.archive(job["id"], True)


def test_archiving_keeps_run_and_journal_through_restart_and_is_idempotent(execution):
    strategies, trading, native, _ = execution
    job, _ = start(execution)
    performance = strategies.execution.performance
    with pytest.raises(ValueError, match="stopped or completed"):
        performance.archive(job["id"], True)
    strategies.status(job["id"], "stopped")
    snapshot = performance.archive(job["id"], True)
    assert performance.archive(job["id"], True) == snapshot
    restarted = Strategies(strategies.market, strategies.store)
    restarted.attach_execution(trading)
    assert restarted.journal.job(job["id"])["archived_at"] == snapshot["archived_at"]
    assert restarted.execution.performance.report(job["id"])["mark"]["kind"] == "flat_cash"
    assert job["id"] in [item["id"] for item in restarted.execution.jobs()]
    restarted.execution.performance.archive(job["id"], False)
    assert not restarted.journal.job(job["id"]).get("archived_at") and not native.calls
    entries = restarted.journal.events(job["id"])["items"]
    assert [row["action"] for row in entries].count("ARCHIVE") == 1
    assert [row["action"] for row in entries].count("RESTORE") == 1


def test_third_currency_fee_withholds_complete_strategy_return(execution):
    strategies, trading, native, _ = execution
    job, order = submit(execution)
    native.settle(order["exchange_order_id"], currency="BNB", fee=0.01)
    reconcile(trading, order["id"])
    report = strategies.execution.performance.report(job["id"])
    assert report["metrics"] is None
    assert "fee values" in report["reason"]


def test_third_currency_fee_requires_a_closed_same_source_rate(execution):
    strategies, trading, native, _ = execution
    job, order = submit(execution)
    native.settle(order["exchange_order_id"], currency="BNB", fee=0.01)
    reconcile(trading, order["id"])
    performance = strategies.execution.performance
    filled_at = int(native.clock * 1000)
    metadata = {"source": job["source"], "environment": job["environment"], "source_label": "Fixture venue"}
    bar = dict(timestamp=iso(filled_at - 120_000), open=500, high=500, low=500, close=500, volume=1)
    archive = strategies.market.archive
    archive.capture({**metadata, "source": "binance"}, "BNB/USDT", "1m", [bar])
    archive.capture({**metadata, "environment": "production"}, "BNB/USDT", "1m", [bar])
    archive.capture(metadata, "BNB/USDT", "1m", [{**bar, "timestamp": iso(filled_at)}])
    assert performance.report(job["id"])["fee_valuation"]["missing_count"] == 1

    archive.capture(metadata, "BNB/USDT", "1m", [bar])
    native.clock = max(native.clock + 60, time.time() + 1)
    native.bid, native.ask = 109.95, 110.05
    report = performance.refresh(job["id"])
    valuation = report["fee_valuation"]
    assert valuation["source"] == job["source"] and valuation["environment"] == job["environment"]
    assert valuation["missing_count"] == 0 and valuation["quote_total"] == 5
    assert valuation["recent"][0]["legs"][0]["candle_close_ms"] == filled_at - 60_000
    assert valuation["recent"][0]["legs"][0]["symbol"] == "BNB/USDT"
    quantity = native.fills[0]["amount"]
    assert report["metrics"]["gain"] == pytest.approx(quantity * 10 - 5)
    assert len(native.calls) == 1


@pytest.mark.parametrize("origin,expected", [("sibyl", "sibyl_manual"), ("imported", "venue_discovered")])
def test_manual_provenance_uses_exact_local_intent_only(origin, expected):
    fill = {"id": "fill"}
    order = {"id": "intent", "origin": origin}
    assert unattributed_fill(fill, [order])["origin"] == expected
    assert unattributed_fill(fill, [])["origin"] == "unknown"
    assert unattributed_fill(fill, [order, order])["origin"] == "unknown"


def test_archived_run_still_reconciles_a_late_fee_correction(execution, ownership):
    strategies, trading, native, _ = execution
    job, order = held(execution)
    approve(
        ownership,
        ownership.preview(
            job["id"], OwnershipReview(action="release", quantity=job["quantity"], note="Release residual")
        ),
    )
    performance = strategies.execution.performance
    assert performance.report(job["id"])["metrics"] is not None
    archived = performance.archive(job["id"], True)
    native.fills[0]["fees"][0]["cost"] = 0.9
    reconcile(trading, order["id"])
    strategies.tick()
    result = strategies.journal.job(job["id"])
    assert result["archived_at"] == archived["archived_at"]
    assert result["accounting_incomplete"] and result["ownership_stale"]
    assert performance.report(job["id"])["metrics"] is None
    assert any(
        event["action"] == "FILL_CORRECTION" for event in strategies.journal.events(job["id"])["items"]
    )
    assert len(native.calls) == 1


def test_balance_inspection_matches_a_manually_submitted_native_fill(execution, ownership):
    _, trading, native, connection = execution
    job = paused(execution)
    preview = trading.preview(
        ExchangeOrderRequest(
            connection_id=connection.id,
            symbol="BTC/USDT",
            side="buy",
            quantity=1,
            order_type="limit",
            limit_price=99,
            idempotency_key=uuid4().hex,
        )
    )
    order = trading.execute(preview["id"], preview["confirmation"])
    native.settle(order["exchange_order_id"])
    reconcile(trading, order["id"])
    result = ownership.inspect(job["id"])
    (fill,) = result["check"]["unattributed_fills"]
    assert fill["intent_id"] == order["id"] and fill["origin"] == "sibyl_manual"
    assert result["quantity"] == 0 and not result["history"]
    assert len(native.calls) == 1
