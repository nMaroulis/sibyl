"""Shared, content-safe service definitions and bounded native command execution."""

import json
import subprocess
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from pathlib import Path

MARKER = "Sibyl managed user service v1"


def clean_path(value):
    """Store absolute paths only; reject characters with service-file/control semantics."""
    text = str(value)
    if any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise ValueError("Service paths must not contain control characters.")
    return str(Path(text).expanduser().absolute())


@dataclass(frozen=True)
class ServiceConfig:
    """Only nonsecret launch choices are serialized; shell environment values are never copied."""

    executable: str
    data_dir: str
    port: int = 8000
    env_file: str | None = None
    dashboard_dir: str | None = None

    def __post_init__(self):
        if type(self.port) is not int or not 1024 <= self.port <= 65535:
            raise ValueError("Choose a user-service port from 1,024 to 65,535.")
        for name in ("executable", "data_dir", "env_file", "dashboard_dir"):
            value = getattr(self, name)
            if value is None and name in {"env_file", "dashboard_dir"}:
                continue
            if not isinstance(value, str) or not value:
                raise ValueError("Service paths must be nonempty absolute strings.")
            if any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise ValueError("Service paths must not contain control characters.")
            if not Path(value).is_absolute():
                raise ValueError("Service paths must be absolute.")

    @property
    def log_file(self):
        return str(Path(self.data_dir) / "service-logs" / "sibyl.log")

    def arguments(self):
        """Use the installed interpreter/module with loopback binding and explicit environment-file semantics."""
        args = [
            self.executable,
            "-m",
            "sibyl",
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--data-dir",
            self.data_dir,
            "--log-file",
            self.log_file,
            "--no-access-log",
        ]
        args += ["--env-file", self.env_file] if self.env_file else ["--no-env-file"]
        if self.dashboard_dir:
            args += ["--dashboard-dir", self.dashboard_dir]
        return args

    def record(self):
        return asdict(self)


class NativeCommands:
    """Run argument arrays without a shell; never expose native stdout/stderr on failure."""

    def run(self, args, *, check=True, timeout=5):
        try:
            result = subprocess.run(
                args, shell=False, capture_output=True, text=True, errors="replace", timeout=timeout
            )
        except (OSError, subprocess.SubprocessError):
            raise ValueError(
                "The user-service manager is unavailable or timed out. Inspect service status before retrying."
            ) from None
        if len(result.stdout) > 262144 or len(result.stderr) > 262144:
            raise ValueError("The service manager returned an oversized response.")
        if check and result.returncode:
            raise ValueError(
                "The service manager did not confirm this action. Inspect status before retrying; no automatic retry was made."
            )
        return result


class UserService(ABC):
    """Native provider contract; implementations return allowlisted state, never native environment output."""

    name: str
    platform: str
    encoding = "utf-8"

    def __init__(self, home, commands=None):
        self.home = Path(home)
        self.commands = commands or NativeCommands()

    @property
    @abstractmethod
    def definition(self): ...

    @property
    def record_path(self):
        return self.definition.with_suffix(self.definition.suffix + ".json")

    @abstractmethod
    def render(self, config): ...

    @abstractmethod
    def native_status(self): ...

    def register(self):
        """Publish startup registration after files exist; never start a process here."""
        return None

    @abstractmethod
    def start(self, status): ...

    @abstractmethod
    def stop(self, status): ...

    @abstractmethod
    def unregister(self, status): ...

    def owned_file(self):
        return (
            self.definition.is_file()
            and not self.definition.is_symlink()
            and MARKER in self.definition.read_text(encoding=self.encoding)
        )

    def owned_record(self):
        path = self.record_path
        if not path.is_file() or path.is_symlink():
            return None
        try:
            value = json.loads(path.read_text())
            if not isinstance(value, dict) or value.get("managed_by") != MARKER or value.get("schema") != 1:
                return None
            ServiceConfig(**value["config"])
            return value
        except (ValueError, OSError, TypeError, KeyError):
            return None
