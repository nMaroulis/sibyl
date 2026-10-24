"""Native Ollama status and explicitly owned process lifecycle; no actual server spawn."""

import subprocess

import httpx
import pytest

from sibyl.local_models.ollama import OllamaRequest, OllamaService
from sibyl.services.llm_settings import ModelSettings


@pytest.fixture
def service(settings, store, monkeypatch):
    def transport(request):
        result = {
            "/api/version": {"version": "test-version"},
            "/api/tags": {
                "models": [{"name": "qwen3:8b", "size": 5000, "details": {"parameter_size": "8B"}}]
            },
            "/api/ps": {"models": [{"name": "qwen3:8b"}]},
        }[request.url.path]
        return httpx.Response(200, json=result)

    result = OllamaService(
        ModelSettings(settings, store), httpx.Client(transport=httpx.MockTransport(transport))
    )
    monkeypatch.setattr(result, "executable", lambda: "/trusted/ollama")
    yield result
    result.close()


def test_checks_real_native_catalog_and_loaded_models_without_inference(service):
    result = service.check(OllamaRequest(model="qwen3:8b"))
    assert result["installed"] and result["status"] == "running" and result["version"] == "test-version"
    assert result["selected_model_installed"] and result["loaded_models"] == ["qwen3:8b"]
    assert not result["can_start"] and not result["can_stop"] and not result["managed"]
    assert service.check(OllamaRequest(model="missing"))["selected_model_installed"] is False
    with pytest.raises(ValueError, match="not started"):
        service.stop(OllamaRequest())


def test_only_saved_endpoint_receives_saved_credential(service):
    from sibyl.services.llm_settings import ModelSettingsRequest

    service.models.save(
        ModelSettingsRequest(
            provider="ollama", model="qwen3:8b", api_key="PRIVATE-KEY", base_url="http://localhost:11434"
        )
    )
    assert service._headers("http://localhost:11434") == {"Authorization": "Bearer PRIVATE-KEY"}
    assert service._headers("https://other.example") == {}


class Process:
    def __init__(self):
        self.alive = True
        self.terminated = False

    def poll(self):
        return None if self.alive else 0

    def terminate(self):
        self.terminated = True
        self.alive = False

    def wait(self, timeout):
        self.alive = False
        return 0


@pytest.mark.parametrize(
    ("endpoint", "host"),
    [("http://127.0.0.1:11434", "127.0.0.1:11434"), ("http://localhost", "127.0.0.1:80")],
)
def test_start_uses_fixed_cli_and_loopback_env_is_idempotent_and_only_stops_owned(
    service, monkeypatch, endpoint, host
):
    service.http.close()

    def unavailable(request):
        raise httpx.ConnectError("PRIVATE", request=request)

    service.http = httpx.Client(transport=httpx.MockTransport(unavailable))
    launched = []
    process = Process()

    def spawn(args, **kwargs):
        launched.append((args, kwargs))
        return process

    monkeypatch.setattr(subprocess, "Popen", spawn)
    monkeypatch.setenv("SECRET_TEST_KEY", "DO-NOT-FORWARD")
    request = OllamaRequest(base_url=endpoint)
    first = service.start(request)
    assert first["status"] == "starting" and first["managed"] and first["can_stop"]
    service.start(request)
    assert len(launched) == 1
    args, kwargs = launched[0]
    assert args == ["/trusted/ollama", "serve"]
    assert kwargs["env"]["OLLAMA_HOST"] == host
    assert "SECRET_TEST_KEY" not in kwargs["env"] and "shell" not in kwargs
    service.stop(request)
    assert process.terminated


@pytest.mark.parametrize(
    "endpoint", ["http://0.0.0.0:11434", "https://remote.example", "http://127.0.0.1:11434/proxy"]
)
def test_remote_or_wildcard_endpoint_can_never_launch_a_process(service, endpoint, monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: pytest.fail("Unexpected process"))
    with pytest.raises(ValueError, match="local"):
        service.start(OllamaRequest(base_url=endpoint))


def test_api_rejects_shell_fields_and_invalid_endpoints(client):
    assert client.post("/api/v1/settings/ollama/start", json={"command": "arbitrary"}).status_code == 422
    for endpoint in [
        "file:///tmp/bin",
        "http://user:secret@localhost:11434",
        "http://localhost:11434?token=secret",
    ]:
        assert client.post("/api/v1/settings/ollama/check", json={"base_url": endpoint}).status_code == 422
