"""Verify remote readiness and the privacy of bounded local API observations."""

import json

import httpx
import pytest

from sibyl.cli import main
from sibyl.operations.probe import health_url, probe
from sibyl.operations.traffic import SAMPLE_LIMIT, ApiTraffic


def test_api_request_ids_are_generated_and_diagnostics_do_not_keep_payloads(client):
    first = client.get("/api/v1/system?unlogged=PRIVATE-PAYLOAD", headers={"X-Request-ID": "PRIVATE-HEADER"})
    second = client.get("/api/v1/does-not-exist?unlogged=PRIVATE-PAYLOAD")
    assert first.status_code == 200 and second.status_code == 404
    assert len(first.headers["X-Request-ID"]) == 32
    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]
    report = client.post("/api/v1/workspace/diagnostics", json={}).json()
    assert report["api_traffic"]["sample_size"] >= 2
    assert report["api_traffic"]["status_classes"]["4xx"] >= 1
    exported = client.get("/api/v1/workspace/diagnostics/export").text
    assert "PRIVATE" not in exported
    assert first.headers["X-Request-ID"] not in exported
    assert second.headers["X-Request-ID"] not in exported


def test_traffic_window_remains_bounded():
    traffic = ApiTraffic()
    traffic.record(200, 0)
    for _ in range(SAMPLE_LIMIT):
        traffic.record(503, 0.01)
    assert traffic.summary() == {
        "sample_size": SAMPLE_LIMIT,
        "sample_limit": SAMPLE_LIMIT,
        "status_classes": {"5xx": SAMPLE_LIMIT},
        "median_response_start_ms": 10,
    }


@pytest.mark.parametrize(
    ("status", "body", "expected"),
    [
        (200, b'{"service":"sibyl","status":"ok","version":"2.4.0"}', "ok"),
        (200, b'{"service":"other","status":"ok","version":"2.4.0"}', "invalid_response"),
        (200, b"x" * 1025, "invalid_response"),
        (302, b"", "http_error"),
        (503, b"private", "http_error"),
    ],
)
def test_probe_checks_identity_and_rejects_redirects_and_oversize_bodies(status, body, expected):
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(status, stream=httpx.ByteStream(body), headers={"Location": "/elsewhere"})

    result = probe("https://dashboard.example/health", 1, transport=httpx.MockTransport(transport))
    assert result["status"] == expected
    assert [request.url.path for request in requests] == ["/health"]
    assert "Authorization" not in requests[0].headers
    assert "private" not in repr(result)


@pytest.mark.parametrize(
    "error,expected",
    [
        (httpx.ReadTimeout, "timeout"),
        (httpx.ConnectError, "unreachable"),
    ],
)
def test_probe_can_detect_health_failures_from_outside_the_app(error, expected):
    def transport(request):
        raise error("PRIVATE-HOST-DETAIL")

    result = probe("https://dashboard.example/health", 1, transport=httpx.MockTransport(transport))
    assert result == {"status": expected}


def test_probe_cli_version_check_and_exit_codes(monkeypatch, capsys):
    from sibyl.operations import probe as module

    url = health_url("http://[::1]:8000")
    assert url == "http://[::1]:8000/health"
    with pytest.raises(ValueError, match="origin"):
        health_url("https://username:secret@example.test")

    def checked(url, timeout, *, expected_version):
        assert url == "http://127.0.0.1:8000/health" and timeout == 2
        return {"status": "ok" if expected_version == "2.4.0" else "version_mismatch", "version": "2.4.0"}

    monkeypatch.setattr(module, "probe", checked)
    for version, code in [("2.4.0", 0), ("2.3.0", 1)]:
        with pytest.raises(SystemExit) as error:
            main(["probe", "--expect-version", version])
        assert error.value.code == code
        assert json.loads(capsys.readouterr().out)["version"] == "2.4.0"


def test_watcher_reports_outages_and_recovery_only_on_change(monkeypatch, capsys):
    from sibyl.operations import probe as module

    responses = iter(
        [
            {"status": "ok", "version": "2.4.0"},
            {"status": "ok", "version": "2.4.0"},
            {"status": "unreachable"},
            {"status": "unreachable"},
            {"status": "ok", "version": "2.4.0"},
        ]
    )
    intervals = []
    monkeypatch.setattr(module, "probe", lambda *_args, **_kwargs: next(responses))

    def wait(interval):
        intervals.append(interval)
        if len(intervals) == 5:
            raise KeyboardInterrupt

    monkeypatch.setattr(module, "sleep", wait)
    with pytest.raises(SystemExit) as error:
        main(["probe", "--watch", "--interval", "15"])
    assert error.value.code == 130 and intervals == [15] * 5
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [event["status"] for event in events] == ["ok", "unreachable", "ok"]
    assert all("observed_at" in event for event in events)
