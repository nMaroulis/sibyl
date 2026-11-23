"""Offline CoinEx v2 transport contracts for order discovery, recovery and shared fills."""

import json
import time

import ccxt
import pytest
from test_expanded_order_adapters import saved_account
from test_order_discovery import advance, job
from test_order_management import submit

from sibyl.exchanges.registry import provider_catalog
from sibyl.services.accounts.sync import AccountSync
from sibyl.services.trading.discovery import OrderDiscoveryRequest
from sibyl.services.trading.service import ExchangeTrading


def response(rows, more=False):
    return {"code": 0, "data": rows, "pagination": {"has_next": more}, "message": "PRIVATE"}


def order(identity=2**60 + 18, **changes):
    return {
        "order_id": identity,
        "market": "BTCUSDT",
        "market_type": "SPOT",
        "ccy": "BTC",
        "side": "buy",
        "type": "limit",
        "amount": "0.01",
        "price": "50000",
        "unfilled_amount": "0.01",
        "filled_amount": "0",
        "filled_value": "0",
        "client_id": "external",
        "created_at": int(time.time() * 1000) - 1000,
        **changes,
    }


def fill(identity=2**60 + 6, **changes):
    return {
        "deal_id": identity,
        "order_id": 2**60 + 18,
        "market": "BTCUSDT",
        "side": "buy",
        "margin_market": "",
        "price": "50000",
        "amount": "0.01",
        "fee": "0.2",
        "fee_ccy": "USDT",
        "created_at": int(time.time() * 1000) - 1000,
        **changes,
    }


def test_discovery_scans_native_pages_before_filtering_dates_and_preserves_terminal_state(
    manual_client, monkeypatch
):
    owner = manual_client.app.state.services
    account, adapter = saved_account(owner, "coinex", "BTCUSDT")
    native, seen = adapter._exchange, []
    complete = order(unfilled_amount="0", filled_amount="0.01", filled_value="500")
    canceled = order(2**60 + 17, unfilled_amount="0.006", filled_amount="0.004", filled_value="200")

    def pending(params):
        seen.append(("open", params.copy()))
        assert params == {"market_type": "SPOT", "page": 1, "limit": 100}
        return response([order(2**60 + 20)])

    def finished(params):
        seen.append(("recent", params.copy()))
        assert params["market_type"] == "SPOT" and "start_time" not in params
        if params["page"] == 1:
            return response(
                [complete, order(2**60 + 16, created_at=1), order(2**60 + 15, market_type="MARGIN")], True
            )
        return response([canceled])

    monkeypatch.setattr(native, "v2PrivateGetSpotPendingOrder", pending)
    monkeypatch.setattr(native, "v2PrivateGetSpotFinishedOrder", finished)
    service = owner.trading
    service.discovery.enqueue(OrderDiscoveryRequest(account_id=account.id, days=3))
    advance(service, account)
    advance(service, account)
    assert not job(service, account)["complete"] and job(service, account)["cursor"]["page"] == 2
    restarted = ExchangeTrading(owner.market, owner.store)
    advance(restarted, account)
    saved = job(restarted, account)
    assert saved["complete"] and saved["skipped"] == 2
    orders = {row["exchange_order_id"]: row for row in restarted.monitor(account_id=account.id)["items"]}
    assert len(orders) == 3 and all(row["read_only"] for row in orders.values())
    assert orders[str(2**60 + 18)]["status"] == "closed"
    assert orders[str(2**60 + 17)]["status"] == "canceled"
    assert orders[str(2**60 + 17)]["filled"] == 0.004
    assert seen[-1][1]["page"] == 2


def test_uncertain_limit_recovers_only_after_both_native_streams_finish(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    owner.settings.allow_live_trading = True
    account, adapter = saved_account(owner, "coinex", "BTCUSDT")
    native, writes, reads = adapter._exchange, [], []
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 10_000}})

    def lost_ack(symbol, kind, side, amount, price, *, params):
        assert (symbol, kind, side, amount, price) == ("BTC/USDT", "limit", "buy", 0.01, 50000)
        writes.append(params["client_id"])
        raise ccxt.RequestTimeout("PRIVATE")

    def pending(params):
        reads.append(params.copy())
        assert params["client_id"] == writes[0] and params["market"] == "BTCUSDT"
        return response([])

    def finished(params):
        reads.append(params.copy())
        assert params["market_type"] == "SPOT" and "client_id" not in params
        if params["page"] == 1:
            return response(
                [order(client_id=writes[0], unfilled_amount="0", filled_amount="0.01", filled_value="500")],
                True,
            )
        return response([])

    monkeypatch.setattr(native, "create_order", lost_ack)
    monkeypatch.setattr(native, "v2PrivateGetSpotPendingOrder", pending)
    monkeypatch.setattr(native, "v2PrivateGetSpotFinishedOrder", finished)
    uncertain = submit(owner.trading, account)
    assert uncertain["status"] == "unknown"
    owner.settings.allow_live_trading = False
    initial = owner.trading.recover(uncertain["id"])
    assert initial["recovery"]["state"] == "searching"
    restarted = ExchangeTrading(owner.market, owner.store)
    middle = restarted.recover(uncertain["id"])
    assert middle["recovery"]["state"] == "searching" and not middle.get("exchange_order_id")
    result = restarted.recover(uncertain["id"])
    assert result["recovery"]["state"] == "found" and result["status"] == "closed"
    assert result["exchange_order_id"] == str(2**60 + 18)
    assert len(writes) == 1 and len(reads) == 3 and "PRIVATE" not in json.dumps(result)


def test_recovery_missing_cancelled_record_keeps_uncertainty(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    owner.settings.allow_live_trading = True
    account, adapter = saved_account(owner, "coinex", "BTCUSDT")
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 10_000}})

    def lost_ack(*args, **kwargs):
        raise ccxt.RequestTimeout("PRIVATE")

    monkeypatch.setattr(adapter._exchange, "create_order", lost_ack)
    monkeypatch.setattr(adapter._exchange, "v2PrivateGetSpotPendingOrder", lambda _: response([]))
    monkeypatch.setattr(adapter._exchange, "v2PrivateGetSpotFinishedOrder", lambda _: response([]))
    uncertain = submit(owner.trading, account)
    owner.trading.recover(uncertain["id"])
    result = owner.trading.recover(uncertain["id"])
    assert result["recovery"]["state"] == "not_found" and result["status"] == "unknown"
    assert not result.get("exchange_order_id")


def test_exact_and_account_fills_share_order_scoped_identity_and_observe_fee_corrections(
    manual_client, monkeypatch
):
    owner = manual_client.app.state.services
    account, adapter = saved_account(owner, "coinex", "BTCUSDT")
    native, requests = adapter._exchange, []
    closed = order(unfilled_amount="0", filled_amount="0.01", filled_value="500")
    execution = fill()
    monkeypatch.setattr(native, "v2PrivateGetSpotPendingOrder", lambda _: response([]))
    monkeypatch.setattr(native, "v2PrivateGetSpotFinishedOrder", lambda _: response([closed]))

    def exact(params):
        requests.append(params.copy())
        assert params["order_id"] == str(closed["order_id"]) and params["market_type"] == "SPOT"
        return response([execution], True) if params["page"] == 1 else response([])

    def history(params):
        requests.append(params.copy())
        assert params["market"] == "BTCUSDT" and params["market_type"] == "SPOT"
        assert params["start_time"] < execution["created_at"] <= params["end_time"]
        return response([execution, {**execution, "order_id": 2**60 + 19, "side": "sell"}])

    monkeypatch.setattr(native, "v2PrivateGetSpotOrderDeals", exact)
    monkeypatch.setattr(native, "v2PrivateGetSpotUserDeals", history)
    service = owner.trading
    service.discovery.enqueue(OrderDiscoveryRequest(account_id=account.id))
    advance(service, account)
    advance(service, account)
    (saved,) = service.monitor(account_id=account.id)["items"]
    first = service.reconciliation.sync(saved["id"], manual=True)
    assert first["reconciliation"]["status"] == "pending"
    restarted = ExchangeTrading(owner.market, owner.store)
    result = restarted.reconciliation.sync(saved["id"], manual=True)
    assert result["reconciliation"]["status"] == "matched"
    owner.account_sync.enqueue(account, ["BTC/USDT"])
    owner.account_sync.tick()
    ledger = owner.account_sync.ledger
    assert ledger.fills(account_id=account.id)["total"] == 2
    execution["fee"] = "0.25"
    owner.account_sync.enqueue(account, ["BTC/USDT"])
    AccountSync(owner.market, owner.store).tick()
    assert ledger.fills(account_id=account.id)["total"] == 2
    corrected = restarted.reconciliation.detail(saved["id"])
    assert corrected["reconciliation"]["fees"] == [{"currency": "USDT", "cost": 0.25}]
    assert {row["trade_id"] for row in ledger.fills(account_id=account.id)["items"]} == {
        str(execution["deal_id"])
    }
    assert "PRIVATE" not in json.dumps(corrected)


@pytest.mark.parametrize(
    "fault", ["margin", "wrong order", "wrong market", "no pagination", "empty continuation"]
)
def test_unverified_execution_pages_cannot_enter_the_ledger(manual_client, monkeypatch, fault):
    owner = manual_client.app.state.services
    _, adapter = saved_account(owner, "coinex", "BTCUSDT")
    changes = {
        "margin": {"margin_market": "BTCUSDT"},
        "wrong order": {"order_id": 99},
        "wrong market": {"market": "ETHUSDT"},
    }.get(fault, {})
    row = fill(**changes)
    page = response([] if fault == "empty continuation" else [row], fault == "empty continuation")
    if fault == "no pagination":
        page.pop("pagination")
    monkeypatch.setattr(adapter._exchange, "v2PrivateGetSpotOrderDeals", lambda _: page)
    with pytest.raises(ccxt.ExchangeError):
        adapter.fetch_order_fill_page(str(2**60 + 18), "BTC/USDT", {})


def test_repeated_native_pages_reject_the_checkpoint(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    _, adapter = saved_account(owner, "coinex", "BTCUSDT")
    monkeypatch.setattr(adapter._exchange, "v2PrivateGetSpotUserDeals", lambda _: response([fill()], True))
    first = adapter.fetch_trade_page("BTC/USDT", {})
    assert not first.caught_up
    with pytest.raises(ccxt.ExchangeError, match="repeated"):
        adapter.fetch_trade_page("BTC/USDT", first.cursor)


@pytest.mark.parametrize(
    "state,expected",
    [("part_filled", "open"), ("filled", "closed"), ("part_canceled", "canceled"), ("canceled", "canceled")],
)
def test_known_order_status_checks_normalize_v2_states(manual_client, monkeypatch, state, expected):
    owner = manual_client.app.state.services
    _, adapter = saved_account(owner, "coinex", "BTCUSDT")
    row = order(status=state)
    monkeypatch.setattr(adapter._exchange, "fetch_order", lambda *_: adapter._exchange.parse_order(row))
    assert adapter.fetch_order(str(row["order_id"]), "BTC/USDT")["status"] == expected


def test_settings_report_market_orders_and_reviewed_read_paths():
    (coinex,) = [row for row in provider_catalog()["items"] if row["id"] == "coinex"]
    features = {feature["id"]: feature for group in coinex["support"] for feature in group["features"]}
    assert coinex["history_import"] == "coinex-page"
    for name in ("history_import", "fill_reconciliation", "recovery", "discovery"):
        assert features[name]["status"] == "available"
    assert features["automated"]["status"] == "pending"
    assert coinex["market_orders"] and features["market_orders"]["status"] == "available"


@pytest.mark.parametrize("reported", ["0.01", None])
def test_market_quote_budgets_cannot_become_base_quantities(manual_client, monkeypatch, reported):
    owner = manual_client.app.state.services
    _, adapter = saved_account(owner, "coinex", "BTCUSDT")
    native = adapter._exchange
    row = order(
        type="market",
        ccy="USDT",
        amount="510",
        unfilled_amount="10",
        filled_amount=reported,
        filled_value="500",
    )
    monkeypatch.setattr(native, "v2PrivateGetSpotFinishedOrder", lambda _: response([row]))
    end = int(time.time() * 1000)
    page = adapter.fetch_account_order_page("recent", {}, end - 86400000, end, [])
    (saved,) = page.items
    assert saved["amount"] is None and saved["remaining"] is None
    assert saved["filled"] == (0.01 if reported else None)
    assert saved["cost"] == 500 and saved["status"] == "unknown"
    assert saved["average"] == (50000 if reported else None)
