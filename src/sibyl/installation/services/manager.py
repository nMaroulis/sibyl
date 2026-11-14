"""Explicit install/control of one managed user service; application/API access is read-only."""

import hashlib
import json
import os
import shlex
import socket
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from sibyl.installation.services.base import MARKER, ServiceConfig
from sibyl.installation.services.launchd import LaunchdService
from sibyl.installation.services.systemd import SystemdService
from sibyl.installation.services.windows import WindowsService


def atomic_write(path, content):
    """Publish owner-readable definitions without following an existing terminal symlink."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(".sibyl-" + uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as stream:
            os.chmod(temporary, 0o600)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def port_available(port):
    """Refuse to compete with a manual server; the OS still arbitrates races after this check."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            if os.name != "nt":
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", port))
    except OSError:
        raise ValueError(
            f"Port {port} is already occupied. Stop the manual server or install the service on another port."
        ) from None


class ServiceManager:
    """Own definitions/launch receipts, never exchange state, API credentials or domain workers."""

    def __init__(self, provider, *, check_port=None):
        self.provider = provider
        self.check_port = check_port or port_available

    def status(self):
        provider = self.provider
        try:
            record = provider.owned_record()
            file_owned = provider.owned_file()
            native = provider.native_status()
            valid = bool(
                record
                and file_owned
                and hashlib.sha256(provider.definition.read_bytes()).hexdigest()
                == record.get("definition_sha256")
            )
            owned = bool(file_owned and (not native.get("registered") or native.get("native_owned")))
            config = record.get("config") if valid else None
            if config:
                ServiceConfig(**config)
            return {
                "supported": True,
                "platform": provider.platform,
                "manager": type(provider).__name__,
                "name": provider.name,
                "definition": str(provider.definition),
                "installed": bool(provider.definition.exists() or native.get("registered")),
                "owned": owned,
                "configuration_valid": valid,
                "state": native["state"],
                "available": native["available"],
                "registered": native.get("registered"),
                "enabled": native.get("enabled"),
                "running": native["state"] in {"running", "active"},
                "pid": native.get("pid"),
                "last_exit_code": native.get("last_exit_code"),
                "last_task_result": native.get("last_task_result"),
                "this_process": native["pid"] == os.getpid() if native.get("pid") else None,
                "config": config,
                "log_file": ServiceConfig(**config).log_file if config else None,
                "note": "User-login service state from the OS; it does not establish API readiness, worker health or venue uptime. Stop disables future login starts; start enables them again. Shell-only environment values are not copied. Windows task termination may be abrupt.",
            }
        except (OSError, ValueError, TypeError, KeyError):
            return {
                "supported": True,
                "platform": provider.platform,
                "name": type(provider).__name__,
                "available": False,
                "installed": None,
                "owned": False,
                "configuration_valid": False,
                "state": "unavailable",
                "running": False,
                "note": "The user-service state could not be verified. No changes were performed.",
            }

    def _control_state(self, *, require_config=True):
        state = self.status()
        if not state.get("available"):
            raise ValueError(
                "The user-service manager cannot be reached. Check your login session and native service manager."
            )
        if not state.get("owned"):
            raise ValueError(
                "No verified Sibyl-managed definition is installed. Unmanaged services are never changed."
            )
        if require_config and not state.get("configuration_valid"):
            raise ValueError(
                "The service definition or launch receipt changed. Stop it and explicitly reinstall with --replace."
            )
        return state

    def preview(self, config):
        return {
            "definition": str(self.provider.definition),
            "content": self.provider.render(config).decode(self.provider.encoding),
            "config": config.record(),
            "arguments": config.arguments(),
            "log_file": config.log_file,
            "note": "Preview only. No files, startup registration or processes were changed.",
        }

    def install(self, config, *, replace=False):
        """Stage exact launch choices and register next-login startup, without starting the app now."""
        p = self.provider
        state = self.status()
        if not state.get("available"):
            raise ValueError("The user-service manager cannot be reached. No installation was attempted.")
        if state.get("registered") and not state.get("owned"):
            raise ValueError(
                "A service with this name is not verified as Sibyl-managed. No service was replaced."
            )
        if (
            p.definition.exists()
            and not p.owned_file()
            or p.definition.is_symlink()
            or p.record_path.is_symlink()
        ):
            raise ValueError(
                "An unmanaged or symbolic-link service file already exists. No file was replaced."
            )
        if p.record_path.exists() and not p.owned_record():
            raise ValueError("An unmanaged launch receipt already exists. No file was replaced.")
        if state.get("running") or state.get("state") in {"activating", "deactivating", "queued"}:
            raise ValueError("Stop the managed service before installing or replacing its definition.")
        content = p.render(config)
        if p.definition.exists():
            record = p.owned_record()
            if p.definition.read_bytes() == content and record and record.get("config") == config.record():
                return {
                    **state,
                    "action": "already_installed",
                    "note": "Identical definition retained. No process was started.",
                }
            if not replace:
                raise ValueError(
                    "A managed definition already exists. Use install --replace explicitly after stopping it."
                )
        if not Path(config.executable).is_file():
            raise ValueError("The recorded Python interpreter does not exist.")
        for name in ("env_file", "dashboard_dir"):
            value = getattr(config, name)
            if value and not (
                Path(value).is_file() if name == "env_file" else (Path(value) / "index.html").is_file()
            ):
                raise ValueError(f"The selected {name.replace('_', ' ')} is unavailable.")
        Path(config.data_dir).mkdir(parents=True, exist_ok=True, mode=0o700)
        logs = Path(config.log_file).parent
        logs.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_write(p.definition, content)
        atomic_write(
            p.record_path,
            json.dumps(
                {
                    "schema": 1,
                    "managed_by": MARKER,
                    "config": config.record(),
                    "definition_sha256": hashlib.sha256(content).hexdigest(),
                },
                indent=2,
            ).encode(),
        )
        p.register()
        return {
            **self.status(),
            "action": "installed",
            "note": "Registered for future logins. The app was not started; run sibyl service start deliberately. Keep this Python environment installed, and retain your workspace/vault together.",
        }

    def start(self):
        state = self._control_state()
        if state["running"] or state["state"] in {"activating", "queued"}:
            return {**state, "action": "already_running"}
        if state["state"] == "deactivating":
            raise ValueError("The old service is still stopping. Wait for shutdown before starting it.")
        config = ServiceConfig(**state["config"])
        if not Path(config.executable).is_file():
            raise ValueError(
                "The service interpreter was moved or removed. Reinstall with the current environment."
            )
        self.check_port(config.port)
        self.provider.start(state)
        return {
            **self.status(),
            "action": "start_requested",
            "note": "The OS accepted a start request. Inspect status/logs; this does not confirm HTTP readiness.",
        }

    def stop(self):
        state = self._control_state(require_config=False)
        self.provider.stop(state)
        return {
            **self.status(),
            "action": "stop_requested",
            "note": "Stop requested and future login starts disabled. Inspect status; Windows may terminate the task abruptly. Venue orders and already sent messages are not undone.",
        }

    def restart(self):
        self.stop()
        state = self.status()
        if state.get("running") or state.get("state") in {"activating", "deactivating", "queued"}:
            raise ValueError(
                "The old service is still stopping. Inspect status and start it after shutdown completes."
            )
        return self.start()

    def uninstall(self):
        state = self._control_state(require_config=False)
        self.provider.unregister(state)
        self.provider.definition.unlink(missing_ok=True)
        self.provider.record_path.unlink(missing_ok=True)
        if hasattr(self.provider, "removed"):
            self.provider.removed()
        return {
            "action": "uninstalled",
            "platform": self.provider.platform,
            "note": "Managed startup definition removed. Workspace databases, credentials, backups and logs were retained.",
        }


def service_manager(*, platform=None, home=None, commands=None):
    platform = platform or sys.platform
    home = Path(home) if home else Path.home()
    cls = (
        LaunchdService
        if platform == "darwin"
        else SystemdService
        if platform.startswith("linux")
        else WindowsService
        if platform == "win32"
        else None
    )
    if cls is None:
        raise ValueError(
            "Managed user services currently support macOS, Linux systemd and Windows Task Scheduler."
        )
    return ServiceManager(cls(home, commands))


def service_status(data_dir=None, port=8000):
    """Read safe OS facts for the UI/native Technician; never install/start/stop from an agent or route."""
    try:
        result = service_manager().status()
        workspace = str(Path(data_dir).resolve()) if data_dir else "<workspace>"
        args = [
            sys.executable,
            "-m",
            "sibyl",
            "service",
            "install",
            "--data-dir",
            workspace,
            "--port",
            str(port),
        ]
        quoted = subprocess.list2cmdline if sys.platform == "win32" else shlex.join
        result["commands"] = {
            "preview": quoted([*args[:4], "preview", *args[5:]]),
            "install": quoted(args),
            **{
                action: quoted([*args[:4], action])
                for action in ("status", "start", "stop", "restart", "uninstall")
            },
        }
        config = result.get("config")
        result["workspace_matches"] = (
            str(Path(config["data_dir"]).resolve()) == str(Path(data_dir).resolve())
            if config and data_dir
            else None
        )
        return result
    except ValueError:
        return {
            "supported": False,
            "available": False,
            "state": "unsupported",
            "running": False,
            "note": "Use the foreground launcher or Docker on this platform.",
        }
