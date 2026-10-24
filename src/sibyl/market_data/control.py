"""Local provider admission, transport budgets and sanitized observed health.

One process owns the queues. Adapters retain their native weighted rate limiters;
this layer adds conservative spacing across clients sharing a provider/environment.
Only explicit read methods may retry. Raw URLs, arguments and provider messages
never enter diagnostics.
"""

import math
import threading
import time
from collections import deque
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from functools import wraps
from uuid import uuid4

import ccxt

READS = {
    "load_markets",
    "fetch_ticker",
    "fetch_ohlcv",
    "fetch_candle_page",
    "fetch_order_book",
    "fetch_balance",
    "fetch_open_orders",
    "fetch_my_trades",
    "fetch_trade_page",
    "fetch_funding_page",
    "fetch_order",
    "fetch_order_lookup_page",
    "fetch_order_fill_page",
    "fetch_account_order_page",
}
WRITES = {"create_order", "cancel_order"}
MESSAGES = {
    "rate_limit": "Provider rate limit reached; shared reads are cooling down.",
    "network": "Provider temporarily unavailable; shared reads will retry after backoff.",
    "authentication": "Provider rejected credentials or account permissions.",
    "invalid_data": "Provider response could not be validated.",
    "request": "This operation or exact market is unavailable.",
}


def utc(seconds=None):
    """Format diagnostics timestamps independently of the host timezone."""
    return datetime.fromtimestamp(time.time() if seconds is None else seconds, UTC).isoformat()


def retry_after(value, wall=None):
    """Parse numeric or HTTP-date hints; accept finite delays up to one day."""
    try:
        seconds = float(value)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = parsedate_to_datetime(str(value))
            if parsed.tzinfo is None:
                return None
            seconds = parsed.timestamp() - (time.time() if wall is None else wall)
        except (ValueError, TypeError, OverflowError):
            return None
    return max(0.0, min(86400.0, seconds)) if math.isfinite(seconds) else None


def failure_kind(error):
    """Classify exception types, never their potentially credential-bearing text."""
    if isinstance(error, (ccxt.AuthenticationError, ccxt.PermissionDenied)):
        return "authentication"
    if isinstance(error, (ccxt.RateLimitExceeded, ccxt.DDoSProtection)):
        return "rate_limit"
    if isinstance(error, ccxt.NetworkError):
        return "network"
    if isinstance(
        error, (ccxt.BadSymbol, ccxt.NotSupported, ccxt.ArgumentsRequired, ccxt.InvalidOrder, ccxt.BadRequest)
    ):
        return "request"
    return "invalid_data"


class ProviderDeferred(ccxt.NetworkError):
    """No new network attempt occurred; workers must preserve their retry budget."""

    def __init__(self, seconds=1):
        self.retry_after = max(1, math.ceil(seconds))
        super().__init__("Provider reads are queued or cooling down. Retry after the indicated delay.")


class ClientGuard:
    """Retire a credential-bearing client only after its active leases finish."""

    def __init__(self, close):
        self._close = close
        self._lock = threading.RLock()
        self._local = threading.local()
        self._users = 0
        self._retired = False
        self._closed = False

    @contextmanager
    def hold(self):
        with self._lock:
            depth = getattr(self._local, "depth", 0)
            if self._retired and not depth:
                raise ProviderDeferred()
            self._users += 1
            self._local.depth = depth + 1
        try:
            yield
        finally:
            with self._lock:
                self._users -= 1
                self._local.depth -= 1
                self._finish()

    def _finish(self):
        if self._retired and not self._users and not self._closed:
            self._closed = True
            self._close()

    def retire(self):
        """Block new users immediately; close transport once existing users release it."""
        with self._lock:
            self._retired = True
            self._finish()


class ProviderControl:
    """Coordinate explicit adapter operations before locks and actual HTTP reads after them."""

    def __init__(self, min_interval=0.25, max_inflight=4, max_wait=5, history=None):
        self.min_interval = min_interval
        self.max_inflight = max_inflight
        self.max_wait = max_wait
        self.history = history
        self.started_at = utc()
        self._condition = threading.Condition(threading.RLock())
        self._local = threading.local()
        self._sources = {}
        self._buckets = {}
        self._inflight = 0
        self._http_waiters = []
        self._closed = False

    @contextmanager
    def background(self):
        """Give worker reads lower admission priority; restore it after every tick."""
        previous = getattr(self._local, "background", False)
        self._local.background = True
        try:
            yield
        finally:
            self._local.background = previous

    def register(self, source, *, retained=True):
        """Store only public source identity; diagnostics never retain adapter credentials."""
        if "_state" in source:
            return source["_state"]
        with self._condition:
            identity = source["id"]
            if not retained or identity not in self._sources:
                if retained and len(self._sources) >= 512:
                    self._sources.pop(next(iter(self._sources)))
                state = {
                    **{k: source[k] for k in ("id", "name", "kind", "provider", "environment")},
                    "requests": 0,
                    "successful_requests": 0,
                    "failed_requests": 0,
                    "read_retries": 0,
                    "deferred": 0,
                    "cache_hits": 0,
                    "waiting_http": 0,
                    "last_success_at": None,
                    "last_request_at": None,
                    "latency_ms": None,
                    "last_error": None,
                    "errors": deque(maxlen=5),
                    "quote": None,
                    "generation": uuid4().hex,
                }
                if retained:
                    self._sources[identity] = state
                return state
            return self._sources[identity]

    def _bucket(self, source):
        key = (source["provider"], source["environment"])
        with self._condition:
            return self._buckets.setdefault(
                key,
                {"busy": False, "queue": [], "next": 0.0, "cooldown": 0.0, "failures": 0, "waiting_http": 0},
            )

    @contextmanager
    def operation(self, source, name="account_sequence", read=False):
        """Admit queued interactive work before background work, then preserve adapter atomicity."""
        if source["provider"] == "demo":
            yield
            return
        old = getattr(self._local, "operation", None)
        if old and (old["source"]["provider"], old["source"]["environment"]) != (
            source["provider"],
            source["environment"],
        ):
            raise ValueError("Nested operations cannot combine provider admission lanes.")
        owned = old is None
        ticket = {
            "background": getattr(self._local, "background", False),
            "created": time.monotonic(),
            "source": source["id"],
            "nonce": object(),
        }
        deadline = time.monotonic() + self.max_wait
        bucket = self._bucket(source)
        state = self.register(source)
        if owned:
            with self._condition:
                if len(bucket["queue"]) >= 64 or sum(len(b["queue"]) for b in self._buckets.values()) >= 256:
                    state["deferred"] += 1
                    raise ProviderDeferred()
                bucket["queue"].append(ticket)
                self._condition.notify_all()
                try:
                    while True:
                        if self._closed:
                            raise ProviderDeferred()
                        first = min(bucket["queue"], key=lambda t: (int(t["background"]), t["created"]))
                        delay = bucket["cooldown"] - time.monotonic()
                        if delay > (2 if ticket["background"] else self.max_wait):
                            raise ProviderDeferred(delay)
                        if first is ticket and not bucket["busy"] and delay <= 0:
                            bucket["busy"] = True
                            break
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise ProviderDeferred(max(1, delay))
                        self._condition.wait(min(remaining, max(0.01, delay) if delay > 0 else remaining))
                except ProviderDeferred:
                    state["deferred"] += 1
                    raise
                finally:
                    bucket["queue"].remove(ticket)
                    self._condition.notify_all()
        shared = old["counter"] if old else {"calls": 0, "errors": 0}
        self._local.operation = {"source": source, "name": name, "read": read, "counter": shared}
        try:
            yield
        finally:
            self._local.operation = old
            if owned:
                with self._condition:
                    bucket["busy"] = False
                    self._condition.notify_all()

    def transport(self, loader, headers=None):
        """Count and space one real transport read; never replay a signed/native request here."""
        context = getattr(self._local, "operation", None)
        if not context or not context["read"] or getattr(self._local, "mutation", False):
            return loader()  # mutations keep the existing one-attempt execution contract
        source = context["source"]
        state = self.register(source)
        with self._condition:
            bucket = self._bucket(source)
            # Conservative app budgets, not claims about an account's purchased quota.
            interval = max(
                self.min_interval,
                1.0 if source["provider"] in {"coingecko", "cryptocompare"} and self.min_interval else 0,
            )
            deadline = time.monotonic() + (2 if getattr(self._local, "background", False) else self.max_wait)
            state["waiting_http"] += 1
            bucket["waiting_http"] += 1
            ticket = {
                "nonce": object(),
                "background": getattr(self._local, "background", False),
                "created": time.monotonic(),
                "bucket": bucket,
            }
            self._http_waiters.append(ticket)
            self._condition.notify_all()
            try:
                while True:
                    now = time.monotonic()
                    delay = max(bucket["next"], bucket["cooldown"]) - now
                    if self._closed or (delay > deadline - now):
                        state["deferred"] += 1
                        raise ProviderDeferred(max(1, delay))
                    ready = [
                        ticket
                        for ticket in self._http_waiters
                        if max(ticket["bucket"]["next"], ticket["bucket"]["cooldown"]) <= now
                    ]
                    first = min(ready, key=lambda t: (int(t["background"]), t["created"])) if ready else None
                    if first is ticket and delay <= 0 and self._inflight < self.max_inflight:
                        bucket["next"] = now + interval
                        self._inflight += 1
                        context["counter"]["calls"] += 1
                        state["requests"] += 1
                        state["last_request_at"] = utc()
                        break
                    remaining = deadline - now
                    if remaining <= 0:
                        state["deferred"] += 1
                        raise ProviderDeferred()
                    self._condition.wait(min(remaining, delay if delay > 0 else remaining))
            finally:
                state["waiting_http"] -= 1
                bucket["waiting_http"] -= 1
                self._http_waiters.remove(ticket)
                self._condition.notify_all()
        start = time.monotonic()
        outcome = None
        try:
            result = loader()
            with self._condition:
                state["successful_requests"] += 1
            outcome = "success"
            return result
        except Exception as error:
            outcome = failure_kind(error)
            with self._condition:
                state["failed_requests"] += 1
            hint = getattr(error, "retry_after", None)
            if hint is None and headers:
                raw = headers() or {}
                hint = retry_after(next((v for k, v in raw.items() if k.lower() == "retry-after"), None))
            self._failure(source, error, hint)
            context["counter"]["errors"] += 1
            raise
        finally:
            latency = round((time.monotonic() - start) * 1000, 1)
            with self._condition:
                state["latency_ms"] = latency
                self._inflight -= 1
                self._condition.notify_all()
                retired = self._sources.get(source["id"]) is not state
            if self.history is not None and outcome is not None:
                self.history.record(
                    source,
                    state["generation"],
                    latency,
                    None if outcome == "success" else outcome,
                    operation=context["name"],
                    retired=retired,
                )

    def _failure(self, source, error, hint=None):
        if isinstance(error, ProviderDeferred):
            return
        kind = failure_kind(error)
        if kind == "request":
            return
        with self._condition:
            state, bucket = self.register(source), self._bucket(source)
            event = {"at": utc(), "kind": kind, "message": MESSAGES[kind]}
            state["last_error"] = event
            state["errors"].appendleft(event)
            if kind in {"network", "rate_limit"}:
                bucket["failures"] = min(8, bucket["failures"] + 1)
                delay = min(60, 0.5 * 2 ** (bucket["failures"] - 1))
                if kind == "rate_limit":
                    delay = max(2, delay)
                bucket["cooldown"] = max(
                    bucket["cooldown"], time.monotonic() + max(delay, retry_after(hint) or 0)
                )
            self._condition.notify_all()

    def _run(self, client, source, name, method, args, kwargs):
        if getattr(self._local, "mutation", False):
            return method(*args, **kwargs)
        if name in WRITES:
            with self.mutation():
                return method(*args, **kwargs)
        nested = getattr(self._local, "operation", None) is not None
        for attempt in range(2):
            with self.operation(source, name, name in READS):
                context = self._local.operation
                before = dict(context["counter"])
                try:
                    result = method(*args, **kwargs)
                except Exception as error:
                    if (
                        context["counter"]["calls"] > before["calls"]
                        and context["counter"]["errors"] == before["errors"]
                    ):
                        self._failure(source, error)
                        context["counter"]["errors"] += 1
                    bucket = self._bucket(source)
                    retry = (
                        name in READS
                        and not nested
                        and not attempt
                        and not getattr(self._local, "background", False)
                        and isinstance(error, ccxt.NetworkError)
                        and not isinstance(error, ProviderDeferred)
                        and 0 < bucket["cooldown"] - time.monotonic() <= 0.75
                    )
                    if not retry:
                        raise
                    with self._condition:
                        self.register(source)["read_retries"] += 1
                else:
                    if context["counter"]["calls"] > before["calls"]:
                        with self._condition:
                            state = self.register(source)
                            state["last_success_at"] = utc()
                            state["last_error"] = None
                            self._bucket(source)["failures"] = 0
                    if name == "fetch_ticker":
                        self.observe_quote(source, args[0] if args else kwargs.get("symbol"), result)
                    return result

    def observe_quote(self, source, symbol, quote):
        """Keep one timestamped quote sample separate from transport health and balances."""
        if not isinstance(quote, dict):
            return
        stamp = quote.get("timestamp")
        price = quote.get("last") or quote.get("close")
        valid = (
            isinstance(price, (int, float))
            and not isinstance(price, bool)
            and math.isfinite(price)
            and price > 0
        )
        dated = (
            isinstance(stamp, (int, float))
            and not isinstance(stamp, bool)
            and math.isfinite(stamp)
            and stamp > 0
            and stamp <= (time.time() + 60) * 1000
        )
        with self._condition:
            self.register(source)["quote"] = {
                "symbol": symbol,
                "observed_at": utc(stamp / 1000) if dated else None,
                "received_at": utc(),
                "valid": valid and (stamp is None or dated),
            }

    def cache_hit(self, source):
        """A cache hit never establishes new connectivity or changes a provider quote time."""
        with self._condition:
            self.register(source)["cache_hits"] += 1

    def bind(self, client, source, *, retired=False):
        """Instrument typed adapters in place, preserving their types and public contracts."""
        if hasattr(client, "_request_guard"):
            return client
        source = {key: source[key] for key in ("id", "name", "kind", "provider", "environment")}
        source["_state"] = self.register(source, retained=not retired)
        guard = client._request_guard = ClientGuard(client.close)
        client._request_source = source
        client.close = guard.retire
        if source["provider"] == "demo":
            return client
        native = getattr(client, "_exchange", None)
        if native is not None and callable(getattr(native, "fetch", None)):
            original = native.fetch

            @wraps(original)
            def fetch(*args, **kwargs):
                native.last_response_headers = None
                return self.transport(
                    lambda: original(*args, **kwargs), lambda: getattr(native, "last_response_headers", None)
                )

            native.fetch = fetch
        elif hasattr(client, "_get"):
            original = client._get

            @wraps(original)
            def get(*args, **kwargs):
                return self.transport(lambda: original(*args, **kwargs))

            client._get = get
        for name in READS | WRITES:
            method = getattr(client, name, None)
            if not callable(method):
                continue

            def wrap(method=method, name=name):
                @wraps(method)
                def call(*args, **kwargs):
                    with guard.hold():
                        return self._run(client, source, name, method, args, kwargs)

                return call

            setattr(client, name, wrap())
        return client

    @contextmanager
    def mutation(self):
        """Keep writes and their preflight reads outside read retry/admission policy."""
        old = getattr(self._local, "mutation", False)
        self._local.mutation = True
        try:
            yield
        finally:
            self._local.mutation = old

    @contextmanager
    def sequence(self, client, *, write=False):
        """Take admission before a multi-step account lock; nested reads cannot deadlock the lane."""
        guard = getattr(client, "_request_guard", None)
        source = getattr(client, "_request_source", None)
        with guard.hold() if guard else nullcontext():
            with self.mutation() if write else self.operation(source) if source else nullcontext():
                with getattr(client, "lock", nullcontext()):
                    yield client

    def snapshot(self, catalog, active):
        """Return bounded current-process diagnostics without any network probes."""
        with self._condition:
            now, wall = time.monotonic(), time.time()
            rows = []
            catalog_ids = {s["id"] for s in catalog}
            # Keep observed disconnected identities inspectable, with no inherited access claim.
            all_sources = [
                *catalog,
                *[{**s, "available": False} for s in self._sources.values() if s["id"] not in catalog_ids],
            ]
            for source in all_sources:
                state = self._sources.get(source["id"])
                bucket = self._bucket(source)
                delay = max(0, bucket["cooldown"] - now)
                quote = state["quote"] if state else None
                age = (
                    wall - datetime.fromisoformat(quote["observed_at"]).timestamp()
                    if quote and quote["observed_at"]
                    else None
                )
                data_status = (
                    "not_observed"
                    if not quote
                    else "invalid"
                    if not quote["valid"]
                    else "undated"
                    if age is None
                    else "stale"
                    if age > 300
                    else "fresh"
                )
                last = state["last_success_at"] if state else None
                stale = last and wall - datetime.fromisoformat(last).timestamp() > 300
                status = (
                    "demo"
                    if source["provider"] == "demo"
                    else "unavailable"
                    if not source.get("available", True)
                    else "retrying"
                    if delay > 0
                    else "degraded"
                    if state and state["last_error"]
                    else "stale"
                    if stale
                    else "healthy"
                    if last
                    else "not_checked"
                )
                queue = bucket["queue"]
                rows.append(
                    {
                        **{k: source[k] for k in ("id", "name", "kind", "provider", "environment")},
                        "available": source.get("available", True),
                        "default": source["id"] == active,
                        "status": status,
                        "data_status": "synthetic" if status == "demo" else data_status,
                        "requests": state["requests"] if state else 0,
                        "successful_requests": state["successful_requests"] if state else 0,
                        "failed_requests": state["failed_requests"] if state else 0,
                        "read_retries": state["read_retries"] if state else 0,
                        "deferred": state["deferred"] if state else 0,
                        "cache_hits": state["cache_hits"] if state else 0,
                        "last_success_at": last,
                        "last_request_at": state["last_request_at"] if state else None,
                        "latency_ms": state["latency_ms"] if state else None,
                        "last_error": state["last_error"] if state else None,
                        "errors": list(state["errors"]) if state else [],
                        "quote": quote,
                        "retry_after": math.ceil(delay),
                        "retry_at": utc(wall + delay) if delay else None,
                        "queued": sum(t["source"] == source["id"] for t in queue)
                        + (state["waiting_http"] if state else 0),
                        "shared_queued": len(queue) + bucket["waiting_http"],
                        "shared_busy": bucket["busy"],
                    }
                )
            return {
                "items": rows,
                "as_of": utc(),
                "started_at": self.started_at,
                "in_flight": self._inflight,
                "queued": sum(len(b["queue"]) + b["waiting_http"] for b in self._buckets.values()),
                "policy": {
                    "min_interval_ms": round(self.min_interval * 1000),
                    "max_inflight": self.max_inflight,
                    "max_queue_per_provider": 64,
                    "interactive_first": True,
                    "max_read_attempts": 2,
                    "scope": "single_process",
                    "telemetry": "actual_transport_reads",
                },
            }

    def reset(self, identity):
        """New credentials start unchecked; old leased reads update only their retired evidence."""
        with self._condition:
            self._sources.pop(identity, None)

    def close(self):
        """Wake queued readers at shutdown; no canceled request is replayed."""
        with self._condition:
            self._closed = True
            self._condition.notify_all()
