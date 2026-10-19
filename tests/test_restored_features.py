"""Behavioral coverage for restored analysis, reports, research, and account views."""

import json
from types import SimpleNamespace

import pandas as pd
import pytest
from pydantic import ValidationError

from sibyl.models import BacktestRequest, ConnectionCreate
from sibyl.services.analytics import correlation, performance_metrics
from sibyl.services.market import Market
from sibyl.services.portfolio import Portfolio
from sibyl.services.reporting import trading_report
from sibyl.services.research import Research
from sibyl.services.strategies import backtest


@pytest.mark.parametrize("timeframe,seconds", [("1m", 60), ("4h", 14400), ("1w", 604800)])
def test_demo_intervals_and_cross_quotes_are_consistent(settings, store, timeframe, seconds):
    market = Market(settings, store)
    candles = market.candles("ETH/BTC", 90, timeframe)
    assert candles[-60:] == market.candles("ETH/BTC", 60, timeframe)
    assert (
        pd.Timestamp(candles[-1]["timestamp"]) - pd.Timestamp(candles[-2]["timestamp"])
    ).total_seconds() == seconds
    assert candles[-1]["close"] == pytest.approx(market.price("ETH/USDT") / market.price("BTC/USDT"))
    assert all(
        c["low"] <= min(c["open"], c["close"]) <= max(c["open"], c["close"]) <= c["high"] for c in candles
    )


def test_live_intraday_candles_drop_unfinished_interval(settings, store, monkeypatch):
    settings.mode = "live"
    market = Market(settings, store)
    now = pd.Timestamp.now(tz="UTC").floor("h")
    requested = []

    class Provider:
        def load_markets(self):
            return {"BTC/USDT": {}}

        def fetch_ohlcv(self, symbol, timeframe, limit):
            requested.append((symbol, timeframe))
            return [
                [int((now - pd.Timedelta(hours=i)).timestamp() * 1000), 100, 102, 99, 101, 50]
                for i in reversed(range(61))
            ]

    monkeypatch.setattr(market, "client", lambda: Provider())
    result = market.candles("BTC/USDT", 60, "1h")
    assert len(result) == 60
    assert pd.Timestamp(result[-1]["timestamp"]) == now - pd.Timedelta(hours=1)
    assert requested == [("BTC/USDT", "1h")]


def test_rank_correlation_and_transform_have_observable_effect():
    first = [{"timestamp": str(i), "close": value} for i, value in enumerate([1, 2, 3, 4, 5])]
    second = [{**c, "close": c["close"] ** 3} for c in first]
    rank = correlation({"A": first, "B": second}, "spearman", "prices")
    linear = correlation({"A": first, "B": second}, "pearson", "prices")
    assert rank["matrix"][0][1] == pytest.approx(1)
    assert linear["matrix"][0][1] < 0.96
    assert correlation({"A": first, "B": second}, transform="changes")["observations"] == 4


@pytest.mark.parametrize(
    "changes",
    [
        {"fast_period": 30, "slow_period": 20},
        {"candles": 60, "window": 70},
        {"rsi_lower": 60},
        {"stop_loss_pct": 0},
        {"timeframe": "2h"},
    ],
)
def test_strategy_rejects_invalid_parameters(changes):
    with pytest.raises(ValidationError):
        BacktestRequest(**changes)


def test_close_based_risk_exit_waits_for_next_open_and_honors_trade_limit(settings, store):
    market = Market(settings, store)
    history = market.candles(limit=100)
    for i, row in enumerate(history):
        price = 100 + i if i < 31 else 90
        row.update(open=float(price), close=float(price), high=price + 1, low=price - 1)
    history[32]["open"] = 80
    request = BacktestRequest(strategy="ema", fee_bps=0, slippage_bps=0, stop_loss_pct=5, max_trades=1)
    result = backtest(history, request)
    assert result["fills"][0]["timestamp"] == history[30]["timestamp"]
    assert result["fills"][1]["timestamp"] == history[32]["timestamp"]
    assert result["fills"][1]["price"] == 80
    assert result["fills"][1]["reason"] == "Stop loss at observed close"
    assert result["trades"] == 1
    assert len(result["metrics"]["drawdown_curve"]) == len(result["curve"]) + 1


def test_metric_ratios_remain_json_safe_when_undefined():
    result = performance_metrics([100, 100, 100], [], 365)
    assert result["sortino"] is result["calmar"] is result["profit_factor"] is None
    assert result["sharpe"] == 0
    json.dumps(result, allow_nan=False)
    result = performance_metrics([100, 110, 99, 120], [10, -5, 2], 12)
    assert result["profit_factor"] == pytest.approx(2.4)
    assert result["max_drawdown"] == pytest.approx(10)


def test_fifo_report_excludes_seed_sales_and_allocates_fees():
    def order(side, qty, price, fee, time):
        return {
            "id": time,
            "symbol": "BTC/USDT",
            "side": side,
            "quantity": qty,
            "price": price,
            "notional": qty * price,
            "fee": fee,
            "created_at": time,
            "status": "filled",
        }

    # Chronological: unknown-basis seed sale, two buys, then a partial matched sale.
    orders = [
        order("sell", 1, 90, 1, "1"),
        order("buy", 1, 100, 1, "2"),
        order("buy", 1, 120, 1, "3"),
        order("sell", 1.5, 150, 1.5, "4"),
    ]
    report = trading_report(
        SimpleNamespace(orders=lambda: list(reversed(orders))), SimpleNamespace(list_orders=lambda: [])
    )
    assert report["realized_paper_pnl"]["USDT"] == pytest.approx(48 + 14)
    assert report["unmatched_sold_quantity"] == 1
    assert report["paper_pnl_curve"][-1]["value"] == pytest.approx(62)


def test_account_balances_are_separate_normalized_and_secret_free(settings, store, monkeypatch):
    settings.mode = "live"
    connection = store.add_connection(
        ConnectionCreate(
            exchange="binance",
            label="Private account",
            api_key="do-not-expose-key",
            secret="do-not-expose-secret",
        )
    )
    market = Market(settings, store)
    monkeypatch.setattr(market, "overview", lambda: {"items": [{"asset": "BTC", "price": 100}]})
    monkeypatch.setattr(
        market,
        "account_balances",
        lambda c: [
            {"asset": "BTC", "total": 2, "free": 1.5, "used": 0.5},
            {"asset": "UNKNOWN", "total": 3, "free": None, "used": None},
        ],
    )
    result = Portfolio(market, store).accounts()
    assert result["accounts"][0]["id"] == connection.id
    assert result["accounts"][0]["total"] == 200
    assert result["accounts"][0]["unpriced"] == 1
    assert result["accounts"][0]["holdings"][0]["used"] == 0.5
    assert "do-not-expose" not in json.dumps(result)


def test_research_sentiment_extraction_and_stock_statistics(settings, monkeypatch):
    research = Research(settings)
    monkeypatch.setattr(
        research,
        "_news_feed",
        lambda: {
            "source": "test",
            "items": [
                {
                    "id": "1",
                    "title": "Excellent growth and strong success!",
                    "summary": "A great improvement. Strong growth continues. A loss was avoided.",
                }
            ],
        },
    )
    news = research.news("extractive")
    assert news["items"][0]["sentiment"]["label"] == "positive"
    assert news["sentiment"]["positive"] == 1
    assert len(news["items"][0]["summary"]) < len(
        "A great improvement. Strong growth continues. A loss was avoided."
    )
    stock = research.stock("AAPL")
    assert stock["statistics"]["observations"] == len(stock["history"])
    assert stock["statistics"]["high"] >= stock["price"]
    assert len(research.blocks(50)["items"]) == 50


def test_restored_endpoints_validate_bounds_and_return_real_shapes(client):
    assert "ETH/BTC" in [i["symbol"] for i in client.get("/api/v1/markets/symbols").json()["items"]]
    response = client.get("/api/v1/markets/analysis?symbol=ETH/BTC&timeframe=1h&limit=90")
    assert response.status_code == 200
    assert response.json()["timeframe"] == "1h"
    assert len(response.json()["candles"]) == 90
    book = client.get("/api/v1/markets/orderbook?depth=5").json()
    assert len(book["asks"]) == len(book["bids"]) == 5
    assert book["asks"][0][0] > book["bids"][0][0]
    assert client.get("/api/v1/markets/analysis?timeframe=invalid").status_code == 422
    assert client.get("/api/v1/blocks?count=101").status_code == 422
    assert client.get("/api/v1/markets/correlation?symbols=BTC/USDT").status_code == 400
    assert client.get("/api/v1/portfolio/accounts").json()["accounts"][0]["status"] == "simulated"
    assert client.get("/api/v1/reports/trading").json()["items"] == []


def test_agent_keeps_exact_chart_context_without_adding_defaults(client):
    context = {"symbol": "ETH/BTC", "timeframe": "4h", "limit": 90}
    response = client.post(
        "/api/v1/agents/ask",
        json={"module": "analyst", "message": "Explain this window.", "context": context},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["context"] == context
    assert result["evidence"]["timeframe"] == "4h"
    assert result["evidence"]["symbol"] == "ETH/BTC"


def test_block_pagination_uses_last_height_and_stops_at_requested_count(settings, monkeypatch):
    import sibyl.services.research as module

    settings.mode = "live"
    urls = []

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url):
            urls.append(url)
            end = 100 if len(urls) == 1 else 85
            batch = [
                {"height": h, "id": str(h), "timestamp": h * 600, "tx_count": 1000, "size": 1000000}
                for h in range(end, end - 15, -1)
            ]
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: batch)

    monkeypatch.setattr(module.httpx, "Client", Client)
    result = Research(settings).blocks(25)
    assert len(result["items"]) == 25
    assert result["items"][0]["height"] == 100
    assert result["items"][-1]["height"] == 76
    assert urls == ["https://mempool.space/api/v1/blocks", "https://mempool.space/api/v1/blocks/85"]


def test_optional_equity_fundamentals_fail_without_losing_history(settings, monkeypatch):
    import sys

    settings.mode = "live"

    class Ticker:
        fast_info = {"currency": "EUR"}

        def history(self, **kwargs):
            return pd.DataFrame({"Close": [100, 110, 105]}, index=pd.date_range("2025-01-01", periods=3))

        def get_info(self):
            raise RuntimeError("provider unavailable")

    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(Ticker=lambda symbol: Ticker()))
    result = Research(settings).stock("TEST")
    assert result["currency"] == "EUR"
    assert result["price"] == 105
    assert result["statistics"]["period_return"] == pytest.approx(5)
    assert result["profile"] == {}
    assert result["profile_warning"]


def test_paper_risk_uses_closed_price_but_fills_at_observed_quote(settings, store, monkeypatch):
    import sibyl.services.strategies as module

    market = Market(settings, store)
    history = market.candles(limit=90)
    history[-1]["close"] = 100
    quote = [100]
    monkeypatch.setattr(market, "candles", lambda *args: history)
    monkeypatch.setattr(market, "price", lambda symbol: quote[0])
    monkeypatch.setattr(module, "signals", lambda frame, *args: pd.Series([1] * len(frame)))
    service = module.Strategies(market, store)
    job = service.start(BacktestRequest(stop_loss_pct=5, fee_bps=0, slippage_bps=0, max_trades=1))
    service.tick()
    assert service.jobs()[0]["quantity"] == 100
    history.append(
        {
            **history[-1],
            "timestamp": (pd.Timestamp(history[-1]["timestamp"]) + pd.Timedelta(days=1)).isoformat(),
            "close": 90,
        }
    )
    quote[0] = 105
    service.tick()
    result = service.jobs()[0]
    assert result["fills"][-1]["side"] == "sell"
    assert result["fills"][-1]["price"] == 105
    assert result["fills"][-1]["reason"] == "Stop loss at observed close"
    assert result["status"] == "completed"
    assert result["quantity"] == 0
    with pytest.raises(ValueError, match="completed|Completed"):
        service.status(job["id"], "running")
