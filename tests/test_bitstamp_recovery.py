"""Recover a resting Bitstamp limit with original terms from native account reads."""

from datetime import UTC, datetime

import ccxt
import pytest
from test_expanded_order_adapters import saved_account
from test_order_management import submit

from sibyl.exchanges.bitstamp_orders import lookup_order
from sibyl.services.trading.service import ExchangeTrading

CLIENT_ID = "135d8630-4dcc-4bfe-8918-41555302a029"
ORDER_ID = 2**60 + 9


def evidence(client_id=CLIENT_ID):
    """Use the sparse detail and richer open-list contracts with a partially filled order."""
    status = {
        "id": ORDER_ID,
        "client_order_id": client_id,
        "market": "BTC/USDT",
        "type": "0",
        "subtype": "LIMIT",
        "status": "Open",
        "datetime": datetime.now(UTC).isoformat(timespec="seconds"),
        "amount_remaining": "0.006",
        "transactions": [],
    }
    return status, {**status, "amount": "0.006", "amount_at_create": "0.01", "price": "50000"}


@pytest.fixture
def bitstamp(manual_client):
    owner = manual_client.app.state.services
    account, adapter = saved_account(owner, "bitstamp", "btcusdt")
    return owner, account, adapter


def test_lost_response_recovers_original_size_after_restart_without_resubmitting(bitstamp, monkeypatch):
    owner, account, adapter = bitstamp
    owner.settings.allow_live_trading = True
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 10000}})
    writes, reads = [], []

    def transport(path, api, method, params, *args, **kwargs):
        if path == "buy/{pair}/":
            writes.append(params.copy())
            raise ccxt.RequestTimeout("PRIVATE")
        reads.append((path, params.copy()))
        status, opened = evidence(writes[0]["client_order_id"])
        if path == "order_status/":
            return status
        if path == "open_orders/{pair}/":
            return [opened]
        pytest.fail(f"Unexpected native request {path}")

    monkeypatch.setattr(adapter._exchange, "fetch2", transport)
    intent = submit(owner.trading, account)
    assert intent["status"] == "unknown"
    assert owner.trading.reconciliation.detail(intent["id"])["order"]["recovery"]["supported"]

    owner.settings.allow_live_trading = False
    restarted = ExchangeTrading(owner.market, owner.store)
    restored = restarted.recover(intent["id"])
    assert restored["recovery"]["state"] == "found"
    assert restored["status"] == "open" and restored["exchange_order_id"] == str(ORDER_ID)
    assert reads[:2] == [
        ("order_status/", {"client_order_id": intent["client_order_id"], "omit_transactions": "True"}),
        ("open_orders/{pair}/", {"pair": "btcusdt"}),
    ]
    assert len(writes) == 1 and restored.get("filled") is None


@pytest.mark.parametrize(
    "changes",
    [
        {"id": ORDER_ID + 1},
        {"market": "ETH/USDT"},
        {"type": "1"},
        {"margin_mode": "ISOLATED"},
        {"ioc_order": True},
        {"limit_price": "50000"},
        {"moc_order": True},
        {"amount_at_create": None},
        {"datetime": "2020-01-01 00:00:00"},
    ],
)
def test_open_snapshot_requires_same_order_and_original_terms(bitstamp, monkeypatch, changes):
    _, _, adapter = bitstamp
    status, row = evidence()
    monkeypatch.setattr(adapter._exchange, "privatePostOrderStatus", lambda _: status)
    monkeypatch.setattr(adapter._exchange, "privatePostOpenOrdersPair", lambda _: [{**row, **changes}])
    with pytest.raises(ValueError, match="differs"):
        lookup_order(adapter._exchange, CLIENT_ID, "BTC/USDT")


def test_snapshot_miss_can_retry_but_duplicate_client_ids_require_review(bitstamp, monkeypatch):
    _, _, adapter = bitstamp
    status, row = evidence()
    monkeypatch.setattr(adapter._exchange, "privatePostOrderStatus", lambda _: status)
    monkeypatch.setattr(adapter._exchange, "privatePostOpenOrdersPair", lambda _: [])
    assert lookup_order(adapter._exchange, CLIENT_ID, "BTC/USDT") == []
    monkeypatch.setattr(
        adapter._exchange, "privatePostOpenOrdersPair", lambda _: [row, {**row, "id": ORDER_ID + 1}]
    )
    with pytest.raises(ValueError, match="duplicate"):
        lookup_order(adapter._exchange, CLIENT_ID, "BTC/USDT")


def test_closed_lookup_does_not_substitute_remaining_for_original_amount(bitstamp, monkeypatch):
    _, _, adapter = bitstamp
    status, _ = evidence()
    monkeypatch.setattr(
        adapter._exchange, "privatePostOrderStatus", lambda _: {**status, "status": "Finished"}
    )
    monkeypatch.setattr(adapter._exchange, "privatePostOpenOrdersPair", lambda _: pytest.fail("Closed order"))
    with pytest.raises(ValueError, match="closed"):
        lookup_order(adapter._exchange, CLIENT_ID, "BTC/USDT")


def test_market_intent_shows_lookup_as_unavailable_and_never_calls_bitstamp(bitstamp, monkeypatch):
    owner, account, adapter = bitstamp
    owner.settings.allow_live_trading = True
    monkeypatch.setattr(adapter, "fetch_balance", lambda: {"free": {"USDT": 10000}})
    monkeypatch.setattr(adapter, "fetch_ticker", lambda _: {"ask": 50000})

    def timeout(*args, **kwargs):
        raise ccxt.RequestTimeout("PRIVATE")

    monkeypatch.setattr(adapter._exchange, "create_order", timeout)
    intent = submit(owner.trading, account, order_type="market", limit_price=None)
    assert intent["status"] == "unknown"
    assert not owner.trading.reconciliation.detail(intent["id"])["order"]["recovery"]["supported"]
    monkeypatch.setattr(
        adapter._exchange, "privatePostOrderStatus", lambda _: pytest.fail("Unsupported market lookup")
    )
    assert owner.trading.recover(intent["id"])["recovery"]["state"] == "unsupported"
