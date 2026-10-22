"""Account discovery contracts use isolated wallets and fake native read transports."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import ccxt
import pytest
from pydantic import ValidationError
from test_order_management import setup as setup
from test_order_management import submit

from sibyl.exchanges.demo import DemoClient
from sibyl.exchanges.history import TradePage
from sibyl.exchanges.order_discovery import DAY_MS, OrderDiscoveryPage, discovery_page
from sibyl.market_data.control import ProviderDeferred
from sibyl.models import ConnectionCreate, OrderRequest
from sibyl.services.ledger import AccountLedger
from sibyl.services.market import Market
from sibyl.services.order_discovery import OrderDiscoveryRequest, normalized_order
from sibyl.services.trading import ExchangeTrading


def order(identity="outside-1", **changes):
    return {
        "id": identity,
        "clientOrderId": "external-client",
        "symbol": "BTC/USDT",
        "side": "buy",
        "type": "limit",
        "status": "open",
        "amount": 0.01,
        "price": 50000,
        "filled": 0.004,
        "remaining": 0.006,
        "average": 50000,
        "cost": 200,
        "timestamp": int(time.time() * 1000),
        "timeInForce": "GTC",
        **changes,
    }


@pytest.fixture
def discovery(setup):
    service, venue, connection = setup
    venue.discovery_reads = []
    venue.page = OrderDiscoveryPage([order()], {}, True)

    def read(*args):
        venue.discovery_reads.append(args)
        if isinstance(venue.page, Exception):
            raise venue.page
        return venue.page

    venue.fetch_account_order_page = read
    service.discovery.enqueue(OrderDiscoveryRequest(account_id=connection.id, symbols=["BTC/USDT"]))
    return service, venue, connection


def job(service, account):
    with service.store.db() as db:
        return service.discovery.read(db, getattr(account, "id", account))


def advance(service, account):
    with service.store.db() as db:
        current = service.discovery.read(db, getattr(account, "id", account))
        current["next_attempt"] = 0
        service.discovery.write(db, current)
    service.discovery.tick()


def test_import_native_identity_is_read_only_and_not_an_executable_intent(discovery):
    service, venue, connection = discovery
    advance(service, connection)
    imported = service.monitor()["items"][0]
    assert imported["origin"] == "imported" and imported["read_only"]
    assert imported["request"]["quantity"] == 0.01
    assert imported["filled"] == 0.004 and imported["reconciliation"]["status"] == "missing_fills"
    assert service.list_orders() == []  # Existing submission/report contract remains local-only.
    with pytest.raises(ValueError, match="read-only"):
        service.execute(imported["id"], "BUY BTC")
    with pytest.raises(ValueError, match="read-only"):
        service.lifecycle.preview_cancel(imported["id"])
    assert venue.calls == venue.cancels == 0
    assert job(service, connection)["stream"] == "recent"


def test_native_identity_and_history_fill_id_are_shared_without_duplicates(discovery):
    service, venue, connection = discovery
    advance(service, connection)
    identity = service.monitor()["items"][0]["id"]
    venue.fetch_order_fill_page = lambda *args: TradePage(
        [
            {
                "id": "fill-1",
                "order": "outside-1",
                "symbol": "BTC/USDT",
                "side": "buy",
                "amount": 0.004,
                "price": 50000,
                "cost": 200,
                "timestamp": int(time.time() * 1000),
                "fees": [{"currency": "USDT", "cost": 0.2}],
            }
        ],
        {},
        True,
    )
    first = service.reconciliation.sync(identity, manual=True)
    advance(service, connection)
    service.reconciliation.sync(identity, manual=True)
    assert service.monitor()["total"] == 1
    assert AccountLedger(service.store, recover=False).fills(account_id=connection.id)["total"] == 1
    assert first["reconciliation"]["fill_count"] == 1
    assert job(service, connection)["complete"]
    assert venue.calls == 0


def test_existing_sibyl_order_is_updated_in_place(discovery):
    service, venue, connection = discovery
    intent = submit(service, connection)
    venue.page = OrderDiscoveryPage([order("native-123")], {}, True)
    advance(service, connection)
    rows = service.monitor()["items"]
    assert len(rows) == 1 and rows[0]["id"] == intent["id"]
    assert rows[0].get("origin", "sibyl") == "sibyl"
    assert rows[0]["filled"] == 0.004 and job(service, connection)["linked"] == 1


def test_matching_uncertain_client_id_does_not_bypass_reviewed_recovery(discovery):
    service, venue, connection = discovery
    venue.failure = ccxt.RequestTimeout("secret")
    intent = submit(service, connection)
    venue.page = OrderDiscoveryPage([order(clientOrderId=intent["client_order_id"])], {}, True)
    advance(service, connection)
    assert service.monitor()["total"] == 1
    assert service.monitor()["items"][0]["status"] == "unknown"
    assert job(service, connection)["deferred"] == 1
    assert venue.calls == 1


def test_incomplete_pagination_and_cursor_survive_restart(discovery):
    service, venue, connection = discovery
    venue.page = OrderDiscoveryPage([order()], {"opaque": "private-cursor"}, False)
    advance(service, connection)
    restarted = ExchangeTrading(service.market, service.store)
    venue.page = OrderDiscoveryPage([order("outside-2")], {}, True)
    advance(restarted, connection)
    assert venue.discovery_reads[-1][1] == {"opaque": "private-cursor"}
    assert restarted.monitor()["total"] == 2
    assert "private-cursor" not in json.dumps(restarted.discovery.snapshot())


def test_interrupted_running_job_is_queued_on_restart(discovery):
    service, _, connection = discovery
    with service.store.db() as db:
        current = service.discovery.read(db, connection.id)
        current.update(state="running", cursor={"offset": 50}, pages=1)
        service.discovery.write(db, current)
    restarted = ExchangeTrading(service.market, service.store)
    assert job(restarted, connection)["state"] == "queued"
    assert job(restarted, connection)["cursor"] == {"offset": 50}


def test_pausing_during_a_page_preserves_pause_and_atomic_checkpoint(discovery):
    service, venue, connection = discovery

    def pause_and_read(*args):
        service.discovery.pause(connection.id)
        return OrderDiscoveryPage([order()], {"after": "next"}, False)

    venue.fetch_account_order_page = pause_and_read
    advance(service, connection)
    current = job(service, connection)
    assert current["state"] == "paused" and not current["enabled"]
    assert current["cursor"] == {"after": "next"}
    assert service.monitor()["total"] == 1


def test_new_settings_discard_an_old_in_flight_page(discovery):
    service, venue, connection = discovery

    def replace_and_read(*args):
        service.discovery.enqueue(OrderDiscoveryRequest(account_id=connection.id, days=3))
        return OrderDiscoveryPage([order()], {"after": "old"}, False)

    venue.fetch_account_order_page = replace_and_read
    advance(service, connection)
    assert service.monitor()["total"] == 0
    assert job(service, connection)["days"] == 3 and job(service, connection)["cursor"] == {}


@pytest.mark.parametrize(
    "bad",
    [
        {"id": ""},
        {"amount": float("nan")},
        {"filled": 2},
        {"side": "hidden"},
        {"symbol": "BTC/USDT:USDT"},
        {"clientOrderId": "secret\nvalue"},
        {"cost": -1},
        {"timestamp": time.time() * 1000 + DAY_MS},
    ],
)
def test_invalid_page_rolls_back_all_orders_and_checkpoint(discovery, bad):
    service, venue, connection = discovery
    venue.page = OrderDiscoveryPage([order(), order("outside-2", **bad)], {"next": "invalid"}, False)
    advance(service, connection)
    assert service.monitor()["total"] == 0
    current = job(service, connection)
    assert current["cursor"] == {} and current["pages"] == 0 and current["state"] == "error"


def test_transaction_failure_rolls_back_order_and_checkpoint(discovery, monkeypatch):
    service, _, connection = discovery
    original = service.discovery._upsert

    def fail(db, account, row):
        original(db, account, row)
        raise ValueError("invalid evidence")

    monkeypatch.setattr(service.discovery, "_upsert", fail)
    advance(service, connection)
    assert service.monitor()["total"] == 0 and job(service, connection)["pages"] == 0


def test_duplicate_checks_cannot_create_duplicate_order_rows(discovery):
    service, _, connection = discovery
    with ThreadPoolExecutor(3) as pool:
        list(pool.map(lambda _: service.discovery.tick(), range(3)))
    assert service.monitor()["total"] == 1
    assert job(service, connection)["pages"] == 1


def test_absence_never_infers_cancellation_and_pause_is_independent(discovery):
    service, venue, connection = discovery
    advance(service, connection)
    identity = service.monitor()["items"][0]["id"]
    service.lifecycle.track(identity, False)
    venue.page = OrderDiscoveryPage([], {}, True)
    advance(service, connection)
    retained = service.monitor()["items"][0]
    assert retained["status"] == "open" and not retained["tracking"]
    assert not service.reconciliation.detail(identity)["reconciliation"]["sync"]["enabled"]


def test_imported_refresh_is_read_only_and_accepts_external_amount_amendments(discovery):
    service, venue, connection = discovery
    advance(service, connection)
    identity = service.monitor()["items"][0]["id"]
    venue.fetch_order = lambda *args: order(amount=0.02, remaining=0.016)
    result = service.lifecycle.refresh(identity)
    assert result["request"]["quantity"] == 0.02
    assert venue.calls == venue.cancels == 0


def test_inactive_and_disconnected_accounts_do_not_read_providers(discovery):
    service, venue, connection = discovery
    service.store.activate_account(connection.id, False)
    advance(service, connection)
    assert not venue.discovery_reads and job(service, connection)["state"] == "waiting_account"
    service.store.delete_connection(connection.id)
    advance(service, connection)
    assert job(service, connection)["state"] == "disconnected" and not job(service, connection)["enabled"]


def test_bounded_failures_and_provider_deferral_are_sanitized(discovery):
    service, venue, connection = discovery
    venue.page = ProviderDeferred(7)
    advance(service, connection)
    assert job(service, connection)["failures"] == 0
    venue.page = ccxt.RequestTimeout("TOP-SECRET-provider-payload")
    for _ in range(5):
        advance(service, connection)
    current = job(service, connection)
    assert current["state"] == "error" and not current["enabled"]
    assert "TOP-SECRET" not in json.dumps(service.discovery.snapshot())


def test_cyclic_cursor_and_page_budgets_do_not_skip_evidence(discovery):
    service, venue, connection = discovery
    venue.page = OrderDiscoveryPage([order()], {"page": "a"}, False)
    advance(service, connection)
    advance(service, connection)
    assert job(service, connection)["state"] == "error"
    assert job(service, connection)["pages"] == 1
    with service.store.db() as db:
        current = service.discovery.read(db, connection.id)
        current.update(enabled=True, state="queued", pages=100)
        service.discovery.write(db, current)
    before = len(venue.discovery_reads)
    advance(service, connection)
    assert len(venue.discovery_reads) == before and job(service, connection)["state"] == "limited"


def test_unknown_quantities_and_conditional_order_types_remain_honest(discovery):
    service, venue, connection = discovery
    venue.page = OrderDiscoveryPage(
        [order(amount=None, filled=None, remaining=None, average=None, cost=None, type="stop-limit")],
        {},
        True,
    )
    advance(service, connection)
    imported = service.monitor()["items"][0]
    assert imported["request"]["quantity"] is None and imported["filled"] is None
    assert imported["request"]["order_type"] == "stop-limit"
    assert imported["notional"] is None and imported["reconciliation"]["status"] == "unverified"


def test_monitor_filters_before_pagination_and_scopes_native_ids_to_accounts(discovery):
    service, venue, connection = discovery
    venue.page = OrderDiscoveryPage([order(str(index)) for index in range(32)], {}, True)
    advance(service, connection)
    other = service.store.add_connection(
        ConnectionCreate(exchange="kraken", label="Other account", api_key="fake", secret="fake")
    )
    service.discovery.enqueue(OrderDiscoveryRequest(account_id=other.id))
    with service.store.db() as db:
        service.discovery._upsert(db, other, normalized_order(order("0")))
    result = service.monitor(
        account_id=connection.id, origin="imported", status="active", limit=10, offset=30
    )
    assert len(result["items"]) == 2 and result["total"] == 32 and not result["has_more"]
    assert service.monitor(exchange="kraken")["total"] == 1
    assert service.monitor(origin="sibyl")["total"] == 0


def test_demo_discovers_real_paper_orders_without_seeding_or_matching(settings, store):
    market = Market(settings, store)
    client = DemoClient(store)
    resting = client.create_order(
        "BTC/USDT", "limit", "buy", 0.01, {"clientOrderId": "outside-limit"}, price=50000
    )
    store.execute_paper(
        OrderRequest(symbol="ETH/USDT", side="buy", quantity=0.1, idempotency_key="outside-market"),
        3500,
        require_demo=True,
    )
    before = client.fetch_balance()
    service = ExchangeTrading(market, store)
    service.discovery.enqueue(OrderDiscoveryRequest(account_id="demo"))
    advance(service, "demo")
    advance(service, "demo")
    assert service.monitor()["total"] == 2
    imported = next(row for row in service.monitor()["items"] if row["exchange_order_id"] == resting["id"])
    refreshed = service.lifecycle.refresh(imported["id"])
    assert refreshed["time_in_force"] == "GTC" and refreshed["order_created_at"]
    assert client.fetch_balance() == before
    assert client.fetch_order(resting["id"], "BTC/USDT")["status"] == "open"
    assert len(store.orders()) == 1


def test_http_reads_are_local_filters_validate_and_examples_stay_isolated(client, monkeypatch):
    service = client.app.state.services.trading
    monkeypatch.setattr(service.discovery, "tick", lambda: None)
    assert client.get("/api/v1/exchange-orders/monitor").json()["total"] == 0
    assert client.get("/api/v1/exchange-orders/discovery").json()["jobs"] == []
    assert client.get("/api/v1/exchange-orders/monitor?origin=invalid").status_code == 422
    assert client.get("/api/v1/exchange-orders/monitor?limit=51").status_code == 422
    response = client.post("/api/v1/exchange-orders/discovery", json={"account_id": "demo"})
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    assert client.post("/api/v1/exchange-orders/discovery/demo/pause").status_code == 200
    assert client.get("/api/v1/exchange-orders/example").status_code == 200
    assert service.monitor()["total"] == 0 and service.store.orders() == []


def test_request_limits_are_explicit():
    for values in (
        {"days": 8},
        {"symbols": ["BTC/USDT:USDT"]},
        {"symbols": [f"COIN{i}/USD" for i in range(13)]},
    ):
        with pytest.raises(ValidationError):
            OrderDiscoveryRequest(**values)


class Native:
    """Capture one low-level request, returning already normalized rows to the contract reader."""

    def __init__(self, result):
        self.result, self.calls, self.last_response_headers = result, [], {}

    def __getattr__(self, name):
        def read(request):
            self.calls.append((name, request))
            return self.result

        return read

    def market(self, symbol):
        return {"id": symbol.replace("/", "")}

    def iso8601(self, value):
        return datetime.fromtimestamp(value / 1000, UTC).isoformat()

    def parse_order(self, row):
        return row


@pytest.mark.parametrize("provider", ["binance", "binanceus", "binance-testnet"])
def test_binance_reads_all_open_orders_and_selected_history_windows(provider):
    native = Native([order()])
    assert discovery_page(native, provider, "open", {}, DAY_MS, 3 * DAY_MS, []).complete
    assert native.calls[-1] == ("privateGetOpenOrders", {})
    page = discovery_page(native, provider, "recent", {}, DAY_MS, 3 * DAY_MS, ["BTC/USDT"])
    assert not page.complete and page.cursor["windows"] == [[2 * DAY_MS, 3 * DAY_MS]]
    request = native.calls[-1][1]
    assert request == {"symbol": "BTCUSDT", "startTime": DAY_MS, "endTime": 2 * DAY_MS - 1, "limit": 1000}
    assert "orderId" not in request
    assert discovery_page(native, provider, "recent", page.cursor, DAY_MS, 3 * DAY_MS, ["BTC/USDT"]).complete


def test_binance_splits_saturated_windows_without_losing_timestamp_ties():
    native = Native([order(str(index)) for index in range(1000)])
    page = discovery_page(native, "binance", "recent", {}, 10, 30, ["BTC/USDT"])
    assert page.items == [] and page.cursor["windows"] == [[10, 20], [20, 30]]
    with pytest.raises(ccxt.NotSupported):
        discovery_page(native, "binance", "recent", {}, 10, 11, ["BTC/USDT"])


def test_coinbase_advances_native_cursor_with_explicit_spot_and_open_statuses():
    native = Native({"orders": [order()], "has_next": True, "cursor": "native-next"})
    page = discovery_page(native, "coinbase", "open", {}, DAY_MS, 2 * DAY_MS, [])
    assert page.cursor == {"page": "native-next"} and not page.complete
    request = native.calls[-1][1]
    assert request["product_type"] == "SPOT" and "EDIT_QUEUED" in request["order_status"]
    assert "start_date" not in request and request["order_placement_source"] == "RETAIL_ADVANCED"
    discovery_page(native, "coinbase", "recent", page.cursor, DAY_MS, 2 * DAY_MS, [])
    assert native.calls[-1][1]["cursor"] == "native-next" and "start_date" in native.calls[-1][1]


@pytest.mark.parametrize(
    "result",
    [
        {"orders": [], "has_next": "false"},
        {"orders": [], "has_next": True},
        {"orders": [], "proof_token_required": True},
    ],
)
def test_coinbase_rejects_ambiguous_pagination_and_additional_verification(result):
    with pytest.raises(ccxt.BaseError):
        discovery_page(Native(result), "coinbase", "open", {}, DAY_MS, 2 * DAY_MS, [])


def test_sandbox_uses_response_header_cursor_and_keeps_environment_native():
    native = Native([order()])
    native.last_response_headers = {"CB-AFTER": "sandbox-next"}
    page = discovery_page(native, "coinbase-sandbox", "open", {}, DAY_MS, 2 * DAY_MS, [])
    assert not page.complete and native.calls[-1] == ("privateGetOrders", {"limit": 100})
    discovery_page(native, "coinbase-sandbox", "recent", page.cursor, DAY_MS, 2 * DAY_MS, [])
    assert native.calls[-1][1]["after"] == "sandbox-next" and native.calls[-1][1]["status"] == "all"


def test_kraken_counts_margin_exclusions_and_paginates_closed_at_time():
    native = Native(
        {
            "result": {
                "open": {"spot": {"descr": {"leverage": "none"}}, "margin": {"descr": {"leverage": "2:1"}}}
            }
        }
    )
    page = discovery_page(native, "kraken", "open", {}, DAY_MS, 2 * DAY_MS, [])
    assert len(page.items) == 1 and page.skipped == 1 and page.complete
    native.result = {"result": {"closed": {"closed-1": {"descr": {"leverage": "none"}}}, "count": 2}}
    page = discovery_page(native, "kraken", "recent", {}, DAY_MS, 2 * DAY_MS, [])
    assert not page.complete and page.cursor == {"offset": 1}
    assert native.calls[-1][1]["closetime"] == "close" and native.calls[-1][1]["ofs"] == 0


def test_provider_normalization_strips_private_fields_and_counts_unsupported_markets(monkeypatch):
    from test_exchange_clients import fake_client

    adapter = fake_client(monkeypatch, "coinbase")
    native = adapter._exchange
    native.v3PrivateGetBrokerageOrdersHistoricalBatch = lambda request: {
        "orders": [order(info="PRIVATE-SENTINEL"), order("old", symbol="OLD/USDT")],
        "has_next": False,
        "cursor": "",
    }
    native.parse_order = lambda row: row
    native.iso8601 = ccxt.Exchange.iso8601
    page = adapter.fetch_account_order_page("recent", {}, DAY_MS, 2 * DAY_MS, ["ETH/USD"])
    assert page.skipped == 1 and len(page.items) == 1
    assert "PRIVATE-SENTINEL" not in json.dumps(page.items)
    # Binance-only history pairs must not be validated against another venue's catalog.
    assert page.items[0]["symbol"] == "BTC/USDT"


def test_binance_missing_historical_cost_and_empty_terminal_sandbox_cursor():
    native = Native([order(cummulativeQuoteQty="-1", cost=-1, average=50000)])
    page = discovery_page(native, "binance", "recent", {}, DAY_MS, 2 * DAY_MS, ["BTC/USDT"])
    assert page.items[0]["cost"] is None and page.items[0]["average"] is None
    native.result = []
    native.last_response_headers = {"cb-after": "terminal-token"}
    assert discovery_page(native, "coinbase-sandbox", "recent", {}, DAY_MS, 2 * DAY_MS, []).complete


def test_completed_discovery_pass_waits_and_refreshes_its_window(discovery):
    service, venue, connection = discovery
    advance(service, connection)
    advance(service, connection)
    current = job(service, connection)
    assert current["complete"] and current["next_attempt"] > time.time() + 250
    previous_reads = len(venue.discovery_reads)
    service.discovery.tick()
    assert len(venue.discovery_reads) == previous_reads
    advance(service, connection)
    assert venue.discovery_reads[-1][0] == "open"
    assert job(service, connection)["pages"] == 1 and not job(service, connection)["complete"]


def test_native_id_side_conflict_and_regressed_fills_never_replace_retained_evidence(discovery):
    service, venue, connection = discovery
    advance(service, connection)
    for changes in ({"side": "sell"}, {"filled": 0.001}):
        service.discovery.enqueue(OrderDiscoveryRequest(account_id=connection.id, symbols=["BTC/USDT"]))
        venue.page = OrderDiscoveryPage([order(**changes)], {}, True)
        advance(service, connection)
        retained = service.monitor()["items"][0]
        assert retained["request"]["side"] == "buy" and retained["filled"] == 0.004
        assert job(service, connection)["state"] == "error"


def test_imported_order_reads_still_work_with_native_execution_disabled(discovery):
    service, venue, connection = discovery
    service.market.settings.allow_live_trading = False
    advance(service, connection)
    identity = service.monitor()["items"][0]["id"]
    venue.fetch_order = lambda *args: order()
    service.lifecycle.refresh(identity)
    assert venue.calls == venue.cancels == 0


def test_missing_credentials_and_budget_overflow_preserve_records(discovery):
    service, venue, connection = discovery
    venue.page = ccxt.AuthenticationError("TOP-SECRET")
    advance(service, connection)
    assert "read permissions" in job(service, connection)["error"]
    assert "TOP-SECRET" not in json.dumps(service.discovery.snapshot())
    service.discovery.enqueue(OrderDiscoveryRequest(account_id=connection.id, symbols=["BTC/USDT"]))
    with service.store.db() as db:
        current = service.discovery.read(db, connection.id)
        current["records"] = 9999
        service.discovery.write(db, current)
    venue.page = OrderDiscoveryPage([order(), order("other")], {}, True)
    advance(service, connection)
    assert service.monitor()["total"] == 0 and job(service, connection)["state"] == "limited"


def test_http_rejects_imported_submission_and_cancellation(client):
    service = client.app.state.services.trading
    connection = service.store.connections()[0]
    with service.store.db() as db:
        service.discovery._upsert(db, connection, normalized_order(order()))
    identity = service.monitor()["items"][0]["id"]
    response = client.post(f"/api/v1/exchange-orders/{identity}/confirm", json={"confirmation": "BUY BTC"})
    assert response.status_code == 400 and "read-only" in response.json()["detail"]
    assert client.post(f"/api/v1/exchange-orders/{identity}/cancel/preview").status_code == 400


def test_no_active_account_is_enabled_implicitly(discovery):
    service, venue, connection = discovery
    service.store.activate_account(connection.id, False)
    with pytest.raises(ValueError, match="active"):
        service.discovery.enqueue(OrderDiscoveryRequest())
    assert not any(account.active for account in service.store.connections())
    assert not venue.discovery_reads
