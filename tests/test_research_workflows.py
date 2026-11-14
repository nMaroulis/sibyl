"""Native durable questions/approvals, frozen model choices and specialist receipts."""

import json
import time
from uuid import uuid4

import pytest
from agent_helpers import coordinator_factory, delegate
from fastapi.testclient import TestClient
from protolink import create_llm, current_request_context
from test_investigations import answer, create

from sibyl.api.app import create_app


def observations(history):
    found = {}
    for message in history.messages:
        try:
            body = json.loads(message.get("content", ""))
        except (ValueError, TypeError):
            continue
        if isinstance(body, dict) and body.get("type") == "tool_result":
            found[body["tool"]] = body.get("result")
    return found


def configure(client, monkeypatch, callback):
    assert client.post("/api/v1/settings/llm", json={"provider": "mock"}).status_code == 200
    calls = []

    def factory(*args, **kwargs):
        calls.append(current_request_context()["models"]["_agents"]["sibyl"]["model"])
        return create_llm("mock", response_callback=callback)

    coordinator_factory(monkeypatch, factory)
    return calls


def start(client, definition):
    response = client.post(
        f"/api/v1/investigations/{definition['id']}/runs",
        json={"request_id": uuid4().hex, "checkpoints": True},
    )
    assert response.status_code == 202, response.text
    assert response.json()["durable"]
    return response.json()


def wait(client, definition, run):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/investigations/{definition['id']}/runs/{run['id']}")
        assert response.status_code == 200, response.text
        result = response.json()
        if result["status"] not in {"queued", "running", "cancelling"}:
            return result
        time.sleep(0.01)
    pytest.fail("The bounded native workflow did not reach an observation boundary.")


def respond(client, definition, run, kind, **patch):
    pending = run["workflow"]["interruption"]
    response = client.post(
        f"/api/v1/investigations/{definition['id']}/runs/{run['id']}/resume",
        json={
            "kind": kind,
            "request_id": pending["request_id"],
            "fingerprint": pending["fingerprint"],
            **patch,
        },
    )
    assert response.status_code == 202, response.text
    return wait(client, definition, run)


def test_native_question_freezes_models_and_keeps_actual_specialist_sources(client, monkeypatch):
    def callback(history, prompt):
        seen = observations(history)
        if "ask_user" not in seen:
            return {
                "type": "tool_call",
                "tool": "ask_user",
                "args": {"question": "Which coin should I review?"},
            }
        if not any(
            message.get("role") == "assistant" and "agent_call" in str(message.get("content"))
            for message in history.messages
        ):
            return delegate("reporter", "Explain the retained Demo headlines", {"news_mode": "demo"})
        return answer(["reporter.news_briefing"])

    calls = configure(client, monkeypatch, callback)
    definition = create(client)
    waiting = wait(client, definition, start(client, definition))
    assert waiting["status"] == "input_required", waiting
    assert waiting["workflow"]["interruption"]["kind"] == "input"
    assert "Which coin" in json.dumps(waiting["workflow"]["interruption"]["request"])
    accepted_model = calls[0]
    assert (
        client.post("/api/v1/settings/llm", json={"provider": "mock", "model": "later-model"}).status_code
        == 200
    )
    bad = client.post(
        f"/api/v1/investigations/{definition['id']}/runs/{waiting['id']}/resume",
        json={"kind": "answer", "request_id": "stale", "fingerprint": "a" * 64, "answer": "ETH"},
    )
    assert bad.status_code == 409 and len(calls) == 1
    completed = respond(client, definition, waiting, "answer", answer="ETH")
    assert completed["status"] == "completed", completed
    assert all(model == accepted_model for model in calls)
    assert any(source["key"] == "reporter.news_briefing" for source in completed["sources"])
    assert completed["report"]["findings"][0]["sources"] == ["reporter.news_briefing"]
    assert not client.app.state.services.store.data_profile("workflow-models:" + waiting["id"])


def test_native_note_approval_precedes_write_and_is_bound_to_exact_arguments(client, monkeypatch):
    text = "A local AI draft. Demo inputs are synthetic and this is not investment advice."

    def callback(history, prompt):
        if "save_research_note" not in observations(history):
            return {
                "type": "tool_call",
                "tool": "save_research_note",
                "args": {"title": "Reviewed research note", "text": text},
            }
        return answer(summary="The approved local draft was retained.")

    configure(client, monkeypatch, callback)
    definition = create(client, question="Retain a local research note after I approve its text.")
    waiting = wait(client, definition, start(client, definition))
    assert waiting["status"] == "input_required", waiting
    pending = waiting["workflow"]["interruption"]
    assert pending["kind"] == "approval"
    assert text in json.dumps(pending["request"])
    library = client.app.state.services.library
    assert library.catalog(kind="document")["counts"].get("document", 0) == 0
    completed = respond(client, definition, waiting, "approve")
    assert completed["status"] == "completed", completed
    documents = library.catalog(kind="document")
    assert documents["counts"].get("document", 0) == 1
    assert documents["items"][0]["publisher"] == "Sibyl · AI research draft"
    exported = client.get(f"/api/v1/investigations/{definition['id']}/runs/{completed['id']}/export")
    assert "workflow-models" not in exported.text and "api_key" not in exported.text
    # An HTTP retry of an already completed continuation cannot run the write twice.
    repeated = client.post(
        f"/api/v1/investigations/{definition['id']}/runs/{completed['id']}/resume",
        json={"kind": "approve", "request_id": pending["request_id"], "fingerprint": pending["fingerprint"]},
    )
    assert repeated.status_code == 202
    assert library.catalog(kind="document")["counts"].get("document", 0) == 1


def test_reject_and_stop_never_write_the_local_note(client, monkeypatch):
    def callback(history, prompt):
        if "save_research_note" not in observations(history):
            return {
                "type": "tool_call",
                "tool": "save_research_note",
                "args": {"title": "Do not save", "text": "A rejected draft."},
            }
        return answer(summary="No note was saved.")

    configure(client, monkeypatch, callback)
    definition = create(client)
    waiting = wait(client, definition, start(client, definition))
    completed = respond(client, definition, waiting, "reject")
    assert completed["status"] == "cancelled" and completed["report"] is None, completed
    assert client.app.state.services.library.catalog(kind="document")["counts"].get("document", 0) == 0
    another = wait(client, definition, start(client, definition))
    stopped = client.post(f"/api/v1/investigations/{definition['id']}/runs/{another['id']}/cancel")
    assert stopped.status_code == 202 and stopped.json()["status"] == "cancelled"
    refused = client.post(
        f"/api/v1/investigations/{definition['id']}/runs/{another['id']}/resume", json={"kind": "continue"}
    )
    assert refused.status_code == 409
    assert client.app.state.services.library.catalog(kind="document")["counts"].get("document", 0) == 0


def test_native_wait_survives_restart_without_inference_and_resumes_same_checkpoint(settings, monkeypatch):
    def callback(history, prompt):
        if "ask_user" not in observations(history):
            return {
                "type": "tool_call",
                "tool": "ask_user",
                "args": {"question": "Choose the comparison window."},
            }
        return answer(summary="The retained question was answered after restart.")

    with TestClient(create_app(settings)) as first:
        calls = configure(first, monkeypatch, callback)
        definition = create(first)
        waiting = wait(first, definition, start(first, definition))
        assert waiting["status"] == "input_required", waiting
        native = waiting["native_run_id"]
    count = len(calls)
    with TestClient(create_app(settings)) as second:
        restored = second.get(f"/api/v1/investigations/{definition['id']}/runs/{waiting['id']}").json()
        assert restored["status"] == "input_required"
        assert restored["native_run_id"] == native
        assert len(calls) == count
        completed = respond(second, definition, restored, "answer", answer="Thirty daily bars")
        assert completed["status"] == "completed", completed
        assert completed["native_run_id"] == native


def test_waiting_workflow_owns_its_report_slot_and_cannot_be_deleted_or_pruned(client, monkeypatch):
    configure(
        client,
        monkeypatch,
        lambda *args: {"type": "tool_call", "tool": "ask_user", "args": {"question": "Which source?"}},
    )
    definition = create(client)
    waiting = wait(client, definition, start(client, definition))
    assert waiting["status"] == "input_required"
    blocked = client.post(f"/api/v1/investigations/{definition['id']}/runs", json={"request_id": uuid4().hex})
    assert blocked.status_code == 409
    assert client.delete(f"/api/v1/investigations/{definition['id']}").status_code == 409
    assert (
        client.app.state.services.investigations.repository.prune_scheduled(definition["id"], "a-schedule", 1)
        == []
    )


def test_private_model_snapshot_is_encrypted_and_never_checkpointed_or_exported(client, monkeypatch):
    from sibyl.agents.utils import providers

    available = providers.find_spec
    monkeypatch.setattr(
        providers, "find_spec", lambda name: object() if name == "openai" else available(name)
    )
    secret = "WORKFLOW-PROVIDER-PRIVATE-123"
    assert (
        client.post(
            "/api/v1/settings/llm", json={"provider": "openai", "model": "accepted-model", "api_key": secret}
        ).status_code
        == 200
    )
    calls = []

    def callback(history, prompt):
        if "ask_user" not in observations(history):
            return {"type": "tool_call", "tool": "ask_user", "args": {"question": "Which horizon?"}}
        return answer()

    def factory(provider, **kwargs):
        calls.append((provider, kwargs["api_key"], kwargs["model"]))
        return create_llm("mock", response_callback=callback)

    coordinator_factory(monkeypatch, factory)
    definition = create(client)
    waiting = wait(client, definition, start(client, definition))
    assert waiting["status"] == "input_required"
    workflows = client.app.state.services.investigations.workflows
    assert secret.encode() not in workflows.path.read_bytes()
    with workflows.store.db() as db:
        encrypted = db.execute(
            "SELECT value FROM workspace_settings WHERE key=?", ("data:workflow-models:" + waiting["id"],)
        ).fetchone()[0]
    assert secret.encode() not in encrypted
    assert secret not in json.dumps(waiting)
    assert (
        client.post(
            "/api/v1/settings/llm",
            json={"provider": "openai", "model": "new-model", "api_key": "NEW-PROVIDER-PRIVATE"},
        ).status_code
        == 200
    )
    completed = respond(client, definition, waiting, "answer", answer="Seven days")
    assert completed["status"] == "completed", completed
    assert calls == [("openai", secret, "accepted-model"), ("openai", secret, "accepted-model")]
    exported = client.get(f"/api/v1/investigations/{definition['id']}/runs/{waiting['id']}/export")
    assert secret not in exported.text and "api_key" not in exported.text
    assert not workflows.store.data_profile("workflow-models:" + waiting["id"])


def test_restored_native_wait_is_quarantined_and_cannot_replay(client, monkeypatch):
    from sibyl.operations.recovery import prepare_recovery

    configure(
        client,
        monkeypatch,
        lambda *args: {"type": "tool_call", "tool": "ask_user", "args": {"question": "Which source?"}},
    )
    definition = create(client)
    waiting = wait(client, definition, start(client, definition))
    service = client.app.state.services.investigations
    prepare_recovery(service.repository.store, "restored-native-fixture")
    restored = client.get(f"/api/v1/investigations/{definition['id']}/runs/{waiting['id']}").json()
    assert restored["status"] == "interrupted" and "quarantined" in restored["error"]
    assert not service.repository.store.data_profile("workflow-models:" + waiting["id"])
    refused = client.post(
        f"/api/v1/investigations/{definition['id']}/runs/{waiting['id']}/resume", json={"kind": "continue"}
    )
    assert refused.status_code == 409


def test_uncertain_note_verification_reads_actual_matching_content_without_writing(client, monkeypatch):
    from sibyl.research_library.notes import ResearchNotes

    configure(
        client,
        monkeypatch,
        lambda *args: {
            "type": "tool_call",
            "tool": "save_research_note",
            "args": {"title": "Recovered note", "text": "Exact retained local AI draft."},
        },
    )
    definition = create(client)
    waiting = wait(client, definition, start(client, definition))
    service = client.app.state.services.investigations
    store = service.workflows.checkpoints
    record = store.get(waiting["native_run_id"])
    entry = next(iter(record.data["actions"].values()))
    action_id = entry["action"]["action_id"]
    # Public SDK fixture: simulate an admitted action without a committed return.
    token, record = store.acquire(record.run_id, record.agent_name, record.data)
    record.data["actions"][next(iter(record.data["actions"]))]["state"] = "uncertain"
    store.save(record.run_id, token, "uncertain", record.data)
    store.release(record.run_id, token)
    path = f"/api/v1/investigations/{definition['id']}/runs/{waiting['id']}/verify-note/{action_id}"
    not_found = client.post(path)
    assert not_found.status_code == 409 and "outcome remains unknown" in not_found.text
    library = client.app.state.services.library
    original = ResearchNotes(library).save("Recovered note", "Exact retained local AI draft.")
    monkeypatch.setattr(
        library, "import_document", lambda *args, **kwargs: pytest.fail("Verification replayed a write")
    )
    verified = client.post(path)
    assert verified.status_code == 200, verified.text
    assert verified.json()["workflow"]["uncertain_actions"] == []
    updated = store.get(waiting["native_run_id"])
    result = next(iter(updated.data["actions"].values()))["result"]
    assert result["document_id"] == original["document_id"]
    assert "original tool return was not retained" in result["note"]
