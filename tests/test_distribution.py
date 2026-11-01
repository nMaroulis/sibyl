"""Check installed-app boundaries, launch configuration and release artifact contracts."""

import hashlib
import json
import shutil
import subprocess
import sys
import threading
import tomllib
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sibyl import __version__, cli, paths
from sibyl.api.dashboard import dashboard_directory, mount_dashboard
from sibyl.config import Settings

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "distribution"


@pytest.mark.parametrize(
    "platform,environment,expected",
    [
        ("darwin", {}, "Library/Application Support/Sibyl"),
        ("win32", {}, "AppData/Local/Sibyl"),
        ("linux", {}, ".local/share/sibyl"),
        ("linux", {"XDG_DATA_HOME": "relative"}, ".local/share/sibyl"),
    ],
)
def test_default_workspace_is_per_user_not_the_launch_directory(
    tmp_path, monkeypatch, platform, environment, expected
):
    monkeypatch.setattr(paths.sys, "platform", platform)
    monkeypatch.setattr(paths, "_checkout_workspace", lambda: None)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for name in ("LOCALAPPDATA", "XDG_DATA_HOME"):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    assert paths.default_data_dir() == tmp_path / expected
    assert not (tmp_path / expected).exists()


def test_explicit_workspace_environment_keeps_existing_source_layout(tmp_path, monkeypatch):
    monkeypatch.setenv("SIBYL_DATA_DIR", str(tmp_path / ".sibyl"))
    assert Settings(_env_file=None).data_dir == tmp_path / ".sibyl"
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setattr(paths, "_checkout_workspace", lambda: None)
    assert paths.default_data_dir() == tmp_path / "xdg" / "sibyl"


def test_source_checkout_retains_its_workspace_without_an_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("SIBYL_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert Settings(_env_file=None).data_dir == ROOT / ".sibyl"


@pytest.fixture
def dashboard(tmp_path):
    (tmp_path / "index.html").write_text('<html><div id="root">Installed dashboard</div></html>')
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "main.js").write_text("console.log('dashboard');")
    app = FastAPI()
    mount_dashboard(app, tmp_path)
    return TestClient(app)


@pytest.mark.parametrize("route", ["/", "/account", "/strategies?view=monitor", "/settings/"])
def test_bundled_dashboard_supports_page_navigation(dashboard, route):
    response = dashboard.get(route)
    assert response.status_code == 200
    assert "Installed dashboard" in response.text
    assert response.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize(
    "route",
    ["/api", "/api/missing", "/assets/missing", "/assets/missing.js", "/missing.css", "/health/missing"],
)
def test_missing_api_and_assets_never_return_the_dashboard(dashboard, route):
    response = dashboard.get(route)
    assert response.status_code == 404
    assert "Installed dashboard" not in response.text


def test_dashboard_override_is_validated_and_asset_is_served(dashboard, tmp_path):
    assert dashboard_directory(tmp_path) == tmp_path
    assert dashboard.get("/assets/main.js").headers["content-type"].startswith("text/javascript")
    with pytest.raises(ValueError, match="index.html"):
        dashboard_directory(tmp_path / "missing")


def test_help_and_version_do_not_import_the_application(tmp_path):
    program = (
        "import sys; from sibyl.cli import main; "
        "\ntry: main(['--version'])"
        "\nexcept SystemExit as exc: assert exc.code == 0"
        "\nassert 'sibyl.api.app' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", program], cwd=tmp_path, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert f"Sibyl {__version__}" in result.stdout
    assert list(tmp_path.iterdir()) == []


def test_launcher_passes_cli_overrides_to_the_actual_app(tmp_path, monkeypatch):
    captured = {}
    monkeypatch.setenv("SIBYL_PORT", "9999")
    monkeypatch.setenv("SIBYL_ALLOW_LIVE_TRADING", "false")

    def create(settings):
        captured["settings"] = settings
        return FastAPI()

    class Server:
        def __init__(self, config):
            captured["config"] = config

        def run(self):
            captured["ran"] = True

    monkeypatch.setattr("sibyl.api.app.create_app", create)
    monkeypatch.setattr("uvicorn.Server", Server)
    cli.main(["--no-env-file", "--port", "8123", "--data-dir", str(tmp_path)])
    assert captured["settings"].port == captured["config"].port == 8123
    assert captured["settings"].data_dir == tmp_path
    assert captured["settings"].allow_live_trading is False
    assert captured["ran"]
    assert list(tmp_path.iterdir()) == []


def test_invalid_configuration_does_not_print_private_input(monkeypatch, capsys):
    monkeypatch.setenv("SIBYL_API_TOKEN", "DO-NOT-PRINT-THIS")
    with pytest.raises(SystemExit) as error:
        cli.main(["--no-env-file", "--port", "99999"])
    assert error.value.code == 2
    output = capsys.readouterr().err
    assert "port" in output and "DO-NOT-PRINT-THIS" not in output


def test_launcher_requires_token_for_non_loopback(monkeypatch, capsys):
    monkeypatch.delenv("SIBYL_API_TOKEN", raising=False)
    with pytest.raises(SystemExit) as error:
        cli.main(["--no-env-file", "--host", "0.0.0.0"])
    assert error.value.code == 2
    assert "SIBYL_API_TOKEN" in capsys.readouterr().err


def test_browser_waits_for_our_ready_server_and_respects_stop(monkeypatch):
    opened = []
    monkeypatch.setattr(cli.webbrowser, "open", opened.append)
    server = SimpleNamespace(started=True, should_exit=False)
    cli._open_when_ready(server, threading.Event(), "http://127.0.0.1:8000")
    assert opened == ["http://127.0.0.1:8000"]
    stopped = threading.Event()
    stopped.set()
    cli._open_when_ready(server, stopped, "http://127.0.0.1:8001")
    server.should_exit = True
    cli._open_when_ready(server, threading.Event(), "http://127.0.0.1:8002")
    assert len(opened) == 1


@pytest.mark.parametrize("host,expected", [("::", "[::1]"), ("0.0.0.0", "127.0.0.1")])
def test_launcher_opens_a_reachable_loopback_url_after_startup(monkeypatch, host, expected):
    opened = threading.Event()
    urls = []
    monkeypatch.setenv("SIBYL_API_TOKEN", "test-launch-token")
    monkeypatch.setattr("sibyl.api.app.create_app", lambda settings: FastAPI())

    def open_browser(url):
        urls.append(url)
        opened.set()
        return True

    class Server:
        def __init__(self, config):
            self.started = self.should_exit = False

        def run(self):
            self.started = True
            assert opened.wait(3), "Browser was not opened after startup."

    monkeypatch.setattr("uvicorn.Server", Server)
    monkeypatch.setattr(cli.webbrowser, "open", open_browser)
    cli.main(["--no-env-file", "--host", host, "--port", "8123", "--open-browser"])
    assert urls == [f"http://{expected}:8123"]


def run_script(name, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *(str(arg) for arg in args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_release_tag_must_match_all_version_metadata():
    assert run_script("release.py", "version", "--tag", f"v{__version__}").returncode == 0
    assert run_script("release.py", "version", "--tag", "v9.9.9").returncode != 0


@pytest.fixture
def version_workspace(tmp_path):
    """Copy only release metadata; never edit the user's working tree in a version test."""
    for relative in (
        "pyproject.toml",
        "src/sibyl/__init__.py",
        "package.json",
        "frontend/package.json",
        "docs/package.json",
        "package-lock.json",
        "uv.lock",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    (tmp_path / "changelog.md").write_text("Historical releases remain fixed.\n")
    return tmp_path


def test_one_version_command_updates_metadata_and_locks_without_upgrading_dependencies(version_workspace):
    root = version_workspace
    previous_uv = tomllib.loads((root / "uv.lock").read_text())
    previous_npm = json.loads((root / "package-lock.json").read_text())
    result = run_script("release.py", "set-version", "9.8.7", "--root", root)
    assert result.returncode == 0, result.stderr
    assert run_script("release.py", "version", "--tag", "v9.8.7", "--root", root).returncode == 0
    updated_uv = tomllib.loads((root / "uv.lock").read_text())
    for package in updated_uv["package"]:
        if package["name"] == "sibyl":
            assert package["version"] == "9.8.7"
            package["version"] = __version__
    assert updated_uv == previous_uv
    updated_npm = json.loads((root / "package-lock.json").read_text())
    assert updated_npm["version"] == "9.8.7"
    updated_npm["version"] = __version__
    for workspace in ("", "frontend", "docs"):
        assert updated_npm["packages"][workspace]["version"] == "9.8.7"
        updated_npm["packages"][workspace]["version"] = __version__
    assert updated_npm == previous_npm
    assert (root / "changelog.md").read_text() == "Historical releases remain fixed.\n"


def test_version_preview_and_repeated_version_leave_files_unchanged(version_workspace):
    before = {p: p.read_bytes() for p in version_workspace.rglob("*") if p.is_file()}
    preview = run_script("release.py", "set-version", "9.8.7", "--root", version_workspace, "--dry-run")
    assert preview.returncode == 0, preview.stderr
    assert "Would set" in preview.stdout
    repeated = run_script("release.py", "set-version", __version__, "--root", version_workspace)
    assert repeated.returncode == 0, repeated.stderr
    assert all(p.read_bytes() == contents for p, contents in before.items())


@pytest.mark.parametrize("version", ["v3.0.0", "3.0", "3.0.0\ninvalid", "03.0.0"])
def test_invalid_versions_do_not_change_metadata(version_workspace, version):
    before = {p: p.read_bytes() for p in version_workspace.rglob("*") if p.is_file()}
    assert run_script("release.py", "set-version", version, "--root", version_workspace).returncode != 0
    assert all(p.read_bytes() == contents for p, contents in before.items())


def test_invalid_target_is_detected_before_any_metadata_is_written(version_workspace):
    (version_workspace / "src/sibyl/__init__.py").write_text("# Missing version declaration\n")
    before = {p: p.read_bytes() for p in version_workspace.rglob("*") if p.is_file()}
    result = run_script("release.py", "set-version", "9.8.7", "--root", version_workspace)
    assert result.returncode != 0
    assert all(p.read_bytes() == contents for p, contents in before.items())


def test_version_command_repairs_mismatched_mirrors_and_lock_entries(version_workspace):
    lock = version_workspace / "package-lock.json"
    metadata = json.loads(lock.read_text())
    metadata["packages"]["frontend"]["version"] = "0.0.1"
    lock.write_text(json.dumps(metadata, indent=2) + "\n")
    mismatch = run_script("release.py", "version", "--root", version_workspace)
    assert mismatch.returncode != 0 and "package-lock.json" in mismatch.stderr
    repaired = run_script("release.py", "set-version", __version__, "--root", version_workspace)
    assert repaired.returncode == 0, repaired.stderr
    assert run_script("release.py", "version", "--root", version_workspace).returncode == 0


def test_incomplete_wheel_is_rejected_before_publication(tmp_path):
    wheel = tmp_path / "sibyl.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(f"sibyl-{__version__}.dist-info/METADATA", f"Name: sibyl\nVersion: {__version__}\n")
    result = run_script("release.py", "inspect-wheel", wheel)
    assert result.returncode != 0 and "Incomplete wheel" in result.stderr


def test_checksum_manifest_is_stable_and_does_not_hash_itself(tmp_path):
    (tmp_path / "artifact.whl").write_bytes(b"release artifact")
    (tmp_path / "SHA256SUMS").write_text("old manifest")
    (tmp_path / ".gitignore").write_text("*")
    assert run_script("release.py", "checksums", tmp_path).returncode == 0
    assert (tmp_path / "SHA256SUMS").read_text() == (
        f"{hashlib.sha256(b'release artifact').hexdigest()}  artifact.whl\n"
    )
