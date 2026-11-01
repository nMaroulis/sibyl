"""Exercise an installed Sibyl outside its checkout, with isolated offline state and no credentials."""

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
from urllib.request import urlopen


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
            "from sibyl.storage import Store; import sibyl, sys; from pathlib import Path; "
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
                for missing in ("/api/does-not-exist", "/assets/does-not-exist.js"):
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
                print(
                    f"{version}: installed CLI, dashboard, assets, deep links, API boundaries and workspace OK."
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
