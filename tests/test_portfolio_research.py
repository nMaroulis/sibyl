"""Independent portfolio arithmetic, causal schedules, immutable inputs and native Broker evidence."""

import json
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest
from pydantic import ValidationError
from test_candle_history import DAY, META, START, insert

from sibyl.market_data.archive import iso
from sibyl.strategies.portfolio.contracts import PortfolioStudy
from sibyl.strategies.portfolio.engine import simulate


def recipe(**kwargs):
    return PortfolioStudy(
        **(
            dict(
                legs=[{"symbol": "BTC/USDT", "weight_pct": 60}, {"symbol": "ETH/USDT", "weight_pct": 30}],
                fee_bps=0,
                slippage_bps=0,
            )
            | kwargs
        )
    )


def prices(a=None, b=None):
    a = a or [(100, 100)] * 3
    b = b or [(100, 100)] * len(a)
    times = [iso(START + i * DAY) for i in range(len(a))]
    return {
        symbol: [
            dict(timestamp=t, open=o, close=c, high=max(o, c), low=min(o, c), volume=10)
            for t, (o, c) in zip(times, values, strict=True)
        ]
        for symbol, values in [("BTC/USDT", a), ("ETH/USDT", b)]
    }, times


def saved(owner, symbol, *, count=90, start=START, metadata=None, frame="1d", scale=1):
    data = [
        [start + i * DAY, (100 + i) * scale, (103 + i) * scale, (98 + i) * scale, (101 + i) * scale, 10]
        for i in range(count)
    ]
    insert(owner.archive, data, metadata or META, symbol, frame)
    return owner.archive.snapshot(metadata or META, symbol, frame, iso(start), iso(start + count * DAY))


def saved_body(owner, **kwargs):
    a = saved(owner, "BTC/USDT")
    b = saved(owner, "ETH/USDT", scale=2)
    return recipe(
        input_kind="saved_datasets",
        legs=[
            {"symbol": "BTC/USDT", "weight_pct": 60, "dataset_id": a["id"]},
            {"symbol": "ETH/USDT", "weight_pct": 30, "dataset_id": b["id"]},
        ],
        **kwargs,
    )


def test_flat_prices_conserve_cash_with_exact_two_sided_fees_and_slippage():
    body = recipe(fee_bps=10, slippage_bps=5)
    data, times = prices()
    result = simulate(body, data, times)
    f, s = 0.001, 0.0005
    # 90% post-cost exposure; the 10% reserve and both entry/exit costs are solved explicitly.
    marked = 10000 / (1 + 0.9 * (s + f + s * f))
    final = marked * (0.1 + 0.9 * (1 - s) * (1 - f))
    assert result["curve"][0]["value"] == pytest.approx(marked, abs=1e-8)
    assert result["final_equity"] == pytest.approx(final, abs=1e-8)
    assert 10000 - result["final_equity"] == pytest.approx(result["fees"] + result["slippage_cost"], abs=1e-8)
    assert result["pre_liquidation"]["cash"] == pytest.approx(marked * 0.1)
    assert result["allocations"][0]["weights"]["BTC/USDT"] == pytest.approx(60)
    assert result["allocations"][0]["cash_pct"] == pytest.approx(10)
    assert result["final_equity"] == result["benchmarks"]["buy_hold"]["final_equity"]
    assert all(row["value"] == 10000 for row in result["benchmarks"]["cash"]["curve"])


def test_fully_invested_targets_pay_fees_without_negative_cash_or_symbol_priority():
    body = recipe(
        legs=[{"symbol": "BTC/USDT", "weight_pct": 50}, {"symbol": "ETH/USDT", "weight_pct": 50}],
        fee_bps=100,
        slippage_bps=100,
        interval_bars=1,
    )
    data, times = prices([(100, 180), (180, 80), (80, 130)], [(100, 90), (90, 140), (140, 75)])
    result = simulate(body, data, times)
    reverse = simulate(body.model_copy(update={"legs": list(reversed(body.legs))}), data, times)
    assert result["final_equity"] == pytest.approx(reverse["final_equity"], abs=1e-7)
    assert all(0 <= row["cash_pct"] < 1e-8 for row in result["allocations"])
    assert all(
        math.fsum(row["weights"].values()) + row["cash_pct"] == pytest.approx(100)
        for row in result["allocations"]
    )
    assert result["rebalance_count"] == 2
    assert result["rebalance_turnover_pct"] > 0
    for event in result["rebalance_events"]:
        assert event["equity_before"] - event["equity_after"] == pytest.approx(event["cost"], abs=1e-7)
    for timestamp in times:
        legs = [
            row["side"]
            for row in result["fills"]
            if row["timestamp"] == timestamp and row["reason"] == "rebalance"
        ]
        assert legs == sorted(legs, key=lambda side: side == "buy")


def test_drift_uses_previous_close_and_actual_next_open_not_future_close():
    body = recipe(
        rule="drift",
        drift_pct=10,
        legs=[{"symbol": "BTC/USDT", "weight_pct": 50}, {"symbol": "ETH/USDT", "weight_pct": 50}],
    )
    data, times = prices([(100, 200), (250, 250), (250, 400)], [(100, 100)] * 3)
    result = simulate(body, data, times)
    event = result["rebalance_events"][1]
    assert event["bar"] == 1 and event["drift_pct"] == pytest.approx(100 / 6)
    fills = [f for f in result["fills"] if f["reason"] == "rebalance"]
    assert fills and all(f["bar"] == 1 for f in fills)
    assert next(f for f in fills if f["symbol"] == "BTC/USDT")["reference_price"] == 250
    assert all(f["decision_at"] == times[1] and f["phase"] == "open" for f in fills)
    changed = deepcopy(data)
    changed["BTC/USDT"][-1]["close"] = 1000
    changed["BTC/USDT"][-1]["high"] = 1000
    repeated = simulate(body, changed, times)
    assert [f for f in repeated["fills"] if f["reason"] != "liquidation"] == [
        f for f in result["fills"] if f["reason"] != "liquidation"
    ]
    assert result["fills"][-1]["execution_at"] == iso(START + 3 * DAY)
    assert result["fills"][-1]["phase"] == "close"


def test_interval_and_noop_rebalances_are_distinct_from_executed_trades():
    body = recipe(interval_bars=2)
    data, times = prices([(100, 100)] * 6, [(100, 100)] * 6)
    result = simulate(body, data, times)
    assert [r["bar"] for r in result["rebalance_events"] if r["reason"] == "rebalance"] == [2, 4]
    assert result["rebalance_count"] == 0 and result["rebalance_turnover_pct"] == 0
    assert result["sharpe"] is None and result["sortino"] is None
    assert result["return_pct"] == pytest.approx(0)


def test_aggregate_metrics_include_initial_and_final_costs_and_actual_periods():
    data, times = prices([(100, 110), (110, 80), (80, 90)], [(100, 100)] * 3)
    result = simulate(recipe(fee_bps=10), data, times)
    values = [10000] + [row["value"] for row in result["curve"]]
    expected = []
    peak = values[0]
    for value in values[1:]:
        peak = max(peak, value)
        expected.append((value / peak - 1) * 100)
    assert [row["drawdown_pct"] for row in result["curve"]] == pytest.approx(expected)
    assert result["max_drawdown"] == pytest.approx(-min(expected))
    assert result["return_observations"] == len(times)
    assert result["final_cash"] == result["final_equity"]


def test_exact_demo_capture_does_not_activate_accounts_change_feeds_or_read_balances(
    manual_client, monkeypatch
):
    s = manual_client.app.state.services
    s.store.save_data_profile("market", {"source": "exchange:binance", "profiles": {}})
    original = s.store.data_profile("market")
    active = [c.id for c in s.store.connections() if c.active]
    monkeypatch.setattr(s.portfolio, "overview", lambda *args: pytest.fail("Research read account balances"))
    response = manual_client.post(
        "/api/v1/strategies/portfolios", json=recipe(input_kind="demo").model_dump()
    )
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    item = response.json()
    assert item["source"] == item["environment"] == "demo" and item["simulation"]
    assert item["window"]["count"] == 180 and len(item["datasets"]) == 2
    assert item["target_cash_pct"] == 10 and item["parameters"]["input_kind"] == "saved_datasets"
    assert s.store.data_profile("market") == original
    assert [c.id for c in s.store.connections() if c.active] == active
    assert manual_client.get("/api/v1/strategies/portfolios/inputs").status_code == 200
    assert len(manual_client.get("/api/v1/strategies/portfolios?demo=true").json()["items"]) == 1
    assert not manual_client.get("/api/v1/strategies/portfolios?demo=false").json()["items"]
    monkeypatch.setattr(s.market, "client", lambda *args: pytest.fail("Offline replay contacted a provider"))
    replay = manual_client.post(f"/api/v1/strategies/portfolios/{item['id']}/rerun")
    assert replay.status_code == 201, replay.text
    repeated = replay.json()
    assert repeated["id"] != item["id"] and repeated["rerun_of"] == item["id"]
    for key in ("curve", "fills", "allocations", "benchmarks", "decision_fingerprint", "window"):
        assert item[key] == repeated[key]
    for module in ("broker",):
        from test_agent_guidance import tool_call

        context = tool_call(manual_client, module, "strategy_context")
        assert any(row["id"] == item["id"] for row in context["portfolio_studies"])
        result = tool_call(manual_client, module, "backtest_report", run_id=item["id"])
        assert result["kind"] == "portfolio_backtest" and result["fees"] == item["fees"]
        assert len(result["recent_fills"]) <= 10 and "allocations" not in result
        assert "allocations" not in result["benchmarks"]["buy_hold"]
    chat = manual_client.post(
        "/api/v1/agents/ask",
        json={
            "module": "broker",
            "message": "Explain this portfolio study",
            "context": {"backtest_id": item["id"]},
        },
    )
    assert chat.status_code == 200, chat.text
    assert "2 assets" in chat.json()["answer"] and "no running strategy" in chat.json()["answer"].lower()


def test_current_feed_inputs_pin_source_and_never_mix_with_demo(manual_client):
    s = manual_client.app.state.services
    item = s.strategies.portfolios.run(recipe())
    assert item["source"] == "demo"  # The isolated fixture deliberately selected Demo as its current feed.
    assert item["captured_from"] == "current_feed"
    assert all(d["source"] == item["source"] for d in item["datasets"])


def test_saved_inputs_trim_to_common_consecutive_window_and_retain_full_receipts(manual_client, monkeypatch):
    owner = manual_client.app.state.services.strategies.portfolios
    a = saved(owner, "BTC/USDT", count=100)
    b = saved(owner, "ETH/USDT", count=80, start=START + 10 * DAY)
    body = recipe(
        input_kind="saved_datasets",
        legs=[
            {"symbol": "BTC/USDT", "weight_pct": 60, "dataset_id": a["id"]},
            {"symbol": "ETH/USDT", "weight_pct": 30, "dataset_id": b["id"]},
        ],
    )
    monkeypatch.setattr(owner.market, "client", lambda *_: pytest.fail("Saved inputs fetched a provider"))
    result = owner.run(body)
    assert result["window"]["count"] == 80 and result["window"]["trimmed"]
    assert result["window"]["start"] == iso(START + 10 * DAY) and result["window"]["end"] == iso(
        START + 90 * DAY
    )
    assert result["datasets"][0]["count"] == 100
    assert len(result["curve"]) == 80


@pytest.mark.parametrize(
    "mutation", ["source", "environment", "symbol", "frame", "short_overlap", "tamper", "oversized"]
)
def test_incompatible_or_corrupt_datasets_never_save_a_success(manual_client, mutation):
    owner = manual_client.app.state.services.strategies.portfolios
    a = saved(owner, "BTC/USDT")
    meta = META.copy()
    if mutation == "source":
        meta["source"] = "another-feed"
    if mutation == "environment":
        meta["environment"] = "test"
    symbol = "SOL/USDT" if mutation == "symbol" else "ETH/USDT"
    # Weekly mismatches are represented by metadata on the immutable dataset,
    # without introducing a fake weekly price feed.
    count = 2001 if mutation == "oversized" else 90
    start = (
        START + 80 * DAY
        if mutation == "short_overlap"
        else START - 3000 * DAY
        if mutation == "oversized"
        else START
    )
    b = saved(owner, symbol, count=count, start=start, metadata=meta)
    if mutation in {"tamper", "frame"}:
        with owner.store.db() as db:
            row = db.execute("SELECT candles,metadata FROM candle_datasets WHERE id=?", (b["id"],)).fetchone()
            if mutation == "tamper":
                rows = json.loads(row["candles"])
                rows[0]["close"] = 999
                db.execute("UPDATE candle_datasets SET candles=? WHERE id=?", (json.dumps(rows), b["id"]))
            else:
                values = json.loads(row["metadata"])
                values["timeframe"] = "1w"
                db.execute("UPDATE candle_datasets SET metadata=? WHERE id=?", (json.dumps(values), b["id"]))
    body = recipe(
        input_kind="saved_datasets",
        legs=[
            {"symbol": "BTC/USDT", "weight_pct": 60, "dataset_id": a["id"]},
            {"symbol": "ETH/USDT", "weight_pct": 30, "dataset_id": b["id"]},
        ],
    )
    with pytest.raises(ValueError):
        owner.run(body)
    assert not owner.list()["items"]


def test_archived_gap_is_not_filled_or_silently_dropped(manual_client, monkeypatch):
    owner = manual_client.app.state.services.strategies.portfolios
    body = saved_body(owner)
    original = owner.archive.dataset

    def missing(identity):
        result = original(identity)
        if identity == body.legs[1].dataset_id:
            result["candles"].pop(30)
        return result

    monkeypatch.setattr(owner.archive, "dataset", missing)
    with pytest.raises(ValueError, match="consecutive"):
        owner.run(body)
    assert not owner.list()["items"]


def test_native_pair_aliases_are_rejected_before_capture(manual_client, monkeypatch):
    owner = manual_client.app.state.services.strategies.portfolios
    monkeypatch.setattr(owner.market, "provider_symbol", lambda symbol: symbol.replace("USDT", "USD"))
    with pytest.raises(ValueError, match="aliases"):
        owner.run(recipe(input_kind="demo"))
    assert not owner.list()["items"]


def test_replay_engine_or_decision_changes_fail_without_new_artifact(manual_client, monkeypatch):
    owner = manual_client.app.state.services.strategies.portfolios
    item = owner.run(saved_body(owner))
    with owner.store.db() as db:
        old = deepcopy(item)
        old.pop("id")
        old.pop("created_at")
        old["engine_revision"] = "future-engine"
        db.execute("UPDATE runs SET payload=? WHERE id=?", (json.dumps(old), item["id"]))
    with pytest.raises(ValueError, match="engine changed"):
        owner.rerun(item["id"])
    with owner.store.db() as db:
        old["engine_revision"] = item["engine_revision"]
        old["decision_fingerprint"] = "different"
        db.execute("UPDATE runs SET payload=? WHERE id=?", (json.dumps(old), item["id"]))
    with pytest.raises(ValueError, match="reproduce"):
        owner.rerun(item["id"])
    assert len(owner.list()["items"]) == 1


def test_one_study_admission_and_failure_cleanup_are_explicit(manual_client, monkeypatch):
    owner = manual_client.app.state.services.strategies.portfolios
    body = saved_body(owner)
    entered, release = threading.Event(), threading.Event()
    original = owner._input

    def blocking(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    monkeypatch.setattr(owner, "_input", blocking)
    with ThreadPoolExecutor() as pool:
        pending = pool.submit(owner.run, body)
        assert entered.wait(5)
        with pytest.raises(ValueError, match="Another"):
            owner.run(body)
        release.set()
        pending.result(5)
    monkeypatch.setattr(
        owner, "_input", lambda *_: (_ for _ in ()).throw(ValueError("controlled failed input"))
    )
    with pytest.raises(ValueError):
        owner.run(body)
    assert len(owner.list()["items"]) == 1


def test_deletion_keeps_datasets_orders_accounts_and_live_strategy_jobs(manual_client):
    s = manual_client.app.state.services
    owner = s.strategies.portfolios
    item = owner.run(saved_body(owner))
    before = s.strategies.jobs()
    assert manual_client.delete(f"/api/v1/strategies/portfolios/{item['id']}").status_code == 204
    assert manual_client.get(f"/api/v1/strategies/portfolios/{item['id']}").status_code == 404
    assert all(owner.archive.dataset(d["id"])["candles"] for d in item["datasets"])
    assert s.strategies.jobs() == before


@pytest.mark.parametrize(
    "change",
    [
        {"capital": True},
        {"fee_bps": True},
        {"slippage_bps": -1},
        {"interval_bars": 0},
        {"drift_pct": 0},
        {"candles": 2001},
        {"legs": [{"symbol": "BTC/USDT", "weight_pct": 80}, {"symbol": "ETH/USDT", "weight_pct": 30}]},
        {"legs": [{"symbol": "BTC/USDT", "weight_pct": 50}, {"symbol": "ETH/USD", "weight_pct": 50}]},
        {"legs": [{"symbol": "BTC/USDT", "weight_pct": 50}, {"symbol": "BTC/USDT", "weight_pct": 50}]},
        {"legs": [{"symbol": "BTC/USDT", "weight_pct": True}, {"symbol": "ETH/USDT", "weight_pct": 50}]},
        {"title": "  "},
    ],
)
def test_request_contracts_reject_invalid_allocations_or_unsafe_numbers(change):
    with pytest.raises(ValidationError):
        recipe(**change)


def test_missing_inputs_and_private_routes_require_real_workspace_access(settings):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from sibyl.api.app import create_app

    settings.api_token = SecretStr("fixture-only-workspace-token")
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/strategies/portfolios").status_code == 401
        assert (
            client.post(
                "/api/v1/strategies/portfolios", json=recipe(input_kind="demo").model_dump()
            ).status_code
            == 401
        )
