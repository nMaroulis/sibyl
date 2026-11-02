"""Deterministic worker faults, encrypted archive boundaries and safe restored startup."""

import asyncio
import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sibyl.api.app import create_app
from sibyl.config import Settings
from sibyl.models import BacktestRequest
from sibyl.operations.archives import MAGIC, WorkspaceArchives, cipher
from sibyl.operations.health import WorkerHealth
from sibyl.storage import Store

PASSWORD = "a distinct archive passphrase"


def test_archives_and_recovery_stay_in_writable_volume_and_are_not_backed_up(tmp_path):
    parent = tmp_path / "container-root"
    data = parent / "data"
    data.mkdir(parents=True)
    repository = Store(data)
    parent.chmod(0o555)
    try:
        archives = WorkspaceArchives(repository)
        first = archives.create(PASSWORD)
        restored = archives.restore(first["id"], PASSWORD)
        assert Path(restored["data_dir"]).is_relative_to(data)
        second = archives.create(PASSWORD)
        archive, manifest = archives._read(second["id"], PASSWORD)
        try:
            assert all(not entry["path"].startswith(".sibyl-managed/") for entry in manifest["files"])
        finally:
            archive.close()
    finally:
        parent.chmod(0o700)


def test_recovered_directory_is_absolute_even_for_a_relative_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    archive = WorkspaceArchives(Store(Path("workspace")))
    backup = archive.create(PASSWORD)
    result = archive.restore(backup["id"], PASSWORD)
    assert Path(result["data_dir"]).is_absolute()


def test_archive_admission_rejects_overlapping_work_before_key_derivation(store, monkeypatch):
    archive = WorkspaceArchives(store)
    monkeypatch.setattr(
        "sibyl.operations.archives.cipher", lambda *a: pytest.fail("Busy operation derived a key")
    )
    with archive._operation():
        with pytest.raises(ValueError, match="progress"):
            archive.create(PASSWORD)
    with archive.admit_upload():
        with pytest.raises(ValueError, match="upload"):
            with archive.admit_upload():
                pass


async def test_upload_bound_works_without_content_length():
    from fastapi import HTTPException

    from sibyl.api.uploads import bounded_body

    class Stream:
        async def stream(self):
            for chunk in (b"123", b"456"):
                yield chunk

    with pytest.raises(HTTPException) as error:
        await bounded_body(Stream(), 5)
    assert error.value.status_code == 413


async def eventually(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0.005)


async def test_failed_worker_is_visible_and_does_not_replay_side_effects(store):
    health = WorkerHealth(store)
    calls = []

    def fail():
        calls.append(1)
        raise RuntimeError("PRIVATE-CREDENTIAL-FAILURE")

    health.start("test", "Faulted task", fail, interval=0.01)
    await eventually(lambda: health.workers["test"]["state"] == "failed")
    result = health.snapshot()
    assert result["issue_count"] == 1 and result["workers"][0]["last_error"] == "RuntimeError"
    assert "PRIVATE" not in json.dumps(result) and calls == [1]
    await health.close()


async def test_progress_deadline_comes_from_actual_work_and_shutdown_drains_threads(store):
    import threading

    now = [0.0]
    entered = threading.Event()
    release = threading.Event()

    def slow():
        entered.set()
        release.wait(3)

    health = WorkerHealth(store, clock=lambda: now[0])
    health.start("slow", "Slow work", slow, deadline=5)
    await eventually(entered.is_set)
    now[0] = 6
    assert health.snapshot()["workers"][0]["state"] == "stalled"
    closing = asyncio.create_task(health.close())
    await asyncio.sleep(0.01)
    assert not closing.done()
    release.set()
    await closing
    assert not health.inflight


async def test_explicit_retry_and_fault_history_survive_supervisor_restart(store):
    import sqlite3

    health = WorkerHealth(store)
    calls = []

    def action():
        calls.append(1)
        if len(calls) == 1:
            raise sqlite3.OperationalError("PRIVATE")

    health.start("retry", "Storage retry", action, interval=0.01, retryable=(sqlite3.Error,))
    await eventually(lambda: health.workers["retry"]["iterations"] >= 1)
    assert health.snapshot()["issue_count"] == 0
    await health.close()
    restored = WorkerHealth(store)
    assert any(row["kind"] == "retrying" for row in restored.snapshot()["events"])
    assert any(row["kind"] == "recovered" for row in restored.snapshot()["events"])


def test_archive_is_encrypted_authenticates_and_restores_database_and_vault(store):
    store.save_data_profile("test-secret", {"api_key": "PRIVATE-ARCHIVE-KEY"})
    archives = WorkspaceArchives(store)
    item = archives.create(PASSWORD)
    raw = archives.path(item["id"]).read_bytes()
    assert raw.startswith(MAGIC) and b"PRIVATE-ARCHIVE-KEY" not in raw
    assert store.path.read_bytes() not in raw
    inspection = archives.inspect(item["id"], PASSWORD)
    assert inspection["includes_credentials"] and "api_key" not in str(inspection)
    with pytest.raises(ValueError, match="passphrase"):
        archives.inspect(item["id"], "incorrect passphrase")
    result = archives.restore(item["id"], PASSWORD)
    target = Path(result["data_dir"])
    assert target != store.path.parent
    recovered = Store(target)
    assert (target / ".gitignore").read_text() == "*\n"
    assert (archives.directory / ".gitignore").read_text() == "*\n"
    assert recovered.data_profile("test-secret")["api_key"] == "PRIVATE-ARCHIVE-KEY"
    assert recovered.data_profile("workspace-recovery")["required"]
    with recovered.db() as db:
        assert not db.execute("SELECT * FROM active_accounts").fetchall()
    assert store.data_profile("test-secret")["api_key"] == "PRIVATE-ARCHIVE-KEY"
    assert not store.data_profile("workspace-recovery")


def test_restore_is_paused_and_does_not_enable_background_or_exchange_work(client):
    services = client.app.state.services
    job = services.strategies.start(BacktestRequest(), source="demo")
    item = services.archives.create(PASSWORD)
    restored = services.archives.restore(item["id"], PASSWORD)
    with TestClient(
        create_app(
            Settings(
                data_dir=restored["data_dir"],
                _env_file=None,
                allow_live_trading=True,
                allow_strategy_execution=True,
            )
        )
    ) as other:
        runtime = other.app.state.services
        result = other.get("/api/v1/workspace/health").json()
        assert result["recovery_required"] and all(w["state"] == "paused" for w in result["workers"])
        assert not runtime.settings.allow_live_trading and not runtime.settings.allow_strategy_execution
        assert runtime.strategies.journal.job(job["id"])["status"] == "paused"
        assert not runtime.workers.tasks
        assert other.post(
            "/api/v1/workspace/recovery/complete", json={"confirmation": "I REVIEWED THE RESTORED WORKSPACE"}
        ).json()["restart_required"]
        assert not runtime.workers.tasks  # An explicit restart is still required.
        assert runtime.store.data_profile("workspace-recovery")["source_backup"] == item["id"]


@pytest.mark.parametrize(
    "bad_path",
    ["../escape", "/absolute", "C:/drive", "folder\\escape", "NUL.txt", "dir/./alias", ".", "trailing."],
)
def test_authenticated_but_unsafe_archive_paths_are_rejected(store, bad_path):
    archives = WorkspaceArchives(store)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as output:
        output.writestr(bad_path, "unsafe")
        output.writestr("backup-manifest.json", json.dumps({"format": 1, "files": []}))
    salt = b"0123456789abcdef"
    item = archives.upload(MAGIC + salt + cipher(PASSWORD, salt).encrypt(buffer.getvalue()))
    with pytest.raises(ValueError):
        archives.restore(item["id"], PASSWORD)
    assert not (archives.managed / "recovered").exists()


def test_archive_api_requires_explicit_confirmation_and_never_returns_a_passphrase(client):
    result = client.post("/api/v1/workspace/backups", json={"passphrase": PASSWORD})
    assert result.status_code == 201 and PASSWORD not in result.text
    identifier = result.json()["id"]
    assert (
        client.post(
            f"/api/v1/workspace/backups/{identifier}/restore",
            json={"passphrase": PASSWORD, "confirmation": "yes"},
        ).status_code
        == 422
    )
    assert (
        client.get(f"/api/v1/workspace/backups/{identifier}/download").headers["cache-control"] == "no-store"
    )
    assert client.get("/api/v1/workspace/health").headers["cache-control"] == "no-store"
    assert client.post("/api/v1/workspace/backups", json={"passphrase": "PRIVATE"}).status_code == 422
    assert PASSWORD not in str(client.app.state.services.store.model_profiles())


def test_recovery_quarantines_queued_messages_and_pauses_calendars_without_network(store):
    from sibyl.operations.recovery import prepare_recovery

    store.save_data_profile("messaging:telegram", {"enabled": True, "bot_token": "PRIVATE-TEST-TOKEN"})
    with store.db() as db:
        db.executescript("""
          CREATE TABLE briefing_schedules(id TEXT,status TEXT,next_at REAL,payload TEXT);
          CREATE TABLE briefing_occurrences(id TEXT,status TEXT,payload TEXT);
          CREATE TABLE telegram_outbox(state TEXT,error TEXT);
          CREATE TABLE telegram_updates(state TEXT);
        """)
        db.execute(
            "INSERT INTO briefing_schedules VALUES(?,?,?,?)",
            (
                "calendar",
                "armed",
                123,
                json.dumps({"status": "armed", "next_run_at": "2026-12-01", "revision": 1}),
            ),
        )
        db.execute(
            "INSERT INTO briefing_occurrences VALUES(?,?,?)",
            ("queued", "waiting", json.dumps({"status": "waiting"})),
        )
        db.execute("INSERT INTO telegram_outbox VALUES('pending',NULL)")
        db.execute("INSERT INTO telegram_updates VALUES('processing')")
    prepare_recovery(store, "backup-reference")
    assert not store.data_profile("messaging:telegram")["enabled"]
    with store.db() as db:
        assert db.execute("SELECT status FROM briefing_schedules").fetchone()[0] == "paused"
        assert db.execute("SELECT status FROM briefing_occurrences").fetchone()[0] == "interrupted"
        assert db.execute("SELECT state FROM telegram_outbox").fetchone()[0] == "uncertain"
        assert db.execute("SELECT state FROM telegram_updates").fetchone()[0] == "interrupted"


def test_tampered_ciphertext_fails_authentication(store):
    archives = WorkspaceArchives(store)
    item = archives.create(PASSWORD)
    path = archives.path(item["id"])
    data = bytearray(path.read_bytes())
    data[-20] ^= 1
    path.write_bytes(data)
    with pytest.raises(ValueError, match="passphrase|damaged"):
        archives.inspect(item["id"], PASSWORD)


def test_manifest_has_its_own_decompression_limit(store):
    archives = WorkspaceArchives(store)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as output:
        output.writestr("backup-manifest.json", " " * 512001)
    salt = b"0123456789abcdef"
    item = archives.upload(MAGIC + salt + cipher(PASSWORD, salt).encrypt(buffer.getvalue()))
    with pytest.raises(ValueError, match="limits"):
        archives.inspect(item["id"], PASSWORD)
