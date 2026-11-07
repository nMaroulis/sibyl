"""Read-only health outcomes and strict content-free export boundaries."""

import json
from types import SimpleNamespace

import pytest
from test_agent_guidance import tool_call

from sibyl.operations.diagnostics import WorkspaceDiagnostics


def owner():
    return SimpleNamespace(
        snapshot=lambda: {
            "workers": [{"state": "waiting", "label": "PRIVATE-ACCOUNT", "last_error": "PRIVATE-TOKEN"}],
            "resources": {"rss_bytes": 123, "path": "PRIVATE-PATH", "cpu_percent": float("nan")},
        }
    )


def test_real_database_check_is_read_only_and_returns_only_allowlisted_evidence(store):
    with store.db() as db:
        db.execute("CREATE TABLE private_payload (secret TEXT)")
        db.execute("INSERT INTO private_payload VALUES('PRIVATE-CONTENT')")
    report = WorkspaceDiagnostics(store, owner()).run()
    assert report["database"]["status"] == "passed"
    assert report["database"]["findings"] == 0 and report["worker_states"] == {"waiting": 1}
    assert report["resources"]["rss_bytes"] == 123 and report["resources"]["cpu_percent"] is None
    assert "PRIVATE" not in json.dumps(report) and str(store.path) not in json.dumps(report)
    with store.db() as db:
        assert db.execute("SELECT secret FROM private_payload").fetchone()[0] == "PRIVATE-CONTENT"


def test_corrupt_and_missing_databases_never_claim_health_or_reveal_native_errors(tmp_path):
    path = tmp_path / "private-name.db"
    path.write_bytes(b"PRIVATE-BROKEN-DATABASE")
    for file in (path, tmp_path / "missing.db"):
        report = WorkspaceDiagnostics(SimpleNamespace(path=file), owner()).run()
        assert report["database"]["status"] == "unavailable"
        assert "PRIVATE" not in json.dumps(report)
    assert not (tmp_path / "missing.db").exists()


def test_expired_budget_is_incomplete_and_overlap_is_rejected(store):
    service = WorkspaceDiagnostics(store, owner(), budget_seconds=0)
    assert service.run()["database"]["status"] == "incomplete"
    with service.lock:
        with pytest.raises(ValueError, match="already running"):
            service.run()


def test_export_is_exact_private_and_passive_and_agent_does_not_run_check(manual_client, monkeypatch):
    client = manual_client
    diagnostics = client.app.state.services.workers.diagnostics
    assert client.get("/api/v1/workspace/diagnostics").json() == {"report": None}
    assert client.get("/api/v1/workspace/diagnostics/export").status_code == 400
    response = client.post("/api/v1/workspace/diagnostics", json={})
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["database"]["status"] == "passed" and response.headers["cache-control"] == "no-store"
    monkeypatch.setattr(diagnostics, "run", lambda: pytest.fail("Read/export reran the check"))
    exported = client.get("/api/v1/workspace/diagnostics/export")
    assert exported.json() == saved and "attachment" in exported.headers["content-disposition"]
    assert exported.headers["cache-control"] == "no-store"
    assert tool_call(client, "technician", "workspace_operations")["last_health_report"] == saved
    copied = diagnostics.last()
    copied["database"]["status"] = "tampered"
    assert diagnostics.last()["database"]["status"] == "passed"


def test_native_findings_cannot_reveal_private_table_names(store):
    with store.db() as db:
        db.execute("CREATE TABLE PRIVATE_TABLE(value INTEGER)")
        db.execute("INSERT INTO PRIVATE_TABLE VALUES(NULL)")
        # Deliberately malformed schema in this isolated test database only.
        # CHECK violations are not consistently reported by SQLite quick_check.
        db.execute("PRAGMA writable_schema=ON")
        db.execute(
            "UPDATE sqlite_master SET sql='CREATE TABLE PRIVATE_TABLE(value INTEGER NOT NULL)' WHERE name='PRIVATE_TABLE'"
        )
    report = WorkspaceDiagnostics(store, owner()).run()
    assert report["database"]["status"] == "issues_detected"
    assert report["database"]["findings"] > 0
    assert "PRIVATE" not in json.dumps(report)
