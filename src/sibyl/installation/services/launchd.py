"""macOS per-login LaunchAgent definitions and explicit launchctl lifecycle."""

import os
import plistlib
import re

from sibyl.installation.services.base import MARKER, UserService


class LaunchdService(UserService):
    name = "io.sibyl.dashboard"
    platform = "macos"

    def __init__(self, home, commands=None, uid=None):
        super().__init__(home, commands)
        self.uid = os.getuid() if uid is None else uid

    @property
    def target(self):
        return f"gui/{self.uid}/{self.name}"

    @property
    def definition(self):
        return self.home / "Library" / "LaunchAgents" / (self.name + ".plist")

    def render(self, config):
        value = {
            "Label": self.name,
            "ProgramArguments": config.arguments(),
            "WorkingDirectory": str(self.home),
            "RunAtLoad": True,
            "KeepAlive": {"SuccessfulExit": False},
            "ThrottleInterval": 30,
            "ExitTimeOut": 20,
            "Umask": 0o077,
        }
        return plistlib.dumps(value, fmt=plistlib.FMT_XML).replace(
            b"<plist", ("<!-- " + MARKER + " -->\n<plist").encode(), 1
        )

    def native_status(self):
        result = self.commands.run(["launchctl", "print", self.target], check=False)
        if result.returncode:
            absent = "Could not find service" in result.stderr
            return {
                "available": absent,
                "registered": False if absent else None,
                "state": "not_loaded" if absent else "unavailable",
            }

        def field(name):
            found = re.search(r"^\s*" + re.escape(name) + r" = ([^\n]*)$", result.stdout, re.MULTILINE)
            return found[1].strip().strip('"') if found else None

        state = field("state")
        state = (
            state
            if state
            in {"running", "not running", "waiting", "exited", "stopped", "spawn scheduled", "on-demand"}
            else "unknown"
        )
        pid = field("pid")
        code = field("last exit code")
        return {
            "available": True,
            "registered": True,
            "state": state,
            "pid": int(pid) if pid and pid.isdigit() and int(pid) > 0 else None,
            "last_exit_code": int(code) if code and re.fullmatch(r"-?\d+", code) else None,
            "native_owned": field("path") == str(self.definition),
        }

    def register(self):
        # Clear a previous persistent disable without bootstrapping or starting the job.
        self.commands.run(["launchctl", "enable", self.target])

    def start(self, status):
        if status.get("registered"):
            self.commands.run(["launchctl", "bootout", self.target], timeout=30)
        self.commands.run(["launchctl", "enable", self.target])
        self.commands.run(["launchctl", "bootstrap", f"gui/{self.uid}", str(self.definition)], timeout=30)

    def stop(self, status):
        # Persistent disable is needed: bootout alone would allow launch again at next login.
        self.commands.run(["launchctl", "disable", self.target])
        if status.get("registered"):
            self.commands.run(["launchctl", "bootout", self.target], timeout=30)

    def unregister(self, status):
        self.stop(status)
