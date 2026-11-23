"""Native user-service contracts using temporary files and fake OS managers; no host service is installed."""

import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pytest

from sibyl import cli
from sibyl.installation.services.base import MARKER, NativeCommands, ServiceConfig
from sibyl.installation.services.launchd import LaunchdService
from sibyl.installation.services.manager import ServiceManager
from sibyl.installation.services.systemd import SystemdService, quoted
from sibyl.installation.services.windows import NS, WindowsService

SID = "S-1-5-21-123-456-789-1001"


class Native:
    """Model native state/commands only; no subprocess or user-directory writes occur."""

    def __init__(self):
        self.calls = []
        self.registered = False
        self.running = False
        self.enabled = False
        self.foreign = False
        self.unavailable = False
        self.fail = None
        self.provider = None

    def run(self, args, *, check=True, timeout=5):
        self.calls.append(list(args))
        if self.fail and self.fail(args):
            raise ValueError(
                "The service manager did not confirm this action. Inspect status before retrying."
            )
        if args[0] == "whoami":
            return SimpleNamespace(returncode=0, stdout=f'"DOMAIN\\owner","{SID}"', stderr="")
        if args[0] == "launchctl" and args[1] == "print":
            if self.unavailable:
                return SimpleNamespace(returncode=113, stdout="", stderr="Could not find domain")
            if not self.registered:
                return SimpleNamespace(returncode=113, stdout="", stderr="Could not find service")
            path = "/other/service.plist" if self.foreign else str(self.provider.definition)
            content = f"path = {path}\nstate = {'running' if self.running else 'waiting'}\npid = {8765 if self.running else 0}\nlast exit code = 0\nenvironment = PRIVATE-ENV-SECRET\n"
            return SimpleNamespace(returncode=0, stdout=content, stderr="")
        if args[0] == "systemctl" and "show" in args:
            if self.unavailable:
                return SimpleNamespace(returncode=1, stdout="", stderr="PRIVATE-BUS-DIAGNOSTIC")
            if not self.registered:
                return SimpleNamespace(returncode=4, stdout="LoadState=not-found\n", stderr="")
            path = "/other/service.unit" if self.foreign else str(self.provider.definition)
            content = f"LoadState=loaded\nActiveState={'active' if self.running else 'inactive'}\nSubState=dead\nMainPID={8765 if self.running else 0}\nExecMainStatus=0\nFragmentPath={path}\nUnitFileState={'enabled' if self.enabled else 'disabled'}\nPRIVATE=PRIVATE-ENV-SECRET\n"
            return SimpleNamespace(returncode=0, stdout=content, stderr="")
        if args[0] == "powershell.exe":
            if self.unavailable:
                return SimpleNamespace(returncode=3, stdout="", stderr="PRIVATE-NATIVE-SECRET")
            content = {
                "exists": self.registered,
                "owned": not self.foreign,
                "state": 4 if self.running else 3,
                "enabled": self.enabled,
                "last_result": 267009 if self.running else 0,
                "private": "PRIVATE-ENV-SECRET",
            }
            return SimpleNamespace(returncode=0, stdout=json.dumps(content), stderr="")
        if args[0] == "launchctl":
            if args[1] == "bootstrap":
                self.registered = True
                self.running = True
            if args[1] == "bootout":
                self.registered = False
                self.running = False
            if args[1] == "enable":
                self.enabled = True
            if args[1] == "disable":
                self.enabled = False
        if args[0] == "systemctl":
            if "daemon-reload" in args:
                self.registered = self.provider.definition.exists()
            if "enable" in args:
                self.enabled = True
            if "start" in args:
                self.running = True
            if "disable" in args:
                self.enabled = False
                self.running = False
        if args[0] == "schtasks.exe":
            if "/Create" in args:
                self.registered = True
                self.enabled = True
            if "/Run" in args:
                self.running = True
            if "/End" in args:
                self.running = False
            if "/DISABLE" in args:
                self.enabled = False
            if "/ENABLE" in args:
                self.enabled = True
            if "/Delete" in args:
                self.registered = False
        return SimpleNamespace(returncode=0, stdout="", stderr="")


@pytest.fixture(params=["macos", "linux", "windows"])
def manager(tmp_path, request):
    native = Native()
    home = tmp_path / "home with spaces"
    home.mkdir()
    provider = (
        LaunchdService(home, native, uid=501)
        if request.param == "macos"
        else SystemdService(home, native, config_home=home / "cfg")
        if request.param == "linux"
        else WindowsService(home, native, appdata=home / "appdata")
    )
    native.provider = provider
    config = ServiceConfig(
        str(Path(sys.executable).absolute()), str(tmp_path / "workspace with spaces"), 8766
    )
    ports = []
    owner = ServiceManager(provider, check_port=ports.append)
    return owner, native, config, ports


def test_preview_and_status_do_not_write_register_or_launch(manager):
    owner, native, config, _ = manager
    preview = owner.preview(config)
    assert not Path(config.data_dir).exists() and not owner.provider.definition.exists()
    assert MARKER in preview["content"] and "--no-env-file" in preview["arguments"]
    state = owner.status()
    assert not state["installed"] and not state["running"]
    assert all(a[0] in {"whoami", "powershell.exe"} or "print" in a or "show" in a for a in native.calls)


def test_install_registers_login_only_start_stop_and_uninstall_preserve_workspace(manager):
    owner, native, config, ports = manager
    installed = owner.install(config)
    assert installed["action"] == "installed" and not native.running
    assert owner.provider.definition.is_file() and owner.provider.record_path.is_file()
    if os.name != "nt":
        assert owner.provider.definition.stat().st_mode & 0o777 == 0o600
    source = Path(config.data_dir) / "vault.key"
    source.write_text("EXISTING-PRIVATE-KEY")
    before = len(native.calls)
    assert owner.install(config)["action"] == "already_installed"
    assert all(
        a[0] in {"powershell.exe", "whoami"} or "print" in a or "show" in a for a in native.calls[before:]
    )
    started = owner.start()
    assert started["action"] == "start_requested" and native.running and ports == [8766]
    count = len(native.calls)
    assert owner.start()["action"] == "already_running"
    assert all(
        a[0] in {"powershell.exe", "whoami"} or "print" in a or "show" in a for a in native.calls[count:]
    )
    assert "PRIVATE-ENV-SECRET" not in json.dumps(started)
    owner.stop()
    assert not native.running and not native.enabled
    owner.start()
    assert native.running and native.enabled
    owner.uninstall()
    assert not owner.provider.definition.exists() and not owner.provider.record_path.exists()
    assert source.read_text() == "EXISTING-PRIVATE-KEY" and Path(config.log_file).parent.exists()


def test_definition_is_real_platform_contract_without_shell_or_environment_capture(
    manager, tmp_path, monkeypatch
):
    owner, native, config, _ = manager
    env = tmp_path / "private env file.env"
    env.write_text("SIBYL_API_TOKEN=PRIVATE-CONFIG-SECRET")
    monkeypatch.setenv("OPENAI_API_KEY", "PRIVATE-SHELL-SECRET")
    config = ServiceConfig(config.executable, config.data_dir, 8766, str(env))
    content = owner.preview(config)["content"]
    assert "PRIVATE-CONFIG-SECRET" not in content and "PRIVATE-SHELL-SECRET" not in content
    args = config.arguments()
    assert args[-2:] == ["--env-file", str(env)]
    assert args[args.index("--host") + 1] == "127.0.0.1" and "--open-browser" not in args
    if isinstance(owner.provider, LaunchdService):
        definition = plistlib.loads(content.encode())
        assert definition["ProgramArguments"] == args and definition["RunAtLoad"] is True
        assert definition["KeepAlive"] == {"SuccessfulExit": False} and definition["Umask"] == 0o077
        assert "EnvironmentVariables" not in definition
    elif isinstance(owner.provider, SystemdService):
        assert "Type=exec" in content and "WantedBy=default.target" in content
        assert "Restart=on-failure" in content and "TimeoutStopSec=20" in content
        assert "User=root" not in content and "Environment=" not in content
    else:
        definition = ET.fromstring(content)

        def path(name):
            return definition.find(".//{" + NS + "}" + name)

        assert path("UserId").text == SID and path("LogonType").text == "InteractiveToken"
        assert path("RunLevel").text == "LeastPrivilege" and path("ExecutionTimeLimit").text == "PT0S"
        assert path("MultipleInstancesPolicy").text == "IgnoreNew" and path("Source").text == MARKER
        assert path("Arguments").text == subprocess.list2cmdline(args[1:])
        assert SID in owner.provider.name


def test_foreign_native_service_and_unmanaged_files_are_never_overwritten(manager):
    owner, native, config, _ = manager
    native.registered = True
    native.foreign = True
    with pytest.raises(ValueError, match="not verified"):
        owner.install(config)
    assert not owner.provider.definition.exists()
    native.registered = False
    native.foreign = False
    owner.provider.definition.parent.mkdir(parents=True, exist_ok=True)
    owner.provider.definition.write_text("DO NOT REPLACE", encoding=owner.provider.encoding)
    with pytest.raises(ValueError, match="unmanaged"):
        owner.install(config, replace=True)
    assert owner.provider.definition.read_text(encoding=owner.provider.encoding) == "DO NOT REPLACE"


def test_port_conflict_blocks_native_start_without_killing_anything(manager):
    owner, native, config, _ = manager
    owner.install(config)
    count = len(native.calls)

    def busy(port):
        raise ValueError("occupied port")

    owner.check_port = busy
    with pytest.raises(ValueError, match="occupied"):
        owner.start()
    assert not native.running
    assert all(
        a[0] in {"powershell.exe", "whoami"} or "print" in a or "show" in a for a in native.calls[count:]
    )


def test_replacement_is_deliberate_stopped_only_and_tampering_blocks_start(manager):
    owner, native, config, _ = manager
    owner.install(config)
    changed = ServiceConfig(config.executable, config.data_dir, 9001)
    with pytest.raises(ValueError, match="replace"):
        owner.install(changed)
    owner.start()
    with pytest.raises(ValueError, match="Stop"):
        owner.install(changed, replace=True)
    owner.stop()
    owner.install(changed, replace=True)
    assert owner.status()["config"]["port"] == 9001
    with owner.provider.definition.open("a", encoding=owner.provider.encoding) as file:
        file.write("\n<!-- changed -->")
    assert not owner.status()["configuration_valid"]
    with pytest.raises(ValueError, match="changed"):
        owner.start()
    owner.install(changed, replace=True)
    assert owner.status()["configuration_valid"]


def test_unavailable_manager_does_not_claim_absence_or_modify_files(manager):
    owner, native, config, _ = manager
    native.unavailable = True
    state = owner.status()
    assert not state["available"] and state["registered"] is None
    with pytest.raises(ValueError, match="cannot be reached"):
        owner.install(config)
    assert not owner.provider.definition.exists() and not Path(config.data_dir).exists()


def test_single_attempt_failure_leaves_explicit_receipts_for_inspection(manager):
    owner, native, config, _ = manager

    def fail(args):
        return args[0] == "schtasks.exe" or "bootstrap" in args or "enable" in args

    native.fail = fail
    with pytest.raises(ValueError, match="did not confirm"):
        owner.install(config) if not isinstance(owner.provider, LaunchdService) else (
            owner.install(config),
            owner.start(),
        )
    assert owner.provider.definition.exists() and owner.provider.record_path.exists()
    writes = [args for args in native.calls if fail(args)]
    assert len(writes) == 1


def test_systemd_escapes_arguments_and_specifiers_without_a_shell(tmp_path):
    owner = SystemdService(tmp_path, Native(), config_home=tmp_path)
    value = str(tmp_path / 'A space %n $HOME "quoted" \\path')
    content = owner.render(ServiceConfig(value, str(tmp_path / "100% $NAME"))).decode()
    assert quoted(value, command=True) in content
    assert "%%n" in content and "$$HOME" in content and '\\"quoted\\"' in content
    assert 'WorkingDirectory="' in content and "bash" not in content


def test_windows_task_name_is_user_specific_and_status_never_returns_scheduler_payload(tmp_path):
    a = Native()
    p = WindowsService(tmp_path, a, appdata=tmp_path)
    a.provider = p
    assert p.name.endswith(SID)
    a.registered = True
    a.running = True
    result = p.native_status()
    assert result["state"] == "running" and result["last_task_result"] == 267009
    assert "PRIVATE-ENV-SECRET" not in json.dumps(result)
    assert a.calls[0] == ["whoami", "/user", "/fo", "csv", "/nh"]
    command = next(row[-1] for row in a.calls if row[0] == "powershell.exe")
    assert p.name in command and "-TaskPath" in command


def test_native_runner_uses_no_shell_safe_failures_and_timeout(monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=3, stdout="PRIVATE-OUTPUT", stderr="PRIVATE-ERROR")

    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(ValueError) as error:
        NativeCommands().run(["service-manager", "stop"])
    assert "PRIVATE" not in str(error.value) and len(calls) == 1
    assert calls[0][1]["shell"] is False and calls[0][1]["timeout"] == 5
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(subprocess.TimeoutExpired("PRIVATE", 5))
    )
    with pytest.raises(ValueError, match="timed out"):
        NativeCommands().run(["safe"])


@pytest.mark.parametrize("port", [True, False, 0, 80, 65536])
def test_service_config_rejects_privileged_or_invalid_ports(port):
    with pytest.raises(ValueError):
        ServiceConfig("/python", "/data", port)


def test_service_config_rejects_control_characters(tmp_path):
    with pytest.raises(ValueError, match="control"):
        ServiceConfig(sys.executable, str(tmp_path) + "\nExecStart=evil")


def test_file_logging_rotates_privately_and_does_not_enable_http_query_logging(tmp_path):
    old = os.umask(0o077)
    try:
        path = tmp_path / "private" / "sibyl.log"
        config = cli.file_logging(path)
        assert config["handlers"]["default"]["class"] == "logging.handlers.RotatingFileHandler"
        assert config["handlers"]["default"]["backupCount"] == 3
        assert config["formatters"]["default"]["use_colors"] is False
        assert config["loggers"]["uvicorn.access"]["handlers"] == []
        assert config["root"]["level"] == "WARNING"
        if os.name != "nt":
            assert path.stat().st_mode & 0o777 == 0o600
    finally:
        os.umask(old)


def test_cli_help_preview_do_not_import_or_start_application(tmp_path):
    code = """import sys; from sibyl.cli import main
try: main(['service','--help'])
except SystemExit as e: assert e.code==0
assert 'sibyl.api.app' not in sys.modules
"""
    result = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "preview" in result.stdout and list(tmp_path.iterdir()) == []


def test_cli_dispatches_only_explicit_action_and_safe_defaults(tmp_path, monkeypatch, capsys):
    from sibyl.installation.services import cli as service_cli

    captured = []
    owner = SimpleNamespace(preview=lambda value: captured.append(value) or {"action": "preview"})
    monkeypatch.setattr(service_cli, "service_manager", lambda: owner)
    cli.main(["service", "preview", "--data-dir", str(tmp_path), "--port", "9123"])
    assert captured[0].data_dir == str(tmp_path) and captured[0].port == 9123
    assert captured[0].env_file is None and "--no-env-file" in captured[0].arguments()
    assert json.loads(capsys.readouterr().out)["action"] == "preview"


def test_http_status_is_read_only_private_and_reports_workspace_match(client, monkeypatch):
    observed = []

    def status(directory, port):
        observed.append((directory, port))
        return {
            "supported": True,
            "available": True,
            "state": "running",
            "running": True,
            "workspace_matches": False,
        }

    monkeypatch.setattr("sibyl.installation.services.manager.service_status", status)
    result = client.get("/api/v1/workspace/service")
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    assert result.json()["workspace_matches"] is False and observed
    assert client.post("/api/v1/workspace/service/start").status_code in {404, 405}


def test_native_technician_reads_service_state_without_control(client, monkeypatch):
    from protolink import create_llm

    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    monkeypatch.setattr(
        "sibyl.installation.services.manager.service_status",
        lambda *a, **kw: {"supported": True, "state": "not_loaded", "installed": False, "running": False},
    )
    monkeypatch.setattr(
        "sibyl.agents.utils.registry.create_llm",
        lambda *a, **kw: create_llm(
            "mock",
            sequential_responses=[
                {"type": "tool_call", "tool": "background_service_status", "args": {}},
                "No background service is currently loaded. Preview and install it deliberately from your terminal.",
            ],
        ),
    )
    response = client.post(
        "/api/v1/agents/ask", json={"module": "technician", "message": "Does Sibyl start at login?"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["evidence"]["state"] == "not_loaded"


def test_restart_never_claims_success_while_old_process_still_runs(manager, monkeypatch):
    owner, native, config, _ = manager
    owner.install(config)
    owner.start()
    monkeypatch.setattr(owner.provider, "stop", lambda state: None)
    before = len(native.calls)
    with pytest.raises(ValueError, match="still stopping"):
        owner.restart()
    assert all(
        a[0] in {"whoami", "powershell.exe"} or "show" in a or "print" in a for a in native.calls[before:]
    )


def test_occupied_port_preflight_uses_only_its_own_socket():
    import socket

    from sibyl.installation.services.manager import port_available

    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        held.listen()
        with pytest.raises(ValueError, match="occupied"):
            port_available(held.getsockname()[1])


def test_windowless_process_starts_with_private_rotating_log(tmp_path):
    import socket
    import time
    from urllib.error import URLError
    from urllib.request import urlopen

    from sibyl.storage import Store

    workspace = tmp_path / "workspace"
    store = Store(workspace)
    store.save_data_profile("market", {"source": "demo", "profiles": {}})
    store.save_data_profile("news", {"mode": "demo", "profiles": {}})
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    logfile = tmp_path / "logs" / "backend.log"
    code = "import sys;sys.stdout=None;sys.stderr=None;from sibyl.cli import main;main(sys.argv[1:])"
    command = [
        sys.executable,
        "-I",
        "-c",
        code,
        "--no-env-file",
        "--port",
        str(port),
        "--data-dir",
        str(workspace),
        "--log-file",
        str(logfile),
        "--no-access-log",
    ]
    env = {key: value for key, value in os.environ.items() if not key.startswith("SIBYL_")}
    process = subprocess.Popen(
        command, cwd=tmp_path, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        deadline = time.monotonic() + 20
        while True:
            if process.poll() is not None:
                pytest.fail("Windowless app exited before health readiness")
            try:
                with urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
                    assert json.load(response)["status"] == "ok"
                break
            except (URLError, TimeoutError):
                if time.monotonic() > deadline:
                    pytest.fail("Windowless app did not become ready")
                time.sleep(0.1)
        content = logfile.read_text()
        assert "Application startup complete" in content
        assert "GET /health" not in content
        if os.name != "nt":
            assert logfile.stat().st_mode & 0o777 == 0o600
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


@pytest.mark.parametrize("value", [None, [], "relative/workspace"])
def test_service_config_requires_absolute_paths(value):
    with pytest.raises(ValueError, match="absolute"):
        ServiceConfig(sys.executable, value)


@pytest.mark.parametrize(
    "value", [[], {"schema": 1, "managed_by": MARKER}, {"schema": 1, "managed_by": MARKER, "config": None}]
)
def test_malformed_receipts_are_passive_and_cannot_launch(manager, value):
    owner, native, config, _ = manager
    owner.install(config)
    owner.provider.record_path.write_text(json.dumps(value))
    assert owner.status()["configuration_valid"] is False
    with pytest.raises(ValueError, match="changed"):
        owner.start()
    assert not native.running
