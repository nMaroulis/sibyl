"""Manual OpenTelemetry boundaries with W3C correlation and bounded metadata."""

from opentelemetry.trace import Status, StatusCode, get_tracer
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

tracer = get_tracer("sibyl.http")
propagator = TraceContextTextMapPropagator()


def record_response(span, status, *, error_at=500):
    """Tag the status class without retaining native errors or request details."""
    span.set_attribute("http.response.status_code", status)
    if status >= error_at:
        span.set_status(Status(StatusCode.ERROR))
