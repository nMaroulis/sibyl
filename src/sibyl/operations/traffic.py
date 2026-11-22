"""Bounded, process-local API response IDs and content-free timing observations."""

from collections import Counter, deque
from statistics import median
from threading import Lock
from time import monotonic
from uuid import uuid4

from starlette.datastructures import MutableHeaders

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
        if scope["type"] != "http" or not scope["path"].startswith("/api/v1/"):
            await self.app(scope, receive, send)
            return

        request_id = uuid4().hex
        started = monotonic()
        scope.setdefault("state", {})["request_id"] = request_id

        async def observe(message):
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
                self.traffic.record(message["status"], monotonic() - started)
            await send(message)

        await self.app(scope, receive, observe)
