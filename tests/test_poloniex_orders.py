"""Exercise Poloniex cash order reads with real parsing and offline native transports."""

import json
import time

import ccxt
import pytest
from test_expanded_order_adapters import saved_account
from test_order_discovery import advance, job
from test_order_management import submit

from sibyl.exchanges.poloniex_orders import discover_page, lookup_order
from sibyl.exchanges.registry import provider_catalog
from sibyl.services.trading.discovery import OrderDiscoveryRequest
from sibyl.services.trading.service import ExchangeTrading

FIRST_ID = 2**60 + 7


def order(identity=FIRST_ID, **changes):
    stamp = int(time.time() * 1000) - 1000
    return {
        "id": str(identity),
        "clientOrderId": "external",
        "symbol": "BTC_USDT",
        "accountType": "SPOT",
        "loan": False,
        "side": "BUY",
        "type": "LIMIT",
        "timeInForce": "GTC",
        "quantity": "0.01",
        "amount": "0",
        "price": "50000",
        "avgPrice": "0",
        "filledQuantity": "0",
        "filledAmount": "0",
        "state": "NEW",
        "createTime": stamp,
        "updateTime": stamp,
        "orderSource": "API",
        **changes,
    }


@pytest.fixture
def poloniex(manual_client):
    owner = manual_client.app.state.services
    account, adapter = saved_account(owner, "poloniex", "BTC_USDT")
    return owner, account, adapter


def test_discovery_resumes_exact_native_ids_and_keeps_update_window(poloniex, monkeypatch):
    owner, account, adapter = poloniex
    native, reads = adapter._exchange, []
    older = order(createTime=int(time.time() * 1000) - 30 * 86400000)
    pending = order(FIRST_ID + 3, state="PENDING_CANCEL")
    closed = order(
        FIRST_ID + 4,
        state="FILLED",
        createTime=older["createTime"],
        filledQuantity="0.01",
        filledAmount="500",
        avgPrice="50000",
    )

    def opened(params):
        reads.append(("open", params.copy()))
        after = int(params["from"])
        assert params["direction"] == "NEXT" and params["limit"] == 100
        if after == 0:
            return [older, order(FIRST_ID + 1, loan=True), order(FIRST_ID + 2, symbol="OLD_USDT")]
        if after == FIRST_ID + 2:
            return [order(FIRST_ID + 2, symbol="OLD_USDT"), pending]
        return [pending]  # The native boundary can be inclusive.

    def finished(params):
        reads.append(("recent", params.copy()))
        assert params["accountType"] == "SPOT" and params["direction"] == "NEXT"
        return [closed]

    monkeypatch.setattr(native, "privateGetOrders", opened)
    monkeypatch.setattr(native, "privateGetOrdersHistory", finished)
    service = owner.trading
    service.discovery.enqueue(OrderDiscoveryRequest(account_id=account.id, days=3))
    advance(service, account)
    assert job(service, account)["cursor"] == {"after": str(FIRST_ID + 2)}
    restarted = ExchangeTrading(owner.market, owner.store)
    for _ in range(4):
        advance(restarted, account)
    saved = job(restarted, account)
    assert saved["complete"] and saved["skipped"] == 2
    rows = restarted.monitor(account_id=account.id)["items"]
    assert len(rows) == 3 and all(row["read_only"] for row in rows)
    assert {row["exchange_order_id"] for row in rows} == {older["id"], pending["id"], closed["id"]}
    assert next(row for row in rows if row["exchange_order_id"] == pending["id"])["status"] == "open"
    assert next(row for row in rows if row["exchange_order_id"] == closed["id"])["cost"] == 500
    history = [params for stream, params in reads if stream == "recent"]
    assert len(history) == 2
    assert history[0]["startTime"] == history[1]["startTime"]
    assert history[0]["endTime"] == history[1]["endTime"]
    assert history[1]["from"] == closed["id"]


def test_quote_budget_is_not_imported_as_base_quantity(poloniex, monkeypatch):
    _, _, adapter = poloniex
    end = int(time.time() * 1000)
    native = order(
        type="MARKET",
        state="FILLED",
        quantity="0",
        amount="500",
        filledQuantity="0.01",
        filledAmount="500",
        avgPrice="50000",
    )
    monkeypatch.setattr(adapter._exchange, "privateGetOrdersHistory", lambda _: [native])
    page = adapter.fetch_account_order_page("recent", {}, end - 10000, end, [])
    (saved,) = page.items
    assert saved["amount"] is None and saved["remaining"] is None
    assert saved["filled"] == 0.01 and saved["cost"] == 500 and saved["average"] == 50000
    assert "info" not in saved


@pytest.mark.parametrize("state,status", [("PENDING_CANCEL", "open"), ("FAILED", "rejected")])
def test_regular_status_reads_preserve_cancel_races_and_native_costs(poloniex, monkeypatch, state, status):
    _, _, adapter = poloniex
    native = order(state=state, filledQuantity="0.004", filledAmount="200", avgPrice="50000")
    monkeypatch.setattr(adapter._exchange, "fetch_order", lambda *_: adapter._exchange.parse_order(native))
    saved = adapter.fetch_order(native["id"], "BTC/USDT")
    assert saved["status"] == status and saved["cost"] == 200 and saved["filled"] == 0.004


def test_lost_ack_recovery_reads_exact_client_id_without_resubmission(poloniex, monkeypatch):
    owner, account, adapter = poloniex
    owner.settings.allow_live_trading = True
    native, writes, reads = adapter._exchange, [], []
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 10000}})

    def lost_ack(symbol, kind, side, quantity, price, *, params):
        assert (symbol, kind, side, quantity, price) == ("BTC/USDT", "limit", "buy", 0.01, 50000)
        writes.append(params["clientOrderId"])
        raise ccxt.RequestTimeout("PRIVATE")

    def lookup(params):
        reads.append(params.copy())
        assert params in ({"id": "cid:" + writes[0]}, {"id": str(FIRST_ID)})
        return order(
            clientOrderId=writes[0],
            state="PARTIALLY_FILLED",
            filledQuantity="0.004",
            filledAmount="200",
            avgPrice="50000",
        )

    monkeypatch.setattr(native, "create_order", lost_ack)
    monkeypatch.setattr(native, "privateGetOrdersId", lookup)
    monkeypatch.setattr(native, "privateGetOrdersIdTrades", lambda _: [])
    uncertain = submit(owner.trading, account)
    assert uncertain["status"] == "unknown"
    owner.settings.allow_live_trading = False
    restarted = ExchangeTrading(owner.market, owner.store)
    recovered = restarted.recover(uncertain["id"])
    assert recovered["recovery"]["state"] == "found" and recovered["filled"] == 0.004
    assert recovered["exchange_order_id"] == str(FIRST_ID) and recovered["cost"] == 200
    assert len(writes) == 1 and reads == [{"id": "cid:" + writes[0]}, {"id": str(FIRST_ID)}]
    assert "PRIVATE" not in json.dumps(recovered)


@pytest.mark.parametrize(
    "change",
    [
        {"loan": True},
        {"loan": None},
        {"allowBorrow": True},
        {"accountType": "MARGIN"},
        {"symbol": "ETH_USDT"},
        {"clientOrderId": "different"},
        {"timeInForce": "IOC"},
        {"orderSource": "WEB"},
        {"type": "LIMIT_MAKER"},
        {"stopPrice": "48000"},
    ],
)
def test_recovery_rejects_evidence_outside_reviewed_cash_terms(poloniex, monkeypatch, change):
    _, _, adapter = poloniex
    monkeypatch.setattr(
        adapter._exchange,
        "privateGetOrdersId",
        lambda _: order(**{"clientOrderId": "a" * 32, **change}),
    )
    with pytest.raises(ValueError, match="differs"):
        lookup_order(adapter._exchange, "a" * 32, "BTC/USDT")


def test_missing_native_order_returns_no_candidate(poloniex, monkeypatch):
    _, _, adapter = poloniex

    def missing(_):
        raise ccxt.OrderNotFound("PRIVATE")

    monkeypatch.setattr(adapter._exchange, "privateGetOrdersId", missing)
    assert lookup_order(adapter._exchange, "a" * 32, "BTC/USDT") == []


@pytest.mark.parametrize(
    "rows,checkpoint",
    [
        ([order(), order()], {}),
        ([order()], {"after": str(FIRST_ID + 1)}),
        ([order(identity=float(FIRST_ID))], {}),
        ([order(state="FILLED")], {}),
    ],
)
def test_invalid_pages_fail_without_advancing_cursor(poloniex, monkeypatch, rows, checkpoint):
    _, _, adapter = poloniex
    monkeypatch.setattr(adapter._exchange, "privateGetOrders", lambda _: rows)
    with pytest.raises(ccxt.ExchangeError):
        discover_page(adapter._exchange, "open", checkpoint, 1, int(time.time() * 1000))


def test_recent_history_requires_native_update_time_inside_the_fixed_range(poloniex, monkeypatch):
    _, _, adapter = poloniex
    end = int(time.time() * 1000)
    monkeypatch.setattr(
        adapter._exchange, "privateGetOrdersHistory", lambda _: [order(state="FILLED", updateTime=end)]
    )
    with pytest.raises(ccxt.ExchangeError, match="update window"):
        discover_page(adapter._exchange, "recent", {}, end - 10000, end)


def test_settings_expose_only_the_implemented_cash_order_reads():
    (provider,) = [row for row in provider_catalog()["items"] if row["id"] == "poloniex"]
    features = {feature["id"]: feature for group in provider["support"] for feature in group["features"]}
    for name in ("recovery", "discovery", "history_import", "fill_reconciliation"):
        assert features[name]["status"] == "available"
    for name in ("automated",):
        assert features[name]["status"] == "pending"
    assert provider["market_order_sides"] == ["buy", "sell"]
    assert provider["market_buy_budget"]
