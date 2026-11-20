"""Read-only identity recovery uses controlled venues and temporary ledgers, never native writes."""

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import ccxt
import pytest
from test_order_discovery import bybit_order, okx_order, spot_market
from test_order_management import save, submit
from test_order_management import setup as setup

from sibyl.exchanges.history import TradePage
from sibyl.exchanges.order_lookup import OrderLookupPage, lookup_order_page
from sibyl.market_data.control import ProviderDeferred
from sibyl.models import ConnectionCreate
from sibyl.services.trading.service import ExchangeTrading


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


@pytest.mark.parametrize(
    "changes",
    [
        {"clOrdId": "different"},
        {"instId": "ETH-USDT"},
        {"instType": "MARGIN", "tdMode": "cross"},
        {"tdMode": "cross"},
        {"ordType": "post_only"},
        {"ordType": "market", "tgtCcy": "quote_ccy"},
        {"ordType": "market", "tgtCcy": ""},
        {"algoId": "123"},
        {"attachAlgoOrds": [{"attachAlgoId": "123"}]},
        {"state": "effective"},
    ],
)
def test_okx_lookup_rejects_mismatched_native_evidence(monkeypatch, changes):
    native = LookupTransport()
    row = okx_order(2**60, **({"clOrdId": "client1"} | changes))
    monkeypatch.setattr(native, "privateGetTradeOrder", lambda _: {"code": "0", "data": [row]}, raising=False)
    with pytest.raises(ValueError, match="OKX"):
        lookup_order_page(native, "okx", "client1", "BTC/USDT", {}, 1000, 2000)


def test_okx_lookup_rejects_unexpected_multiple_results_and_malformed_client_ids(monkeypatch):
    native = LookupTransport()
    rows = [okx_order(identity, clOrdId="client1") for identity in (91, 92)]
    monkeypatch.setattr(native, "privateGetTradeOrder", lambda _: {"code": "0", "data": rows}, raising=False)
    with pytest.raises(ccxt.ExchangeError, match="Invalid OKX order details response"):
        lookup_order_page(native, "okx", "client1", "BTC/USDT", {}, 1000, 2000)
    with pytest.raises(ValueError, match="client order ID"):
        lookup_order_page(native, "okx", "client/1", "BTC/USDT", {}, 1000, 2000)


@pytest.mark.parametrize("order_type", ["limit", "market"])
def test_okx_lost_ack_recovers_native_identity_without_resending(manual_client, monkeypatch, order_type):
    owner = manual_client.app.state.services
    owner.settings.allow_live_trading = True
    account = owner.store.add_connection(
        ConnectionCreate(
            exchange="okx", label="Isolated OKX recovery", api_key="fake", secret="fake", passphrase="fake"
        )
    )
    adapter = owner.market.client(account)
    native = adapter._exchange
    native.set_markets(
        [
            {
                "id": "BTC-USDT",
                "symbol": "BTC/USDT",
                "base": "BTC",
                "quote": "USDT",
                "baseId": "BTC",
                "quoteId": "USDT",
                "type": "spot",
                "spot": True,
                "contract": False,
                "active": True,
                "precision": {"amount": 0.00000001, "price": 0.01},
            }
        ]
    )
    native_id = str(2**60 + 3)
    writes, reads, rows = [], [], []
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 10_000}})
    monkeypatch.setattr(adapter, "fetch_ticker", lambda symbol: {"ask": 50_000, "bid": 49_999})

    def lost_ack(symbol, kind, side, amount, price=None, *, params):
        writes.append(params["clientOrderId"])
        assert (symbol, kind, side, amount) == ("BTC/USDT", order_type, "buy", 0.01)
        if kind == "market":
            assert params.get("tdMode") == "cash" and params.get("tgtCcy") == "base_ccy"
        rows.append(
            okx_order(
                native_id,
                clOrdId=params["clientOrderId"],
                ordType=kind,
                cTime=str(int(time.time() * 1000)),
                tgtCcy="base_ccy" if kind == "market" else "",
                state="filled" if kind == "market" else "live",
                accFillSz="0.01" if kind == "market" else "0",
                px=str(price) if price is not None else "",
                avgPx="50000" if kind == "market" else "",
            )
        )
        raise ccxt.RequestTimeout("PRIVATE LOST ACK")

    def read(request):
        reads.append(request)
        assert request["instId"] == "BTC-USDT"
        assert request.get("ordId") == native_id or request.get("clOrdId") == writes[0]
        if len(reads) == 1:
            raise ccxt.OrderNotFound("okx 51603 PRIVATE ERROR DETAILS")
        return {"code": "0", "data": rows}

    monkeypatch.setattr(native, "create_order", lost_ack)
    monkeypatch.setattr(native, "privateGetTradeOrder", read)
    monkeypatch.setattr(native, "privateGetTradeFillsHistory", lambda request: {"data": []})
    trading = owner.trading
    submission = submit(
        trading,
        account,
        order_type=order_type,
        limit_price=50_000 if order_type == "limit" else None,
    )
    assert submission["status"] == "unknown" and not submission.get("exchange_order_id")
    identity = submission["id"]
    owner.settings.allow_live_trading = False
    missed = trading.recover(identity)
    assert missed["recovery"]["state"] == "not_found" and missed["status"] == "unknown"
    assert "PRIVATE ERROR DETAILS" not in json.dumps(missed)
    assert reads == [{"instId": "BTC-USDT", "clOrdId": submission["client_order_id"]}]

    actual_time = rows[0]["cTime"]
    rows[0]["cTime"] = str(int(actual_time) - 30 * 60 * 1000)
    restarted = ExchangeTrading(owner.market, owner.store)
    stale = restarted.recover(identity)
    assert stale["recovery"]["state"] == "mismatch" and not stale.get("exchange_order_id")
    rows[0]["cTime"] = actual_time
    recovered = restarted.recover(identity)
    assert recovered["recovery"]["state"] == "found"
    assert recovered["exchange_order_id"] == native_id
    assert recovered["status"] == ("closed" if order_type == "market" else "open")
    assert len(reads) == 3 and reads[-1]["clOrdId"] == submission["client_order_id"]
    assert restarted.refresh(identity)["exchange_order_id"] == native_id
    assert reads[-1]["ordId"] == native_id
    assert restarted.execute(identity, submission["confirmation"])["exchange_order_id"] == native_id
    assert writes == [submission["client_order_id"]]


@pytest.mark.parametrize(
    ("provider", "order_type", "source"),
    [
        ("bybit", "limit", "history"),
        ("bybit", "market", "history"),
        ("kucoin", "limit", "legacy"),
        ("kucoin", "market", "hf"),
    ],
)
def test_new_spot_recovery_providers_retain_lost_submissions(
    manual_client, monkeypatch, provider, order_type, source
):
    owner = manual_client.app.state.services
    owner.settings.allow_live_trading = True
    account = owner.store.add_connection(
        ConnectionCreate(
            exchange=provider, label="Isolated spot", api_key="fake", secret="fake", passphrase="fake"
        )
    )
    adapter = owner.market.client(account)
    native = adapter._exchange
    instrument = "BTCUSDT" if provider == "bybit" else "BTC-USDT"
    native.set_markets([spot_market(instrument)])
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 10_000}})
    monkeypatch.setattr(adapter, "fetch_ticker", lambda symbol: {"ask": 50_000, "bid": 49_999})
    monkeypatch.setattr(native, "fetch_order", lambda *_: pytest.fail("Recovery status was already observed"))
    writes, reads = [], []
    fill_checks = []
    payload = {}
    identity = "native-8063"

    def lost_ack(symbol, kind, side, amount, price=None, *, params):
        client_id = params["clientOrderId"]
        writes.append(client_id)
        assert (symbol, kind, side, amount) == ("BTC/USDT", order_type, "buy", 0.01)
        stamp = int(time.time() * 1000)
        filled = kind == "market" or provider == "bybit"
        if provider == "bybit":
            payload.update(
                bybit_order(
                    identity,
                    orderLinkId=client_id,
                    createdTime=str(stamp),
                    orderType=kind.title(),
                    marketUnit="baseCoin" if kind == "market" else "",
                    orderStatus="Filled" if kind == "market" else "PartiallyFilledCanceled",
                    cumExecQty="0.01" if kind == "market" else "0.004",
                    leavesQty="0",
                    cumExecValue="500" if kind == "market" else "200",
                    avgPrice="50000",
                    price=str(price or 0),
                )
            )
        else:
            payload.update(
                {
                    "id": identity,
                    "clientOid": client_id,
                    "symbol": instrument,
                    "tradeType": "TRADE",
                    "size": str(amount),
                    "price": str(price or 0),
                    "type": kind,
                    "side": side,
                    "createdAt": stamp,
                    "active": not filled,
                    "timeInForce": "GTC",
                    "dealSize": "0.01" if filled else "0",
                    "dealFunds": "500" if filled else "0",
                    "cancelExist": False,
                }
            )
        raise ccxt.RequestTimeout("PRIVATE LOST ACK")

    def realtime(params):
        reads.append(("realtime", params))
        assert params["orderLinkId"] == writes[0] and params["symbol"] == instrument
        raise ccxt.OrderNotFound("PRIVATE NO REALTIME ROW")

    def history(params):
        reads.append(("history", params))
        assert params["orderLinkId"] == writes[0] and params["symbol"] == instrument
        assert params["startTime"] <= int(payload["createdTime"]) <= params["endTime"]
        return {"retCode": 0, "result": {"category": "spot", "list": [payload], "nextPageCursor": ""}}

    def hf(params):
        reads.append(("hf", params))
        assert params == {"clientOid": writes[0], "symbol": instrument}
        return {"code": "200000", "data": payload if source == "hf" else None}

    def legacy(params):
        reads.append(("legacy", params))
        assert params == {"clientOid": writes[0]}
        return {"code": "200000", "data": payload}

    def fills(*args):
        fill_checks.append(args)
        return TradePage([], {}, True)

    monkeypatch.setattr(native, "create_order", lost_ack)
    monkeypatch.setattr(adapter, "fetch_order_fill_page", fills)
    if provider == "bybit":
        monkeypatch.setattr(native, "privateGetV5OrderRealtime", realtime)
        monkeypatch.setattr(native, "privateGetV5OrderHistory", history)
    else:
        monkeypatch.setattr(native, "privateGetHfOrdersClientOrderClientOid", hf)
        monkeypatch.setattr(native, "privateGetOrderClientOrderClientOid", legacy)
    result = submit(
        owner.trading, account, order_type=order_type, limit_price=50000 if order_type == "limit" else None
    )
    local_id = result["id"]
    owner.settings.allow_live_trading = False
    result = owner.trading.recover(local_id)
    if source != "hf":
        assert result["status"] == "unknown" and result["recovery"]["state"] == "searching"
        assert not result.get("exchange_order_id")
        assert "PRIVATE NO REALTIME ROW" not in json.dumps(result)
        restarted = ExchangeTrading(owner.market, owner.store)
        result = restarted.recover(local_id)
    assert result["recovery"]["state"] == "found" and result["exchange_order_id"] == identity
    assert reads[-1][0] == source
    [(checked_id, checked_market, _)] = fill_checks
    assert (checked_id, checked_market) == (identity, "BTC/USDT")
    if provider == "bybit" and order_type == "limit":
        assert result["status"] == "canceled" and result["filled"] == 0.004
    assert owner.trading.execute(local_id, result["confirmation"])["exchange_order_id"] == identity
    assert len(writes) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"orderLinkId": "other"},
        {"isLeverage": "1"},
        {"marketUnit": "quoteCoin", "orderType": "Market"},
        {"timeInForce": "IOC"},
        {"stopOrderType": "Stop"},
    ],
)
def test_bybit_lookup_rejects_nonmatching_or_unreviewed_rows(monkeypatch, changes):
    venue = LookupTransport()
    monkeypatch.setattr(venue, "market", lambda symbol: {"id": "BTCUSDT"})
    row = bybit_order("order-1", **({"orderLinkId": "client1"} | changes))
    monkeypatch.setattr(
        venue,
        "privateGetV5OrderRealtime",
        lambda _: {"retCode": 0, "result": {"category": "spot", "list": [row], "nextPageCursor": ""}},
        raising=False,
    )
    with pytest.raises(ValueError, match="Bybit order evidence differs"):
        lookup_order_page(venue, "bybit", "client1", "BTC/USDT", {}, 1000, 2000)


@pytest.mark.parametrize(
    "changes",
    [
        {"tradeType": "MARGIN_TRADE"},
        {"hidden": True},
        {"active": "true"},
        {"type": "market", "size": "0", "funds": "5"},
        {"timeInForce": "FOK"},
    ],
)
def test_kucoin_lookup_rejects_unreviewed_or_ambiguous_shapes(monkeypatch, changes):
    venue = LookupTransport()
    row = {
        "symbol": "BTC-USDT",
        "clientOid": "client1",
        "tradeType": "TRADE",
        "active": True,
        "size": "0.01",
        "type": "limit",
        "timeInForce": "GTC",
    } | changes
    monkeypatch.setattr(
        venue,
        "privateGetHfOrdersClientOrderClientOid",
        lambda _: {"code": "200000", "data": row},
        raising=False,
    )
    with pytest.raises(ValueError, match="KuCoin order evidence differs"):
        lookup_order_page(venue, "kucoin", "client1", "BTC/USDT", {}, 1000, 2000)


def gemini_order(**changes):
    return {
        "order_id": 2**60 + 9,
        "symbol": "btcusd",
        "exchange": "gemini",
        "side": "buy",
        "original_amount": "0.01",
        "remaining_amount": "0.01",
        "executed_amount": "0",
        "price": "50000",
        "type": "exchange limit",
        "options": [],
        "is_live": True,
        "is_cancelled": False,
        "timestampms": int(time.time() * 1000),
        **changes,
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"options": ["maker-or-cancel"]},
        {"original_amount": None},
        {"is_live": "true"},
        {"exchange": "other"},
        {"symbol": "ethusd"},
        {"was_forced": True},
        {"type": "exchange stop limit"},
    ],
)
def test_gemini_recovery_rejects_unproven_original_terms(monkeypatch, changes):
    venue = LookupTransport()
    monkeypatch.setattr(venue, "market", lambda symbol: {"id": "btcusd"})
    row = gemini_order(client_order_id="client-8", **changes)
    monkeypatch.setattr(venue, "privatePostV1OrderStatus", lambda _: row, raising=False)
    with pytest.raises(ValueError, match="Gemini order evidence differs"):
        lookup_order_page(venue, "gemini", "client-8", "BTC/USD", {}, 1000, 2000)


def test_gemini_lost_ack_uses_client_lookup_before_native_fill_read(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    owner.settings.allow_live_trading = True
    account = owner.store.add_connection(
        ConnectionCreate(exchange="gemini", label="Isolated Gemini", api_key="fake", secret="fake")
    )
    adapter = owner.market.client(account)
    native = adapter._exchange
    native.set_markets([{**spot_market("btcusd"), "quote": "USD", "quoteId": "usd", "symbol": "BTC/USD"}])
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USD": 10_000}})
    native_id = str(2**60 + 9)
    writes, reads = [], []

    def lost_ack(symbol, kind, side, amount, price, *, params):
        assert (symbol, kind, side, amount, price) == ("BTC/USD", "limit", "buy", 0.01, 50000)
        writes.append(params["clientOrderId"])
        raise ccxt.RequestTimeout("PRIVATE")

    def order_status(request):
        reads.append(request)
        if len(reads) == 1:
            raise ccxt.OrderNotFound("private lookup detail")
        return gemini_order(client_order_id=writes[0], trades=[])

    monkeypatch.setattr(native, "create_order", lost_ack)
    monkeypatch.setattr(native, "privatePostV1OrderStatus", order_status)
    service = owner.trading
    placement = submit(service, account, symbol="BTC/USD")
    assert placement["status"] == "unknown"
    owner.settings.allow_live_trading = False
    missed = service.recover(placement["id"])
    assert missed["recovery"]["state"] == "not_found" and missed["status"] == "unknown"
    resumed = ExchangeTrading(owner.market, owner.store)
    result = resumed.recover(placement["id"])
    assert result["exchange_order_id"] == native_id and result["recovery"]["state"] == "found"
    assert reads == [
        {"client_order_id": writes[0], "include_trades": False},
        {"client_order_id": writes[0], "include_trades": False},
        {"order_id": native_id, "include_trades": True},
    ]
    assert resumed.execute(placement["id"], placement["confirmation"])["exchange_order_id"] == native_id
    assert writes == [placement["client_order_id"]]


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
