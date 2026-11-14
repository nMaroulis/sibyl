"""Linux systemd user units; never install a system/root service or enable lingering."""

import os
from pathlib import Path

from sibyl.installation.services.base import MARKER, UserService


def quoted(value, *, command=False):
    """Escape systemd C-string/specifier syntax and command environment expansion without a shell."""
    text = str(value).replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    if command:
        text = text.replace("$", "$$")
    return '"' + text + '"'


class SystemdService(UserService):
    name = "sibyl.service"
    platform = "linux"

    def __init__(self, home, commands=None, config_home=None):
        super().__init__(home, commands)
        configured = config_home or os.environ.get("XDG_CONFIG_HOME", "")
        self.config_home = (
            Path(configured) if configured and Path(configured).is_absolute() else self.home / ".config"
        )

    @property
    def definition(self):
        return self.config_home / "systemd" / "user" / self.name

    def render(self, config):
        args = " ".join(quoted(value, command=True) for value in config.arguments())
        return (
            f"# {MARKER}\n[Unit]\nDescription=Sibyl local dashboard\nStartLimitIntervalSec=300\nStartLimitBurst=3\n\n"
            f"[Service]\nType=exec\nExecStart={args}\nWorkingDirectory={quoted(self.home)}\n"
            "Restart=on-failure\nRestartSec=15\nTimeoutStopSec=20\nKillSignal=SIGTERM\nUMask=0077\n\n"
            "[Install]\nWantedBy=default.target\n"
        ).encode()

    def native_status(self):
        result = self.commands.run(
            [
                "systemctl",
                "--user",
                "show",
                self.name,
                "--property=LoadState,ActiveState,SubState,MainPID,ExecMainStatus,FragmentPath,UnitFileState",
            ],
            check=False,
        )
        fields = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        if fields.get("LoadState") == "not-found":
            return {"available": True, "registered": False, "state": "not_loaded"}
        if result.returncode or not fields.get("LoadState"):
            return {"available": False, "registered": None, "state": "unavailable"}
        pid, code = fields.get("MainPID", ""), fields.get("ExecMainStatus", "")
        state = fields.get("ActiveState", "unknown")
        state = (
            state
            if state
            in {"active", "inactive", "failed", "activating", "deactivating", "reloading", "maintenance"}
            else "unknown"
        )
        return {
            "available": True,
            "registered": True,
            "state": state,
            "pid": int(pid) if pid.isdigit() and int(pid) > 0 else None,
            "last_exit_code": int(code) if code.isdigit() else None,
            "enabled": fields.get("UnitFileState") in {"enabled", "enabled-runtime"},
            "native_owned": fields.get("FragmentPath") == str(self.definition),
        }

    def register(self):
        self.commands.run(["systemctl", "--user", "daemon-reload"])
        self.commands.run(["systemctl", "--user", "enable", self.name])

    def start(self, status):
        self.commands.run(["systemctl", "--user", "daemon-reload"])
        self.commands.run(["systemctl", "--user", "enable", self.name])
        self.commands.run(["systemctl", "--user", "start", self.name], timeout=30)

    def stop(self, status):
        self.commands.run(["systemctl", "--user", "disable", "--now", self.name], timeout=30)

    def unregister(self, status):
        self.stop(status)

    def removed(self):
        self.commands.run(["systemctl", "--user", "daemon-reload"])
