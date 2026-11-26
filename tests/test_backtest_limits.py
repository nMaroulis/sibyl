"""Order caps, loss pause and preserved open amounts in bounded backtests."""

from datetime import UTC, datetime, timedelta

import pytest

from sibyl.models import BacktestRequest
from sibyl.strategies.backtest import BacktestEngine


def scenario(prices, actions, **options):
    start = datetime(2024, 1, 1, tzinfo=UTC)
    bars = []
    for index in range(70):
        opening, close = prices.get(index, (100, 100))
        bars.append(
            {
                "timestamp": (start + timedelta(days=index)).isoformat(),
                "open": opening,
                "high": max(opening, close),
                "low": min(opening, close),
                "close": close,
                "volume": 10,
            }
        )
    signals = [0] * len(bars)
    for i, direction in actions.items():
        signals[i - 1] = direction  # the previous close signals this bar's open
    params = BacktestRequest(
        capital=1000,
        candles=len(bars),
        slippage_bps=0,
        backtest_limits={"max_order_quote": 500, "max_loss_pct": 10},
        **options,
    )
    return bars, BacktestEngine().run(bars, params, signal_override=signals)


def test_order_cap_applies_to_each_side_and_partial_sales_form_one_round_trip():
    _, result = scenario({31: (250, 250), 32: (150, 150)}, {30: 1, 31: -1, 32: -1}, fee_bps=100)
    fills = result["fills"]
    assert [f["side"] for f in fills] == ["buy", "sell", "sell"]
    assert [f["quantity"] * f["price"] for f in fills] == pytest.approx([500, 500, 450])
    assert result["fees"] == pytest.approx(14.5)
    assert result["final_equity"] == pytest.approx(1435.5)
    assert result["trades"] == 1
    (trade,) = result["round_trips"]
    assert trade["exit_price"] == pytest.approx(190)
    assert trade["pnl"] == pytest.approx(435.5)
    assert trade["exit_fee"] == pytest.approx(9.5)
    evidence = result["execution_limits"]
    assert evidence["capped_orders"] == 2 and evidence["partial_exits"] == 1
    assert evidence["open_position"] is None
    assert result["summary"]["exposure_pct"] == pytest.approx(5)


def test_unclosed_residual_reports_proportional_basis_and_continues_marking():
    _, result = scenario({31: (250, 250), 69: (200, 200)}, {30: 1, 31: -1}, fee_bps=100)
    assert [fill["side"] for fill in result["fills"]] == ["buy", "sell"]
    assert not result["round_trips"]
    evidence = result["execution_limits"]
    assert evidence["loss_pause"] is None
    assert evidence["ending_cash"] == pytest.approx(990)
    assert evidence["realized_pnl"] == pytest.approx(293)
    assert evidence["open_position"] == pytest.approx(
        {
            "quantity": 3,
            "price": 200,
            "market_value": 600,
            "cost_basis": 303,
            "unrealized_pnl": 297,
        }
    )
    assert result["final_equity"] == pytest.approx(1590)


def test_allocated_loss_pause_is_latched_at_the_close_and_keeps_open_units():
    bars, result = scenario(
        {31: (100, 80), 32: (50, 65), 33: (100, 150), 69: (100, 110)},
        {30: 1, 32: -1, 35: -1},
        fee_bps=0,
        stop_loss_pct=5,
    )
    assert [fill["side"] for fill in result["fills"]] == ["buy"]
    evidence = result["execution_limits"]
    assert evidence["loss_pause"] == {"timestamp": bars[32]["timestamp"], "equity": 900, "threshold": 900}
    assert evidence["ending_cash"] == 500
    assert evidence["open_position"]["quantity"] == 5
    assert evidence["open_position"]["market_value"] == 550
    assert result["curve"][2]["value"] == 825
    assert result["final_equity"] == 1050
    assert result["summary"]["exposure_pct"] == 100


def test_browser_backtest_contract_persists_limits_and_reuses_them_offline(client, monkeypatch):
    limits = {"max_order_quote": 500, "max_loss_pct": 10}
    response = client.post(
        "/api/v1/strategies/backtest/demo",
        json={"symbol": "BTC/USDT", "capital": 1000, "backtest_limits": limits},
    )
    assert response.status_code == 200, response.text
    first = response.json()
    assert first["parameters"]["backtest_limits"] == limits
    assert first["engine_revision"] == "next-open-v3-limits"
    assert all(fill["price"] * fill["quantity"] <= 500 + 1e-9 for fill in first["fills"])
    services = client.app.state.services
    monkeypatch.setattr(services.market, "client", lambda *args: pytest.fail("Rerun read a feed"))
    replay = client.post(f"/api/v1/strategies/backtests/{first['id']}/rerun")
    assert replay.status_code == 200, replay.text
    repeat = replay.json()
    for key in ("dataset", "parameters", "fills", "curve", "execution_limits", "summary"):
        assert repeat[key] == first[key]


def test_backtest_rejects_an_order_cap_above_the_allocated_amount(client):
    response = client.post(
        "/api/v1/strategies/backtest/demo",
        json={"capital": 100, "backtest_limits": {"max_order_quote": 500, "max_loss_pct": 10}},
    )
    assert response.status_code == 422, response.text
    assert "Maximum order value cannot exceed the allocated amount" in response.text
