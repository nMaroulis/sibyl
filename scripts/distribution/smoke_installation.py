"""Exercise an installed Sibyl outside its checkout, with isolated offline state and no credentials."""

import base64
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


def main() -> None:
    """Check CLI, readiness, deep links, referenced assets, API isolation and durable workspace state."""
    # This script intentionally imports no Sibyl module in its own source directory.
    with tempfile.TemporaryDirectory(prefix="sibyl-install-check-") as temporary:
        root = Path(temporary)
        workspace = root / "workspace"
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("SIBYL_") and key not in {"PYTHONPATH", "PYTHONHOME"}
        }
        # Seed only source preferences, never a Demo account or an exchange connection.
        prepare = (
            "from sibyl.storage import Store; import pypdf, sibyl, sys; from pathlib import Path; "
            "assert Path(sibyl.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()), "
            "'Expected an installed package, not an editable checkout'; "
            "store=Store(Path(sys.argv[1])); "
            "store.save_data_profile('market', {'source':'demo','profiles':{}}); "
            "store.save_data_profile('news', {'mode':'demo','profiles':{}})"
        )
        subprocess.run([sys.executable, "-I", "-c", prepare, str(workspace)], cwd=root, env=env, check=True)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        command = [
            sys.executable,
            "-I",
            "-m",
            "sibyl",
            "--no-env-file",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--data-dir",
            str(workspace),
        ]
        version = subprocess.check_output(command[:4] + ["--version"], cwd=root, env=env, text=True).strip()
        preview = json.loads(
            subprocess.check_output(
                command[:4] + ["service", "preview", "--data-dir", str(workspace), "--port", str(port)],
                cwd=root,
                env=env,
                text=True,
            )
        )
        assert preview["config"]["data_dir"] == str(workspace)
        assert preview["config"]["port"] == port and "--no-env-file" in preview["arguments"]
        assert "--no-access-log" in preview["arguments"] and "--log-file" in preview["arguments"]
        url = f"http://127.0.0.1:{port}"
        with (root / "server.log").open("w+", encoding="utf-8") as log:
            process = subprocess.Popen(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 45
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("Installed application exited before readiness.")
                    try:
                        with urlopen(url + "/health", timeout=1) as response:
                            health = json.load(response)
                        assert health["status"] == "ok" and version == f"Sibyl {health['version']}"
                        break
                    except (URLError, TimeoutError):
                        if time.monotonic() >= deadline:
                            raise RuntimeError("Installed application did not become ready.") from None
                        time.sleep(0.15)
                with urlopen(url + "/strategies?view=monitor", timeout=5) as response:
                    assert response.headers.get_content_type() == "text/html"
                    html = response.read().decode()
                assets = re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html)
                assert any(asset.endswith(".js") for asset in assets), "Dashboard entry has no JavaScript."
                for asset in assets:
                    with urlopen(url + asset, timeout=5) as response:
                        assert response.status == 200
                for missing in ("/api/does-not-exist", "/assets/does-not-exist", "/assets/does-not-exist.js"):
                    try:
                        urlopen(url + missing, timeout=5).close()
                    except URLError as exc:
                        assert getattr(exc, "code", None) == 404
                    else:
                        raise AssertionError(f"Missing endpoint returned the dashboard: {missing}")
                assert (workspace / "sibyl.db").is_file()
                assert (workspace / "vault.key").is_file()
                with urlopen(url + "/api/v1/connections", timeout=5) as response:
                    assert json.load(response) == [], "Installation activated an account."

                def request_json(path, body=None):
                    request = Request(
                        url + "/api/v1" + path,
                        data=json.dumps(body).encode() if body is not None else None,
                        headers={"Content-Type": "application/json"},
                    )
                    with urlopen(request, timeout=20) as response:
                        assert response.headers.get("Cache-Control") == "no-store"
                        return json.load(response)

                document = request_json(
                    "/library/documents",
                    {
                        "filename": "installation-check.txt",
                        "title": "Installation research",
                        "data_base64": base64.b64encode(
                            b"Isolated installation research about quasar reserves."
                        ).decode(),
                    },
                )
                matches = request_json("/library/search?query=quasar")
                assert matches["items"][0]["document_id"] == document["id"]
                workers = request_json("/workspace/health")
                assert any(worker["id"] == "library" for worker in workers["workers"])
                assert "rss_bytes" in workers["resources"] and "cpu_percent" in workers["resources"]
                retention = request_json("/notifications/retention")
                assert not retention["policy"]["enabled"], (
                    "Installation enabled automatic notification deletion."
                )
                assert retention["preview"]["eligible"] == 0
                assert request_json("/notifications/export")["items"] == []
                passphrase = "isolated installation archive passphrase"
                archive = request_json("/workspace/backups", {"passphrase": passphrase})
                inspected = request_json(
                    f"/workspace/backups/{archive['id']}/inspect", {"passphrase": passphrase}
                )
                assert inspected["includes_credentials"] and inspected["files"] >= 2
                restored = request_json(
                    f"/workspace/backups/{archive['id']}/restore",
                    {
                        "passphrase": passphrase,
                        "confirmation": "RESTORE AS NEW WORKSPACE",
                    },
                )
                recovered = Path(restored["data_dir"]).resolve()
                assert (
                    recovered.is_relative_to(workspace.resolve() / ".sibyl-managed" / "recovered")
                    and recovered != workspace.resolve()
                )
                check = (
                    "from sibyl.storage import Store; from pathlib import Path; import sys; "
                    "store=Store(Path(sys.argv[1])); assert store.data_profile('workspace-recovery')['required']; "
                    "\nwith store.db() as db:\n    assert not db.execute('SELECT account_id FROM active_accounts').fetchall()\n"
                )
                subprocess.run(
                    [sys.executable, "-I", "-c", check, str(recovered)], cwd=root, env=env, check=True
                )
                print(
                    f"{version}: installed CLI, service preview, dashboard, API boundaries, research, worker health and encrypted recovery OK."
                )
            except BaseException:
                log.flush()
                log.seek(0)
                print(log.read(), file=sys.stderr)
                raise
            finally:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    main()
