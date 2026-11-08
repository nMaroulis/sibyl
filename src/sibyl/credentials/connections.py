"""Replace write-only API credentials while retaining one explicitly confirmed account identity.

No generic exchange API proves that two keys represent the same principal. The
owner must confirm that fact. Replacing an account with another principal would
mix retained history, so a distinct account must use a separate connection.
"""

import hashlib
import json
from datetime import UTC, datetime

from pydantic import Field, SecretStr, model_validator

from sibyl.models import ConnectionCreate, Request

CONFIRMATION = "REPLACE SAVED EXCHANGE CREDENTIALS"


class ReplaceCredentials(Request):
    api_key: SecretStr
    secret: SecretStr
    passphrase: SecretStr = SecretStr("")
    uid: SecretStr = SecretStr("")
    revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmation: str = Field(max_length=100)
    same_account: bool = Field(strict=True)

    @model_validator(mode="after")
    def confirm(self):
        if not self.same_account or self.confirmation != CONFIRMATION:
            raise ValueError(
                "Confirm that these keys belong to the same exchange account and type the replacement phrase."
            )
        return self


class ConnectionCredentials:
    """Rotate saved provider secrets; metadata and imported financial records are unchanged."""

    def __init__(self, store):
        self.store = store
        with store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS connection_key_changes (id INTEGER PRIMARY KEY, account_id TEXT NOT NULL, changed_at TEXT NOT NULL, previous_revision TEXT NOT NULL, revision TEXT NOT NULL)"
            )

    @staticmethod
    def _read(db, identity):
        row = db.execute(
            "SELECT *,EXISTS(SELECT 1 FROM active_accounts WHERE account_id=connections.id) AS active FROM connections WHERE id=?",
            (identity,),
        ).fetchone()
        if row is None:
            raise LookupError("Connection not found.")
        if row["exchange"] == "demo":
            raise ValueError("Demo has no API credentials to replace.")
        return row

    def state(self, identity):
        """Expose an opaque revision and change dates, never key prefixes or secret fields."""
        with self.store.db() as db:
            row = self._read(db, identity)
            history = [
                dict(item)
                for item in db.execute(
                    "SELECT id,changed_at FROM connection_key_changes WHERE account_id=? ORDER BY id DESC LIMIT 20",
                    (identity,),
                )
            ]
            return {
                "id": identity,
                "exchange": row["exchange"],
                "label": row["label"],
                "active": bool(row["active"]),
                "revision": hashlib.sha256(row["credentials"]).hexdigest(),
                "history": history,
                "confirmation": CONFIRMATION,
                "note": "Replacement keeps this connection ID and all retained history. Use a new connection for a different exchange account. No provider is contacted when saving; check access before activating again.",
            }

    def replace(self, identity, body):
        """Check inactivity and revision atomically before saving a complete validated credential set."""
        with self.store.vault.lock, self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._read(db, identity)
            if row["active"]:
                raise ValueError("Deactivate this connection before replacing its credentials.")
            previous = hashlib.sha256(row["credentials"]).hexdigest()
            if body.revision != previous:
                raise ValueError("Saved credentials changed. Reload this form before replacing them.")
            validated = ConnectionCreate(
                exchange=row["exchange"],
                label=row["label"],
                sandbox=bool(row["sandbox"]),
                api_key=body.api_key,
                secret=body.secret,
                passphrase=body.passphrase,
                uid=body.uid,
            )
            values = {
                "apiKey": validated.api_key.get_secret_value(),
                "secret": validated.secret.get_secret_value(),
                "password": validated.passphrase.get_secret_value(),
                "uid": validated.uid.get_secret_value(),
            }
            encrypted = self.store.cipher.encrypt(json.dumps(values).encode())
            db.execute("UPDATE connections SET credentials=? WHERE id=?", (encrypted, identity))
            db.execute(
                "INSERT INTO connection_key_changes(account_id,changed_at,previous_revision,revision) VALUES(?,?,?,?)",
                (identity, datetime.now(UTC).isoformat(), previous, hashlib.sha256(encrypted).hexdigest()),
            )
        return self.state(identity)
