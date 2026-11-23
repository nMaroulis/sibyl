"""Wrapping-key rotation preserves secrets through commits, interruptions and competing writers."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from cryptography.fernet import Fernet, InvalidToken

from sibyl.credentials.rotation import CONFIRMATION, RotateVault, VaultRotation
from sibyl.models import ConnectionCreate
from sibyl.storage import Store


def seed(store):
    account = store.add_connection(
        ConnectionCreate(
            exchange="binance",
            label="Private test account",
            api_key="EXCHANGE-PRIVATE-KEY",
            secret="EXCHANGE-PRIVATE-SECRET",
        )
    )
    store.save_model_profile("openai", {"api_key": "MODEL-PRIVATE-KEY", "model": "configured-model"})
    store.save_data_profile("messaging:telegram", {"bot_token": "BOT-PRIVATE-TOKEN", "allowed_user_id": 42})
    return account


def rotate(service):
    return service.rotate(RotateVault(key_id=service.state()["key_id"], confirmation=CONFIRMATION))


def assert_secrets(store, identity):
    assert store.credentials(identity)["apiKey"] == "EXCHANGE-PRIVATE-KEY"
    assert store.model_profiles()[1]["openai"]["api_key"] == "MODEL-PRIVATE-KEY"
    assert store.data_profile("messaging:telegram")["bot_token"] == "BOT-PRIVATE-TOKEN"


def test_rotation_reencrypts_all_private_columns_without_changing_provider_values(store):
    account = seed(store)
    old_key = store.vault.path.read_bytes()
    with store.db() as db:
        old_token = db.execute("SELECT credentials FROM connections WHERE id=?", (account.id,)).fetchone()[0]
    state = rotate(VaultRotation(store))
    new_key = store.vault.path.read_bytes()
    assert old_key != new_key
    assert not store.vault.previous.exists()
    assert state["history"][0]["records"] >= 4
    assert_secrets(Store(store.path.parent), account.id)
    with store.db() as db:
        new_token = db.execute("SELECT credentials FROM connections WHERE id=?", (account.id,)).fetchone()[0]
        assert (
            db.execute("SELECT value FROM workspace_settings WHERE key='llm_provider'").fetchone()[0]
            == "openai"
        )
    assert Fernet(old_key).extract_timestamp(old_token) == Fernet(new_key).extract_timestamp(new_token)
    with pytest.raises(InvalidToken):
        Fernet(old_key).decrypt(new_token)
    assert all(
        secret not in json.dumps(state)
        for secret in ["EXCHANGE-PRIVATE", "MODEL-PRIVATE", "BOT-PRIVATE", old_key.decode(), new_key.decode()]
    )


@pytest.mark.parametrize("published", [False, True])
def test_interruption_keeps_recovery_keys_and_can_complete_after_reopening(store, monkeypatch, published):
    account = seed(store)
    service = VaultRotation(store)
    original = store.vault.publish
    with monkeypatch.context() as patch:

        def interrupted(key):
            if published:
                original(key)
            raise RuntimeError("simulated process loss before SQLite commit")

        patch.setattr(store.vault, "publish", interrupted)
        with pytest.raises(RuntimeError):
            rotate(service)
    assert store.vault.previous.exists()
    reopened = Store(store.path.parent)
    assert_secrets(reopened, account.id)
    resumed = VaultRotation(reopened)
    assert resumed.state()["recovery_pending"]
    assert resumed.state()["history"] == []  # The failed SQL transaction did not invent success.
    result = rotate(resumed)
    assert not result["recovery_pending"]
    assert result["history"][0]["recovered"] == 1
    assert_secrets(Store(store.path.parent), account.id)


def test_competing_store_writer_selects_current_key_after_sqlite_admission(store, monkeypatch):
    account = seed(store)
    other = Store(store.path.parent)  # This instance initially cached the old key.
    entered, release = threading.Event(), threading.Event()
    original = store.vault.publish

    def paused(key):
        original(key)
        entered.set()
        assert release.wait(timeout=10)

    monkeypatch.setattr(store.vault, "publish", paused)
    with ThreadPoolExecutor(max_workers=2) as pool:
        rotating = pool.submit(rotate, VaultRotation(store))
        try:
            assert entered.wait(timeout=3)
            saving = pool.submit(
                other.save_data_profile, "new-private-profile", {"api_key": "LATE-PRIVATE-KEY"}
            )
        finally:
            release.set()
        rotating.result(timeout=5)
        saving.result(timeout=5)
    reopened = Store(store.path.parent)
    assert_secrets(reopened, account.id)
    assert reopened.data_profile("new-private-profile")["api_key"] == "LATE-PRIVATE-KEY"
    with reopened.db() as db:
        token = db.execute(
            "SELECT value FROM workspace_settings WHERE key='data:new-private-profile'"
        ).fetchone()[0]
    assert (
        json.loads(Fernet(reopened.vault.path.read_bytes()).decrypt(token))["api_key"] == "LATE-PRIVATE-KEY"
    )


def test_invalid_record_rolls_back_all_prior_reencryptions(store):
    account = seed(store)
    with store.db() as db:
        before = db.execute("SELECT credentials FROM connections WHERE id=?", (account.id,)).fetchone()[0]
        db.execute(
            "UPDATE model_profiles SET config=? WHERE provider='openai'", (b"not-an-authenticated-token",)
        )
    key = store.vault.path.read_bytes()
    with pytest.raises(ValueError, match="authenticated"):
        rotate(VaultRotation(store))
    assert store.vault.path.read_bytes() == key
    with store.db() as db:
        assert (
            db.execute("SELECT credentials FROM connections WHERE id=?", (account.id,)).fetchone()[0]
            == before
        )
        assert db.execute("SELECT COUNT(*) FROM vault_rotations").fetchone()[0] == 0
    assert store.credentials(account.id)["apiKey"] == "EXCHANGE-PRIVATE-KEY"


def test_revision_and_confirmation_are_required_before_key_or_database_changes(store):
    seed(store)
    service = VaultRotation(store)
    state = service.state()
    with pytest.raises(ValueError, match="Type"):
        service.rotate(RotateVault(key_id=state["key_id"], confirmation="no"))
    with pytest.raises(ValueError, match="changed"):
        service.rotate(RotateVault(key_id="0" * 16, confirmation=CONFIRMATION))
    assert not store.vault.previous.exists()
    assert service.state()["history"] == []


def test_missing_key_never_generates_a_replacement_for_an_existing_database(store):
    key = store.vault.path.read_bytes()
    store.vault.path.unlink()
    with pytest.raises(ValueError, match="missing"):
        Store(store.path.parent)
    assert not store.vault.path.exists()
    store.vault.path.write_bytes(key)


def test_api_returns_no_key_material_and_preserves_account_ids(manual_client):
    client = manual_client
    account = seed(client.app.state.services.store)
    state = client.get("/api/v1/workspace/vault").json()
    response = client.post(
        "/api/v1/workspace/vault/rotate", json={"key_id": state["key_id"], "confirmation": CONFIRMATION}
    )
    assert response.status_code == 200, response.text
    assert response.json()["key_id"] != state["key_id"]
    assert response.headers["cache-control"] == "no-store"
    assert "PRIVATE" not in response.text
    assert client.app.state.services.store.credentials(account.id)["secret"] == "EXCHANGE-PRIVATE-SECRET"


def test_post_rotation_encrypted_archive_restores_its_matching_key(manual_client):
    from sibyl.operations.archives import WorkspaceArchives

    client = manual_client
    store = client.app.state.services.store
    account = seed(store)
    rotate(VaultRotation(store))
    archives = WorkspaceArchives(store)
    saved = archives.create("a-long-test-archive-passphrase")
    restored = archives.restore(saved["id"], "a-long-test-archive-passphrase")
    reopened = Store(Path(restored["data_dir"]))
    assert_secrets(reopened, account.id)
