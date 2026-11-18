"""Native-shaped Crypto.com cash contracts: exact identity, scope, fees and restart checkpoints."""

import time

import ccxt
import pytest
from test_expanded_order_adapters import saved_account
from test_order_discovery import advance, job
from test_order_management import submit

from sibyl.exchanges.cryptocom_orders import DAY_NS, discover_page, lookup_order
from sibyl.exchanges.registry import provider_catalog
from sibyl.services.accounts.sync import AccountSync
from sibyl.services.trading.discovery import OrderDiscoveryRequest
from sibyl.services.trading.service import ExchangeTrading


def response(value):
    return {"code": 0, "result": value}


def order(identity=2**60 + 1, **changes):
    stamp = time.time_ns() // 1000000 - 2000
    return {
        "account_id": "cash-account",
        "order_id": str(identity),
        "client_oid": "external",
        "instrument_name": "BTC_USDT",
        "order_type": "LIMIT",
        "side": "BUY",
        "exec_inst": [],
        "time_in_force": "GOOD_TILL_CANCEL",
        "quantity": "0.01",
        "limit_price": "50000",
        "cumulative_quantity": "0",
        "cumulative_value": "0",
        "cumulative_fee": "0",
        "avg_price": "0",
        "status": "ACTIVE",
        "create_time": stamp,
        "create_time_ns": str(stamp * 1000000 + 123456),
        **changes,
    }


def fill(identity=2**60 + 100, **changes):
    stamp = time.time_ns() // 1000000 - 1000
    return {
        "account_id": "cash-account",
        "trade_id": str(identity),
        "order_id": str(2**60 + 1),
        "instrument_name": "BTC_USDT",
        "side": "BUY",
        "journal_type": "TRADING",
        "traded_quantity": "0.01",
        "traded_price": "50000",
        "fees": "-0.25",
        "fee_instrument_name": "USDT",
        "create_time": stamp,
        "create_time_ns": str(stamp * 1000000 + 987654),
        **changes,
    }


@pytest.fixture
def crypto(manual_client):
    owner = manual_client.app.state.services
    account, adapter = saved_account(owner, "cryptocom", "BTC_USDT")
    return owner, account, adapter


def test_discovery_imports_only_explicit_cash_scope_and_recent_selected_pairs(crypto, monkeypatch):
    owner, account, adapter = crypto
    native, reads = adapter._exchange, []
    closed = order(2**60 + 2, status="CANCELED", cumulative_quantity="0.004", cumulative_value="200")
    monkeypatch.setattr(
        native,
        "v1PrivatePostPrivateGetOpenOrders",
        lambda _: response(
            {
                "data": [
                    order(),
                    order(3, exec_inst=["MARGIN_ORDER"]),
                    order(4, exec_inst=None),
                    order(5, order_type="STOP_LOSS"),
                    order(6, instrument_name="BTCUSD-PERP"),
                ]
            }
        ),
    )

    def history(params):
        reads.append(params.copy())
        assert params["instrument_name"] == "BTC_USDT"
        assert int(params["end_time"]) - int(params["start_time"]) <= DAY_NS
        return response({"data": [closed]})

    monkeypatch.setattr(native, "v1PrivatePostPrivateGetOrderHistory", history)
    owner.trading.discovery.enqueue(OrderDiscoveryRequest(account_id=account.id, symbols=["BTC/USDT"]))
    advance(owner.trading, account)
    restarted = ExchangeTrading(owner.market, owner.store)
    advance(restarted, account)
    assert job(restarted, account)["complete"] and job(restarted, account)["skipped"] == 4
    rows = restarted.monitor(account_id=account.id)["items"]
    assert len(rows) == 2 and all(row["read_only"] for row in rows)
    saved = next(row for row in rows if row["exchange_order_id"] == closed["order_id"])
    assert saved["status"] == "canceled" and saved["filled"] == 0.004 and saved["cost"] == 200
    assert len(reads) == 1


def test_saturated_history_saves_nanosecond_splits_and_never_discards_ties(crypto, monkeypatch):
    _, _, adapter = crypto
    native = adapter._exchange
    raw = [order(index + 1) for index in range(100)]
    monkeypatch.setattr(native, "v1PrivatePostPrivateGetOrderHistory", lambda _: response({"data": raw}))
    end = native.milliseconds()
    page = discover_page(native, "recent", {}, end - 10000, end, ["BTC/USDT"])
    assert not page[2] and not page[0] and len(page[1]["windows"]) == 2
    with pytest.raises(ccxt.NotSupported, match="capacity"):
        discover_page(native, "recent", {"windows": [[1000000, 1000001]]}, 1, 2, ["BTC/USDT"])


def test_lost_ack_recovers_exact_client_oid_without_any_second_write(crypto, monkeypatch):
    owner, account, adapter = crypto
    owner.settings.allow_live_trading = True
    native, writes = adapter._exchange, []
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 10000}})

    def lost_ack(*args, params):
        writes.append(params["client_oid"])
        assert params["spot_margin"] == "SPOT" and params["timeInForce"] == "GTC"
        raise ccxt.RequestTimeout("PRIVATE")

    def details(params):
        assert params == {"client_oid": writes[0]}
        return response(order(client_oid=writes[0]))

    monkeypatch.setattr(native, "create_order", lost_ack)
    monkeypatch.setattr(native, "v1PrivatePostPrivateGetOrderDetail", details)
    intent = submit(owner.trading, account)
    assert intent["status"] == "unknown"
    owner.settings.allow_live_trading = False
    # Recovery may immediately continue execution reconciliation using the known native ID.
    monkeypatch.setattr(native, "v1PrivatePostPrivateGetTrades", lambda _: response({"data": []}))
    monkeypatch.setattr(
        native,
        "fetch_order",
        lambda *_: native.parse_order(order(client_oid=writes[0]), native.market("BTC/USDT")),
    )
    original = details
    monkeypatch.setattr(
        native,
        "v1PrivatePostPrivateGetOrderDetail",
        lambda params: original(params) if "client_oid" in params else response(order(client_oid=writes[0])),
    )
    saved = ExchangeTrading(owner.market, owner.store).recover(intent["id"])
    assert saved["recovery"]["state"] == "found" and len(writes) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"exec_inst": ["MARGIN_ORDER"]},
        {"exec_inst": ["ISOLATED_MARGIN"]},
        {"exec_inst": None},
        {"isolation_id": "5"},
        {"contingency_type": "OCO"},
        {"client_oid": "other"},
        {"time_in_force": "FILL_OR_KILL"},
        {"order_type": "MARKET"},
        {"instrument_name": "ETH_USDT"},
    ],
)
def test_recovery_abstains_on_unverified_scope_and_changed_terms(crypto, monkeypatch, changes):
    _, _, adapter = crypto
    monkeypatch.setattr(
        adapter._exchange,
        "v1PrivatePostPrivateGetOrderDetail",
        lambda _: response(order(**{"client_oid": "saved", **changes})),
    )
    with pytest.raises(ValueError, match="differs"):
        lookup_order(adapter._exchange, "saved", "BTC/USDT")


def test_history_restart_shares_exact_native_fill_ids_and_fee_corrections(crypto, monkeypatch):
    owner, account, adapter = crypto
    native, reads = adapter._exchange, []
    execution, parent = fill(), order()
    monkeypatch.setattr(native, "v1PrivatePostPrivateGetOrderDetail", lambda _: response(parent))

    def trades(params):
        reads.append(params.copy())
        lower, upper = int(params["start_time"]), int(params["end_time"])
        return response({"data": [execution] if lower <= int(execution["create_time_ns"]) < upper else []})

    monkeypatch.setattr(native, "v1PrivatePostPrivateGetTrades", trades)
    owner.account_sync.enqueue(account, ["BTC/USDT"])
    owner.account_sync.tick()
    restarted = AccountSync(owner.market, owner.store)
    for _ in range(6):
        restarted.tick()
    assert restarted.snapshot()["jobs"][0]["status"] == "caught_up"
    saved = restarted.ledger.fills(account_id=account.id)
    assert saved["total"] == 1 and saved["items"][0]["trade_id"] == execution["trade_id"]
    assert saved["items"][0]["fees"] == [{"currency": "USDT", "cost": 0.25}]
    exact = adapter.fetch_order_fill_page(parent["order_id"], "BTC/USDT", {})
    assert exact.caught_up and exact.items[0]["id"] == execution["trade_id"]
    execution["fees"] = "0.1"
    owner.account_sync.enqueue(account, ["BTC/USDT"])
    owner.account_sync.tick()
    owner.account_sync.tick()
    assert restarted.ledger.fills(account_id=account.id)["items"][0]["fees"] == [
        {"currency": "USDT", "cost": -0.1}
    ]
    assert all(int(row["end_time"]) - int(row["start_time"]) <= DAY_NS for row in reads)


@pytest.mark.parametrize(
    "changes",
    [{"account_id": "other"}, {"side": "SELL"}, {"journal_type": "TRANSFER"}, {"isolation_id": "8"}],
)
def test_executions_require_same_cash_parent_account_and_direction(crypto, monkeypatch, changes):
    _, _, adapter = crypto
    monkeypatch.setattr(adapter._exchange, "v1PrivatePostPrivateGetOrderDetail", lambda _: response(order()))
    monkeypatch.setattr(
        adapter._exchange, "v1PrivatePostPrivateGetTrades", lambda _: response({"data": [fill(**changes)]})
    )
    with pytest.raises(ccxt.ExchangeError, match="account|direction"):
        adapter.fetch_order_fill_page(order()["order_id"], "BTC/USDT", {})


def test_fee_credit_consumption_does_not_become_a_zero_fee(crypto, monkeypatch):
    _, _, adapter = crypto
    monkeypatch.setattr(adapter._exchange, "v1PrivatePostPrivateGetOrderDetail", lambda _: response(order()))
    monkeypatch.setattr(
        adapter._exchange,
        "v1PrivatePostPrivateGetTrades",
        lambda _: response({"data": [fill(fees="0", fee_credits="-0.2")]}),
    )
    page = adapter.fetch_order_fill_page(order()["order_id"], "BTC/USDT", {})
    assert page.items[0]["fee"] == {"currency": None, "cost": None}


def test_market_buy_notional_is_not_presented_as_executed_base_or_cost(crypto, monkeypatch):
    _, _, adapter = crypto
    native = order(order_type="MARKET", quantity="0", order_value="500", cumulative_value=None)
    monkeypatch.setattr(
        adapter._exchange,
        "fetch_order",
        lambda *_: adapter._exchange.parse_order(native, adapter._exchange.market("BTC/USDT")),
    )
    row = adapter.fetch_order(native["order_id"], "BTC/USDT")
    assert row["amount"] is None and row["remaining"] is None and row["cost"] is None


def test_provider_catalog_enables_reads_without_enabling_market_or_automated_writes():
    provider = next(row for row in provider_catalog()["items"] if row["id"] == "cryptocom")
    features = {f["id"]: f for group in provider["support"] for f in group["features"]}
    assert all(
        features[name]["status"] == "available"
        for name in ("discovery", "recovery", "fill_reconciliation", "history_import")
    )
    assert features["market_orders"]["status"] == "pending" and features["automated"]["status"] == "pending"


def test_inconsistent_nanosecond_time_cannot_commit_any_part_of_a_history_page(crypto, monkeypatch):
    owner, account, adapter = crypto
    valid = fill()
    bad = fill(2**60 + 101, create_time_ns="1")
    native = adapter._exchange
    monkeypatch.setattr(native, "v1PrivatePostPrivateGetOrderDetail", lambda _: response(order()))
    owner.account_sync.enqueue(account, ["BTC/USDT"])

    def page(params):
        low, high = int(params["start_time"]), int(params["end_time"])
        return response({"data": [valid, bad] if low <= int(valid["create_time_ns"]) < high else []})

    monkeypatch.setattr(native, "v1PrivatePostPrivateGetTrades", page)
    for _ in range(7):
        owner.account_sync.tick()
    assert owner.account_sync.snapshot()["jobs"][0]["status"] == "error"
    assert owner.account_sync.ledger.fills(account_id=account.id)["total"] == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"code": False, "result": {"data": []}},
        {"code": 1, "result": {"data": []}},
        {"code": 0, "result": {}},
        {"code": 0, "result": {"data": None}},
    ],
)
def test_invalid_native_envelopes_cannot_complete_history(crypto, monkeypatch, payload):
    _, _, adapter = crypto
    monkeypatch.setattr(adapter._exchange, "v1PrivatePostPrivateGetTrades", lambda _: payload)
    with pytest.raises(ccxt.ExchangeError):
        adapter.fetch_trade_page("BTC/USDT", {})


def test_saturated_execution_query_retains_its_fixed_range_between_pages(crypto, monkeypatch):
    owner, account, adapter = crypto
    native, reads = adapter._exchange, []
    end = (native.milliseconds() + 1) * 1000000
    lower, upper = end - 1000, end
    monkeypatch.setattr(native, "v1PrivatePostPrivateGetOrderDetail", lambda _: response(order()))
    raw = [
        fill(index + 1, create_time=(lower + 5) // 1000000, create_time_ns=str(lower + 5))
        for index in range(20)
    ]

    def page(params):
        reads.append(params.copy())
        if int(params["end_time"]) - int(params["start_time"]) > 500:
            return response({"data": raw})
        return response({"data": []})

    monkeypatch.setattr(native, "v1PrivatePostPrivateGetTrades", page)
    first = adapter.fetch_trade_page("BTC/USDT", {"start": lower, "end": upper})
    assert not first.caught_up and not first.items
    assert first.cursor["windows"] == [[lower, (lower + upper) // 2], [(lower + upper) // 2, upper]]
    second = adapter.fetch_trade_page("BTC/USDT", first.cursor)
    assert not second.caught_up and second.cursor["start"] == lower and second.cursor["end"] == upper
    assert adapter.fetch_trade_page("BTC/USDT", second.cursor).caught_up
    assert len(reads) == 3


@pytest.mark.parametrize("status", ["PENDING", "NEW"])
def test_native_pre_fill_states_remain_active_on_discovery_and_direct_reads(crypto, monkeypatch, status):
    _, _, adapter = crypto
    native = adapter._exchange
    raw = order(status=status)
    monkeypatch.setattr(native, "v1PrivatePostPrivateGetOpenOrders", lambda _: response({"data": [raw]}))
    monkeypatch.setattr(native, "fetch_order", lambda *_: native.parse_order(raw, native.market("BTC/USDT")))
    assert discover_page(native, "open", {}, 1, native.milliseconds(), [])[0][0]["status"] == "open"
    assert adapter.fetch_order(raw["order_id"], "BTC/USDT")["status"] == "open"


def test_short_order_acknowledgement_does_not_require_creation_details(crypto):
    _, _, adapter = crypto
    normalized = adapter._order({"id": "123", "info": {"order_id": "123", "instrument_name": "BTC_USDT"}})
    assert normalized["id"] == "123" and normalized["timestamp"] is None
    assert normalized["filled"] is None and normalized["cost"] is None


def test_future_parent_creation_cannot_turn_into_a_completed_execution_pass(crypto, monkeypatch):
    _, _, adapter = crypto
    future = adapter._exchange.milliseconds() + 100000
    monkeypatch.setattr(
        adapter._exchange,
        "v1PrivatePostPrivateGetOrderDetail",
        lambda _: response(order(create_time=future, create_time_ns=str(future * 1000000))),
    )
    monkeypatch.setattr(
        adapter._exchange,
        "v1PrivatePostPrivateGetTrades",
        lambda _: pytest.fail("Invalid range must not contact the provider"),
    )
    with pytest.raises(ValueError, match="range"):
        adapter.fetch_order_fill_page(order()["order_id"], "BTC/USDT", {})
