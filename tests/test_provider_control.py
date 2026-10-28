"""Deterministic provider scheduling and health tests, without external accounts or writes."""

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import ccxt
import httpx
import pytest

from sibyl.exchanges.demo import DemoClient
from sibyl.market_data.clients import CoinGeckoClient
from sibyl.market_data.control import ClientGuard, ProviderControl, ProviderDeferred, retry_after
from sibyl.services.data_settings import DataSettings, MarketSettingsRequest
from sibyl.services.market import Market


def source(identity="binance", provider="binance", environment="production"):
    return {
        "id": identity,
        "name": identity,
        "kind": "connection" if identity.startswith("connection:") else "exchange",
        "provider": provider,
        "environment": environment,
        "available": True,
    }


class Native:
    """A controllable SDK transport boundary; no real provider is instantiated."""

    def __init__(self):
        self.calls = []
        self.callback = lambda *a, **k: {"last": 100, "timestamp": time.time() * 1000}
        self.last_response_headers = {}
        self.next_response_headers = {}

    def fetch(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        self.last_response_headers = self.next_response_headers
        return self.callback(*args, **kwargs)


class Adapter:
    def __init__(self):
        self.lock = threading.RLock()
        self._exchange = Native()
        self.closed = False

    def close(self):
        self.closed = True

    def fetch_ticker(self, symbol):
        with self.lock:
            return self._exchange.fetch(symbol)

    def fetch_balance_snapshot(self):
        with self.lock:
            return self._exchange.fetch("balance-check")

    def create_order(self, *args, **kwargs):
        with self.lock:
            return self._exchange.fetch("mutate", method="POST")

    def cancel_order(self, *args, **kwargs):
        with self.lock:
            return self._exchange.fetch("cancel", method="DELETE")


def bind(control, meta=None):
    adapter = Adapter()
    return control.bind(adapter, meta or source())


def read_status(control, meta=None):
    meta = meta or source()
    return control.snapshot([meta], meta["id"])["items"][0]


def test_balance_check_observations_use_provider_read_admission_and_sanitized_health():
    control = ProviderControl(min_interval=0)
    adapter = bind(control, source("connection:balance-check"))
    adapter._exchange.callback = lambda *a, **k: (_ for _ in ()).throw(ccxt.AuthenticationError("PRIVATE"))
    with pytest.raises(ccxt.AuthenticationError):
        adapter.fetch_balance_snapshot()
    status = read_status(control, source("connection:balance-check"))
    assert status["status"] == "degraded"
    assert "PRIVATE" not in json.dumps(status)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("12", 12),
        ("0", 0),
        ("nonsense", None),
        (None, None),
        ("NaN", None),
        ("Infinity", None),
        (-5, 0),
        (999999, 86400),
    ],
)
def test_retry_after_bounded_and_sanitized(value, expected):
    assert retry_after(value) == expected


def test_retry_after_accepts_http_date():
    wall = 1704067200
    assert retry_after("Mon, 01 Jan 2024 00:01:00 GMT", wall) == 60


def test_network_retry_is_one_fresh_read_and_health_has_no_raw_payload():
    control = ProviderControl(min_interval=0)
    adapter = bind(control)

    def transient(*a, **k):
        if len(adapter._exchange.calls) == 1:
            raise ccxt.RequestTimeout("PRIVATE-KEY https://bad.example?secret=PRIVATE")
        return {"last": 100, "timestamp": time.time() * 1000}

    adapter._exchange.callback = transient
    assert adapter.fetch_ticker("BTC/USDT")["last"] == 100
    result = read_status(control)
    assert len(adapter._exchange.calls) == 2 and result["read_retries"] == 1
    assert result["requests"] == 2 and result["failed_requests"] == 1
    assert result["status"] == "healthy" and result["data_status"] == "fresh"
    assert "PRIVATE" not in json.dumps(result) and "bad.example" not in json.dumps(result)


def test_rate_limit_is_shared_across_clients_but_not_environments():
    control = ProviderControl(min_interval=0, max_wait=0.01)
    public = bind(control)
    private_meta = source("connection:one")
    private = bind(control, private_meta)
    sandbox_meta = source("connection:test", environment="test")
    sandbox = bind(control, sandbox_meta)
    public._exchange.next_response_headers = {"Retry-After": "60", "PRIVATE": "SECRET"}
    public._exchange.callback = lambda *a, **k: (_ for _ in ()).throw(ccxt.RateLimitExceeded("PRIVATE"))
    with pytest.raises(ccxt.RateLimitExceeded):
        public.fetch_ticker("BTC/USDT")
    with pytest.raises(ProviderDeferred) as error:
        private.fetch_ticker("BTC/USDT")
    assert error.value.retry_after >= 59 and not private._exchange.calls
    assert sandbox.fetch_ticker("BTC/USDT")["last"] == 100
    assert read_status(control, private_meta)["status"] == "retrying"
    assert read_status(control, sandbox_meta)["status"] == "healthy"


def test_credential_failure_does_not_cool_down_public_feed():
    control = ProviderControl(min_interval=0)
    meta = source("connection:one")
    private = bind(control, meta)
    private._exchange.callback = lambda *a, **k: (_ for _ in ()).throw(ccxt.AuthenticationError("PRIVATE"))
    with pytest.raises(ccxt.AuthenticationError):
        private.fetch_ticker("BTC/USDT")
    public = bind(control)
    assert public.fetch_ticker("BTC/USDT")["last"] == 100
    assert read_status(control, meta)["status"] == "degraded"
    assert read_status(control)["status"] == "healthy"


@pytest.mark.parametrize("method", ["create_order", "cancel_order"])
def test_mutations_bypass_read_cooldowns_and_are_never_retried(method):
    control = ProviderControl(min_interval=0)
    adapter = bind(control)
    with control._condition:
        control._bucket(source())["cooldown"] = time.monotonic() + 60
    adapter._exchange.callback = lambda *a, **k: (_ for _ in ()).throw(ccxt.RequestTimeout("PRIVATE"))
    with pytest.raises(ccxt.RequestTimeout):
        with control.sequence(adapter, write=True):
            getattr(adapter, method)("BTC/USDT")
    assert len(adapter._exchange.calls) == 1
    assert read_status(control)["requests"] == 0


def test_interactive_queue_precedes_waiting_background_before_adapter_lock():
    control = ProviderControl(min_interval=0, max_wait=3)
    adapter = bind(control)
    entered, release = threading.Event(), threading.Event()
    order = []

    def callback(symbol):
        order.append(symbol)
        if symbol == "first":
            entered.set()
            assert release.wait(2)
        return {"last": 100, "timestamp": time.time() * 1000}

    adapter._exchange.callback = callback

    def background():
        with control.background():
            return adapter.fetch_ticker("history")

    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(adapter.fetch_ticker, "first")
        assert entered.wait(1)
        background_result = pool.submit(background)
        with control._condition:
            assert control._condition.wait_for(lambda: len(control._bucket(source())["queue"]) == 1, 1)
        foreground = pool.submit(adapter.fetch_ticker, "interactive")
        with control._condition:
            assert control._condition.wait_for(lambda: len(control._bucket(source())["queue"]) == 2, 1)
        assert read_status(control)["queued"] == 2
        release.set()
        assert first.result(2) and foreground.result(2) and background_result.result(2)
    assert order == ["first", "interactive", "history"]


def test_global_http_bound_allows_independent_providers():
    control = ProviderControl(min_interval=0, max_inflight=2, max_wait=3)
    release, entered = threading.Event(), threading.Event()
    lock = threading.Lock()
    active = 0
    maximum = 0

    def callback(*a, **k):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
            if active == 2:
                entered.set()
        assert release.wait(2)
        with lock:
            active -= 1
        return {"last": 100, "timestamp": time.time() * 1000}

    adapters = [bind(control, source(p, p)) for p in ("binance", "coinbase", "kraken")]
    for adapter in adapters:
        adapter._exchange.callback = callback
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(a.fetch_ticker, "BTC/USDT") for a in adapters]
        assert entered.wait(1)
        assert control.snapshot([], "")["in_flight"] == 2
        release.set()
        assert all(f.result(2) for f in futures)
    assert maximum == 2 and all(len(a._exchange.calls) == 1 for a in adapters)


def test_queue_timeout_cleans_admission_without_network_attempt():
    control = ProviderControl(min_interval=0, max_wait=0.02)
    adapter = bind(control)
    entered, release = threading.Event(), threading.Event()

    def block(*a, **kw):
        entered.set()
        assert release.wait(1)
        return {"last": 100}

    adapter._exchange.callback = block
    with ThreadPoolExecutor() as pool:
        first = pool.submit(adapter.fetch_ticker, "first")
        assert entered.wait(1)
        with pytest.raises(ProviderDeferred):
            adapter.fetch_ticker("second")
        assert read_status(control)["queued"] == 0
        release.set()
        first.result(1)
    assert len(adapter._exchange.calls) == 1


def test_quote_staleness_does_not_invent_transport_outage_or_freshness():
    control = ProviderControl(min_interval=0)
    adapter = bind(control)
    adapter._exchange.callback = lambda *a, **k: {"last": 100, "timestamp": (time.time() - 3600) * 1000}
    adapter.fetch_ticker("BTC/USDT")
    result = read_status(control)
    assert result["status"] == "healthy" and result["data_status"] == "stale"
    before = result["last_success_at"]
    control.cache_hit(source())
    assert read_status(control)["last_success_at"] == before
    assert read_status(control)["data_status"] == "stale"


def test_late_retired_evidence_cannot_overwrite_new_key_health():
    control = ProviderControl(min_interval=0)
    old = bind(control)
    control.reset("binance")
    new = bind(control)
    old.fetch_ticker("BTC/USDT")
    assert read_status(control)["status"] == "not_checked"
    new.fetch_ticker("BTC/USDT")
    assert read_status(control)["requests"] == 1


def test_guard_retires_after_active_snapshot_and_rejects_new_users():
    closed = []
    guard = ClientGuard(lambda: closed.append(True))
    with guard.hold():
        guard.retire()
        assert not closed
        with guard.hold():
            pass  # an existing frozen read can finish its nested work
        with ThreadPoolExecutor() as pool:

            def late():
                with guard.hold():
                    pass

            with pytest.raises(ProviderDeferred):
                pool.submit(late).result(1)
    assert closed == [True]
    guard.retire()
    assert closed == [True]


def test_identical_cache_misses_coalesce_without_blocking_other_feeds(settings, store, monkeypatch):
    market = Market(settings, store, DataSettings(settings, store))
    entered, release = threading.Event(), threading.Event()
    reads = []

    class Quotes(DemoClient):
        def fetch_ohlcv(self, *args, **kwargs):
            reads.append(True)
            entered.set()
            assert release.wait(2)
            return super().fetch_ohlcv(*args, **kwargs)

    monkeypatch.setattr(
        "sibyl.services.market.create_client",
        lambda provider, **kw: Quotes(store) if provider == "kraken" else DemoClient(store),
    )

    def load(feed):
        with market.snapshot(feed):
            return market.candles("BTC/USDT", 90)

    with ThreadPoolExecutor(max_workers=3) as pool:
        a = pool.submit(load, "kraken")
        assert entered.wait(1)
        b = pool.submit(load, "kraken")
        other = pool.submit(load, "coinbase")
        assert len(other.result(1)) == 90
        release.set()
        assert a.result(1) == b.result(1)
    assert len(reads) == 1
    market.close()


@pytest.mark.parametrize(
    "code,kind",
    [
        (401, ccxt.AuthenticationError),
        (403, ccxt.PermissionDenied),
        (429, ccxt.RateLimitExceeded),
        (503, ccxt.ExchangeNotAvailable),
    ],
)
def test_api_errors_preserve_classification_and_only_numeric_retry_hint(code, kind):
    adapter = CoinGeckoClient(
        "PRIVATE",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(code, headers={"Retry-After": "42"}, text="PRIVATE")
        ),
    )
    with pytest.raises(kind) as error:
        adapter.fetch_ticker("BTC/USD")
    assert error.value.retry_after == 42 and "PRIVATE" not in str(error.value)
    adapter.close()


def test_diagnostics_are_local_and_keys_are_absent(client, monkeypatch):
    client.post("/api/v1/settings/market", json={"source": "coingecko", "api_key": "PRIVATE-KEY"})
    market = client.app.state.services.market

    def forbidden(*a, **k):
        raise AssertionError("diagnostics must not probe a provider")

    monkeypatch.setattr(market, "client", forbidden)
    for path in ["/providers/health", "/providers/health?source=coingecko"]:
        response = client.get("/api/v1" + path)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert "PRIVATE" not in response.text
        assert next(s for s in response.json()["items"] if s["id"] == "coingecko")["status"] == "not_checked"
    assert client.get("/api/v1/providers/health?source=unknown").status_code == 400


def test_api_deferral_exposes_safe_retry_after(client, monkeypatch):
    def deferred(*a, **kw):
        raise ProviderDeferred(12)

    monkeypatch.setattr(client.app.state.services.market, "symbols", deferred)
    response = client.get("/api/v1/markets/symbols")
    assert response.status_code == 503 and response.headers["retry-after"] == "12"
    assert response.json()["retry_after"] == 12


def test_background_import_deferrals_preserve_attempt_budget(client, monkeypatch):
    history = client.app.state.services.history
    end = datetime.now(UTC) - timedelta(days=1)
    request = {
        "source": "demo",
        "symbol": "BTC/USDT",
        "timeframe": "1d",
        "start": (end - timedelta(days=90)).isoformat(),
        "end": end.isoformat(),
    }
    job = client.post("/api/v1/market-history/imports", json=request).json()
    with history.market.snapshot("demo"):
        adapter = history.market.client()

    def deferred(*a, **k):
        raise ProviderDeferred(120)

    monkeypatch.setattr(adapter, "fetch_candle_page", deferred)
    history.tick()
    state = history.status("demo", "BTC/USDT", "1d")["job"]
    assert state["status"] == "retrying" and state["failures"] == 0 and state["cursor"] == job["cursor"]
    assert state["next_attempt"] > time.time() + 115


def test_shared_spacing_is_enforced_across_two_client_instances():
    control = ProviderControl(min_interval=0.025)
    a = bind(control)
    b = bind(control, source("connection:two"))
    a.fetch_ticker("BTC/USDT")
    start = time.monotonic()
    b.fetch_ticker("BTC/USDT")
    assert time.monotonic() - start >= 0.02
    assert len(a._exchange.calls) == len(b._exchange.calls) == 1


def test_global_admission_also_prioritizes_interactive_reads():
    control = ProviderControl(min_interval=0, max_inflight=1, max_wait=3)
    entered, release = threading.Event(), threading.Event()
    order = []
    adapters = [bind(control, source(p, p)) for p in ("binance", "coinbase", "kraken")]

    def callback(name):
        order.append(name)
        if name == "first":
            entered.set()
            assert release.wait(2)
        return {"last": 100}

    for adapter in adapters:
        adapter._exchange.callback = callback

    def historical():
        with control.background():
            return adapters[1].fetch_ticker("history")

    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(adapters[0].fetch_ticker, "first")
        assert entered.wait(1)
        background = pool.submit(historical)
        with control._condition:
            assert control._condition.wait_for(lambda: len(control._http_waiters) == 1, 1)
        foreground = pool.submit(adapters[2].fetch_ticker, "interactive")
        with control._condition:
            assert control._condition.wait_for(lambda: len(control._http_waiters) == 2, 1)
        assert control.snapshot([], "")["queued"] == 2
        release.set()
        assert first.result(2) and foreground.result(2) and background.result(2)
    assert order == ["first", "interactive", "history"]


def test_native_stale_retry_header_does_not_extend_a_new_timeout():
    control = ProviderControl(min_interval=0)
    adapter = bind(control)
    adapter._exchange.last_response_headers = {"Retry-After": "60"}

    def callback(*a, **k):
        if len(adapter._exchange.calls) == 1:
            raise ccxt.RequestTimeout("temporary")
        return {"last": 100}

    adapter._exchange.callback = callback
    assert adapter.fetch_ticker("BTC/USDT")["last"] == 100
    assert len(adapter._exchange.calls) == 2


@pytest.mark.parametrize(
    "timestamp,status", [(None, "undated"), (0, "invalid"), (True, "invalid"), (1e30, "invalid")]
)
def test_quote_time_quality_is_explicit(timestamp, status):
    control = ProviderControl(min_interval=0)
    adapter = bind(control)
    adapter._exchange.callback = lambda *a, **k: {"last": 100, "timestamp": timestamp}
    adapter.fetch_ticker("BTC/USDT")
    assert read_status(control)["data_status"] == status


def test_old_key_snapshot_can_finish_after_rotation_without_repopulating_client_pool(
    settings, store, monkeypatch
):
    preferences = DataSettings(settings, store)
    preferences.save_market(MarketSettingsRequest(source="coingecko", api_key="OLD-PRIVATE"))
    market = Market(settings, store, preferences)
    pinned, release = threading.Event(), threading.Event()
    adapters = []

    def create(key, pro=False):
        def response(request):
            value = 100 if request.headers["x-cg-demo-api-key"] == "OLD-PRIVATE" else 200
            return httpx.Response(200, json={"bitcoin": {"usd": value, "last_updated_at": time.time()}})

        adapter = CoinGeckoClient(key, transport=httpx.MockTransport(response))
        adapters.append(adapter)
        return adapter

    monkeypatch.setattr("sibyl.market_data.clients.CoinGeckoClient", create)

    def old_read():
        with market.snapshot("coingecko"):
            pinned.set()
            assert release.wait(2)
            return market.price("BTC/USD")

    with ThreadPoolExecutor() as pool:
        future = pool.submit(old_read)
        assert pinned.wait(1)
        preferences.save_market(MarketSettingsRequest(source="coingecko", api_key="NEW-PRIVATE"))
        market.forget_source("coingecko")
        release.set()
        assert future.result(2) == 100
    assert adapters[0]._http.is_closed
    assert not market._clients
    assert market.provider_health("coingecko")["items"][0]["status"] == "not_checked"
    assert market.price("BTC/USD") == 200
    assert len(market._clients) == 1
    assert "PRIVATE" not in json.dumps(market.provider_health())
    market.close()
