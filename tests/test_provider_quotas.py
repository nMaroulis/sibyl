"""Reviewed budgets and actual native SDK signing/transport, with no external network."""

import json
import time
from email.utils import formatdate
from http import HTTPStatus
from urllib.parse import urlsplit

import ccxt
import pytest
import requests
from test_provider_control import source

from sibyl.exchanges.providers import BinanceClient, CoinbaseSandboxClient, KrakenClient
from sibyl.market_data.control import ProviderControl, ProviderDeferred
from sibyl.market_data.quotas.budgets import Quotas
from sibyl.market_data.quotas.policies import request

WALL = 1704067200.0


def state(identity="one"):
    return {"generation": identity}


def record(pool, call, meta=None, owner=None, wall=WALL, mono=100, bypass=False, headers=None, result=None):
    meta = meta or source()
    owner = owner or state()
    receipt = pool.charge(meta, owner, call, mono, wall, bypass=bypass)
    pool.observe(receipt, headers, result, mono, wall)
    return pool.snapshot(meta, owner, mono, wall)


def budgets(value):
    return {row["id"]: row for row in value["budgets"]}


@pytest.mark.parametrize(
    "path,params,weight",
    [
        ("exchangeInfo", {}, 20),
        ("account", {}, 20),
        ("order", {}, 4),
        ("depth", {"limit": 100}, 5),
        ("depth", {"limit": 500}, 25),
        ("depth", {"limit": 1000}, 50),
        ("depth", {"limit": 5000}, 250),
        ("myTrades", {"orderId": 123}, 5),
        ("myTrades", {}, 20),
        ("openOrders", {"symbol": "BTCUSDT"}, 6),
        ("openOrders", {}, 80),
        ("ticker/24hr", {"symbol": "BTCUSDT"}, 2),
        ("ticker/24hr", {"symbols": json.dumps(["x"] * 21)}, 40),
        ("ticker/24hr", {}, 80),
    ],
)
def test_endpoint_weights_are_reviewed_not_native_fractional_costs(path, params, weight):
    value = request(
        source(),
        "private" if path in {"account", "order", "myTrades", "openOrders"} else "public",
        "GET",
        path,
        params,
    )
    assert value.reviewed and dict(value.charges)["local_weight"] == weight
    assert all(secret not in repr(value) for secret in ("BTCUSDT", "orderId"))


def test_binance_shared_ip_headroom_and_local_budget_are_distinct():
    pool = Quotas()
    info = request(source(), "public", "GET", "exchangeInfo", {})
    result = {
        "rateLimits": [
            {"rateLimitType": "REQUEST_WEIGHT", "interval": "MINUTE", "intervalNum": 1, "limit": 1000}
        ]
    }
    value = record(pool, info, headers={"X-MBX-USED-WEIGHT-1M": "790", "Secret": "PRIVATE"}, result=result)
    assert budgets(value)["local_weight"]["used"] == 20
    assert budgets(value)["ip_weight"]["used"] == 790
    assert budgets(value)["ip_weight"]["capacity"] == 800
    other = request(source("connection:other"), "private", "GET", "account", {})
    assert pool.delay(other, 100, WALL) == 61  # no new transport is needed to find the wait
    test = request(source(environment="test"), "private", "GET", "account", {})
    assert pool.delay(test, 100, WALL) == 0
    assert "PRIVATE" not in json.dumps(value)


def test_out_of_order_and_prior_minute_headers_never_refund_or_poison_current_usage():
    pool = Quotas()
    meta = source()
    owner = state()
    info = request(meta, "public", "GET", "exchangeInfo", {})
    declarations = {
        "rateLimits": [
            {"rateLimitType": "REQUEST_WEIGHT", "interval": "MINUTE", "intervalNum": 1, "limit": 6000}
        ]
    }
    record(pool, info, result=declarations)
    call = request(meta, "public", "GET", "depth", {"limit": 100})
    first = pool.charge(meta, owner, call, 100, WALL)
    second = pool.charge(meta, owner, call, 100, WALL)
    pool.observe(second, {"X-MBX-USED-WEIGHT-1M": "100"}, None, 100, WALL)
    assert budgets(pool.snapshot(meta, owner, 100, WALL))["ip_weight"]["used"] == 105
    pool.observe(first, {"X-MBX-USED-WEIGHT-1M": "80"}, None, 100, WALL)
    assert budgets(pool.snapshot(meta, owner, 100, WALL))["ip_weight"]["used"] == 105
    old = pool.charge(meta, owner, call, 110, WALL + 10)
    pool.delay(call, 161, WALL + 61)
    pool.observe(
        old,
        {"X-MBX-USED-WEIGHT-1M": "5999", "Date": formatdate(WALL + 10, usegmt=True)},
        None,
        161,
        WALL + 61,
    )
    assert budgets(pool.snapshot(meta, owner, 161, WALL + 61))["ip_weight"]["used"] == 0


def test_failed_and_bypassed_attempts_consume_allowances_without_read_or_write_replay():
    pool = Quotas()
    call = request(source(), "public", "GET", "exchangeInfo", {})
    result = record(pool, call, bypass=True)
    assert result["attempts"] == result["bypassed_attempts"] == 1
    assert budgets(result)["local_weight"]["used"] == 20
    assert result["last_request"]["read_admission"] is False
    record(pool, call, headers=None, result=None)
    assert budgets(pool.snapshot(source(), state(), 100, WALL))["local_weight"]["used"] == 40


def test_kraken_private_estimate_is_key_scoped_and_public_independent():
    pool = Quotas()
    meta = source("connection:kraken", "kraken")
    private = request(meta, "private", "POST", "TradesHistory", {}, "private-key-group")
    for _ in range(3):
        record(pool, private, meta)
    assert pool.delay(private, 100, WALL) == pytest.approx(4 / 0.30)
    same = request(meta, "private", "POST", "Balance", {}, "private-key-group")
    assert pool.delay(same, 100, WALL) == pytest.approx(1 / 0.30)
    other = request(meta, "private", "POST", "Balance", {}, "other-key-group")
    assert pool.delay(other, 100, WALL) == 0
    public = request(source("kraken", "kraken"), "public", "GET", "Ticker", {})
    assert pool.delay(public, 100, WALL) == 0
    result = pool.snapshot(meta, state(), 100, WALL)
    assert all("private-key-group" not in json.dumps(row) for row in result["budgets"])


def test_coinbase_exchange_fills_has_its_own_bucket_and_advanced_is_not_misclassified():
    pool = Quotas()
    meta = source("connection:sandbox", "coinbase-sandbox", "test")
    call = request(meta, "private", "GET", "fills", {})
    for _ in range(8):
        record(pool, call, meta)
    assert pool.delay(call, 100, WALL) == pytest.approx(1 / 8)
    assert pool.delay(request(meta, "private", "GET", "accounts", {}), 100, WALL) == 0
    advanced = request(source("coinbase", "coinbase"), ["v3", "private"], "GET", "brokerage/accounts", {})
    assert not advanced.reviewed and not advanced.charges


@pytest.mark.parametrize(
    "headers",
    [
        {"X-MBX-USED-WEIGHT-1M": "NaN"},
        {"X-MBX-USED-WEIGHT-1M": True},
        {"X-MBX-USED-WEIGHT-1M": "-1"},
        {"X-MBX-USED-WEIGHT-1M": "999999999999999999999"},
        {"X-MBX-USED-WEIGHT-1M": {"secret": "PRIVATE"}},
    ],
)
def test_malformed_headers_never_become_numeric_quota_evidence(headers):
    pool = Quotas()
    value = record(pool, request(source(), "public", "GET", "time", {}), headers=headers)
    assert value["unpaired_ip_weight"] is None
    assert "PRIVATE" not in json.dumps(value)


def native(control, cls=BinanceClient, meta=None, credentials=None):
    client = cls(credentials=credentials)
    client._exchange.enableRateLimit = False  # tests exercise native signing/HTTP, not SDK sleep
    captured = []
    replies = []

    def send(prepared, **kwargs):
        captured.append({"method": prepared.method, "path": urlsplit(prepared.url).path})
        reply = replies.pop(0) if replies else {"body": {"serverTime": int(time.time() * 1000)}}
        response = requests.Response()
        response.status_code = reply.get("status", 200)
        response.reason = HTTPStatus(response.status_code).phrase
        response._content = json.dumps(reply.get("body", {})).encode()
        response.headers.update({"Content-Type": "application/json", **reply.get("headers", {})})
        response.url = prepared.url
        response.request = prepared
        return response

    client._exchange.session.send = send
    control.bind(client, meta or source())
    return client, captured, replies


def invoke(control, meta, method, **kwargs):
    with control.operation(meta, "fetch_balance", read=True):
        return method(kwargs)


def test_actual_native_exchange_info_and_signed_account_read_feed_safe_diagnostics():
    control = ProviderControl(min_interval=0)
    meta = source("connection:native")
    client, captured, replies = native(
        control, meta=meta, credentials={"apiKey": "FAKE-PRIVATE-KEY", "secret": "FAKE-PRIVATE-SECRET"}
    )
    replies.append(
        {
            "body": {
                "serverTime": int(time.time() * 1000),
                "rateLimits": [
                    {
                        "rateLimitType": "REQUEST_WEIGHT",
                        "interval": "MINUTE",
                        "intervalNum": 1,
                        "limit": 6000,
                    },
                    {"rateLimitType": "ORDERS", "interval": "SECOND", "intervalNum": 10, "limit": 50},
                ],
            },
            "headers": {"X-MBX-USED-WEIGHT-1M": "20", "X-Private": "PRIVATE-HEADER"},
        }
    )
    invoke(control, meta, client._exchange.publicGetExchangeInfo)
    replies.append(
        {"body": {"balances": []}, "headers": {"X-MBX-USED-WEIGHT-1M": "40", "X-MBX-ORDER-COUNT-10S": "3"}}
    )
    invoke(control, meta, client._exchange.privateGetAccount)
    value = control.snapshot([meta], meta["id"])["items"][0]["quotas"]
    assert value["reviewed_attempts"] == 2 and value["attempts"] == 2
    assert budgets(value)["ip_weight"]["provider_limit"] == 6000
    assert budgets(value)["local_weight"]["used"] == 40
    assert (
        value["reported_order_counts"][0]["used"] == 3 and not value["reported_order_counts"][0]["enforced"]
    )
    assert [c["path"] for c in captured] == ["/api/v3/exchangeInfo", "/api/v3/account"]
    text = json.dumps(value)
    assert all(
        secret not in text
        for secret in ("FAKE-PRIVATE", "PRIVATE-HEADER", "signature", '"partition"', "api.binance.com")
    )
    client.close()


def test_exhausted_allowance_defers_before_native_signing_and_has_no_network_attempt():
    control = ProviderControl(min_interval=0, max_wait=0.01)
    meta = source()
    client, captured, _ = native(control)
    invoke(control, meta, client._exchange.publicGetTime)
    bucket = next(b for key, b in control.quotas.buckets.items() if key[-1] == "local_weight")
    bucket.capacity = 1
    signed = []
    original = client._exchange.sign
    client._exchange.sign = lambda *a, **kw: signed.append(True) or original(*a, **kw)
    with pytest.raises(ProviderDeferred):
        invoke(control, meta, client._exchange.publicGetTime)
    assert not signed and len(captured) == 1
    row = control.snapshot([meta], meta["id"])["items"][0]
    assert row["requests"] == 1 and row["deferred"] == 1 and row["queued"] == 0
    assert row["quotas"]["retry_after"] > 0 and row["quotas"]["attempts"] == 1
    client.close()


def test_ambiguous_actual_native_write_remains_single_attempt_and_bypasses_read_budget():
    control = ProviderControl(min_interval=0, max_wait=0.01)
    meta = source("connection:native")
    client, captured, replies = native(
        control, meta=meta, credentials={"apiKey": "FAKE-PRIVATE-KEY", "secret": "FAKE-PRIVATE-SECRET"}
    )
    call = request(meta, "public", "GET", "exchangeInfo", {})
    record(control.quotas, call, meta, control.register(meta), wall=time.time(), mono=time.monotonic())
    for key, bucket in control.quotas.buckets.items():
        if key[-1] == "local_weight":
            bucket.capacity = 1
    replies.append({"status": 504, "body": {"code": -1007, "msg": "PRIVATE EXECUTION UNKNOWN"}})
    with pytest.raises(ccxt.BaseError):
        with control.sequence(client, write=True):
            client._exchange.privatePostOrder(
                {
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "type": "LIMIT",
                    "quantity": "1",
                    "price": "1",
                    "timeInForce": "GTC",
                }
            )
    assert len(captured) == 1 and captured[0]["method"] == "POST"
    row = control.snapshot([meta], meta["id"])["items"][0]
    assert row["requests"] == 0 and row["quotas"]["bypassed_attempts"] == 1
    assert "PRIVATE EXECUTION" not in json.dumps(row)
    client.close()


def test_budget_state_is_shared_across_aliases_and_not_reset_with_credentials():
    control = ProviderControl(min_interval=0, max_wait=0.01)
    first, captured, _ = native(control)
    invoke(control, source(), first._exchange.publicGetTime)
    bucket = next(b for key, b in control.quotas.buckets.items() if key[-1] == "local_weight")
    bucket.capacity = 1
    control.reset("binance")
    second, other, _ = native(control, meta=source("connection:alias"))
    with pytest.raises(ProviderDeferred):
        invoke(control, source("connection:alias"), second._exchange.publicGetTime)
    assert len(captured) == 1 and not other
    first.close()
    second.close()


def test_health_http_and_native_technician_projection_remain_passive_and_private(manual_client, monkeypatch):
    market = manual_client.app.state.services.market

    def forbidden(*a, **kw):
        raise AssertionError("Diagnostics contacted a provider")

    monkeypatch.setattr(market, "client", forbidden)
    response = manual_client.get("/api/v1/providers/health?source=binance")
    assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    value = response.json()["items"][0]["quotas"]
    assert value["status"] == "not_observed" and not value["budgets"]
    assert value["policy"]["reviewed_at"] == "2026-11-09"


def test_actual_kraken_post_read_and_identical_key_alias_share_private_estimate():
    control = ProviderControl(min_interval=0, max_wait=0.01)
    meta = source("connection:kraken-one", "kraken")
    creds = {"apiKey": "FAKE-PRIVATE-KRAKEN", "secret": "RkFLRQ=="}
    client, captured, replies = native(control, KrakenClient, meta, creds)
    replies.append({"body": {"error": [], "result": {"ZUSD": "10"}}})
    invoke(control, meta, client._exchange.privatePostBalance)
    counter = next(b for key, b in control.quotas.buckets.items() if key[-1] == "private_counter")
    assert counter.capacity == 12 and counter.refill == 0.30
    counter.tokens = -100
    alias = source("connection:kraken-alias", "kraken")
    other, other_calls, _ = native(control, KrakenClient, alias, creds)
    with pytest.raises(ProviderDeferred):
        invoke(control, alias, other._exchange.privatePostBalance)
    assert len(captured) == 1 and not other_calls
    public = control.snapshot([source("kraken", "kraken")], "kraken")["items"][0]["quotas"]
    assert all(b["id"] != "private_counter" for b in public["budgets"])
    assert all(
        secret not in json.dumps(control.snapshot([meta, alias], meta["id"]))
        for secret in ("FAKE-PRIVATE", "RkFLRQ==", '"partition"')
    )
    client.close()
    other.close()


def test_actual_exchange_sandbox_get_fills_consumes_separate_allowance():
    control = ProviderControl(min_interval=0, max_wait=0.01)
    meta = source("connection:exchange", "coinbase-sandbox", "test")
    client, captured, replies = native(
        control,
        CoinbaseSandboxClient,
        meta,
        {"apiKey": "FAKE-PRIVATE", "secret": "RkFLRQ==", "password": "FAKE-PASSPHRASE"},
    )
    replies.append({"body": []})
    assert invoke(control, meta, client._exchange.privateGetFills, product_id="BTC-USD") == []
    value = control.snapshot([meta], meta["id"])["items"][0]["quotas"]
    assert budgets(value)["private_fills"]["used"] > 0
    assert captured[0]["path"] == "/fills"
    for key, b in control.quotas.buckets.items():
        if key[-1] == "private_fills":
            b.tokens = -100
    with pytest.raises(ProviderDeferred):
        invoke(control, meta, client._exchange.privateGetFills, product_id="BTC-USD")
    assert len(captured) == 1
    client.close()


def test_quota_observer_failure_does_not_change_successful_native_write(monkeypatch):
    control = ProviderControl(min_interval=0)
    meta = source("connection:writer")
    client, captured, replies = native(control, meta=meta, credentials={"apiKey": "FAKE", "secret": "FAKE"})

    def broken(*a, **kw):
        raise RuntimeError("PRIVATE OBSERVATION FAILURE")

    monkeypatch.setattr(control.quotas, "observe", broken)
    replies.append({"body": {"orderId": 123}})
    with control.sequence(client, write=True):
        result = client._exchange.privatePostOrder(
            {
                "symbol": "BTCUSDT",
                "type": "LIMIT",
                "side": "BUY",
                "quantity": "1",
                "price": "1",
                "timeInForce": "GTC",
            }
        )
    assert str(result["orderId"]) == "123" and len(captured) == 1
    value = control.snapshot([meta], meta["id"])["items"][0]["quotas"]
    assert value["coverage_gaps"] == 1 and "PRIVATE OBSERVATION" not in json.dumps(value)
    client.close()


def test_rate_limited_native_write_cools_future_reads_but_is_never_retried():
    control = ProviderControl(min_interval=0, max_wait=0.01)
    meta = source("connection:writer")
    client, captured, replies = native(control, meta=meta, credentials={"apiKey": "FAKE", "secret": "FAKE"})
    replies.append(
        {"status": 429, "headers": {"Retry-After": "45"}, "body": {"code": -1003, "msg": "PRIVATE QUOTA"}}
    )
    with pytest.raises((ccxt.RateLimitExceeded, ccxt.DDoSProtection)):
        with control.sequence(client, write=True):
            client._exchange.privatePostOrder(
                {
                    "symbol": "BTCUSDT",
                    "type": "LIMIT",
                    "side": "BUY",
                    "quantity": "1",
                    "price": "1",
                    "timeInForce": "GTC",
                }
            )
    assert len(captured) == 1
    row = control.snapshot([meta], meta["id"])["items"][0]
    assert row["retry_after"] >= 44 and row["requests"] == 0 and row["last_error"] is None
    with pytest.raises(ProviderDeferred):
        invoke(control, meta, client._exchange.publicGetTime)
    assert len(captured) == 1
    client.close()


def test_native_technician_reads_quota_evidence_without_provider_probe(manual_client, monkeypatch):
    from protolink import create_llm

    client = manual_client
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    monkeypatch.setattr(
        "sibyl.agents.utils.registry.create_llm",
        lambda *a, **kw: create_llm(
            "mock",
            sequential_responses=[
                {"type": "tool_call", "tool": "source_health", "args": {"source_id": "binance"}},
                "This is a conservative local allowance. No connection read has been observed in this session.",
            ],
        ),
    )
    monkeypatch.setattr(
        client.app.state.services.market, "client", lambda *a, **kw: pytest.fail("Agent probed provider")
    )
    response = client.post(
        "/api/v1/agents/ask", json={"module": "technician", "message": "Why are Binance reads waiting?"}
    )
    assert response.status_code == 200, response.text
    evidence = response.json()["evidence"]
    assert evidence["items"][0]["quotas"]["status"] == "not_observed"
    assert evidence["items"][0]["quotas"]["policy"]["name"] == "Binance spot weight budgets"


def test_malformed_declaration_is_ignored_without_telemetry_gap():
    pool = Quotas()
    call = request(source(), "public", "GET", "exchangeInfo", {})
    result = record(
        pool,
        call,
        result={
            "rateLimits": [
                {"rateLimitType": "REQUEST_WEIGHT", "interval": ["MINUTE"], "intervalNum": 1, "limit": 6000},
                {"rateLimitType": "REQUEST_WEIGHT", "interval": "MINUTE", "intervalNum": True, "limit": 6000},
            ]
        },
    )
    assert "ip_weight" not in budgets(result)
    assert result["coverage_gaps"] == 0


def test_quota_wait_releases_global_capacity_and_shutdown_prevents_signing():
    from concurrent.futures import ThreadPoolExecutor

    control = ProviderControl(min_interval=0, max_wait=5, max_inflight=1)
    meta = source("connection:kraken-wait", "kraken")
    client, captured, replies = native(
        control, KrakenClient, meta, {"apiKey": "FAKE-WAIT", "secret": "RkFLRQ=="}
    )
    replies.append({"body": {"error": [], "result": {"ZUSD": "10"}}})
    invoke(control, meta, client._exchange.privatePostBalance)
    counter = next(b for key, b in control.quotas.buckets.items() if key[-1] == "private_counter")
    counter.tokens = 0
    public, public_calls, _ = native(control)
    signed = []
    original = client._exchange.sign
    client._exchange.sign = lambda *a, **kw: signed.append(True) or original(*a, **kw)
    with ThreadPoolExecutor() as pool:
        waiting = pool.submit(invoke, control, meta, client._exchange.privatePostBalance)
        with control._condition:
            assert control._condition.wait_for(lambda: control.register(meta)["waiting_quota"] == 1, 1)
        assert control.snapshot([meta], meta["id"])["in_flight"] == 0
        assert invoke(control, source(), public._exchange.publicGetTime)
        assert len(public_calls) == 1
        control.close()
        with pytest.raises(ProviderDeferred):
            waiting.result(1)
    assert len(captured) == 1 and not signed
    assert control.snapshot([meta], meta["id"])["queued"] == 0
    client.close()
    public.close()


def test_clock_rollback_does_not_refund_window_and_source_reset_does_not_invent_headroom():
    pool = Quotas()
    call = request(source(), "public", "GET", "exchangeInfo", {})
    record(pool, call, wall=WALL + 20)
    before = budgets(pool.snapshot(source(), state(), 100, WALL + 20))["local_weight"]["used"]
    after = budgets(pool.snapshot(source(), state(), 101, WALL - 20))["local_weight"]["used"]
    assert before == after == 20
