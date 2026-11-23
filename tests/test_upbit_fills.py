"""Upbit native UUID executions retain honest fee gaps and checkpoint parent discovery."""

from itertools import pairwise
from uuid import UUID

import ccxt
import pytest
from test_upbit_orders import order
from test_upbit_orders import upbit as upbit

from sibyl.services.accounts.sync import AccountSync


def fill(identity=100, **changes):
    return {
        "uuid": str(UUID(int=identity)),
        "market": "USDT-BTC",
        "side": "bid",
        "price": "50000",
        "volume": "0.01",
        "funds": "500",
        "created_at": order()["created_at"],
        **changes,
    }


def test_exact_execution_fees_stay_unknown_instead_of_allocating_paid_fee(upbit, monkeypatch):
    _, _, adapter = upbit
    parent = order(
        state="done",
        executed_volume="0.01",
        remaining_volume="0",
        paid_fee="0.25",
        trades_count=1,
        trades=[fill()],
    )
    monkeypatch.setattr(
        adapter._exchange,
        "privateGetOrder",
        lambda params: parent if params == {"uuid": parent["uuid"]} else None,
    )
    page = adapter.fetch_order_fill_page(parent["uuid"], "BTC/USDT", {})
    assert page.caught_up and page.items[0]["id"] == fill()["uuid"]
    assert page.items[0]["fee"] == {"currency": None, "cost": None} and page.items[0]["cost"] == 500


def test_history_resumes_order_uuids_and_deduplicates_open_to_closed_transition(upbit, monkeypatch):
    owner, account, adapter = upbit
    native, reads = adapter._exchange, []
    parent = order(
        state="done",
        executed_volume="0.01",
        remaining_volume="0",
        paid_fee="0.25",
        trades_count=1,
        trades=[fill()],
    )
    monkeypatch.setattr(
        native, "privateGetOrdersOpen", lambda params: reads.append(params.copy()) or [order()]
    )

    def closed(params):
        reads.append(params.copy())
        stamp = native.parse8601(parent["created_at"])
        return [parent] if int(params["start_time"]) <= stamp <= int(params["end_time"]) else []

    monkeypatch.setattr(native, "privateGetOrdersClosed", closed)
    monkeypatch.setattr(native, "privateGetOrder", lambda _: parent)
    owner.account_sync.enqueue(account, ["BTC/USDT"])
    owner.account_sync.tick()
    restarted = AccountSync(owner.market, owner.store)
    for _ in range(6):
        restarted.tick()
    assert restarted.snapshot()["jobs"][0]["status"] == "caught_up", restarted.snapshot()["jobs"]
    assert restarted.ledger.fills(account_id=account.id)["total"] == 1
    assert all(row["market"] == "USDT-BTC" for row in reads)
    windows = [row for row in reads if "start_time" in row]
    assert len(windows) == 5
    assert all(int(a["end_time"]) + 1 == int(b["start_time"]) for a, b in pairwise(windows))
    assert not native.has["fetchMyTrades"]  # Explicit native order reads do not forge SDK capability.


@pytest.mark.parametrize("change", [{"market": "KRW-BTC"}, {"side": "ask"}, {"uuid": str(UUID(int=999))}])
def test_exact_parent_mismatches_are_rejected(upbit, monkeypatch, change):
    _, _, adapter = upbit
    monkeypatch.setattr(
        adapter._exchange,
        "privateGetOrder",
        lambda _: order(**{"trades_count": 1, "trades": [fill()], **change}),
    )
    with pytest.raises(ccxt.ExchangeError, match="parent|execution"):
        adapter.fetch_order_fill_page(order()["uuid"], "BTC/USDT", {})


def test_incomplete_native_trade_list_is_not_declared_caught_up(upbit, monkeypatch):
    _, _, adapter = upbit
    monkeypatch.setattr(
        adapter._exchange, "privateGetOrder", lambda _: order(trades_count=2, trades=[fill()])
    )
    with pytest.raises(ccxt.NotSupported, match="incomplete"):
        adapter.fetch_order_fill_page(order()["uuid"], "BTC/USDT", {})
