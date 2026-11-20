"""Gemini closed-order snapshots include actual unfilled cancellations and explicit cap limits."""

import time

import ccxt
import pytest
from test_expanded_order_adapters import saved_account
from test_order_discovery import advance, job
from test_order_recovery import gemini_order

from sibyl.services.trading.discovery import OrderDiscoveryRequest
from sibyl.services.trading.service import ExchangeTrading


def test_recent_native_history_retains_unfilled_cancelled_orders_after_restart(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    account, adapter = saved_account(owner, "gemini", "btcusd", quote="USD")
    native, requests = adapter._exchange, []
    parent = gemini_order(is_live=False, is_cancelled=True, timestampms=int(time.time() * 1000) - 1000)
    monkeypatch.setattr(native, "privatePostV1Orders", lambda _: [])

    def read(path, api, method, params):
        requests.append((path, api, method, params.copy()))
        return [parent]

    monkeypatch.setattr(native, "request", read)
    owner.trading.discovery.enqueue(OrderDiscoveryRequest(account_id=account.id))
    advance(owner.trading, account)
    restarted = ExchangeTrading(owner.market, owner.store)
    advance(restarted, account)
    assert job(restarted, account)["complete"]
    (saved,) = restarted.monitor(account_id=account.id)["items"]
    assert saved["status"] == "canceled" and saved["filled"] == 0 and saved["read_only"]
    assert requests[0][:3] == ("v1/orders/history", "private", "POST")
    assert requests[0][3]["limit_orders"] == 500


def test_saturated_native_snapshot_reports_coverage_limit(manual_client, monkeypatch):
    owner = manual_client.app.state.services
    _, adapter = saved_account(owner, "gemini", "btcusd", quote="USD")
    monkeypatch.setattr(adapter._exchange, "request", lambda *_: [gemini_order(is_live=False)] * 500)
    end = int(time.time() * 1000)
    with pytest.raises(ccxt.NotSupported, match="capacity"):
        adapter.fetch_account_order_page("recent", {}, end - 10000, end, [])
