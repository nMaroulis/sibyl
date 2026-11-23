"""Bounded, process-local API response IDs and content-free timing observations."""

from collections import Counter, deque
from statistics import median
from threading import Lock
from time import monotonic
from uuid import uuid4

from opentelemetry.trace import SpanKind, Status, StatusCode
from starlette.datastructures import Headers, MutableHeaders

from sibyl.operations import traces

REQUEST_ID_HEADER = "X-Request-ID"
SAMPLE_LIMIT = 256


class ApiTraffic:
    """Retain only status and elapsed time for the latest API response starts."""

    def __init__(self):
        self._samples = deque(maxlen=SAMPLE_LIMIT)
        self._lock = Lock()

    def record(self, status: int, elapsed: float):
        with self._lock:
            self._samples.append((status, round(elapsed * 1000, 2)))

    def summary(self):
        """Summarize bounded observations without request IDs or per-route details."""
        with self._lock:
            samples = list(self._samples)
        statuses = Counter(f"{status // 100}xx" for status, _ in samples)
        durations = [elapsed for _, elapsed in samples]
        return {
            "sample_size": len(samples),
            "sample_limit": SAMPLE_LIMIT,
            "status_classes": dict(statuses),
            "median_response_start_ms": round(median(durations), 2) if durations else None,
        }


class ApiTrafficMiddleware:
    """Add response IDs at ASGI response start without buffering streams or bodies."""

    def __init__(self, app, *, traffic: ApiTraffic):
        self.app = app
        self.traffic = traffic

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        api = scope["path"].startswith("/api/v1/")
        if not api and scope["path"] != "/health":
            await self.app(scope, receive, send)
            return

        request_id = uuid4().hex if api else None
        started = monotonic()
        if request_id is not None:
            scope.setdefault("state", {})["request_id"] = request_id
        # Only trace context crosses the boundary. Do not import baggage or
        # collect route parameters, request content, or provider diagnostics.
        parent = traces.propagator.extract(Headers(scope=scope))
        with traces.tracer.start_as_current_span(
            "sibyl.api" if api else "sibyl.readiness",
            context=parent,
            kind=SpanKind.SERVER,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:

            async def observe(message):
                if message["type"] == "http.response.start":
                    traces.record_response(span, message["status"])
                    if request_id is not None:
                        MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
                        self.traffic.record(message["status"], monotonic() - started)
                await send(message)

            try:
                await self.app(scope, receive, observe)
            except Exception:
                span.set_status(Status(StatusCode.ERROR))
                raise
