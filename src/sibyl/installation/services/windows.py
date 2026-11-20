"""Windows per-user interactive Task Scheduler jobs; no account password or elevated service."""

import json
import os
import re
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

from sibyl.installation.services.base import MARKER, UserService

NS = "http://schemas.microsoft.com/windows/2004/02/mit/task"
STATUS = r"""$ErrorActionPreference='Stop'; try { $t=Get-ScheduledTask -TaskName 'SibylLocalDashboard' -TaskPath '\' -ErrorAction Stop; $i=$t|Get-ScheduledTaskInfo; @{exists=$true;owned=($t.Source -eq 'Sibyl managed user service v1');state=[int]$t.State;enabled=[bool]$t.Settings.Enabled;last_result=[long]$i.LastTaskResult}|ConvertTo-Json -Compress } catch { if ($_.CategoryInfo.Category -eq 'ObjectNotFound' -or $_.FullyQualifiedErrorId -like '*CmdletizationQuery_NotFound*') { '{"exists":false}' } else { exit 3 } }"""


class WindowsService(UserService):
    _task_name = None
    _sid = None
    platform = "windows"
    encoding = "utf-16"

    def __init__(self, home, commands=None, appdata=None):
        super().__init__(home, commands)
        self.appdata = Path(appdata or os.environ.get("LOCALAPPDATA") or self.home / "AppData" / "Local")

    @property
    def definition(self):
        return self.appdata / "Sibyl" / "service" / "dashboard.xml"

    @property
    def name(self):
        if self._task_name is None:
            self._task_name = "SibylLocalDashboard-" + self.sid()
        return self._task_name

    def sid(self):
        if self._sid is not None:
            return self._sid
        value = self.commands.run(["whoami", "/user", "/fo", "csv", "/nh"]).stdout
        found = re.search(r"S-1-(?:\d+-)*\d+", value)
        if not found:
            raise ValueError("The current Windows user SID could not be read.")
        self._sid = found[0]
        return self._sid

    def render(self, config):
        ET.register_namespace("", NS)
        root = ET.Element("{" + NS + "}Task", version="1.3")

        def element(parent, name, text=None, **attrs):
            child = ET.SubElement(parent, "{" + NS + "}" + name, attrs)
            child.text = text
            return child

        info = element(root, "RegistrationInfo")
        element(info, "Description", "Sibyl local dashboard for this signed-in user")
        element(info, "Source", MARKER)
        trigger = element(element(root, "Triggers"), "LogonTrigger")
        sid = self.sid()
        element(trigger, "Enabled", "true")
        element(trigger, "UserId", sid)
        principal = element(element(root, "Principals"), "Principal", id="Owner")
        element(principal, "UserId", sid)
        element(principal, "LogonType", "InteractiveToken")
        element(principal, "RunLevel", "LeastPrivilege")
        settings = element(root, "Settings")
        for name, value in (
            ("MultipleInstancesPolicy", "IgnoreNew"),
            ("DisallowStartIfOnBatteries", "false"),
            ("StopIfGoingOnBatteries", "false"),
            ("AllowHardTerminate", "true"),
            ("StartWhenAvailable", "true"),
            ("AllowStartOnDemand", "true"),
            ("Enabled", "true"),
            ("Hidden", "false"),
            ("ExecutionTimeLimit", "PT0S"),
        ):
            element(settings, name, value)
        restart = element(settings, "RestartOnFailure")
        element(restart, "Interval", "PT1M")
        element(restart, "Count", "3")
        action = element(element(root, "Actions", Context="Owner"), "Exec")
        # pythonw uses the same environment without opening a terminal; file logging is explicit.
        executable = Path(config.executable)
        windowless = executable.with_name("pythonw.exe")
        element(action, "Command", str(windowless if windowless.is_file() else executable))
        element(action, "Arguments", subprocess.list2cmdline(config.arguments()[1:]))
        element(action, "WorkingDirectory", str(self.home))
        root.insert(0, ET.Comment(MARKER))
        return ET.tostring(root, encoding="utf-16", xml_declaration=True)

    def native_status(self):
        result = self.commands.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                STATUS.replace("SibylLocalDashboard", self.name),
            ],
            check=False,
        )
        if result.returncode:
            return {"available": False, "registered": None, "state": "unavailable"}
        try:
            value = json.loads(result.stdout.lstrip("\ufeff"))
            if value.get("exists") is False:
                return {"available": True, "registered": False, "state": "not_loaded"}
            if value.get("exists") is not True or type(value.get("state")) is not int:
                raise ValueError
            return {
                "available": True,
                "registered": True,
                "state": {0: "unknown", 1: "disabled", 2: "queued", 3: "ready", 4: "running"}.get(
                    value["state"], "unknown"
                ),
                "native_owned": value.get("owned") is True,
                "enabled": value.get("enabled") is True,
                "last_task_result": value["last_result"] if type(value.get("last_result")) is int else None,
                "pid": None,
            }
        except (ValueError, TypeError, AttributeError):
            return {"available": False, "registered": None, "state": "unavailable"}

    def register(self):
        self.commands.run(
            ["schtasks.exe", "/Create", "/TN", self.name, "/XML", str(self.definition), "/F"], timeout=30
        )

    def start(self, status):
        if not status.get("registered"):
            self.register()
        self.commands.run(["schtasks.exe", "/Change", "/TN", self.name, "/ENABLE"])
        self.commands.run(["schtasks.exe", "/Run", "/TN", self.name])

    def stop(self, status):
        if not status.get("registered"):
            return
        self.commands.run(["schtasks.exe", "/Change", "/TN", self.name, "/DISABLE"])
        if status.get("state") in {"running", "queued"}:
            self.commands.run(["schtasks.exe", "/End", "/TN", self.name], timeout=30)

    def unregister(self, status):
        if not status.get("registered"):
            return
        self.stop(status)
        self.commands.run(["schtasks.exe", "/Delete", "/TN", self.name, "/F"])
