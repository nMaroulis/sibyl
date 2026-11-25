"""Independent credential, runtime and lifecycle checks for named model deployments."""

from fastapi.testclient import TestClient

from sibyl.api.app import create_app
from sibyl.services.workspace import model_checks

ROOT = "/api/v1/settings/llm"
DEPLOYMENTS = ROOT + "/deployments"


def add(client, provider, **fields):
    response = client.post(DEPLOYMENTS, json={"provider": provider, **fields})
    assert response.status_code == 201, response.text
    return response.json()["deployments"][-1]


def test_named_deployments_keep_distinct_keys_models_and_default(client, settings, monkeypatch):
    monkeypatch.setattr("sibyl.agents.utils.providers.find_spec", lambda _: object())
    key_one, key_two = "sk-first-test-only-0001", "sk-second-test-only-0002"
    first = add(client, "openai", api_key=key_one)
    assert first["name"] == "OpenAI API model"
    assert first["model"] == ""
    assert not first["default"]
    one = f"{DEPLOYMENTS}/{first['id']}"
    assert client.post(one + "/default").status_code == 400

    second = add(client, "openai", api_key=key_two, model="second-model")
    assert second["name"] == "OpenAI API model (1)"
    two = f"{DEPLOYMENTS}/{second['id']}"
    assert client.post(DEPLOYMENTS, json={"provider": "openai", "model": "third"}).status_code == 400
    assert client.put(one + "/model", json={"model": "first-model"}).is_success
    state = client.post(one + "/default").json()
    assert state["active_deployment"] == first["id"]
    assert state["active_model"] == "first-model"

    assigned = client.post(
        ROOT + "/agents/reporter", json={"revision": state["agent_revision"], "deployment": second["id"]}
    )
    assert assigned.is_success, assigned.text
    registry = client.app.state.services.agents.models
    assert registry.resolve()["api_key"] == key_one
    assert registry.resolve("reporter")["api_key"] == key_two

    probes = []

    def sample(config):
        probes.append((config["model"], config["api_key"]))
        return "OK"

    monkeypatch.setattr(model_checks, "_sample", sample)
    assert client.post(one + "/check").json()["status"] == "ready"
    assert client.post(two + "/check").json()["status"] == "ready"
    assert probes == [("first-model", key_one), ("second-model", key_two)]
    assert client.put(two, json={"provider": "openai", "name": "Research key"}).is_success
    edited = client.put(two + "/model", json={"model": "new-research-model"})
    assert edited.is_success
    assert edited.json()["active_model"] == "first-model"
    assert registry.resolve("reporter")["model"] == "new-research-model"
    assert registry.resolve("reporter")["api_key"] == key_two
    assert key_one not in edited.text and key_two not in edited.text

    with TestClient(create_app(settings)) as restarted:
        rows = restarted.get(ROOT).json()["deployments"]
        assert [(row["name"], row["key_preview"]) for row in rows] == [
            ("OpenAI API model", "sk-••••••0001"),
            ("Research key", "sk-••••••0002"),
        ]
        removed = restarted.delete(one).json()
        assert removed["active_provider"] == "none"
        assert removed["deployments"][0]["agents"] == ["reporter"]
        assert restarted.app.state.services.agents.models.resolve("reporter")["api_key"] == key_two
        state = restarted.delete(two).json()
        assert state["deployments"] == []
        assert all(agent["inherited"] for agent in state["agents"])
        assert restarted.post(two + "/check").status_code == 404


def test_local_deployment_monitor_uses_its_endpoint_and_credential(client, monkeypatch):
    first = add(client, "ollama", base_url="http://localhost:11452", api_key="first-private-token")
    second = add(client, "ollama", base_url="http://localhost:11453", api_key="second-private-token")
    probes = []

    def check(request, *, api_key):
        probes.append((request.base_url, api_key))
        return {"status": "running", "models": []}

    monkeypatch.setattr(client.app.state.services.ollama, "check", check)
    for row in (first, second):
        result = client.get(f"{DEPLOYMENTS}/{row['id']}/runtime")
        assert result.json() == {"status": "running", "models": []}
    assert probes == [
        ("http://localhost:11452", "first-private-token"),
        ("http://localhost:11453", "second-private-token"),
    ]
