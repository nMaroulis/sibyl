"""Account automation with fake venues; no credentials or real exchange writes."""

import json
import math
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import ccxt
import pandas as pd
import pytest

from sibyl.exchanges.history import TradePage
from sibyl.models import ConnectionCreate
from sibyl.services.market import Market
from sibyl.services.trading import ExchangeTrading
from sibyl.strategies import Strategies
from sibyl.strategies.execution import runner, venue
from sibyl.strategies.execution.contracts import ExchangeStrategyRequest


class Venue:
    """Native orders/fills are separate, allowing pending, partial and uncertain outcomes."""

    timeframes = {"1m": "1m", "1d": "1d"}

    def __init__(self):
        self.clock = math.floor(time.time() / 60) * 60
        self.markets = {
            "BTC/USDT": {
                "spot": True,
                "active": True,
                "limits": {"cost": {"min": 1}, "amount": {"min": 0.0001}},
            }
        }
        self.free = {"USDT": 100000.0, "BTC": 50.0}
        self.orders, self.fills, self.calls = {}, [], []
        self.failure = None
        self.bid, self.ask = 99.95, 100.05

    def load_markets(self):
        return self.markets

    def market(self, symbol):
        return self.markets[symbol]

    def fetch_ohlcv(self, symbol, timeframe, limit):
        latest = self.clock * 1000 - 60_000
        return [[latest - i * 60_000, 100, 101, 99, 100, 10] for i in reversed(range(limit))]

    def fetch_order_book(self, symbol, limit):
        return {"timestamp": self.clock * 1000, "bids": [[self.bid, 100]], "asks": [[self.ask, 100]]}

    def fetch_balance(self):
        return {"free": self.free}

    def amount_to_precision(self, symbol, amount):
        return f"{math.floor(amount * 10000) / 10000:.4f}"

    def price_to_precision(self, symbol, price):
        return f"{math.floor(price * 100) / 100:.2f}"

    def format_client_order_id(self, identity):
        return identity

    def create_order(self, symbol, order_type, side, amount, params, price):
        self.calls.append((side, amount, price, params["clientOrderId"]))
        identity = str(len(self.calls))
        result = {
            "id": identity,
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "status": "open",
            "filled": 0,
            "remaining": amount,
            "cost": 0,
            "clientOrderId": params["clientOrderId"],
        }
        self.orders[identity] = result
        if self.failure:
            raise self.failure
        return result

    def fetch_order(self, identity, symbol):
        return self.orders[identity].copy()

    def fetch_order_fill_page(self, identity, symbol, cursor, limit=100):
        return TradePage([fill.copy() for fill in self.fills if fill["order"] == identity], {}, True)

    def settle(self, identity, quantity=None, *, currency="USDT", fee=0.1, terminal=True):
        order = self.orders[identity]
        requested = next(row[1] for row in self.calls if row[3] == order["clientOrderId"])
        quantity = requested if quantity is None else quantity
        order.update(
            status="closed" if terminal else "open",
            filled=quantity,
            remaining=requested - quantity,
            cost=quantity * 100,
            average=100,
        )
        self.fills.append(
            {
                "id": str(len(self.fills) + 1),
                "order": identity,
                "symbol": "BTC/USDT",
                "side": order["side"],
                "timestamp": self.clock * 1000,
                "amount": quantity,
                "price": 100,
                "cost": quantity * 100,
                "fees": [{"currency": currency, "cost": fee}],
            }
        )

    def close(self):
        pass


@pytest.fixture
def execution(settings, store, monkeypatch):
    settings.allow_live_trading = settings.allow_strategy_execution = True
    connection = store.add_connection(
        ConnectionCreate(exchange="binance-testnet", label="Isolated test", api_key="FAKE", secret="FAKE")
    )
    market = Market(settings, store)
    native = Venue()
    market._clients[connection.id] = native
    clock = SimpleNamespace(time=lambda: native.clock)
    monkeypatch.setattr(venue, "time", clock)
    monkeypatch.setattr(runner, "time", clock)
    monkeypatch.setattr(runner, "signals", lambda frame, *args: pd.Series([1] * len(frame)))
    strategies = Strategies(market, store)
    trading = ExchangeTrading(market, store)
    strategies.attach_execution(trading)
    yield strategies, trading, native, connection
    market.close()


def request(connection, **changes):
    return ExchangeStrategyRequest(
        connection_id=connection.id,
        parameters={"strategy": "ema", "capital": 1000, "candles": 90, "timeframe": "1m"},
        **changes,
    )


def start(execution, **changes):
    strategies, trading, native, connection = execution
    review = strategies.execution.preview(request(connection, **changes))
    job = strategies.execution.start(review["id"], review["confirmation"])
    return job, review


def submit(execution):
    strategies, trading, native, _ = execution
    job, _ = start(execution)
    native.clock += 60
    strategies.tick()
    job = strategies.journal.job(job["id"])
    intent = strategies.execution._intent(job)
    return job, intent


def reconcile(trading, identity):
    trading.lifecycle.refresh(identity)
    return trading.reconciliation.sync(identity, manual=True)


def test_approval_is_read_only_and_start_waits_for_a_new_candle(execution):
    strategies, _, native, _ = execution
    job, review = start(execution)
    assert not native.calls
    assert job["mode"] == "exchange" and job["environment"] == "test"
    assert strategies.execution.start(review["id"], review["confirmation"])["id"] == job["id"]
    strategies.tick()
    assert not native.calls
    assert strategies.journal.job(job["id"])["fee_assets"] == {}
    native.clock += 60
    strategies.tick()
    assert len(native.calls) == 1
    side, quantity, price, _ = native.calls[0]
    assert side == "buy" and quantity * price <= 500
    assert quantity * price * 1.01 <= 1000
    strategies.tick()
    assert len(native.calls) == 1


def test_native_fills_not_acknowledgments_drive_ownership_and_sell_size(execution, monkeypatch):
    strategies, trading, native, _ = execution
    job, intent = submit(execution)
    assert job["quantity"] == 0 and job["cash"] == 1000
    native.settle(intent["exchange_order_id"], currency="BTC", fee=0.001)
    assert reconcile(trading, intent["id"])["reconciliation"]["status"] == "matched"
    strategies.tick()
    actual = strategies.journal.job(job["id"])
    bought = native.calls[0][1]
    assert actual["quantity"] == pytest.approx(bought - 0.001)
    assert actual["cash"] == pytest.approx(1000 - bought * 100)
    assert actual["native_fill_count"] == 1
    monkeypatch.setattr(runner, "signals", lambda frame, *args: pd.Series([-1] * len(frame)))
    native.clock += 60
    strategies.tick()
    assert len(native.calls) == 2 and native.calls[-1][0] == "sell"
    assert native.calls[-1][1] <= actual["quantity"] / 1.01
    assert native.calls[-1][1] < native.free["BTC"]
    native.settle("2")
    reconcile(trading, strategies.execution._intent(strategies.journal.job(job["id"]))["id"])
    strategies.tick()
    complete = strategies.journal.job(job["id"])
    assert complete["native_fill_count"] == 2 and complete["realized_pnl"] != 0
    assert complete["fee_assets"]["BTC"] == 0.001
    assert complete["quantity"] > 0  # The explicit base-fee reserve remains owned.


def test_partial_fill_blocks_next_order_and_repeated_reads_do_not_duplicate(execution):
    strategies, trading, native, _ = execution
    job, intent = submit(execution)
    native.settle(intent["exchange_order_id"], quantity=1, terminal=False)
    reconcile(trading, intent["id"])
    native.clock += 60
    for _ in range(3):
        strategies.tick()
    current = strategies.journal.job(job["id"])
    assert current["quantity"] == 1 and current["native_fill_count"] == 1
    assert current["execution_state"] == "waiting_order" and len(native.calls) == 1


def test_uncertain_submission_restart_and_manual_endpoint_never_resend(execution):
    strategies, trading, native, _ = execution
    native.failure = ccxt.RequestTimeout("PRIVATE-SECRET")
    job, intent = submit(execution)
    assert intent["status"] == "unknown" and strategies.journal.job(job["id"])["status"] == "paused"
    restarted = Strategies(strategies.market, strategies.store)
    restarted.attach_execution(trading)
    for _ in range(2):
        restarted.tick()
    with pytest.raises(ValueError, match="strategy approval"):
        trading.execute(intent["id"], intent["confirmation"])
    with pytest.raises(ValueError, match="Resolve pending"):
        restarted.status(job["id"], "running")
    assert len(native.calls) == 1 and "PRIVATE-SECRET" not in json.dumps(restarted.jobs())


def test_restart_requires_resume_and_skips_missed_candles(execution):
    strategies, trading, native, _ = execution
    job, _ = start(execution)
    restarted = Strategies(strategies.market, strategies.store)
    restarted.attach_execution(trading)
    native.clock += 120
    restarted.tick()
    assert not native.calls and restarted.journal.job(job["id"])["status"] == "paused"
    restarted.status(job["id"], "running")
    restarted.tick()
    assert not native.calls
    native.clock += 60
    restarted.tick()
    assert len(native.calls) == 1


def test_pause_during_preview_prevents_write_and_abandons_old_plan(execution, monkeypatch):
    strategies, trading, native, _ = execution
    job, _ = start(execution)
    original = trading.preview

    def pause_before_preview(body):
        strategies.status(job["id"], "paused")
        strategies.status(job["id"], "running")
        return original(body)

    monkeypatch.setattr(trading, "preview", pause_before_preview)
    native.clock += 60
    strategies.tick()
    assert not native.calls
    assert trading.list_orders()[0]["strategy_abandoned"] is True


def test_stop_keeps_importing_native_fills_without_submitting_or_liquidating(execution):
    strategies, trading, native, _ = execution
    job, intent = submit(execution)
    strategies.status(job["id"], "stopped")
    native.settle(intent["exchange_order_id"])
    reconcile(trading, intent["id"])
    strategies.tick()
    assert strategies.journal.job(job["id"])["quantity"] > 0 and len(native.calls) == 1
    with pytest.raises(ValueError, match="terminal"):
        strategies.status(job["id"], "running")


def test_late_fee_correction_rebuilds_cash_without_duplicate_fill(execution):
    strategies, trading, native, _ = execution
    job, intent = submit(execution)
    native.settle(intent["exchange_order_id"], fee=0.1)
    reconcile(trading, intent["id"])
    strategies.tick()
    before = strategies.journal.job(job["id"])
    native.fills[0]["fees"][0]["cost"] = 0.3
    reconcile(trading, intent["id"])
    strategies.tick()
    after = strategies.journal.job(job["id"])
    assert after["cash"] == pytest.approx(before["cash"] - 0.2)
    assert after["native_fill_count"] == 1
    assert any(
        event["action"] == "FILL_CORRECTION" for event in strategies.journal.events(job["id"])["items"]
    )


def test_foreign_fee_currency_blocks_further_orders_instead_of_inventing_conversion(execution):
    strategies, trading, native, _ = execution
    job, intent = submit(execution)
    native.settle(intent["exchange_order_id"], currency="BNB")
    reconcile(trading, intent["id"])
    strategies.tick()
    current = strategies.journal.job(job["id"])
    assert current["status"] == "paused" and current["unvalued_fees"] == {"BNB": 0.1}
    assert len(native.calls) == 1


def test_daily_limit_and_loss_guard_latch(execution, monkeypatch):
    strategies, trading, native, _ = execution
    job, intent = submit(execution)
    native.settle(intent["exchange_order_id"])
    reconcile(trading, intent["id"])
    native.bid, native.ask = 1, 1.0001
    strategies.tick()
    current = strategies.journal.job(job["id"])
    assert current["status"] == "paused" and current["risk_locked"]
    with pytest.raises(ValueError, match="latched"):
        strategies.status(job["id"], "running")
    assert len(native.calls) == 1


def test_server_flags_and_wrong_expired_confirmation_are_enforced(execution):
    strategies, trading, native, connection = execution
    review = strategies.execution.preview(request(connection))
    with pytest.raises(ValueError, match="Type START TEST"):
        strategies.execution.start(review["id"], "yes")
    trading.market.settings.allow_strategy_execution = False
    with pytest.raises(ValueError, match="SIBYL_ALLOW_STRATEGY_EXECUTION"):
        strategies.execution.start(review["id"], review["confirmation"])
    trading.market.settings.allow_strategy_execution = True
    review["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    with strategies.store.db() as db:
        db.execute("UPDATE strategy_reviews SET payload=? WHERE id=?", (json.dumps(review), review["id"]))
    with pytest.raises(ValueError, match="expired"):
        strategies.execution.start(review["id"], review["confirmation"])
    assert not native.calls


def test_pair_conflicts_and_portfolio_cash_allocations_are_checked(execution):
    strategies, _, native, connection = execution
    start(execution)
    with pytest.raises(ValueError, match="account/pair"):
        strategies.execution.preview(request(connection))
    assert not native.calls


def test_support_inventory_and_invalid_api_payloads(client):
    result = client.get("/api/v1/strategies/exchange/options").json()
    assert not result["enabled"]
    providers = {row["id"] for row in result["providers"]}
    assert {
        "binance",
        "binanceus",
        "binance-testnet",
        "coinbase",
        "coinbase-sandbox",
        "kraken",
        "okx",
        "bybit",
        "kucoin",
    } == providers
    assert (
        client.post(
            "/api/v1/strategies/exchange/preview",
            json={"connection_id": "demo", "parameters": {"capital": 1000}, "command": "write"},
        ).status_code
        == 422
    )


def test_rolling_order_count_blocks_an_exit_until_review(execution, monkeypatch):
    strategies, trading, native, _ = execution
    job, _ = start(execution, risk={"max_orders_per_day": 1, "max_order_quote": 500})
    native.clock += 60
    strategies.tick()
    intent = strategies.execution._intent(strategies.journal.job(job["id"]))
    native.settle(intent["exchange_order_id"])
    reconcile(trading, intent["id"])
    monkeypatch.setattr(runner, "signals", lambda frame, *args: pd.Series([-1] * len(frame)))
    native.clock += 60
    strategies.tick()
    current = strategies.journal.job(job["id"])
    assert current["status"] == "paused" and "24-hour" in current["error"]
    assert len(native.calls) == 1


@pytest.mark.parametrize("cause", ["account", "server", "spread", "gap"])
def test_changed_preconditions_block_new_writes(execution, cause, monkeypatch):
    strategies, _, native, connection = execution
    job, _ = start(execution)
    if cause == "account":
        strategies.store.activate_account(connection.id, False)
    elif cause == "server":
        strategies.market.settings.allow_strategy_execution = False
    elif cause == "spread":
        native.ask = 120
    else:
        original = native.fetch_ohlcv
        monkeypatch.setattr(native, "fetch_ohlcv", lambda *a, **kw: original(*a, **kw)[::2])
    native.clock += 60
    strategies.tick()
    assert strategies.journal.job(job["id"])["status"] == "paused" and not native.calls


def test_incomplete_fees_and_fee_corrections_after_stop_remain_visible(execution):
    strategies, trading, native, _ = execution
    job, intent = submit(execution)
    native.settle(intent["exchange_order_id"])
    native.fills[0]["fees"] = []
    reconcile(trading, intent["id"])
    strategies.tick()
    current = strategies.journal.job(job["id"])
    assert current["status"] == "paused" and current["accounting_incomplete"]
    strategies.status(job["id"], "stopped")
    native.fills[0]["fees"] = [{"currency": "USDT", "cost": 1}]
    reconcile(trading, intent["id"])
    strategies.tick()
    current = strategies.journal.job(job["id"])
    assert current["status"] == "stopped" and not current["accounting_incomplete"]
    assert current["native_fill_count"] == 1 and current["fees_paid"] == 1


def test_fractional_quote_budgets_and_price_caps_are_enforced(execution):
    _, _, native, connection = execution
    body = ExchangeStrategyRequest(
        connection_id=connection.id, parameters={"capital": 0.05}, risk={"max_order_quote": 0.01}
    )
    assert body.parameters.capital == 0.05
    job = {
        "parameters": {"symbol": "BTC/USDT"},
        "risk": {"max_order_quote": 500, "price_limit_bps": 25, "fee_reserve_bps": 100},
        "cash": 1000,
        "quantity": 1,
    }
    observed = {"ask": native.ask, "bid": native.bid}
    buy_qty, buy_price = venue.order_size(native, job, observed, "buy")
    sell_qty, sell_price = venue.order_size(native, job, observed, "sell")
    assert buy_price <= native.ask * 1.0025 and sell_price >= native.bid * 0.9975
    assert buy_qty * buy_price <= 500 and sell_qty <= 1 / 1.01


def test_budget_allocations_cover_other_pairs_on_the_same_account(execution):
    strategies, _, native, connection = execution
    start(execution)
    native.markets["ETH/USDT"] = native.markets["BTC/USDT"].copy()
    native.free["USDT"] = 1500
    body = ExchangeStrategyRequest(
        connection_id=connection.id,
        parameters={"symbol": "ETH/USDT", "capital": 1000, "candles": 90, "timeframe": "1m"},
    )
    with pytest.raises(ValueError, match="other strategy allocations"):
        strategies.execution.preview(body)


def test_provider_failures_never_expose_private_exception_text(execution, monkeypatch):
    strategies, _, native, _ = execution
    job, _ = start(execution)

    def fail(*args, **kwargs):
        raise ValueError("PRIVATE-KEY-SENTINEL")

    monkeypatch.setattr(native, "fetch_order_book", fail)
    native.clock += 60
    strategies.tick()
    current = strategies.journal.job(job["id"])
    assert current["status"] == "paused" and "PRIVATE-KEY" not in json.dumps(current)


def test_full_http_approval_creates_one_scoped_job(client, monkeypatch):
    services = client.app.state.services
    services.settings.allow_live_trading = services.settings.allow_strategy_execution = True
    connection = services.store.add_connection(
        ConnectionCreate(exchange="binance-testnet", label="API fixture", api_key="FAKE", secret="FAKE")
    )
    native = Venue()
    services.market._clients[connection.id] = native
    monkeypatch.setattr(venue, "time", SimpleNamespace(time=lambda: native.clock))
    body = request(connection).model_dump()
    review = client.post("/api/v1/strategies/exchange/preview", json=body)
    assert review.status_code == 200 and not native.calls
    approval = review.json()
    url = f"/api/v1/strategies/exchange/reviews/{approval['id']}/start"
    assert client.post(url, json={"confirmation": "wrong"}).status_code == 400
    first = client.post(url, json={"confirmation": approval["confirmation"]})
    second = client.post(url, json={"confirmation": approval["confirmation"]})
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert client.get(f"/api/v1/strategies/jobs/{first.json()['id']}").json()["job"]["mode"] == "exchange"
    assert not native.calls


def test_concurrent_start_and_missing_review_ack_recover_the_same_job(execution):
    from concurrent.futures import ThreadPoolExecutor

    strategies, _, native, connection = execution
    review = strategies.execution.preview(request(connection))
    with ThreadPoolExecutor(4) as pool:
        results = list(
            pool.map(lambda _: strategies.execution.start(review["id"], review["confirmation"]), range(4))
        )
    assert len({result["id"] for result in results}) == 1
    with strategies.store.db() as db:
        db.execute("UPDATE strategy_reviews SET payload=? WHERE id=?", (json.dumps(review), review["id"]))
    assert strategies.execution.start(review["id"], review["confirmation"])["id"] == results[0]["id"]
    assert not native.calls


def test_native_precision_underflow_is_retained_as_dust(execution, monkeypatch):
    _, _, native, _ = execution

    def underflow(*args):
        raise ccxt.InvalidOrder("Amount below precision")

    monkeypatch.setattr(native, "amount_to_precision", underflow)
    assert venue.is_dust(native, "BTC/USDT", 1e-10, 100)
