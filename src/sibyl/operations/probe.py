"""Read Sibyl's public health endpoint from a separate process or host."""

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from os import getenv
from time import sleep
from urllib.parse import urlsplit

import httpx
from opentelemetry.trace import SpanKind, Status, StatusCode

from sibyl.operations import traces
from sibyl.operations.probe_notifications import WatchNotifications

MAX_BODY = 1024
VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,63}")


def health_url(origin: str) -> str:
    """Accept an explicit HTTP(S) origin without credentials, query or fragments."""
    try:
        parts = urlsplit(origin)
        _ = parts.port
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.path not in {"", "/"}
            or parts.query
            or parts.fragment
            or any(ord(char) <= 32 for char in origin)
        ):
            raise ValueError
        return f"{parts.scheme}://{parts.netloc}/health"
    except ValueError:
        raise ValueError("Provide an HTTP(S) origin such as http://127.0.0.1:8000.") from None


def probe(url: str, timeout: float, *, expected_version: str | None = None, transport=None) -> dict:
    """Return typed readiness evidence with no redirects, proxies, credentials or response text."""
    with traces.tracer.start_as_current_span(
        "sibyl.readiness.probe", kind=SpanKind.CLIENT, record_exception=False, set_status_on_exception=False
    ) as span:
        headers = {"Accept-Encoding": "identity"}
        traces.propagator.inject(headers)
        result = _observe(url, timeout, headers, expected_version, transport, span)
        span.set_attribute("sibyl.readiness.status", result["status"])
        if result["status"] != "ok":
            span.set_status(Status(StatusCode.ERROR))
        return result


def _observe(url, timeout, headers, expected_version, transport, span):
    try:
        with (
            httpx.Client(
                timeout=timeout, follow_redirects=False, trust_env=False, transport=transport
            ) as client,
            client.stream("GET", url, headers=headers) as response,
        ):
            traces.record_response(span, response.status_code, error_at=400)
            if response.status_code != 200:
                return {"status": "http_error", "http_status": response.status_code}
            body = next(response.iter_raw(chunk_size=MAX_BODY + 1), b"")
            if len(body) > MAX_BODY:
                return {"status": "invalid_response"}
            health = json.loads(body)
    except httpx.TimeoutException:
        return {"status": "timeout"}
    except (httpx.HTTPError, httpx.InvalidURL):
        return {"status": "unreachable"}
    except (ValueError, UnicodeError):
        return {"status": "invalid_response"}
    if not isinstance(health, dict) or health.get("service") != "sibyl" or health.get("status") != "ok":
        return {"status": "invalid_response"}
    version = health.get("version")
    if not isinstance(version, str) or VERSION.fullmatch(version) is None:
        return {"status": "invalid_response"}
    return {
        "status": "ok" if expected_version in (None, version) else "version_mismatch",
        "version": version,
    }


def watch(url, timeout, interval, *, expected_version=None, notifications=None, failure_threshold=2):
    """Report observations and notify on confirmed outages and subsequent recovery."""
    previous, failures, outage = None, 0, False
    while True:
        current = probe(url, timeout, expected_version=expected_version)
        observation = {"observed_at": datetime.now(UTC).isoformat(), **current}
        if current != previous:
            print(json.dumps(observation), flush=True)
            previous = current
        if notifications is not None:
            failures = 0 if current["status"] == "ok" else failures + 1
            if not outage and failures >= failure_threshold:
                outage = True
                print(json.dumps(notifications.send("outage", observation)), file=sys.stderr, flush=True)
            elif outage and failures == 0:
                outage = False
                print(json.dumps(notifications.send("recovery", observation)), file=sys.stderr, flush=True)
        sleep(interval)


def main(argv=None):
    """Exit independently of app startup so schedulers and remote monitors can observe outages."""
    parser = argparse.ArgumentParser(prog="sibyl probe", description="Check Sibyl's HTTP readiness.")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Sibyl backend origin.")
    parser.add_argument("--timeout", type=float, default=2, help="Network timeout in seconds (0.1–10).")
    parser.add_argument("--expect-version", help="Require an exact healthy backend version.")
    parser.add_argument("--watch", action="store_true", help="Keep running and print readiness transitions.")
    parser.add_argument("--interval", type=float, default=30, help="Watch interval in seconds (5–3600).")
    parser.add_argument(
        "--notify-webhook", action="store_true", help="Post watch transitions to SIBYL_PROBE_WEBHOOK."
    )
    parser.add_argument(
        "--failure-threshold", type=int, default=2, help="Failures before an outage notification (1–20)."
    )
    args = parser.parse_args(argv)
    if not 0.1 <= args.timeout <= 10:
        parser.error("--timeout must be between 0.1 and 10 seconds.")
    if not 5 <= args.interval <= 3600:
        parser.error("--interval must be between 5 and 3,600 seconds.")
    if args.expect_version and VERSION.fullmatch(args.expect_version) is None:
        parser.error("Invalid expected version.")
    if not 1 <= args.failure_threshold <= 20:
        parser.error("--failure-threshold must be between 1 and 20.")
    if args.notify_webhook and not args.watch:
        parser.error("--notify-webhook requires --watch.")
    try:
        url = health_url(args.url)
        notifications = None
        if args.notify_webhook:
            notifications = WatchNotifications(
                getenv("SIBYL_PROBE_WEBHOOK", ""), getenv("SIBYL_PROBE_WEBHOOK_TOKEN", "")
            )
    except ValueError as error:
        parser.error(str(error))
    if args.watch:
        try:
            watch(
                url,
                args.timeout,
                args.interval,
                expected_version=args.expect_version,
                notifications=notifications,
                failure_threshold=args.failure_threshold,
            )
        except KeyboardInterrupt:
            raise SystemExit(130) from None
    result = probe(url, args.timeout, expected_version=args.expect_version)
    print(json.dumps(result))
    raise SystemExit(0 if result["status"] == "ok" else 1)
