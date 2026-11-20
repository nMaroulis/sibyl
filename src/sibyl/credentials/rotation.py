"""Explicit revision-bound vault re-encryption with an append-only local audit.

This rotates Sibyl's wrapping key, not API credentials at exchanges or AI
providers. Existing backups retain their own keys inside archive encryption.
"""

from datetime import UTC, datetime

from cryptography.fernet import InvalidToken
from pydantic import Field

from sibyl.models import Request

CONFIRMATION = "ROTATE LOCAL VAULT KEY"


class RotateVault(Request):
    key_id: str = Field(pattern=r"^[a-f0-9]{16}$")
    confirmation: str = Field(max_length=80)


class VaultRotation:
    """Serialize local crypto writes and publish keys before releasing SQLite admission."""

    def __init__(self, store):
        self.store = store
        with store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS vault_rotations (id INTEGER PRIMARY KEY, at TEXT NOT NULL, key_id TEXT NOT NULL, records INTEGER NOT NULL, recovered INTEGER NOT NULL)"
            )

    def state(self):
        vault = self.store.vault
        with vault.lock, self.store.db() as db:
            vault.refresh()
            history = [
                dict(row) for row in db.execute("SELECT * FROM vault_rotations ORDER BY id DESC LIMIT 20")
            ]
            counts = {
                "exchange_accounts": db.execute("SELECT COUNT(*) FROM connections").fetchone()[0],
                "model_profiles": db.execute("SELECT COUNT(*) FROM model_profiles").fetchone()[0],
                "encrypted_settings": db.execute(
                    "SELECT COUNT(*) FROM workspace_settings WHERE key LIKE 'data:%' OR key='llm_default_model'"
                ).fetchone()[0],
            }
            return {
                "key_id": vault.identity(vault.path.read_bytes()),
                "recovery_pending": vault.previous.exists(),
                "history": history,
                "record_counts": counts,
                "confirmation": CONFIRMATION,
                "note": "Re-encrypts local saved credentials and settings with a fresh wrapping key. Provider API tokens are unchanged; revoke or replace them at the provider separately. Existing encrypted backups retain their original included vault keys. Credential-bound funding sync controls require fresh review after encrypted records change.",
            }

    def rotate(self, body):
        vault = self.store.vault
        if body.confirmation != CONFIRMATION:
            raise ValueError("Type " + CONFIRMATION + " to rotate the local wrapping key.")
        with vault.lock:
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                vault.refresh()
                if body.key_id != vault.identity(vault.path.read_bytes()):
                    raise ValueError("The vault key changed. Reload before rotating.")
                recovered = vault.previous.exists()
                target = vault.stage()
                # Native rotation preserves each token's original authentication timestamp.
                wrapping = vault.rotation_cipher(target)
                count = 0
                for table, identity, column, where in (
                    ("connections", "id", "credentials", "1=1"),
                    ("model_profiles", "provider", "config", "1=1"),
                    ("workspace_settings", "key", "value", "key LIKE 'data:%' OR key='llm_default_model'"),
                ):
                    for row in db.execute(
                        f"SELECT {identity},{column} FROM {table} WHERE {where}"
                    ).fetchall():
                        try:
                            encrypted = wrapping.rotate(row[1])
                        except InvalidToken:
                            raise ValueError(
                                "A saved encrypted record could not be authenticated. No rotation was committed; review a matching backup or the damaged profile."
                            ) from None
                        db.execute(
                            f"UPDATE {table} SET {column}=? WHERE {identity}=?",
                            (encrypted, row[0]),
                        )
                        count += 1
                vault.publish(target)
                db.execute(
                    "INSERT INTO vault_rotations(at,key_id,records,recovered) VALUES(?,?,?,?)",
                    (datetime.now(UTC).isoformat(), vault.identity(target), count, int(recovered)),
                )
            vault.finish()
        return self.state()
