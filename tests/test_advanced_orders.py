"""Native conditional/list/replacement admission, race and uncertain-write contracts.

Scripted exchanges exercise the real durable services. Request capture separately
checks the actual installed CCXT transport; neither counts as authenticated venue acceptance.
"""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import ccxt
import pytest
from test_exchange_spot_support import MARKET, Captured
from test_exchange_trading import FakeExchange

from sibyl.exchanges import create_client
from sibyl.exchanges.history import TradePage
from sibyl.exchanges.order_lookup import OrderLookupPage
from sibyl.models import ConnectionCreate, ExchangeOrderRequest
from sibyl.services.trading.advanced.contracts import OCORequest, ReplaceRequest
from sibyl.services.trading.advanced.replacement import preview_replacement
from sibyl.services.trading.service import ExchangeTrading


class Venue(FakeExchange):
    """Deterministic venue with independently observable native orders and fees."""

    def __init__(self):
        super().__init__()
        self.orders, self.fees = {}, {}
        self.lists = self.replacements = 0
        self.lose_list = self.lose_replace = False
        self.partial_on_replace = False
        self.fail_new = False

    def close(self):
        pass

    def price_to_precision(self, symbol, price):
        return f"{price:.2f}"

    def advanced_support(self, symbol):
        return {"types": ["stop_loss_limit", "take_profit_limit"], "oco": True, "replace": True}

    def create_order(self, symbol, kind, side, quantity, params=None, *, price=None):
        self.calls += 1
        identity = str(self.calls)
        row = {
            "id": identity,
            "clientOrderId": params["clientOrderId"],
            "symbol": symbol,
            "type": kind,
            "side": side,
            "amount": quantity,
            "filled": 0,
            "remaining": quantity,
            "price": price,
            "triggerPrice": params.get("triggerPrice"),
            "cost": 0,
            "status": "open",
            "timestamp": datetime.now(UTC).timestamp() * 1000,
            "timeInForce": "GTC",
        }
        self.orders[identity] = row
        return dict(row)

    def fetch_order(self, identity, symbol):
        return dict(self.orders[identity])

    def create_oco(self, symbol, side, amount, take, stop, limit, group, take_id, stop_id):
        self.lists += 1
        rows = [
            self.create_order(
                symbol,
                "take_profit_limit",
                side,
                amount,
                {"clientOrderId": take_id, "triggerPrice": take},
                price=take,
            ),
            self.create_order(
                symbol,
                "stop_loss_limit",
                side,
                amount,
                {"clientOrderId": stop_id, "triggerPrice": stop},
                price=limit,
            ),
        ]
        if self.lose_list:
            raise ccxt.RequestTimeout("SECRET-NATIVE-PAYLOAD")
        return {"id": "list-1", "client_id": group, "orders": rows}

    def cancel_replace(self, symbol, old_id, side, amount, price, new_id):
        self.replacements += 1
        if self.partial_on_replace:
            self.orders[old_id].update(filled=0.001, remaining=0.009)
            raise ccxt.InvalidOrder("ONLY_NEW restriction failed")
        old = self.orders[old_id]
        old["status"] = "canceled"
        result = (
            None
            if self.fail_new
            else self.create_order(symbol, "limit", side, amount, {"clientOrderId": new_id}, price=price)
        )
        if self.lose_replace:
            raise ccxt.RequestTimeout("SECRET-NATIVE-PAYLOAD")
        return {
            "cancel_result": "SUCCESS",
            "canceled": dict(old),
            "new_result": "FAILURE" if self.fail_new else "SUCCESS",
            "order": result,
        }

    def fetch_order_lookup_page(self, client_id, symbol, cursor, start, end):
        return OrderLookupPage(
            [dict(row) for row in self.orders.values() if row["clientOrderId"] == client_id], {}, True
        )

    def fetch_order_fill_page(self, order_id, symbol, cursor, limit=100):
        return TradePage(self.fees.get(order_id, []), {}, True)


@pytest.fixture
def venue(manual_client):
    owner = manual_client.app.state.services
    owner.settings.allow_live_trading = True
    connection = owner.store.add_connection(
        ConnectionCreate(exchange="binance-testnet", label="Isolated test", api_key="FAKE", secret="FAKE")
    )
    fake = Venue()
    owner.market._clients[connection.id] = fake
    return owner.trading, fake, connection


def conditional(connection, **changes):
    return ExchangeOrderRequest(
        **{
            "connection_id": connection.id,
            "side": "sell",
            "quantity": 0.01,
            "order_type": "stop_loss_limit",
            "limit_price": 48000,
            "trigger_price": 49000,
            "idempotency_key": uuid4().hex,
            **changes,
        }
    )


def linked(connection, **changes):
    return OCORequest(
        **{
            "connection_id": connection.id,
            "side": "sell",
            "quantity": 0.01,
            "take_profit_price": 55000,
            "trigger_price": 49000,
            "limit_price": 48000,
            "idempotency_key": uuid4().hex,
            **changes,
        }
    )


def original_order(owner, connection):
    preview = owner.preview(conditional(connection, order_type="limit", trigger_price=None))
    return owner.execute(preview["id"], preview["confirmation"])


def test_conditional_review_and_confirmation_preserve_native_trigger(venue):
    owner, native, connection = venue
    preview = owner.preview(conditional(connection))
    assert native.calls == 0
    result = owner.execute(preview["id"], preview["confirmation"])
    row = native.orders[result["exchange_order_id"]]
    assert (row["type"], row["price"], row["triggerPrice"], row["amount"]) == (
        "stop_loss_limit",
        48000,
        49000,
        0.01,
    )
    assert result["filled"] == 0 and result["status"] == "open"


@pytest.mark.parametrize(
    "changes",
    [
        {"trigger_price": 51000},
        {"trigger_price": 49000.001},
        {"limit_price": 49500},
        {"order_type": "take_profit_limit", "trigger_price": 49000},
        {"side": "buy", "trigger_price": 49000},
    ],
)
def test_invalid_conditional_review_cannot_write(venue, changes):
    owner, native, connection = venue
    with pytest.raises(ValueError):
        owner.preview(conditional(connection, **changes))
    assert native.calls == 0


def test_oco_concurrent_confirmations_submit_one_native_list(venue):
    owner, native, connection = venue
    preview = owner.advanced.preview(linked(connection))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda _: owner.advanced.execute(preview["id"], preview["confirmation"]), range(6))
        )
    assert native.lists == 1 and native.calls == 2
    assert all(result["status"] == "submitted" for result in results)
    assert all(
        order["status"] == "open" and order["oco_group_id"] == preview["id"] for order in results[0]["orders"]
    )
    child = results[0]["orders"][0]
    with pytest.raises(ValueError, match="linked list"):
        owner.execute(child["id"], child["confirmation"])


def test_lost_oco_response_recovers_each_child_without_resubmission(venue):
    owner, native, connection = venue
    preview = owner.advanced.preview(linked(connection))
    native.lose_list = True
    result = owner.advanced.execute(preview["id"], preview["confirmation"])
    assert result["status"] == "unknown"
    assert "SECRET" not in str(result)
    restarted = ExchangeTrading(owner.market, owner.store)
    repeated = restarted.advanced.execute(preview["id"], preview["confirmation"])
    assert repeated["status"] == "unknown" and native.lists == 1
    for child in result["orders"]:
        recovered = restarted.recovery.check(child["id"], manual=True)
        assert recovered["exchange_order_id"] in native.orders
        assert (
            recovered["request"]["trigger_price"]
            == native.orders[recovered["exchange_order_id"]]["triggerPrice"]
        )
    assert native.lists == 1


def test_recovery_rejects_changed_conditional_trigger(venue):
    owner, native, connection = venue
    preview = owner.advanced.preview(linked(connection))
    native.lose_list = True
    result = owner.advanced.execute(preview["id"], preview["confirmation"])
    child = result["orders"][0]
    next(row for row in native.orders.values() if row["clientOrderId"] == child["client_order_id"])[
        "triggerPrice"
    ] += 1
    assert owner.recovery.check(child["id"], manual=True).get("exchange_order_id") is None


def test_oco_native_partial_fill_and_sibling_cancel_are_independent_observations(venue):
    owner, native, connection = venue
    preview = owner.advanced.preview(linked(connection))
    group = owner.advanced.execute(preview["id"], preview["confirmation"])
    take, stop = group["orders"]
    native.orders[take["exchange_order_id"]].update(filled=0.004, remaining=0.006, cost=220)
    native.orders[stop["exchange_order_id"]]["status"] = "canceled"
    owner.lifecycle.refresh(take["id"])
    owner.lifecycle.refresh(stop["id"])
    observed = owner.advanced.detail(group["id"])["orders"]
    assert observed[0]["filled"] == 0.004 and observed[0]["status"] == "open"
    assert observed[1]["status"] == "canceled" and observed[1]["filled"] == 0


def test_replacement_is_one_native_attempt_and_both_records_survive(venue):
    owner, native, connection = venue
    original = original_order(owner, connection)
    preview = preview_replacement(
        owner, original["id"], ReplaceRequest(quantity=0.02, limit_price=47000, idempotency_key=uuid4().hex)
    )
    assert native.replacements == 0
    result = owner.execute(preview["id"], preview["confirmation"])
    assert result["status"] == "open" and result["replacement_of"] == original["id"]
    assert owner.lifecycle.refresh(original["id"])["status"] == "canceled"
    owner.execute(preview["id"], preview["confirmation"])
    assert native.replacements == 1


@pytest.mark.parametrize(
    "lost,partial,failed_new", [(True, False, False), (False, True, False), (False, False, True)]
)
def test_replacement_ambiguous_or_partial_outcome_never_retries(venue, lost, partial, failed_new):
    owner, native, connection = venue
    original = original_order(owner, connection)
    preview = preview_replacement(
        owner, original["id"], ReplaceRequest(quantity=0.02, limit_price=47000, idempotency_key=uuid4().hex)
    )
    native.lose_replace, native.partial_on_replace, native.fail_new = lost, partial, failed_new
    result = owner.execute(preview["id"], preview["confirmation"])
    assert result["status"] == "unknown" and "SECRET" not in str(result)
    owner.execute(preview["id"], preview["confirmation"])
    assert native.replacements == 1
    old = owner.lifecycle.refresh(original["id"])
    assert old["status"] == ("open" if partial else "canceled")
    if lost:
        assert owner.recovery.check(result["id"], manual=True)["exchange_order_id"] in native.orders


def test_partial_fill_after_review_blocks_replacement_before_native_write(venue):
    owner, native, connection = venue
    original = original_order(owner, connection)
    review = preview_replacement(
        owner, original["id"], ReplaceRequest(quantity=0.02, limit_price=47000, idempotency_key=uuid4().hex)
    )
    native.orders[original["exchange_order_id"]].update(filled=0.001, remaining=0.009)
    with pytest.raises(ValueError, match="wholly unfilled"):
        owner.execute(review["id"], review["confirmation"])
    assert native.replacements == 0


def test_http_oco_and_provider_capabilities_match_implemented_paths(venue, manual_client):
    owner, native, connection = venue
    capabilities = manual_client.get(f"/api/v1/connections/{connection.id}/order-capabilities").json()
    assert capabilities["oco"] and capabilities["replace"]
    response = manual_client.post(
        "/api/v1/exchange-order-lists/preview", json=linked(connection).model_dump()
    )
    assert response.status_code == 200, response.text
    group = response.json()
    response = manual_client.post(
        f"/api/v1/exchange-order-lists/{group['id']}/confirm", json={"confirmation": group["confirmation"]}
    )
    assert response.status_code == 200 and response.json()["status"] == "submitted"


@pytest.mark.parametrize("provider", ["binance", "binance-testnet"])
@pytest.mark.parametrize("operation", ["stop", "take", "oco", "replace"])
def test_installed_sdk_uses_reviewed_native_spot_endpoints(monkeypatch, provider, operation):
    client = create_client(provider, credentials={"apiKey": "FAKE", "secret": "FAKE"})
    market = deepcopy(MARKET)
    market["info"].update(
        orderTypes=["LIMIT", "MARKET", "STOP_LOSS_LIMIT", "TAKE_PROFIT_LIMIT"],
        ocoAllowed=True,
        cancelReplaceAllowed=True,
    )
    client._exchange.set_markets([market])
    requests = []

    def capture(path, api="public", method="GET", params=None, *a, **kw):
        requests.append((path, method, params))
        raise Captured

    monkeypatch.setattr(client._exchange, "fetch2", capture)
    try:
        with pytest.raises(Captured):
            if operation in {"stop", "take"}:
                client.create_order(
                    "BTC/USDT",
                    "stop_loss_limit" if operation == "stop" else "take_profit_limit",
                    "sell",
                    0.01,
                    {"clientOrderId": "child-id", "triggerPrice": 49000},
                    price=48000,
                )
            elif operation == "oco":
                client.create_oco(
                    "BTC/USDT", "sell", 0.01, 55000, 49000, 48000, "list-id", "take-id", "stop-id"
                )
            else:
                client.cancel_replace("BTC/USDT", "1234", "buy", 0.01, 47000, "new-id")
        assert len(requests) == 1
        path, method, params = requests[0]
        assert (
            path
            == {"stop": "order", "take": "order", "oco": "orderList/oco", "replace": "order/cancelReplace"}[
                operation
            ]
        )
        assert method == "POST" and params["symbol"] == "BTCUSDT" and params["quantity"] == "0.01"
        if operation == "replace":
            assert (
                params["cancelReplaceMode"] == "STOP_ON_FAILURE"
                and params["cancelRestrictions"] == "ONLY_NEW"
            )
        if operation == "oco":
            assert params["aboveClientOrderId"] == "take-id" and params["belowClientOrderId"] == "stop-id"
        if operation in {"stop", "take"}:
            assert params["stopPrice"] == "49000" and params["timeInForce"] == "GTC"
    finally:
        client.close()


def test_oco_leg_late_fee_correction_reuses_shared_ledger_without_another_order(venue):
    from test_order_reconciliation import execution

    from sibyl.services.accounts.ledger import AccountLedger

    owner, native, connection = venue
    preview = owner.advanced.preview(linked(connection))
    group = owner.advanced.execute(preview["id"], preview["confirmation"])
    child = group["orders"][0]
    native_id = child["exchange_order_id"]
    native.orders[native_id].update(status="closed", filled=0.01, remaining=0, cost=550, average=55000)
    owner.lifecycle.refresh(child["id"])
    fill = execution(
        "oco-fill",
        order=native_id,
        side="sell",
        timestamp=int(datetime.now(UTC).timestamp() * 1000),
        price=55000,
        cost=550,
        fees=[],
    )
    native.fees[native_id] = [fill]
    missing = owner.reconciliation.sync(child["id"], manual=True)
    assert missing["reconciliation"]["status"] == "fees_missing"
    native.fees[native_id] = [{**fill, "fees": [{"currency": "USDT", "cost": 0.55}]}]
    corrected = owner.reconciliation.sync(child["id"], manual=True)
    assert corrected["reconciliation"]["status"] == "matched"
    assert corrected["reconciliation"]["fees"] == [{"currency": "USDT", "cost": 0.55}]
    owner.reconciliation.sync(child["id"], manual=True)
    assert AccountLedger(owner.store, recover=False).fills(account_id=connection.id)["total"] == 1
    assert native.lists == 1 and native.calls == 2


def test_deactivated_account_cannot_confirm_an_existing_oco_review(venue):
    owner, native, connection = venue
    preview = owner.advanced.preview(linked(connection))
    owner.store.activate_account(connection.id, False)
    with pytest.raises(ValueError, match="active"):
        owner.advanced.execute(preview["id"], preview["confirmation"])
    assert native.lists == 0


def test_failed_second_oco_leg_review_leaves_no_orphan_child(venue):
    owner, native, connection = venue
    with pytest.raises(ValueError):
        owner.advanced.preview(linked(connection, trigger_price=51000))
    with owner.store.db() as db:
        assert db.execute("SELECT COUNT(*) FROM exchange_orders").fetchone()[0] == 0
    assert native.lists == 0


@pytest.mark.parametrize("response_loss", [False, True])
def test_oco_acknowledgment_keeps_newer_concurrent_recovery_fill_evidence(venue, monkeypatch, response_loss):
    owner, native, connection = venue
    review = owner.advanced.preview(linked(connection))
    submit = native.create_oco

    def concurrent_read(*args):
        result = submit(*args)
        first = result["orders"][0]
        native.orders[first["id"]].update(filled=0.004, remaining=0.006, cost=220)
        recovered = owner.recovery.check(review["orders"][0]["id"], manual=True)
        assert recovered["filled"] == 0.004
        if response_loss:
            raise ccxt.RequestTimeout("Controlled loss after independent native observation")
        return result  # original acknowledgment still reports zero fills

    monkeypatch.setattr(native, "create_oco", concurrent_read)
    result = owner.advanced.execute(review["id"], review["confirmation"])
    assert result["status"] == ("unknown" if response_loss else "submitted")
    assert result["orders"][0]["filled"] == 0.004 and result["orders"][0]["cost"] == 220
    assert native.lists == 1


@pytest.mark.parametrize("response_loss", [False, True])
def test_single_order_acknowledgment_keeps_newer_concurrent_recovery_fill_evidence(
    venue, monkeypatch, response_loss
):
    owner, native, connection = venue
    review = owner.preview(conditional(connection))
    submit = native.create_order

    def concurrent_read(*args, **kwargs):
        result = submit(*args, **kwargs)
        native.orders[result["id"]].update(filled=0.004, remaining=0.006, cost=192)
        assert owner.recovery.check(review["id"], manual=True)["filled"] == 0.004
        if response_loss:
            raise ccxt.RequestTimeout("Controlled loss after independent native observation")
        return result

    monkeypatch.setattr(native, "create_order", concurrent_read)
    result = owner.execute(review["id"], review["confirmation"])
    assert result["filled"] == 0.004 and result["cost"] == 192 and result["status"] == "open"
    assert native.calls == 1
