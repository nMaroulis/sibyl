"""Read-only identity recovery uses controlled venues and temporary ledgers, never native writes."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import ccxt
import pytest
from test_order_management import save, submit
from test_order_management import setup as setup

from sibyl.exchanges.order_lookup import OrderLookupPage, lookup_order_page
from sibyl.market_data.control import ProviderDeferred
from sibyl.services.trading import ExchangeTrading


@pytest.fixture
def recovery(setup):
    service, venue, connection = setup
    venue.lookup_reads = 0
    venue.lookup_pages = lambda client_id, cursor: OrderLookupPage(
        [
            {
                "id": "native-123",
                "clientOrderId": client_id,
                "symbol": "BTC/USDT",
                "type": "limit",
                "side": "buy",
                "amount": 0.01,
                "price": 50000,
                "timestamp": datetime.now(UTC).timestamp() * 1000,
                "status": "open",
                "filled": 0,
                "remaining": 0.01,
            }
        ],
        {},
        True,
    )

    def lookup(client_id, symbol, cursor, start, end):
        assert symbol == "BTC/USDT" and start < end
        venue.lookup_reads += 1
        return venue.lookup_pages(client_id, cursor)

    venue.fetch_order_lookup_page = lookup
    venue.failure = ccxt.RequestTimeout("PRIVATE-SUBMISSION-SENTINEL")
    intent = submit(service, connection)
    venue.failure = None
    assert intent["status"] == "unknown" and not intent.get("exchange_order_id")
    return service, venue, connection, intent["id"]


def force_due(service, identity):
    intent = service.reconciliation.detail(identity)["order"]
    intent["next_check"] = 0
    save(service, intent)


def test_exact_recovery_rejoins_tracking_without_resubmission(recovery):
    service, venue, _, identity = recovery
    service.market.settings.allow_live_trading = False
    result = service.recover(identity)
    assert result["exchange_order_id"] == "native-123" and result["status"] == "open"
    assert result["recovery"]["state"] == "found" and not result["recovery"]["eligible"]
    assert venue.calls == 1 and venue.lookup_reads == 1 and venue.cancels == 0
    assert service.execute(identity, result["confirmation"])["exchange_order_id"] == "native-123"
    assert venue.calls == 1
    assert "cursor" not in json.dumps(result["recovery"])


def test_restart_recovers_submitting_and_keeps_one_native_submission(recovery):
    service, venue, _, identity = recovery
    intent = service.reconciliation.detail(identity)["order"]
    intent.update(status="submitting", next_check=0)
    save(service, intent)
    restarted = ExchangeTrading(service.market, service.store)
    restarted.lifecycle.tick()
    order = restarted.list_orders()[0]
    assert order["status"] == "open" and order["exchange_order_id"] == "native-123"
    assert order["recovery"]["state"] == "found"
    assert venue.calls == 1 and venue.lookup_reads == 1


def test_history_pages_wait_for_exhaustion_and_survive_restart(recovery):
    service, venue, _, identity = recovery
    original = venue.lookup_pages
    venue.lookup_pages = lambda client_id, cursor: (
        OrderLookupPage(original(client_id, {}).candidates, {"page": "PRIVATE-CURSOR"}, False)
        if not cursor
        else OrderLookupPage([], {}, True)
    )
    first = service.recover(identity)
    assert first["recovery"]["state"] == "searching" and not first.get("exchange_order_id")
    assert "PRIVATE-CURSOR" not in json.dumps(first)
    restarted = ExchangeTrading(service.market, service.store)
    result = restarted.recover(identity)
    assert result["exchange_order_id"] == "native-123" and venue.lookup_reads == 2
    assert venue.calls == 1


def test_empty_lookup_never_means_rejection_or_permission_to_resubmit(recovery):
    service, venue, _, identity = recovery
    venue.lookup_pages = lambda client_id, cursor: OrderLookupPage([], {}, True)
    for _ in range(3):
        force_due(service, identity)
        service.lifecycle.tick()
    order = service.list_orders()[0]
    assert order["status"] == "unknown" and not order.get("exchange_order_id")
    assert not order["tracking"] and order["recovery"]["passes"] == 3
    assert "does not prove" in order["recovery"]["message"]
    assert venue.lookup_reads == 3 and venue.calls == 1
    service.lifecycle.track(identity, True)
    assert service.list_orders()[0]["recovery"]["passes"] == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"clientOrderId": "other"},
        {"symbol": "ETH/USDT"},
        {"side": "sell"},
        {"type": "market"},
        {"amount": 0.02},
        {"price": 49999},
        {"timeInForce": "IOC"},
        {"timestamp": None},
        {"timestamp": 1},
        {"id": "bad\nidentity"},
        {"filled": 0.5},
    ],
)
def test_mismatched_or_invalid_evidence_never_attaches_an_id(recovery, changes):
    service, venue, _, identity = recovery
    original = venue.lookup_pages
    venue.lookup_pages = lambda client_id, cursor: OrderLookupPage(
        [{**original(client_id, cursor).candidates[0], **changes}], {}, True
    )
    result = service.recover(identity)
    assert not result.get("exchange_order_id") and result["status"] == "unknown"
    assert result["recovery"]["state"] == "mismatch" and not result["tracking"]
    assert venue.calls == 1


def test_multiple_native_ids_are_ambiguous_even_with_exact_client_id(recovery):
    service, venue, _, identity = recovery
    original = venue.lookup_pages
    venue.lookup_pages = lambda client_id, cursor: OrderLookupPage(
        [
            original(client_id, cursor).candidates[0],
            {**original(client_id, cursor).candidates[0], "id": "another-native"},
        ],
        {},
        True,
    )
    result = service.recover(identity)
    assert result["recovery"]["state"] == "ambiguous" and not result.get("exchange_order_id")


@pytest.mark.parametrize("complete", ["false", 1, None])
def test_malformed_completion_flag_does_not_adopt_early(recovery, complete):
    service, venue, _, identity = recovery
    original = venue.lookup_pages
    venue.lookup_pages = lambda client_id, cursor: OrderLookupPage(
        original(client_id, cursor).candidates, {}, complete
    )
    result = service.recover(identity)
    assert not result.get("exchange_order_id") and result["recovery"]["state"] == "mismatch"


def test_existing_native_attribution_cannot_be_stolen(recovery):
    service, venue, _, identity = recovery
    other = service.reconciliation.detail(identity)["order"]
    other.update(id="different-intent", exchange_order_id="native-123", status="open")
    with service.store.db() as db:
        db.execute(
            "INSERT INTO exchange_orders VALUES(?,?,?)",
            (other["id"], "different-request-key", json.dumps(other)),
        )
    result = service.recover(identity)
    assert not result.get("exchange_order_id") and result["recovery"]["state"] == "mismatch"
    assert service.reconciliation.detail("different-intent")["order"]["exchange_order_id"] == "native-123"


def test_adopted_id_and_found_state_roll_back_together(recovery, monkeypatch):
    service, _, _, identity = recovery
    original = service.lifecycle.write
    failed = False

    def fail(db, intent):
        nonlocal failed
        if intent.get("exchange_order_id") and not failed:
            failed = True
            raise RuntimeError("Simulated transaction failure")
        original(db, intent)

    monkeypatch.setattr(service.lifecycle, "write", fail)
    result = service.recover(identity)
    assert not result.get("exchange_order_id") and result["status"] == "unknown"
    assert result["recovery"]["state"] == "error"


def test_concurrent_checks_adopt_one_identity_once(recovery):
    service, venue, _, identity = recovery
    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(lambda _: service.recovery.check(identity, manual=True), range(6)))
    assert {row["exchange_order_id"] for row in results} == {"native-123"}
    assert venue.lookup_reads == 1 and venue.calls == 1


def test_background_waits_for_account_manual_recovery_respects_pause(recovery):
    service, venue, connection, identity = recovery
    service.store.activate_account(connection.id, False)
    service.lifecycle.tick()
    assert venue.lookup_reads == 0
    service.lifecycle.track(identity, False)
    result = service.recover(identity)
    assert result["exchange_order_id"] == "native-123" and not result["tracking"]
    assert result["reconciliation"]["sync"]["enabled"] is False


def test_provider_deferral_preserves_cursor_and_failure_budget(recovery):
    service, venue, _, identity = recovery

    def deferred(client_id, cursor):
        raise ProviderDeferred(60)

    venue.lookup_pages = deferred
    service.recovery.check(identity)
    with service.store.db() as db:
        job = service.recovery.read(db, identity)
    assert job["failures"] == 0 and job["cursor"] == {} and job["pages"] == 0


def test_native_errors_are_sanitized_and_eventually_pause(recovery):
    service, venue, _, identity = recovery

    def fail(client_id, cursor):
        raise ccxt.AuthenticationError("PRIVATE-CREDENTIAL-SENTINEL")

    venue.lookup_pages = fail
    for _ in range(5):
        force_due(service, identity)
        service.lifecycle.tick()
    result = service.list_orders()[0]
    assert result["recovery"]["state"] == "error" and not result["tracking"]
    with service.store.db() as db:
        assert (
            "PRIVATE-CREDENTIAL-SENTINEL"
            not in db.execute("SELECT payload FROM order_recovery").fetchone()[0]
        )


def test_scans_are_bounded_and_repeated_cursors_do_not_adopt(recovery):
    service, venue, _, identity = recovery
    venue.lookup_pages = lambda client_id, cursor: OrderLookupPage(
        [], {"page": cursor.get("page", 0) + 1}, False
    )
    for _ in range(10):
        service.recover(identity)
    result = service.list_orders()[0]
    assert result["recovery"]["state"] == "incomplete" and not result.get("exchange_order_id")
    assert venue.lookup_reads == 10 and not result["tracking"]


class LookupTransport:
    """Native request contracts and parse boundaries without HTTP or exchange credentials."""

    def __init__(self):
        self.calls = []
        self.more = False

    def market(self, symbol):
        return {"id": "BTC-USDT"}

    def iso8601(self, stamp):
        return f"iso-{stamp}"

    def fetch_order(self, identity, symbol, params):
        self.calls.append(params)
        return {"id": "native-1", "clientOrderId": "client-1"}

    def parse_order(self, row):
        return {
            "id": row.get("id", "native-1"),
            "clientOrderId": row.get("client_order_id", row.get("cl_ord_id")),
        }

    def v3PrivateGetBrokerageOrdersHistoricalBatch(self, params):
        self.calls.append(params)
        return {
            "orders": [{"client_order_id": "other"}, {"client_order_id": "client-1"}],
            "cursor": "next" if self.more else "",
            "has_next": self.more,
        }

    def privatePostOpenOrders(self, params):
        self.calls.append(params)
        return {"result": {"open": {"native-1": {"cl_ord_id": "client-1"}}}}

    def privatePostClosedOrders(self, params):
        self.calls.append(params)
        return {"result": {"closed": {}, "count": 0}}


@pytest.mark.parametrize(
    "provider,param",
    [
        ("binance", "origClientOrderId"),
        ("binance-testnet", "origClientOrderId"),
        ("binanceus", "origClientOrderId"),
        ("coinbase-sandbox", "clientOrderId"),
    ],
)
def test_direct_provider_lookup_only_passes_client_id(provider, param):
    transport = LookupTransport()
    page = lookup_order_page(transport, provider, "client-1", "BTC/USDT", {}, 1000, 2000)
    assert transport.calls == [{param: "client-1"}]
    assert page.complete and len(page.candidates) == 1


def test_coinbase_advanced_exact_product_window_and_client_filter():
    transport = LookupTransport()
    transport.more = True
    page = lookup_order_page(transport, "coinbase", "client-1", "BTC/USDT", {}, 1000, 2000)
    assert len(page.candidates) == 1 and not page.complete
    assert transport.calls[0] == {
        "product_ids": ["BTC-USDT"],
        "product_type": "SPOT",
        "limit": 100,
        "start_date": "iso-1000",
        "end_date": "iso-2000",
    }
    assert page.cursor == {"page": "next"}


def test_kraken_open_then_closed_uses_client_id_and_opening_window():
    transport = LookupTransport()
    first = lookup_order_page(transport, "kraken", "client-1", "BTC/USDT", {}, 1000, 2000)
    final = lookup_order_page(transport, "kraken", "client-1", "BTC/USDT", first.cursor, 1000, 2000)
    assert not first.complete and final.complete
    assert transport.calls[0] == {"cl_ord_id": "client-1", "trades": False}
    assert transport.calls[1] == {
        "cl_ord_id": "client-1",
        "trades": False,
        "start": 1,
        "end": 2,
        "closetime": "open",
        "ofs": 0,
    }


def test_http_refuses_preview_recovery_and_keeps_examples_isolated(client):
    service = client.app.state.services.trading
    service.lifecycle.close()
    from test_order_management import request

    preview = service.preview(request(limit_price=100))
    response = client.post(f"/api/v1/exchange-orders/{preview['id']}/recover")
    assert response.status_code == 400
    sample = client.get("/api/v1/exchange-orders/example").json()[-1]
    assert sample["recovery"]["eligible"] and sample["status"] == "unknown"
    assert not sample.get("exchange_order_id")
    assert len(service.list_orders()) == 1 and service.store.orders() == []
