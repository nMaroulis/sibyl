"""Exercise durable limit/cancel workflows using fake venues and isolated Demo wallets."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import ccxt
import pytest
from pydantic import ValidationError
from test_exchange_clients import fake_client
from test_exchange_trading import FakeExchange

from sibyl.exchanges.demo import DemoClient
from sibyl.exchanges.paper_limits import PaperLimits
from sibyl.models import ConnectionCreate, ExchangeOrderRequest, OrderRequest
from sibyl.services.market import Market
from sibyl.services.reporting import trading_report
from sibyl.services.trading import ExchangeTrading
from sibyl.storage import Store


class Venue(FakeExchange):
    """Return mutable aggregate fill observations, and optionally lose write acknowledgments."""

    def __init__(self):
        super().__init__()
        self.reads = self.cancels = 0
        self.cancel_failure = self.read_failure = None
        self.current = {
            "id": "native-123",
            "symbol": "BTC/USDT",
            "side": "buy",
            "status": "open",
            "filled": 0.0,
            "remaining": 0.01,
            "average": None,
        }
        self.params = None

    def price_to_precision(self, symbol, price):
        return f"{price:.2f}"

    def create_order(self, *args, **kwargs):
        self.calls += 1
        self.params = (args, kwargs)
        if self.failure:
            raise self.failure
        return dict(self.current)

    def fetch_order(self, identity, symbol):
        self.reads += 1
        if self.read_failure:
            raise self.read_failure
        assert (identity, symbol) == ("native-123", "BTC/USDT")
        return dict(self.current)

    def cancel_order(self, identity, symbol):
        self.cancels += 1
        if self.cancel_failure:
            raise self.cancel_failure
        self.current["status"] = "canceled"
        return dict(self.current)


@pytest.fixture
def setup(settings, store):
    settings.allow_live_trading = True
    connection = store.add_connection(
        ConnectionCreate(
            exchange="binance", label="Fake test venue", api_key="fake", secret="fake", sandbox=True
        )
    )
    market = Market(settings, store)
    venue = Venue()
    market._clients[connection.id] = venue
    return ExchangeTrading(market, store), venue, connection


def request(connection="demo", **changes):
    return ExchangeOrderRequest(
        **{
            "connection_id": getattr(connection, "id", connection),
            "symbol": "BTC/USDT",
            "side": "buy",
            "quantity": 0.01,
            "order_type": "limit",
            "limit_price": 50000,
            "idempotency_key": "limit-test-key",
            **changes,
        }
    )


def submit(service, connection="demo", **changes):
    review = service.preview(request(connection, **changes))
    return service.execute(review["id"], review["confirmation"])


def save(service, intent):
    with service.store.db() as db:
        service.lifecycle.write(db, intent)


@pytest.mark.parametrize(
    "changes",
    [
        {"limit_price": None},
        {"order_type": "market"},
        {"limit_price": 0},
        {"limit_price": float("nan")},
        {"order_type": "stop"},
    ],
)
def test_invalid_order_shapes(changes):
    with pytest.raises(ValidationError):
        request(**changes)


def test_limit_uses_exact_price_and_native_gtc_path(setup):
    service, venue, connection = setup
    order = submit(service, connection)
    assert order["status"] == "open" and order["tracking"]
    assert order["price"] == 50000 and order["remaining"] == 0.01
    args, kwargs = venue.params
    assert args == ("BTC/USDT", "limit", "buy", 0.01)
    assert kwargs == {"price": 50000, "params": {"clientOrderId": order["client_order_id"]}}
    assert service.execute(order["id"], order["confirmation"]) == order
    assert venue.calls == 1


def test_price_precision_bounds_and_insufficient_free_balance(setup):
    service, venue, connection = setup
    with pytest.raises(ValueError, match="Price exceeds market precision"):
        service.preview(request(connection, limit_price=50000.001))
    venue.markets["BTC/USDT"]["limits"]["price"] = {"max": 45000}
    with pytest.raises(ValueError, match="maximum price"):
        service.preview(request(connection))
    venue.markets["BTC/USDT"]["limits"]["price"] = {}
    venue.free["USDT"] = 500
    with pytest.raises(ValueError, match="1%"):
        service.preview(request(connection))
    assert venue.calls == 0


def test_limit_preview_key_cannot_change_price(setup):
    service, _, connection = setup
    service.preview(request(connection))
    with pytest.raises(ValueError, match="different exchange order"):
        service.preview(request(connection, limit_price=49000))


def test_partial_fills_merge_monotonically_then_close(setup):
    service, venue, connection = setup
    order = submit(service, connection)
    venue.current.update(filled=0.004, remaining=0.006, average=49990, cost=199.96)
    partial = service.refresh(order["id"])
    assert partial["status"] == "open" and partial["filled"] == 0.004
    assert partial["cost"] == 199.96
    venue.current.update(filled=0.002)
    with pytest.raises(ValueError, match="older cumulative"):
        service.refresh(order["id"])
    assert service.list_orders()[0]["filled"] == 0.004
    venue.current.update(status="closed", filled=0.01, remaining=0)
    assert not service.refresh(order["id"])["tracking"]
    venue.current.update(status="open")
    assert service.refresh(order["id"])["status"] == "closed"


@pytest.mark.parametrize(
    "changes",
    [
        {"symbol": "ETH/USDT"},
        {"id": "another-order"},
        {"side": "sell"},
        {"filled": -0.1},
        {"filled": 1},
        {"remaining": 2},
    ],
)
def test_mismatched_or_invalid_observations_are_not_persisted(setup, changes):
    service, venue, connection = setup
    order = submit(service, connection)
    venue.current.update(changes)
    with pytest.raises(ValueError):
        service.refresh(order["id"])
    assert service.list_orders()[0]["filled"] == 0


def test_cancellation_is_reviewed_and_concurrent_confirmations_send_once(setup):
    service, venue, connection = setup
    order = submit(service, connection)
    service.market.settings.allow_live_trading = False
    review = service.lifecycle.preview_cancel(order["id"])
    with pytest.raises(ValueError, match="Type CANCEL"):
        service.lifecycle.cancel(order["id"], review["id"], "yes")
    with ThreadPoolExecutor(4) as pool:
        results = list(
            pool.map(
                lambda _: service.lifecycle.cancel(order["id"], review["id"], review["confirmation"]),
                range(8),
            )
        )
    assert all(r["status"] == "canceled" and not r["tracking"] for r in results)
    assert venue.cancels == 1
    assert venue.calls == 1


def test_expired_or_unrelated_cancellation_does_not_write(setup):
    service, venue, connection = setup
    order = submit(service, connection)
    review = service.lifecycle.preview_cancel(order["id"])
    review["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    with service.store.db() as db:
        db.execute("UPDATE order_cancellations SET payload=? WHERE id=?", (json.dumps(review), review["id"]))
    with pytest.raises(ValueError, match="expired"):
        service.lifecycle.cancel(order["id"], review["id"], review["confirmation"])
    with pytest.raises(LookupError):
        service.lifecycle.cancel("different-intent", review["id"], review["confirmation"])
    assert venue.cancels == 0


def test_lost_cancel_ack_never_infers_canceled_or_retries(setup):
    service, venue, connection = setup
    order = submit(service, connection)
    review = service.lifecycle.preview_cancel(order["id"])
    venue.cancel_failure = ccxt.RequestTimeout("SECRET apiKey=private")
    result = service.lifecycle.cancel(order["id"], review["id"], review["confirmation"])
    assert result["status"] == "open" and result["cancel_state"] == "unknown"
    assert "SECRET" not in json.dumps(result)
    service.lifecycle.cancel(order["id"], review["id"], review["confirmation"])
    service.lifecycle.tick()
    assert venue.cancels == 1 and venue.calls == 1
    venue.current.update(status="closed", filled=0.01, remaining=0)
    assert service.refresh(order["id"])["status"] == "closed"


def test_fill_can_win_cancellation_race(setup):
    service, venue, connection = setup
    order = submit(service, connection)
    review = service.lifecycle.preview_cancel(order["id"])
    venue.current.update(status="closed", filled=0.01, remaining=0)
    venue.cancel_order = lambda *args: dict(venue.current)
    result = service.lifecycle.cancel(order["id"], review["id"], review["confirmation"])
    assert result["status"] == "closed" and result["filled"] == 0.01


def test_cancel_ack_without_terminal_status_requires_read(setup):
    service, venue, connection = setup
    order = submit(service, connection)
    review = service.lifecycle.preview_cancel(order["id"])
    venue.cancel_order = lambda *args: {"id": "native-123", "status": None}
    result = service.lifecycle.cancel(order["id"], review["id"], review["confirmation"])
    assert result["status"] == "open" and result["cancel_state"] == "requested"


def test_tracking_persists_restart_and_backs_off_without_order_writes(setup):
    service, venue, connection = setup
    order = submit(service, connection)
    order["next_check"] = 0
    save(service, order)
    restarted = ExchangeTrading(service.market, Store(service.store.path.parent))
    venue.read_failure = ccxt.NetworkError("SECRET")
    restarted.lifecycle.tick()
    failed = restarted.list_orders()[0]
    assert failed["status"] == "open" and failed["sync_failures"] == 1
    assert failed["next_check"] > time.time() + 30 and "SECRET" not in json.dumps(failed)
    reads = venue.reads
    restarted.lifecycle.tick()
    assert venue.reads == reads
    restarted.lifecycle.track(order["id"], False)
    restarted.lifecycle.tick()
    assert venue.reads == reads
    venue.read_failure = None
    restarted.lifecycle.track(order["id"], True)
    restarted.lifecycle.tick()
    assert venue.reads == reads + 1 and venue.calls == 1
    restarted.lifecycle.close()


def test_inactive_accounts_pause_automatic_reads_but_keep_manual_checks(setup):
    service, venue, connection = setup
    order = submit(service, connection)
    with service.store.db() as db:
        db.execute("DELETE FROM active_accounts")
    service.lifecycle.tick()
    assert venue.reads == 0
    service.refresh(order["id"])
    assert venue.reads == 1


def test_unknown_submission_is_not_retried_by_worker(setup):
    service, venue, connection = setup
    venue.failure = ccxt.RequestTimeout("SECRET")
    order = submit(service, connection)
    service.lifecycle.tick()
    assert order["status"] == "unknown" and venue.calls == 1 and venue.reads == 0
    assert service.list_orders()[0]["sync_error"]


@pytest.fixture
def demo(settings, store):
    return ExchangeTrading(Market(settings, store), store), DemoClient(store)


def test_demo_resting_limit_reserves_and_cancels_without_fills(demo):
    service, client = demo
    before = client.fetch_balance()
    order = submit(service, limit_price=100)
    balance = client.fetch_balance()
    assert balance["total"] == before["total"]
    assert balance["used"]["USDT"] == pytest.approx(1.001)
    assert balance["free"]["USDT"] == pytest.approx(before["total"]["USDT"] - 1.001)
    assert service.refresh(order["id"])["status"] == "open"
    review = service.lifecycle.preview_cancel(order["id"])
    result = service.lifecycle.cancel(order["id"], review["id"], review["confirmation"])
    assert result["status"] == "canceled"
    assert client.fetch_balance() == before
    assert service.store.orders() == []


def test_demo_crossing_limit_fills_once_and_links_native_fill(demo):
    service, client = demo
    before = client.fetch_balance()["total"]
    order = submit(service, limit_price=100000)
    assert order["status"] == "open" and not service.store.orders()
    filled = service.refresh(order["id"])
    assert filled["status"] == "closed" and filled["filled"] == 0.01
    assert filled["average"] == 100000 and not filled["tracking"]
    service.refresh(order["id"])
    assert len(service.store.orders()) == 1
    fill = client.fetch_trade_page("BTC/USDT", {}).items[0]
    assert fill["order"] == filled["exchange_order_id"]
    assert client.fetch_balance()["total"]["USDT"] == pytest.approx(before["USDT"] - 1001)
    assert not client.fetch_open_orders("BTC/USDT")
    report = trading_report(service.store, service)
    assert len(report["items"]) == 1 and report["items"][0]["mode"] == "paper"


def test_demo_holds_survive_restart_and_prevent_market_spending(demo):
    service, client = demo
    cash = client.fetch_balance()["free"]["USDT"]
    order = client.create_order(
        "BTC/USDT", "limit", "buy", 1, {"clientOrderId": "hold-entire-wallet"}, price=(cash - 0.01) / 1.001
    )
    restarted = DemoClient(service.store)
    assert restarted.fetch_open_orders("BTC/USDT")[0]["id"] == order["id"]
    with pytest.raises(ValueError, match="reservations"):
        service.store.execute_paper(
            OrderRequest(side="buy", quantity=0.01, idempotency_key="cannot-spend-hold"), 100
        )
    restarted.cancel_order(order["id"], "BTC/USDT")
    assert restarted.fetch_balance()["used"]["USDT"] == 0


def test_demo_sell_hold_blocks_double_spend_and_release_is_idempotent(demo):
    service, client = demo
    qty = client.fetch_balance()["free"]["BTC"]
    order = client.create_order(
        "BTC/USDT", "limit", "sell", qty, {"clientOrderId": "hold-all-btc"}, price=200000
    )
    assert client.fetch_balance()["free"]["BTC"] == 0
    with pytest.raises(ValueError, match="reservations"):
        client.create_order(
            "BTC/USDT", "limit", "sell", 0.001, {"clientOrderId": "no-extra-btc"}, price=200000
        )
    client.cancel_order(order["id"], "BTC/USDT")
    client.cancel_order(order["id"], "BTC/USDT")
    assert client.fetch_balance()["free"]["BTC"] == qty


def test_concurrent_demo_match_and_cancel_has_one_atomic_winner(demo):
    service, client = demo
    native = client.create_order(
        "BTC/USDT", "limit", "buy", 0.01, {"clientOrderId": "match-cancel-race"}, price=100000
    )
    book = {"ask": 99000, "bid": 98000}
    with ThreadPoolExecutor(4) as pool:
        list(
            pool.map(
                lambda i: (
                    PaperLimits(service.store).match(native["id"], "BTC/USDT", book)
                    if i % 2
                    else client.cancel_order(native["id"], "BTC/USDT")
                ),
                range(12),
            )
        )
    final = client.fetch_order(native["id"], "BTC/USDT")
    assert final["status"] in {"closed", "canceled"}
    assert len(service.store.orders()) == (1 if final["status"] == "closed" else 0)
    assert client.fetch_balance()["used"]["USDT"] == 0


def test_demo_recovery_after_submitted_native_order_lost_local_ack(demo):
    service, client = demo
    review = service.preview(request(limit_price=100))
    review.update(status="submitting", tracking=True)
    save(service, review)
    native = client.create_order(
        "BTC/USDT", "limit", "buy", 0.01, {"clientOrderId": review["client_order_id"]}, price=100
    )
    restarted = ExchangeTrading(service.market, service.store)
    restarted.lifecycle.tick()
    recovered = restarted.list_orders()[0]
    assert recovered["exchange_order_id"] == native["id"] and recovered["status"] == "open"
    assert len(client.fetch_open_orders("BTC/USDT")) == 1


def test_demo_market_and_limit_keys_cannot_collide(demo):
    service, client = demo
    client.create_order("BTC/USDT", "limit", "buy", 0.01, {"clientOrderId": "shared-key-limit"}, price=100)
    with pytest.raises(ValueError, match="limit order"):
        service.store.execute_paper(
            OrderRequest(side="buy", quantity=0.01, idempotency_key="shared-key-limit"), 100
        )
    client.create_order("BTC/USDT", "market", "buy", 0.01, {"clientOrderId": "shared-key-market"})
    with pytest.raises(ValueError, match="market order"):
        client.create_order(
            "BTC/USDT", "limit", "buy", 0.01, {"clientOrderId": "shared-key-market"}, price=100
        )


def test_demo_paused_account_does_not_match(demo):
    service, client = demo
    order = submit(service, limit_price=100000)
    with service.store.db() as db:
        db.execute("DELETE FROM active_accounts")
    assert service.refresh(order["id"])["status"] == "open"
    assert not service.store.orders()


@pytest.mark.parametrize("identity", ["binance", "coinbase", "kraken", "binance-testnet", "coinbase-sandbox"])
def test_native_limit_and_cancel_adapter_contract(monkeypatch, identity):
    if identity in {"binance-testnet", "coinbase-sandbox"}:
        from test_exchange_clients import Transport

        from sibyl.exchanges import create_client
        from sibyl.exchanges.catalog import exchange_spec

        monkeypatch.setattr(ccxt, exchange_spec(identity).ccxt_id, Transport)
        client = create_client(identity, credentials={"apiKey": "fake", "secret": "fake", "password": "fake"})
    else:
        client = fake_client(monkeypatch, identity)
    client._exchange.has["cancelOrder"] = True
    calls = []

    def create(*args, **kwargs):
        calls.append((args, kwargs))
        return {"id": "native", "status": "open", "filled": 0, "remaining": 0.01, "info": "SECRET"}

    client._exchange.create_order = create
    client._exchange.cancel_order = lambda *args: {"id": "native", "status": "canceled", "info": "SECRET"}
    result = client.create_order(
        "BTC/USDT", "limit", "buy", 0.01, {"clientOrderId": "reviewed-id"}, price=50000
    )
    args, kwargs = calls[0]
    assert args == ("BTC/USDT", "limit", "buy", 0.01, 50000)
    assert kwargs["params"] == {
        "client_order_id" if identity == "coinbase" else "clientOrderId": "reviewed-id",
        "timeInForce": "GTC",
    }
    assert "SECRET" not in json.dumps(result)
    assert client.cancel_order("native", "BTC/USDT")["status"] == "canceled"


def test_read_only_provider_rejects_new_limit_and_cancel(monkeypatch):
    client = fake_client(monkeypatch, "bybit")
    with pytest.raises(ccxt.NotSupported):
        client.create_order("BTC/USDT", "limit", "buy", 0.01, {"clientOrderId": "reviewed-id"}, price=50000)
    with pytest.raises(ccxt.NotSupported):
        client.cancel_order("native", "BTC/USDT")


def test_http_workflow_and_no_mutation_example(client):
    # Exclude the worker during deterministic API assertions; it is tested above.
    service = client.app.state.services.trading
    service.lifecycle.close()
    sample = client.get("/api/v1/exchange-orders/example")
    assert sample.status_code == 200 and sample.headers["cache-control"] == "no-store"
    assert len({row["id"] for row in sample.json()}) == len(sample.json())
    assert service.list_orders() == [] and service.store.orders() == []
    balance = client.get("/api/v1/paper/balances")
    assert balance.status_code == 200 and "used" in balance.json()
    preview = client.post("/api/v1/exchange-orders/preview", json=request(limit_price=100).model_dump())
    assert preview.status_code == 200
    order = preview.json()
    confirmed = client.post(
        f"/api/v1/exchange-orders/{order['id']}/confirm", json={"confirmation": order["confirmation"]}
    )
    assert confirmed.status_code == 200 and confirmed.json()["status"] == "open"
    review = client.post(f"/api/v1/exchange-orders/{order['id']}/cancel/preview").json()
    result = client.post(
        f"/api/v1/exchange-orders/{order['id']}/cancel",
        json={"cancel_id": review["id"], "confirmation": review["confirmation"]},
    )
    assert result.status_code == 200 and result.json()["status"] == "canceled"


def test_old_cancel_reviews_cannot_authorize_a_second_attempt(setup):
    service, venue, connection = setup
    order = submit(service, connection)
    first = service.lifecycle.preview_cancel(order["id"])
    second = service.lifecycle.preview_cancel(order["id"])
    venue.cancel_failure = TimeoutError("lost reply")
    service.lifecycle.cancel(order["id"], first["id"], first["confirmation"])
    service.refresh(order["id"])
    with pytest.raises(ValueError, match="previous cancellation"):
        service.lifecycle.cancel(order["id"], second["id"], second["confirmation"])
    assert venue.cancels == 1
    fresh = service.lifecycle.preview_cancel(order["id"])
    service.lifecycle.cancel(order["id"], fresh["id"], fresh["confirmation"])
    assert venue.cancels == 2  # A fresh explicit review, never an automatic retry.


def test_cancel_attempt_survives_restart_without_resubmission(setup):
    service, venue, connection = setup
    order = submit(service, connection)
    review = service.lifecycle.preview_cancel(order["id"])
    review.update(status="submitting", attempted_at=datetime.now(UTC).isoformat())
    with service.store.db() as db:
        db.execute("UPDATE order_cancellations SET payload=? WHERE id=?", (json.dumps(review), review["id"]))
    restarted = ExchangeTrading(service.market, Store(service.store.path.parent))
    result = restarted.lifecycle.cancel(order["id"], review["id"], review["confirmation"])
    assert result["status"] == "open" and venue.cancels == 0


def test_worker_reads_one_due_intent_beyond_display_limit(setup):
    service, venue, connection = setup
    order = submit(service, connection)
    order["next_check"] = 0
    save(service, order)
    with service.store.db() as db:
        for i in range(105):
            preview = dict(order, id=f"other-{i}", status="preview", tracking=False)
            db.execute(
                "INSERT INTO exchange_orders VALUES(?,?,?)",
                (preview["id"], f"unique-key-{i}", json.dumps(preview)),
            )
    assert order["id"] not in {item["id"] for item in service.list_orders()}
    service.lifecycle.tick()
    assert venue.reads == 1
    service.lifecycle.tick()
    assert venue.reads == 1 and venue.calls == 1


def test_demo_inactive_new_market_or_limit_rejected(demo):
    service, client = demo
    with service.store.db() as db:
        db.execute("DELETE FROM active_accounts")
    with pytest.raises(ValueError, match="Activate"):
        submit(service)
    with pytest.raises(ValueError, match="no longer active"):
        client.create_order("BTC/USDT", "market", "buy", 0.01, {"clientOrderId": "inactive-wallet"})


def test_bad_native_balance_never_passes_preview(setup):
    service, venue, connection = setup
    venue.free["USDT"] = float("nan")
    with pytest.raises(ValueError, match="Insufficient available"):
        service.preview(request(connection))
    assert venue.calls == 0


def test_restart_observation_resolves_unacknowledged_cancel_without_retry(setup):
    service, venue, connection = setup
    order = submit(service, connection)
    order.update(cancel_state="submitting", cancel_requested_at=datetime.now(UTC).isoformat(), next_check=0)
    save(service, order)
    restarted = ExchangeTrading(service.market, Store(service.store.path.parent))
    restarted.lifecycle.tick()
    recovered = restarted.list_orders()[0]
    assert recovered["status"] == "open" and recovered["cancel_state"] == "unknown"
    assert venue.cancels == 0
    venue.current.update(status="canceled")
    assert restarted.refresh(order["id"])["cancel_state"] == "confirmed"
