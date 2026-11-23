"""Native-shaped Gate and HTX responses exercise read-only order workflows offline."""

import json
import time

import ccxt
import pytest
from test_expanded_order_adapters import gate_order, saved_account
from test_order_discovery import advance, job
from test_order_management import submit

from sibyl.exchanges.registry import provider_catalog
from sibyl.services.trading.discovery import OrderDiscoveryRequest
from sibyl.services.trading.service import ExchangeTrading


def htx_order(identity=2**60 + 20, **changes):
    return {
        "id": identity,
        "account-id": 1234,
        "symbol": "btcusdt",
        "client-order-id": "external",
        "type": "buy-limit",
        "source": "spot-api",
        "state": "submitted",
        "amount": "0.01",
        "price": "50000",
        "filled-amount": "0",
        "filled-cash-amount": "0",
        "created-at": int(time.time() * 1000) - 1000,
        **changes,
    }


def htx_fill(identity=2**60 + 15, **changes):
    return {
        "id": identity,
        "trade-id": identity + 10,
        "order-id": 2**60 + 20,
        "symbol": "btcusdt",
        "type": "buy-limit",
        "source": "spot-api",
        "price": "50000",
        "filled-amount": "0.01",
        "filled-fees": "0.2",
        "fee-currency": "usdt",
        "filled-points": "0",
        "created-at": int(time.time() * 1000) - 1000,
        **changes,
    }


def save_htx(owner):
    account, adapter = saved_account(owner, "htx", "btcusdt")
    adapter._exchange.accounts = [{"id": "1234", "type": "spot"}, {"id": "4321", "type": "margin"}]
    return account, adapter


def test_gate_fills_require_cash_parent_and_reconcile_after_restart(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    account, adapter = saved_account(owner, "gate", "BTC_USDT")
    native = adapter._exchange
    native_order = str(2**60 + 17)
    parent = gate_order(native_order, status="closed", left="0", filled_amount="0.01", filled_total="500")
    seen = []
    monkeypatch.setattr(native, "privateSpotGetOpenOrders", lambda _: [])
    monkeypatch.setattr(
        native, "privateSpotGetOrders", lambda params: [parent] if params["page"] == 1 else []
    )
    monkeypatch.setattr(native, "privateSpotGetOrdersOrderId", lambda _: parent)
    stamp = str(int(time.time() * 1000) - 1000) + ".456"

    def fills(params):
        seen.append(params.copy())
        return (
            []
            if params["page"] == 2
            else [
                {
                    "id": str(2**60 + 13),
                    "order_id": native_order,
                    "currency_pair": "BTC_USDT",
                    "side": "buy",
                    "price": "50000",
                    "amount": "0.01",
                    "create_time_ms": stamp,
                    "fee": "0.2",
                    "fee_currency": "USDT",
                    "gt_fee": "0",
                    "point_fee": "0",
                }
            ]
        )

    monkeypatch.setattr(native, "privateSpotGetMyTrades", fills)
    service = owner.trading
    service.discovery.enqueue(OrderDiscoveryRequest(account_id=account.id))
    for _ in range(3):
        advance(service, account)
    (order,) = service.monitor(account_id=account.id)["items"]
    first = service.reconciliation.sync(order["id"], manual=True)
    assert first["reconciliation"]["status"] == "pending"
    resumed = ExchangeTrading(owner.market, owner.store)
    final = resumed.reconciliation.sync(order["id"], manual=True)
    assert final["reconciliation"]["status"] == "matched"
    assert final["reconciliation"]["fees"] == [{"currency": "USDT", "cost": 0.2}]
    assert first["fills"][0]["trade_id"] == str(2**60 + 13)
    assert first["fills"][0]["timestamp_ms"] == float(stamp)
    assert seen[0]["from"] == seen[1]["from"] and seen[0]["to"] == seen[1]["to"]
    assert seen[1]["page"] == 2 and all(row["order_id"] == native_order for row in seen)
    assert owner.account_sync.ledger.fills(account_id=account.id)["total"] == 1


@pytest.mark.parametrize("fault", ["margin parent", "other order", "point fees", "quote currency"])
def test_gate_rejects_unverified_wallet_or_execution_scope(manual_client, monkeypatch, fault):
    owner = manual_client.app.state.services
    _, adapter = saved_account(owner, "gate", "BTC_USDT")
    order_id = str(2**60 + 17)
    parent = gate_order(order_id, account="margin" if fault == "margin parent" else "spot")
    monkeypatch.setattr(adapter._exchange, "privateSpotGetOrdersOrderId", lambda _: parent)
    row = {
        "id": "123",
        "order_id": "456" if fault == "other order" else order_id,
        "currency_pair": "BTC_USDT",
        "side": "buy",
        "price": "50000",
        "amount": "0.01",
        "create_time_ms": str(int(time.time() * 1000) - 1000),
        "fee": "0",
        "fee_currency": "USDT",
        "point_fee": "0.1" if fault == "point fees" else "0",
        "trade_quote": "USDC" if fault == "quote currency" else "USDT",
    }
    monkeypatch.setattr(adapter._exchange, "privateSpotGetMyTrades", lambda _: [row])
    with pytest.raises(ccxt.ExchangeError):
        adapter.fetch_order_fill_page(order_id, "BTC/USDT", {})


def test_htx_discovery_resumes_account_open_pages_and_selected_recent_windows(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    account, adapter = save_htx(owner)
    native = adapter._exchange
    requests = []
    closed = htx_order(2**60 + 18, state="filled", **{"filled-amount": "0.01", "filled-cash-amount": "500"})

    def opened(params):
        requests.append(("open", params))
        assert params["account-id"] == "1234" and params["direct"] == "next"
        return {
            "status": "ok",
            "data": [] if "from" in params else [htx_order(), htx_order(2**60 + 19, type="buy-stop-limit")],
        }

    def history(params):
        requests.append(("recent", params))
        assert params["end-time"] - params["start-time"] < 2 * 86_400_000
        return {
            "status": "ok",
            "data": [closed] if params["start-time"] <= closed["created-at"] <= params["end-time"] else [],
        }

    monkeypatch.setattr(native, "spotPrivateGetV1OrderOpenOrders", opened)
    monkeypatch.setattr(native, "spotPrivateGetV1OrderOrders", history)
    service = owner.trading
    service.discovery.enqueue(OrderDiscoveryRequest(account_id=account.id, days=3, symbols=["BTC/USDT"]))
    advance(service, account)
    assert job(service, account)["cursor"]["after"] == str(2**60 + 19)
    resumed = ExchangeTrading(owner.market, owner.store)
    for _ in range(3):
        advance(resumed, account)
    assert job(resumed, account)["complete"] and job(resumed, account)["skipped"] == 1
    monitor = resumed.monitor(account_id=account.id)
    assert monitor["total"] == 2 and all(order["read_only"] for order in monitor["items"])
    assert requests[1][1]["from"] == str(2**60 + 19)
    assert requests[2][1]["end-time"] + 1 == requests[3][1]["start-time"]
    monkeypatch.setattr(
        native, "spotPrivateGetV1OrderOrdersOrderId", lambda _: {"status": "ok", "data": closed}
    )
    monkeypatch.setattr(
        native,
        "spotPrivateGetV1OrderOrdersOrderIdMatchresults",
        lambda _: {
            "status": "ok",
            "data": [htx_fill(**{"order-id": closed["id"]})],
        },
    )
    executed = next(order for order in monitor["items"] if order["status"] == "closed")
    detail = resumed.reconciliation.sync(executed["id"], manual=True)
    assert detail["reconciliation"]["status"] == "matched"
    assert detail["reconciliation"]["fees"] == [{"currency": "USDT", "cost": 0.2}]
    assert owner.account_sync.ledger.fills(account_id=account.id)["total"] == 1


def test_htx_client_id_recovery_never_repeats_the_uncertain_write(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    owner.settings.allow_live_trading = True
    account, adapter = save_htx(owner)
    native, writes = adapter._exchange, []
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 10_000}})

    def submit_order(symbol, kind, side, quantity, price, *, params):
        assert params["account-id"] == "1234" and params["source"] == "spot-api"
        writes.append(params["clientOrderId"])
        raise ccxt.RequestTimeout("PRIVATE")

    def details(params):
        assert params == {"clientOrderId": writes[0]}
        return {"status": "ok", "data": htx_order(**{"client-order-id": writes[0]})}

    monkeypatch.setattr(native, "create_order", submit_order)
    monkeypatch.setattr(native, "spotPrivateGetV1OrderOrdersGetClientOrder", details)
    uncertain = submit(owner.trading, account)
    assert uncertain["status"] == "unknown"
    owner.settings.allow_live_trading = False
    resumed = ExchangeTrading(owner.market, owner.store)
    recovered = resumed.recover(uncertain["id"])
    assert recovered["recovery"]["state"] == "found" and recovered["exchange_order_id"] == str(2**60 + 20)
    assert len(writes) == 1 and "PRIVATE" not in json.dumps(recovered)


def test_htx_exact_fills_page_by_internal_id_and_keep_fee_deductions_unknown(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    _, adapter = save_htx(owner)
    native, identity = adapter._exchange, str(2**60 + 20)
    monkeypatch.setattr(
        native, "spotPrivateGetV1OrderOrdersOrderId", lambda _: {"status": "ok", "data": htx_order()}
    )
    rows = [htx_fill(2**60 + value) for value in range(101)]
    rows[-1].update({"fee-deduct-currency": "ht", "fee-deduct-state": "ongoing", "filled-points": "0.01"})
    monkeypatch.setattr(
        native, "spotPrivateGetV1OrderOrdersOrderIdMatchresults", lambda _: {"status": "ok", "data": rows}
    )
    first = adapter.fetch_order_fill_page(identity, "BTC/USDT", {}, 100)
    final = adapter.fetch_order_fill_page(identity, "BTC/USDT", first.cursor, 100)
    assert len(first.items) == 100 and not first.caught_up and len(final.items) == 1 and final.caught_up
    assert first.items[0]["id"] == str(2**60)  # The SDK's trade-id is not the account execution ID.
    assert first.items[0]["fees"] == [{"currency": "USDT", "cost": 0.2}]
    assert final.items[0]["fee"] == {"currency": None, "cost": None}


@pytest.mark.parametrize("fault", ["wallet", "symbol", "order", "duplicate"])
def test_htx_rejects_mismatched_parent_and_individual_fills(manual_client, monkeypatch, fault):
    owner = manual_client.app.state.services
    _, adapter = save_htx(owner)
    native = adapter._exchange
    parent = htx_order(**({"account-id": 4321} if fault == "wallet" else {}))
    row = htx_fill(
        **({"symbol": "ethusdt"} if fault == "symbol" else {"order-id": 99} if fault == "order" else {})
    )
    monkeypatch.setattr(
        native, "spotPrivateGetV1OrderOrdersOrderId", lambda _: {"status": "ok", "data": parent}
    )
    monkeypatch.setattr(
        native,
        "spotPrivateGetV1OrderOrdersOrderIdMatchresults",
        lambda _: {"status": "ok", "data": [row, row] if fault == "duplicate" else [row]},
    )
    with pytest.raises(ccxt.ExchangeError):
        adapter.fetch_order_fill_page(str(2**60 + 20), "BTC/USDT", {})


def test_capability_catalog_distinguishes_exact_order_fills_from_account_history():
    providers = {row["id"]: row for row in provider_catalog()["items"]}
    for name in ("gate", "htx"):
        features = {
            feature["id"]: feature for group in providers[name]["support"] for feature in group["features"]
        }
        assert features["fill_reconciliation"]["status"] == "available"
        assert features["history_import"]["status"] == "available"
        assert features["automated"]["status"] == "pending"
        assert providers[name]["history_import"] is not None


def test_htx_open_pages_accept_an_inclusive_boundary_and_reject_wallet_changes(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    _, adapter = save_htx(owner)
    native = adapter._exchange
    rows = [htx_order(100), htx_order(99)]
    monkeypatch.setattr(native, "spotPrivateGetV1OrderOpenOrders", lambda _: {"status": "ok", "data": rows})
    end = int(time.time() * 1000)
    first = adapter.fetch_account_order_page("open", {"after": "100", "account": "1234"}, end - 1000, end, [])
    assert [row["id"] for row in first.items] == ["99"] and first.cursor["after"] == "99"
    rows[:] = [htx_order(99)]
    final = adapter.fetch_account_order_page("open", first.cursor, end - 1000, end, [])
    assert final.complete and final.items == []
    native.accounts = [{"id": "5678", "type": "spot"}]
    with pytest.raises(ccxt.ExchangeError, match="wallet changed"):
        adapter.fetch_account_order_page("open", first.cursor, end - 1000, end, [])


def test_htx_capped_recent_window_splits_without_skipping_timestamp_ties(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    _, adapter = save_htx(owner)
    native = adapter._exchange
    end = int(time.time() * 1000)
    row = htx_order(state="filled", **{"created-at": end - 1})
    monkeypatch.setattr(
        native, "spotPrivateGetV1OrderOrders", lambda _: {"status": "ok", "data": [row] * 100}
    )
    split = adapter.fetch_account_order_page("recent", {}, end - 1000, end, ["BTC/USDT"])
    assert not split.complete and split.items == [] and len(split.cursor["windows"]) == 2
    with pytest.raises(ccxt.NotSupported, match="timestamp"):
        adapter.fetch_account_order_page("recent", {}, end - 1, end, ["BTC/USDT"])


@pytest.mark.parametrize(
    "kind,tif", [("buy-ioc", "IOC"), ("sell-limit-fok", "FOK"), ("buy-limit-maker", "PO")]
)
def test_htx_preserves_native_limit_instructions_in_order_details(manual_client, monkeypatch, kind, tif):
    owner = manual_client.app.state.services
    _, adapter = save_htx(owner)
    native = adapter._exchange
    row = htx_order(type=kind)
    monkeypatch.setattr(native, "fetch_order", lambda *_: native.parse_order(row, native.market("BTC/USDT")))
    order = adapter.fetch_order(str(row["id"]), "BTC/USDT")
    assert order["type"] == "limit" and order["timeInForce"] == tif
