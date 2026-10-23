"""Ollama status and process ownership; no shell commands or automatic installs."""

import os
import re
import shlex
import shutil
import subprocess
import threading
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from pydantic import Field, field_validator

from sibyl.models import Request
from sibyl.services.llm_settings import ModelSettingsRequest


class OllamaRequest(Request):
    """Probe the selected endpoint before saving it as the active model profile."""

    base_url: str = Field(default="http://127.0.0.1:11434", max_length=2048)
    model: str = Field(default="", max_length=500)

    @field_validator("base_url")
    @classmethod
    def valid_url(cls, value):
        validated = ModelSettingsRequest(provider="ollama", model="probe", base_url=value)
        return validated.base_url.rstrip("/")

    @field_validator("model")
    @classmethod
    def clean_model(cls, value):
        if any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("Model IDs cannot contain control characters.")
        return value.strip()


class OllamaService:
    """Inspect installed and running models, and manage only our own local child.

    Remote/custom endpoints can be checked but never spawned. The caller cannot
    supply an executable or arguments. Existing desktop/system Ollama processes
    are reused and never stopped by this application.
    """

    def __init__(self, models, http=None):
        self.models = models
        self.http = http or httpx.Client(timeout=3, follow_redirects=False, trust_env=False)
        self._lock = threading.RLock()
        self._process = None
        self._owned_endpoint = None

    @staticmethod
    def executable():
        """Find the installed CLI on PATH or the standard macOS application bundle."""
        candidates = [
            shutil.which("ollama"),
            "/Applications/Ollama.app/Contents/Resources/ollama",
            str(Path.home() / "Applications/Ollama.app/Contents/Resources/ollama"),
        ]
        return next(
            (str(Path(p).resolve()) for p in candidates if p and Path(p).is_file() and os.access(p, os.X_OK)),
            None,
        )

    @staticmethod
    def local_target(url):
        """Only a plain loopback HTTP origin can be served by a local child process."""
        parsed = urlsplit(url)
        return (
            parsed.scheme == "http"
            and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
            and parsed.path in {"", "/"}
        )

    def _headers(self, endpoint):
        """Use a saved credential only at its saved Ollama endpoint, never a draft override."""
        active = self.models.resolve()
        if (
            active["provider"] == "ollama"
            and active["base_url"].rstrip("/") == endpoint
            and active["api_key"]
        ):
            return {"Authorization": f"Bearer {active['api_key']}"}
        _, profiles = self.models.store.model_profiles()
        saved = profiles.get("ollama", {})
        if saved.get("base_url", "").rstrip("/") == endpoint and saved.get("api_key"):
            return {"Authorization": f"Bearer {saved['api_key']}"}
        return {}

    def check(self, request: OllamaRequest):
        """Read native version, available models and loaded models without inference."""
        endpoint = request.base_url
        executable = self.executable()
        models, loaded, version, error = [], [], None, None
        try:
            headers = self._headers(endpoint)
            response = self.http.get(endpoint + "/api/version", headers=headers)
            response.raise_for_status()
            version = response.json()["version"]
            if not isinstance(version, str) or len(version) > 100:
                raise ValueError("Invalid version.")
            response = self.http.get(endpoint + "/api/tags", headers=headers)
            response.raise_for_status()
            raw = response.json()["models"]
            if not isinstance(raw, list) or len(raw) > 5000:
                raise ValueError("Invalid model list.")
            models = [
                {
                    "name": row["name"],
                    "size": row.get("size"),
                    "parameter_size": row.get("details", {}).get("parameter_size"),
                }
                for row in raw
                if isinstance(row, dict) and isinstance(row.get("name"), str)
            ]
            response = self.http.get(endpoint + "/api/ps", headers=headers)
            if response.is_success:
                loaded = [
                    row["name"]
                    for row in response.json().get("models", [])
                    if isinstance(row, dict) and isinstance(row.get("name"), str)
                ]
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            error = "Ollama could not be reached or did not return its model catalog. Check the endpoint and start the server."
            version = None
        with self._lock:
            process = self._process
            owned = process is not None and process.poll() is None
        starting = owned and endpoint == self._owned_endpoint and version is None
        names = {row["name"] for row in models}
        selected = request.model if ":" in request.model else request.model + ":latest"
        present = bool(request.model and (request.model in names or selected in names))
        safe_model = (
            request.model if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_./:-]{0,200}", request.model) else ""
        )
        return {
            "installed": bool(executable),
            "executable": executable,
            "endpoint": endpoint,
            "local": self.local_target(endpoint),
            "status": "running"
            if version is not None
            else "starting"
            if starting
            else "not_installed"
            if not executable and self.local_target(endpoint)
            else "unreachable",
            "version": version,
            "models": models,
            "loaded_models": loaded,
            "selected_model_installed": present,
            "managed": bool(owned and endpoint == self._owned_endpoint),
            "can_start": bool(executable and self.local_target(endpoint) and not owned and version is None),
            "can_stop": bool(owned and endpoint == self._owned_endpoint),
            "error": None if version is not None else error,
            "install_url": "https://ollama.com/download",
            "setup_url": "https://docs.ollama.com/quickstart",
            "pull_command": f"ollama pull {shlex.quote(safe_model)}" if safe_model else None,
            "note": "Checks run on the machine hosting Sibyl’s Python backend. Starting Ollama does not install or download a model. Only a process started by Sibyl can be stopped here.",
        }

    def start(self, request):
        """Launch exactly `ollama serve` on loopback; repeated starts reuse the same child."""
        with self._lock:
            if not self.local_target(request.base_url):
                raise ValueError("Sibyl can only start Ollama at a plain local HTTP endpoint.")
            status = self.check(request)
            if status["status"] in {"running", "starting"}:
                return status
            executable = self.executable()
            if not executable:
                raise ValueError("Install Ollama on the Python backend machine first, then check again.")
            if self._process is not None and self._process.poll() is None:
                raise ValueError(
                    "Sibyl already manages an Ollama process at another endpoint. Stop it first."
                )
            parsed = urlsplit(request.base_url)
            host = "[::1]" if parsed.hostname == "::1" else "127.0.0.1"
            env = {
                key: value
                for key, value in os.environ.items()
                if key
                in {
                    "PATH",
                    "HOME",
                    "USER",
                    "TMPDIR",
                    "TEMP",
                    "TMP",
                    "SYSTEMROOT",
                    "WINDIR",
                    "LANG",
                    "LD_LIBRARY_PATH",
                    "DYLD_LIBRARY_PATH",
                    "CUDA_VISIBLE_DEVICES",
                    "ROCR_VISIBLE_DEVICES",
                    "OLLAMA_MODELS",
                }
            }
            # Match the checked HTTP origin, including its default port.
            env["OLLAMA_HOST"] = f"{host}:{parsed.port if parsed.port is not None else 80}"
            try:
                self._process = subprocess.Popen(
                    [executable, "serve"],
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                self._owned_endpoint = request.base_url
            except OSError:
                raise ValueError(
                    "Ollama could not start. Check its installation on the backend machine."
                ) from None
            return self.check(request)

    def stop(self, request):
        """Stop only the child owned by this application; external servers are untouched."""
        with self._lock:
            if (
                self._owned_endpoint != request.base_url
                or self._process is None
                or self._process.poll() is not None
            ):
                raise ValueError("This Ollama server was not started by Sibyl. Stop it in Ollama itself.")
            self._stop_owned()
        return self.check(request)

    def _stop_owned(self):
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        self._process, self._owned_endpoint = None, None

    def close(self):
        """Release our server child and HTTP pool during application shutdown."""
        with self._lock:
            self._stop_owned()
            self.http.close()
