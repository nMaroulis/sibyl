"""Read Sibyl's public health endpoint from a separate process or host."""

import argparse
import json
import re
from datetime import UTC, datetime
from time import sleep
from urllib.parse import urlsplit

import httpx

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
    try:
        with (
            httpx.Client(
                timeout=timeout, follow_redirects=False, trust_env=False, transport=transport
            ) as client,
            client.stream("GET", url, headers={"Accept-Encoding": "identity"}) as response,
        ):
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


def watch(url, timeout, interval, *, expected_version=None):
    """Emit state transitions while polling from a caller-owned process."""
    previous = None
    while True:
        current = probe(url, timeout, expected_version=expected_version)
        if current != previous:
            print(json.dumps({"observed_at": datetime.now(UTC).isoformat(), **current}), flush=True)
            previous = current
        sleep(interval)


def main(argv=None):
    """Exit independently of app startup so schedulers and remote monitors can observe outages."""
    parser = argparse.ArgumentParser(prog="sibyl probe", description="Check Sibyl's HTTP readiness.")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Sibyl backend origin.")
    parser.add_argument("--timeout", type=float, default=2, help="Network timeout in seconds (0.1–10).")
    parser.add_argument("--expect-version", help="Require an exact healthy backend version.")
    parser.add_argument("--watch", action="store_true", help="Keep running and print readiness transitions.")
    parser.add_argument("--interval", type=float, default=30, help="Watch interval in seconds (5–3600).")
    args = parser.parse_args(argv)
    if not 0.1 <= args.timeout <= 10:
        parser.error("--timeout must be between 0.1 and 10 seconds.")
    if not 5 <= args.interval <= 3600:
        parser.error("--interval must be between 5 and 3,600 seconds.")
    if args.expect_version and VERSION.fullmatch(args.expect_version) is None:
        parser.error("Invalid expected version.")
    try:
        url = health_url(args.url)
    except ValueError as error:
        parser.error(str(error))
    if args.watch:
        try:
            watch(url, args.timeout, args.interval, expected_version=args.expect_version)
        except KeyboardInterrupt:
            raise SystemExit(130) from None
    result = probe(url, args.timeout, expected_version=args.expect_version)
    print(json.dumps(result))
    raise SystemExit(0 if result["status"] == "ok" else 1)
