"""Fernet key-file ownership and interruption-safe local rotation stages.

Encryption uses cryptography's native MultiFernet; no custom cryptography is
implemented. A previous key remains on disk until the database commit succeeds.
Keys cached for already open snapshots remain process-private until shutdown.
"""

import hashlib
import os
import threading
from uuid import uuid4

from cryptography.fernet import Fernet, MultiFernet


def sync_directory(path):
    """Flush directory metadata where supported; Windows lacks POSIX directory fsync."""
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_key(path, key):
    """Publish an owner-readable complete key with same-directory atomic replacement."""
    temporary = path.with_name(".vault-" + uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as stream:
            os.chmod(temporary, 0o600)
            stream.write(key)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


class CredentialVault:
    """Own key material; application APIs receive only opaque key IDs and status."""

    def __init__(self, directory):
        self.path = directory / "vault.key"
        self.previous = directory / "vault.previous.key"
        self.lock = threading.RLock()
        self._keys = []
        if not self.path.exists() and (directory / "sibyl.db").exists():
            raise ValueError(
                "The workspace vault key is missing. Restore it from a matching backup before starting."
            )
        try:
            with self.path.open("xb") as stream:
                os.chmod(self.path, 0o600)
                stream.write(Fernet.generate_key())
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            pass
        self.refresh()

    @staticmethod
    def identity(key):
        return hashlib.sha256(key).hexdigest()[:16]

    def refresh(self):
        """Read current/recovery files before use, retaining old keys for open snapshots."""
        with self.lock:
            if not self.path.exists():
                raise ValueError("The workspace vault key is missing; no credential operation was performed.")
            keys = []
            for path in (self.path, self.previous):
                if path.is_symlink():
                    raise ValueError("Vault key files must not be symbolic links.")
                if path.exists():
                    try:
                        value = path.read_bytes()
                    except FileNotFoundError:
                        if path == self.previous:
                            continue
                        raise ValueError("The workspace vault key is missing.") from None
                    Fernet(value)  # Validate without putting key bytes in an error message.
                    if value not in keys:
                        keys.append(value)
            for value in self._keys:
                if value not in keys:
                    keys.append(value)
            if not keys:
                raise ValueError("The workspace vault key is unavailable.")
            self._keys = keys
            return MultiFernet([Fernet(key) for key in keys])

    def rotation_cipher(self, target):
        """Use native MultiFernet token rotation without exposing key material."""
        with self.lock:
            self.refresh()
            return MultiFernet([Fernet(target), *[Fernet(key) for key in self._keys]])

    def stage(self):
        """Retain the old key before any database/key publication can occur."""
        current = self.path.read_bytes()
        if not self.previous.exists():
            atomic_key(self.previous, current)
        previous = self.previous.read_bytes()
        return current if current != previous else Fernet.generate_key()

    def publish(self, key):
        """Publish the new primary while the caller still holds its SQLite writer."""
        atomic_key(self.path, key)
        self.refresh()

    def finish(self):
        """Remove recovery material only after the caller committed encrypted rows."""
        self.previous.unlink(missing_ok=True)
        sync_directory(self.path.parent)
