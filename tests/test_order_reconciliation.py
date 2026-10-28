"""Order/fill contracts use isolated ledgers and fake transports, never real account writes."""

import json
from concurrent.futures import ThreadPoolExecutor

import ccxt
import pytest
from test_order_management import save, submit
from test_order_management import setup as setup

from sibyl.exchanges.history import TradePage
from sibyl.exchanges.order_fills import fetch_order_fill_page
from sibyl.services.ledger import AccountLedger, ledger_fill, now_iso
from sibyl.services.trading import ExchangeTrading


def execution(identity="1", quantity=0.01, **changes):
    return {
        "id": identity,
        "order": "native-123",
        "symbol": "BTC/USDT",
        "side": "buy",
        "timestamp": 1768478400000,
        "amount": quantity,
        "price": 50000,
        "cost": quantity * 50000,
        "fees": [{"currency": "USDT", "cost": quantity * 50}],
        **changes,
    }


@pytest.fixture
def reconciliation(setup):
    service, venue, connection = setup
    venue.fill_reads = 0
    venue.fill_pages = lambda cursor: TradePage([execution()], {}, True)

    def fetch(identity, symbol, cursor, limit=100):
        assert (identity, symbol) == ("native-123", "BTC/USDT")
        venue.fill_reads += 1
        return venue.fill_pages(cursor)

    venue.fetch_order_fill_page = fetch
    intent = submit(service, connection)
    venue.current.update(status="closed", filled=0.01, remaining=0, cost=500)
    service.lifecycle.refresh(intent["id"])
    return service, venue, connection, intent["id"]


def due(service, identity):
    with service.store.db() as db:
        job = service.reconciliation._read(db, identity)
        job["next_attempt"] = 0
        service.reconciliation._write(db, identity, job)


def test_native_executions_share_ledger_and_do_not_duplicate(reconciliation):
    service, venue, connection, identity = reconciliation
    first = service.reconciliation.sync(identity, manual=True)
    assert first["reconciliation"]["status"] == "matched"
    assert first["reconciliation"]["fees"] == [{"currency": "USDT", "cost": 0.5}]
    assert first["reconciliation"]["settlement_final"] is False
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda _: service.reconciliation.sync(identity, manual=True), range(4)))
    retained = AccountLedger(service.store, recover=False).fills(account_id=connection.id)
    assert retained["total"] == 1
    assert venue.calls == 1 and venue.cancels == 0
    assert "cursor" not in json.dumps(first["reconciliation"])


def test_pagination_restart_and_late_fee_correction(reconciliation):
    service, venue, _, identity = reconciliation
    venue.fill_pages = lambda cursor: (
        TradePage([execution("1", 0.004, fees=[])], {"page": "second"}, False)
        if not cursor
        else TradePage([execution("2", 0.006)], {}, True)
    )
    first = service.reconciliation.sync(identity, manual=True)
    assert first["reconciliation"]["status"] == "missing_fills"
    restarted = ExchangeTrading(service.market, service.store)
    second = restarted.reconciliation.sync(identity, manual=True)
    assert second["reconciliation"]["status"] == "fees_missing"
    assert second["reconciliation"]["unknown_fee_fills"] == 1
    venue.fill_pages = lambda cursor: TradePage([execution("1", 0.004), execution("2", 0.006)], {}, True)
    updated = restarted.reconciliation.sync(identity, manual=True)
    assert updated["reconciliation"]["status"] == "matched"
    assert updated["reconciliation"]["fill_count"] == 2
    assert updated["reconciliation"]["fees"] == [{"currency": "USDT", "cost": 0.5}]


@pytest.mark.parametrize(
    "bad",
    [
        {"order": "other"},
        {"symbol": "ETH/USDT"},
        {"side": "sell"},
        {"amount": -1},
        {"timestamp": None},
        {"fees": [{"currency": "USDT", "cost": float("inf")}]},
    ],
)
def test_invalid_page_is_atomic_and_cursor_does_not_advance(reconciliation, bad):
    service, venue, _, identity = reconciliation
    venue.fill_pages = lambda cursor: TradePage([execution(), execution("2", **bad)], {"next": 1}, False)
    detail = service.reconciliation.sync(identity, manual=True)
    assert detail["fills"] == []
    assert detail["reconciliation"]["sync"]["state"] == "error"
    with service.store.db() as db:
        assert service.reconciliation._read(db, identity)["cursor"] == {}


def test_repeated_cursor_retains_first_page(reconciliation):
    service, venue, _, identity = reconciliation
    venue.fill_pages = lambda cursor: TradePage([execution("1", 0.004)], {"page": "same"}, False)
    service.reconciliation.sync(identity, manual=True)
    detail = service.reconciliation.sync(identity, manual=True)
    assert detail["reconciliation"]["sync"]["state"] == "error"
    assert detail["reconciliation"]["fill_count"] == 1


def test_duplicate_conflicting_fill_identity_is_not_silently_overwritten(reconciliation):
    service, venue, _, identity = reconciliation
    venue.fill_pages = lambda cursor: TradePage([execution(), execution(price=40000)], {}, True)
    assert service.reconciliation.sync(identity, manual=True)["fills"] == []


def test_terminal_passes_are_bounded_pause_survives_restart(reconciliation):
    service, venue, _, identity = reconciliation
    service.reconciliation.tracking(identity, False)
    service.reconciliation.tick()
    assert venue.fill_reads == 0
    service.reconciliation.tracking(identity, True)
    for _ in range(3):
        due(service, identity)
        service.reconciliation.tick()
    detail = service.reconciliation.detail(identity)
    assert detail["reconciliation"]["sync"]["terminal_passes"] == 3
    assert detail["reconciliation"]["sync"]["enabled"] is False
    ExchangeTrading(service.market, service.store).reconciliation.tick()
    assert venue.fill_reads == 3


def test_failure_is_sanitized_and_keeps_existing_evidence(reconciliation):
    service, venue, _, identity = reconciliation
    service.reconciliation.sync(identity, manual=True)

    def fail(cursor):
        raise ccxt.AuthenticationError("PRIVATE-KEY-SENTINEL")

    venue.fill_pages = fail
    detail = service.reconciliation.sync(identity, manual=True)
    assert detail["reconciliation"]["fill_count"] == 1
    assert detail["reconciliation"]["sync"]["error"]
    with service.store.db() as db:
        assert "PRIVATE-KEY-SENTINEL" not in db.execute("SELECT payload FROM order_fill_sync").fetchone()[0]


def test_local_read_recomputes_after_independent_ledger_fee_correction(reconciliation):
    service, venue, _, identity = reconciliation
    service.reconciliation.sync(identity, manual=True)
    fill = service.reconciliation.detail(identity)["fills"][0]
    fill["fees"] = [{"currency": "BNB", "cost": -0.0001}]
    with service.store.db() as db:
        AccountLedger.upsert_fills(db, [fill], now_iso())
    before = venue.fill_reads
    result = service.reconciliation.detail(identity)
    assert result["reconciliation"]["fees"] == [{"currency": "BNB", "cost": -0.0001}]
    assert venue.fill_reads == before


def test_inactive_account_background_does_not_read_manual_can(reconciliation):
    service, venue, connection, identity = reconciliation
    service.store.activate_account(connection.id, False)
    service.reconciliation.tick()
    assert venue.fill_reads == 0
    assert service.reconciliation.sync(identity, manual=True)["reconciliation"]["status"] == "matched"


def test_uncertain_order_without_native_id_never_scans_or_submits(reconciliation):
    service, venue, _, identity = reconciliation
    intent = service.reconciliation.detail(identity)["order"]
    intent.pop("exchange_order_id")
    intent["status"] = "unknown"
    save(service, intent)
    with pytest.raises(ValueError, match="No confirmed native order ID"):
        service.reconciliation.sync(identity, manual=True)
    assert venue.fill_reads == 0 and venue.calls == 1


def test_mismatch_canceled_partial_and_account_scope(reconciliation):
    service, venue, connection, identity = reconciliation
    intent = service.reconciliation.detail(identity)["order"]
    intent.update(status="canceled", filled=0.004, remaining=0.006, cost=200)
    save(service, intent)
    venue.current.update(status="canceled", filled=0.004, remaining=0.006, cost=200)
    service.lifecycle.refresh(identity)
    venue.fill_pages = lambda cursor: TradePage([execution(quantity=0.006)], {}, True)
    assert service.reconciliation.sync(identity, manual=True)["reconciliation"]["status"] == "mismatch"
    venue.fill_pages = lambda cursor: TradePage([execution(quantity=0.004)], {}, True)
    assert service.reconciliation.sync(identity, manual=True)["reconciliation"]["status"] == "matched"
    metadata = {
        "account_id": "different-account",
        "account": "Elsewhere",
        "exchange": "binance",
        "environment": "production",
        "symbol": "BTC/USDT",
    }
    unrelated = ledger_fill(execution(quantity=2), metadata)
    with service.store.db() as db:
        AccountLedger.upsert_fills(db, [unrelated], now_iso())
    assert service.reconciliation.detail(identity)["reconciliation"]["quantity"] == 0.004


def test_database_failure_rolls_back_fills_and_checkpoint(reconciliation, monkeypatch):
    service, venue, _, identity = reconciliation
    original = service.reconciliation._write
    failed = False

    def fail(db, identity, job):
        nonlocal failed
        if job["pages"] == 1 and not failed:
            failed = True
            raise RuntimeError("Simulated checkpoint commit failure")
        original(db, identity, job)

    monkeypatch.setattr(service.reconciliation, "_write", fail)
    detail = service.reconciliation.sync(identity, manual=True)
    assert not detail["fills"] and detail["reconciliation"]["sync"]["pages"] == 0
    with service.store.db() as db:
        assert service.reconciliation._read(db, identity)["cursor"] == {}


def test_totals_include_retained_rows_beyond_display_page(reconciliation):
    service, _, connection, identity = reconciliation
    metadata = {
        "account_id": connection.id,
        "account": connection.label,
        "exchange": "binance",
        "environment": "test",
        "symbol": "BTC/USDT",
    }
    fills = [ledger_fill(execution(str(i), 0.00004), metadata) for i in range(250)]
    with service.store.db() as db:
        AccountLedger.upsert_fills(db, fills, now_iso())
    detail = service.reconciliation.detail(identity)
    assert detail["has_more"] and len(detail["fills"]) == 200
    assert detail["reconciliation"]["fill_count"] == 250
    assert detail["reconciliation"]["quantity"] == 0.01


class FillTransport:
    """Native cursor transport without credentials or SDK automatic pagination."""

    def __init__(self, rows):
        self.rows, self.calls, self.last_response_headers = rows, [], {}

    def market(self, symbol):
        return {"id": "BTCUSDT"}

    def parse_trades(self, rows, market):
        return rows

    def fetch_my_trades(self, symbol, limit, params):
        self.calls.append(params)
        return self.rows

    def v3PrivateGetBrokerageOrdersHistoricalFills(self, params):
        self.calls.append(params)
        return {"fills": self.rows, "cursor": "next-token"}

    def privateGetFills(self, params):
        self.calls.append(params)
        self.last_response_headers = {"CB-AFTER": "next-token"}
        return self.rows

    def privatePostQueryOrders(self, params):
        self.calls.append(params)
        return {"result": {"native-123": {"trades": [str(i) for i in range(25)]}}}

    def privatePostQueryTrades(self, params):
        self.calls.append(params)
        return {"result": {value: execution(value) for value in params["txid"].split(",")}}


@pytest.mark.parametrize("kind", ["binance-id", "coinbase-cursor", "coinbase-exchange-cursor"])
def test_native_order_filter_and_provider_cursor(kind):
    transport = FillTransport([execution()])
    page = fetch_order_fill_page(transport, kind, "native-123", "BTC/USDT", {}, 100)
    assert page.items[0]["order"] == "native-123"
    params = transport.calls[0]
    if kind == "binance-id":
        assert params == {"orderId": "native-123", "fromId": "0"}
        assert page.cursor == {"from_id": "2"}
    else:
        assert params.get("order_ids", params.get("order_id")) in (["native-123"], "native-123")
        assert page.cursor == {"page": "next-token"}
    assert not page.caught_up


def test_kraken_snapshots_ids_and_reads_bounded_batches():
    transport = FillTransport([])
    first = fetch_order_fill_page(transport, "kraken-cursor", "native-123", "BTC/USDT", {}, 100)
    second = fetch_order_fill_page(transport, "kraken-cursor", "native-123", "BTC/USDT", first.cursor, 100)
    assert len(first.items) == 20 and len(second.items) == 5
    assert second.caught_up and len(transport.calls) == 3
    assert transport.calls[0]["consolidate_taker"] is False


def test_demo_http_reconciliation_and_examples_are_isolated(client):
    service = client.app.state.services
    before = (service.store.orders(), service.account_sync.ledger.fills()["total"])
    example = client.get("/api/v1/exchange-orders/example").json()[0]
    detail = client.get(f"/api/v1/exchange-orders/example/{example['id']}/reconciliation")
    assert detail.status_code == 200 and detail.json()["reconciliation"]["status"] == "fees_missing"
    assert (service.store.orders(), service.account_sync.ledger.fills()["total"]) == before
    preview = client.post(
        "/api/v1/exchange-orders/preview",
        json={
            "connection_id": "demo",
            "symbol": "BTC/USDT",
            "side": "buy",
            "quantity": 0.001,
            "order_type": "limit",
            "limit_price": 100000,
            "idempotency_key": "reconcile-demo-limit",
        },
    ).json()
    identity = preview["id"]
    assert (
        client.post(
            f"/api/v1/exchange-orders/{identity}/confirm", json={"confirmation": preview["confirmation"]}
        ).status_code
        == 200
    )
    checked = client.post(f"/api/v1/exchange-orders/{identity}/reconcile").json()
    assert checked["reconciliation"]["status"] == "matched"
    assert checked["fills"][0]["quantity"] == 0.001
    assert (
        client.get(f"/api/v1/exchange-orders/{identity}/reconciliation").headers["cache-control"]
        == "no-store"
    )
    assert (
        client.post(f"/api/v1/exchange-orders/{identity}/reconcile/tracking", json={"enabled": False}).json()[
            "reconciliation"
        ]["sync"]["enabled"]
        is False
    )
