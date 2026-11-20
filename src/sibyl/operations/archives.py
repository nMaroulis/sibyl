"""Passphrase-encrypted, authenticated workspace snapshots and non-destructive restores."""

import base64
import hashlib
import io
import json
import os
import shutil
import sqlite3
import stat
import threading
import zipfile
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from sibyl import __version__

MAGIC = b"SIBYLBK1\n"
MAX_ARCHIVE = 384 * 1024 * 1024
MAX_RESTORED = 512 * 1024 * 1024


def safe_name(name):
    """Require canonical portable relative paths, excluding devices and traversal aliases."""
    path = PurePosixPath(name)
    reserved = {
        "con",
        "prn",
        "aux",
        "nul",
        *[f"com{i}" for i in range(1, 10)],
        *[f"lpt{i}" for i in range(1, 10)],
    }
    return (
        bool(name)
        and bool(path.parts)
        and name == path.as_posix()
        and not path.is_absolute()
        and all(
            part not in {".", ".."}
            and not part.endswith((".", " "))
            and part.split(".")[0].casefold() not in reserved
            for part in path.parts
        )
        and not any(char in name for char in '\\:"<>|?*')
        and all(ord(char) >= 32 for char in name)
    )


def cipher(passphrase, salt):
    """Derive an archive-only encryption key; never reuse or persist the workspace vault key as a password."""
    if not 12 <= len(passphrase) <= 1024:
        raise ValueError("Use a backup passphrase between 12 and 1,024 characters.")
    key = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode())
    return Fernet(base64.urlsafe_b64encode(key))


class WorkspaceArchives:
    """Manage encrypted archives in an excluded private area of the workspace volume.

    Each SQLite file uses SQLite's online backup API. Separate databases are
    individually consistent, not one distributed transaction. Restores create a
    separate directory and enter recovery mode before any application startup.
    No restore can overwrite the workspace running this service.
    """

    def __init__(self, store):
        self.store = store
        self.root = store.path.parent.resolve()
        self.managed = self.root / ".sibyl-managed"
        self.directory = self.managed / "backups"
        for folder in (self.managed, self.directory):
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                with (folder / ".gitignore").open("x") as ignore:
                    os.chmod(folder / ".gitignore", 0o600)
                    ignore.write("*\n")
            except FileExistsError:
                pass
        self.lock = threading.Lock()
        self._upload_lock = threading.Lock()

    @contextmanager
    def admit_upload(self):
        """Allow one buffered archive upload, independently of archive encryption work."""
        if not self._upload_lock.acquire(blocking=False):
            raise ValueError("Another archive upload is in progress.")
        try:
            yield
        finally:
            self._upload_lock.release()

    @contextmanager
    def _operation(self):
        """Admit one archive operation before allocating plaintext or deriving a key."""
        if not self.lock.acquire(blocking=False):
            raise ValueError("Another archive operation is in progress.")
        try:
            yield
        finally:
            self.lock.release()

    def path(self, identifier):
        if len(identifier) != 32 or any(c not in "0123456789abcdef" for c in identifier):
            raise LookupError("Backup not found.")
        path = self.directory / (identifier + ".sibylbackup")
        if not path.is_file() or path.is_symlink():
            raise LookupError("Backup not found.")
        return path

    def list(self):
        return {
            "items": [
                {
                    "id": p.stem,
                    "bytes": p.stat().st_size,
                    "created_at": datetime.fromtimestamp(p.stat().st_mtime, UTC).isoformat(),
                }
                for p in sorted(
                    self.directory.glob("*.sibylbackup"), key=lambda f: f.stat().st_mtime, reverse=True
                )
                if not p.is_symlink()
            ],
            "scope": "Encrypted local archives. Includes vault key inside the passphrase-protected archive. Separate SQLite snapshots can differ in time. Restore always creates a separate workspace with automatic work paused.",
        }

    def _store(self, content):
        if len(content) > MAX_ARCHIVE or not content.startswith(MAGIC):
            raise ValueError("Not a supported Sibyl archive, or archive exceeds 384 MiB.")
        if len(list(self.directory.glob("*.sibylbackup"))) >= 20:
            raise ValueError("Keep at most twenty local backups; download or remove older ones first.")
        identifier = uuid4().hex
        path = self.directory / (identifier + ".sibylbackup")
        with path.open("xb") as handle:
            os.chmod(path, 0o600)
            handle.write(content)
        return {
            "id": identifier,
            "bytes": len(content),
            "created_at": datetime.now(UTC).isoformat(),
            "sha256": hashlib.sha256(content).hexdigest(),
        }

    def upload(self, content):
        """Retain an encrypted archive for subsequent authenticated inspection; never trust its filename."""
        with self._operation():
            return self._store(content)

    def _workspace_files(self, temporary):
        """Prune managed archives/recoveries and the current staging directory before walking."""
        excluded = {self.managed, Path(temporary).resolve()}
        for directory, folders, files in os.walk(self.root, followlinks=False):
            parent = Path(directory)
            folders.sort()
            for name in folders[:]:
                child = parent / name
                if child in excluded:
                    folders.remove(name)
                elif child.is_symlink():
                    raise ValueError("Workspace contains a symlink; remove it before backup.")
            for name in sorted(files):
                yield parent / name

    def create(self, passphrase):
        """Capture databases and local files; exclude symlinks, transient SQLite journals and lock files."""
        with self.store.vault.lock, self._operation():
            salt = os.urandom(16)
            encryption = cipher(passphrase, salt)
            with TemporaryDirectory(prefix="sibyl-backup-") as temporary:
                root = self.root
                files = []
                total = 0
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    for source in self._workspace_files(temporary):
                        if source.is_symlink():
                            raise ValueError("Workspace contains a symlink; remove it before backup.")
                        if not source.is_file() or source.name.endswith(
                            ("-wal", "-shm", "-journal", ".lock")
                        ):
                            continue
                        name = source.relative_to(root).as_posix()
                        if not safe_name(name):
                            raise ValueError(
                                "Workspace contains a filename that cannot be archived portably."
                            )
                        if name == "backup-manifest.json":
                            raise ValueError("Workspace contains a reserved backup-manifest.json filename.")
                        if source.stat().st_size + total > MAX_RESTORED:
                            raise ValueError("Workspace exceeds the 512 MiB archive limit.")
                        if source.suffix in {".db", ".sqlite", ".sqlite3"}:
                            copy = Path(temporary) / uuid4().hex
                            with (
                                closing(
                                    sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
                                ) as src,
                                closing(sqlite3.connect(copy)) as dst,
                            ):
                                src.backup(dst)
                            data = copy.read_bytes()
                        else:
                            data = source.read_bytes()
                        total += len(data)
                        if total > MAX_RESTORED or len(files) >= 1000:
                            raise ValueError("Workspace exceeds the 512 MiB / 1,000-file archive limit.")
                        archive.writestr(name, data)
                        files.append(
                            {"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                        )
                    archive.writestr(
                        "backup-manifest.json",
                        json.dumps(
                            {
                                "format": 1,
                                "sibyl": __version__,
                                "created_at": datetime.now(UTC).isoformat(),
                                "files": files,
                            }
                        ),
                    )
                packed = buffer.getvalue()
                if len(packed) > MAX_ARCHIVE * 3 // 4 - 1024:
                    raise ValueError("Compressed workspace exceeds the encrypted archive size limit.")
                return self._store(MAGIC + salt + encryption.encrypt(packed))

    def _read(self, identifier, passphrase):
        content = self.path(identifier).read_bytes()
        if len(content) > MAX_ARCHIVE or not content.startswith(MAGIC):
            raise ValueError("Unsupported archive.")
        try:
            plain = cipher(passphrase, content[len(MAGIC) : len(MAGIC) + 16]).decrypt(
                content[len(MAGIC) + 16 :]
            )
        except InvalidToken:
            raise ValueError("Incorrect passphrase or damaged archive.") from None
        try:
            archive = zipfile.ZipFile(io.BytesIO(plain))
            infos = archive.infolist()
            names = [i.filename for i in infos]
            if (
                len(infos) > 1001
                or len(names) != len(set(names))
                or sum(i.file_size for i in infos if i.filename != "backup-manifest.json") > MAX_RESTORED
                or any(i.file_size > 512000 for i in infos if i.filename == "backup-manifest.json")
            ):
                raise ValueError("Archive limits exceeded.")
            for info in infos:
                if not safe_name(info.filename) or info.is_dir() or stat.S_ISLNK(info.external_attr >> 16):
                    raise ValueError("Unsafe archive path.")
            manifest = json.loads(archive.read("backup-manifest.json"))
            files = manifest["files"]
            try:
                archive_version = tuple(int(part) for part in manifest["sibyl"].split("."))
                current_version = tuple(int(part) for part in __version__.split("."))
                if len(archive_version) != 3 or archive_version > current_version:
                    raise ValueError()
            except (KeyError, TypeError, AttributeError, ValueError):
                raise ValueError(
                    "This archive has an invalid or newer Sibyl version. Use a compatible release."
                ) from None
            if (
                manifest.get("format") != 1
                or len(files) != len({f["path"] for f in files})
                or {f["path"] for f in files} != set(names) - {"backup-manifest.json"}
            ):
                raise ValueError("Invalid archive manifest.")
            if not {"sibyl.db", "vault.key"}.issubset({f["path"] for f in files}):
                raise ValueError("Archive lacks its workspace database or vault key.")
            for file in files:
                data = archive.read(file["path"])
                if len(data) != file["bytes"] or hashlib.sha256(data).hexdigest() != file["sha256"]:
                    raise ValueError("Archive integrity check failed.")
            return archive, manifest
        except (KeyError, TypeError, json.JSONDecodeError, zipfile.BadZipFile):
            raise ValueError("Invalid archive manifest or contents.") from None

    def inspect(self, identifier, passphrase):
        """Authenticate the archive and return counts/dates only, never decrypted bytes or credentials."""
        with self._operation():
            archive, manifest = self._read(identifier, passphrase)
            archive.close()
            return {
                "id": identifier,
                "sibyl": manifest["sibyl"],
                "created_at": manifest["created_at"],
                "files": len(manifest["files"]),
                "unpacked_bytes": sum(f["bytes"] for f in manifest["files"]),
                "includes_credentials": True,
                "restore_mode": "Separate workspace; automatic workers and exchange execution paused for review.",
            }

    def restore(self, identifier, passphrase):
        """Validate and restore into a new managed directory; never replace running data."""
        with self._operation():
            archive, manifest = self._read(identifier, passphrase)
            recovery = self.managed / "recovered"
            recovery.mkdir(exist_ok=True, mode=0o700)
            target = recovery / (self.root.name + "-restored-" + uuid4().hex[:10])
            target.mkdir(mode=0o700)
            try:
                for file in manifest["files"]:
                    path = target / file["path"]
                    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    path.write_bytes(archive.read(file["path"]))
                    path.chmod(0o600)
                    if path.suffix in {".db", ".sqlite", ".sqlite3"}:
                        with closing(sqlite3.connect(path)) as db:
                            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                                raise ValueError("Restored database failed validation.")
                from sibyl.storage import Store

                restored = Store(target)
                # Verify the copied vault can decrypt its own provider/account profiles.
                restored.model_profiles()
                from sibyl.operations.recovery import prepare_recovery

                prepare_recovery(restored, identifier)
                (target / ".gitignore").write_text("*\n")
                (target / ".gitignore").chmod(0o600)
            except Exception:
                shutil.rmtree(target)
                raise
            finally:
                archive.close()
            return {
                "data_dir": str(target),
                "created_at": manifest["created_at"],
                "recovery_required": True,
                "note": "Start Sibyl with --data-dir pointing to this directory. Automatic workers and exchange execution remain paused. Accounts start inactive. Review retained orders at their exchanges before completing recovery; a backup cannot undo a trade.",
            }

    def delete(self, identifier):
        """Delete one local encrypted archive; downloaded copies and restored workspaces are independent."""
        with self._operation():
            self.path(identifier).unlink()
