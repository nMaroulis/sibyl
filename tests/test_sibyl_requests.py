"""Real ProtoLink request progress, cooperative Stop, and durable outcome contracts."""

import asyncio
import threading
from uuid import uuid4

import pytest
from agent_helpers import coordinator_factory, delegate
from fastapi.testclient import TestClient
from protolink import create_llm
from pydantic import SecretStr

from sibyl.agents.conversations import SibylRequest
from sibyl.api.app import create_app


def prepare(client):
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    session = client.post("/api/v1/sibyl/conversations").json()["id"]
    return (client.app.state.services.agents.network, session)


def tool(name, **args):
    return {"type": "tool_call", "tool": name, "args": args}


def test_completed_requests_share_answer_commit_and_survive_restart(client, settings, monkeypatch):
    network, session = prepare(client)
    coordinator_factory(
        monkeypatch,
        lambda *a, **kw: create_llm(
            "mock", sequential_responses=[delegate("wiki", "Explain RSI"), "A simulated answer."]
        ),
    )
    request_id = uuid4().hex
    reply = client.post(
        "/api/v1/sibyl/ask", json={"session_id": session, "request_id": request_id, "message": "Explain RSI"}
    )
    assert reply.status_code == 200, reply.text
    activity = client.get(f"/api/v1/sibyl/conversations/{session}/activity").json()
    assert activity["status"] == "completed" and activity["id"] == request_id
    assert activity["reply_id"] == reply.json()["id"]
    assert "answer" not in activity["delegations"][0] and "evidence" not in activity["delegations"][0]
    detail = client.get(f"/api/v1/sibyl/conversations/{session}/requests/{request_id}").json()
    assert detail["delegations"] == reply.json()["delegations"]
    assert detail["delegations"][0]["started_at"] <= detail["delegations"][0]["finished_at"]
    assert (
        client.post(
            f"/api/v1/sibyl/conversations/{session}/cancel", json={"request_id": request_id}
        ).status_code
        == 409
    )
    with TestClient(create_app(settings)) as restarted:
        assert (
            restarted.get(f"/api/v1/sibyl/conversations/{session}/activity").json()["status"] == "completed"
        )
        assert len(restarted.get(f"/api/v1/sibyl/conversations/{session}").json()["turns"]) == 1
        assert restarted.delete(f"/api/v1/sibyl/conversations/{session}").status_code == 204
        with restarted.app.state.services.store.db() as db:
            assert (
                db.execute("SELECT COUNT(*) FROM sibyl_requests WHERE session_id=?", (session,)).fetchone()[0]
                == 0
            )


def test_failed_request_is_retained_without_private_adapter_error(client, monkeypatch):
    _, session = prepare(client)

    def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE-PROVIDER-SECRET")

    coordinator_factory(monkeypatch, fail)
    response = client.post("/api/v1/sibyl/ask", json={"session_id": session, "message": "Hello"})
    assert response.status_code == 502
    history = client.get(f"/api/v1/sibyl/conversations/{session}/requests")
    assert history.json()[0]["status"] == "failed" and "SECRET" not in history.text
    assert client.get(f"/api/v1/sibyl/conversations/{session}").json()["turns"] == []


def test_stop_returns_while_provider_is_blocked_and_prevents_late_consultation(client, monkeypatch):
    network, session = prepare(client)
    started, release, finished = (threading.Event(), threading.Event(), threading.Event())
    calls, run = ([], network.group.run)

    def capture(agent, task, **kwargs):
        calls.append(agent.card.url)
        return run(agent, task, **kwargs)

    monkeypatch.setattr(network.group, "run", capture)

    def factory(*args, **kwargs):

        def answer(history, prompt):
            started.set()
            release.wait(timeout=5)
            finished.set()
            return delegate("wiki", "A late consultation must not run")

        return create_llm("mock", response_callback=answer)

    coordinator_factory(monkeypatch, factory)
    request_id = uuid4().hex
    future = client.portal.start_task_soon(
        network.ask, SibylRequest(session_id=session, request_id=request_id, message="A slow question")
    )
    try:
        assert started.wait(timeout=2)
        activity = client.get(f"/api/v1/sibyl/conversations/{session}/activity").json()
        assert activity["id"] == request_id and activity["status"] == "running"
        stopped = client.post(
            f"/api/v1/sibyl/conversations/{session}/cancel", json={"request_id": request_id}
        )
        assert stopped.status_code == 202, stopped.text
        result = future.result(timeout=2)
        assert result["status"] == "cancelled"
        assert not network._active_requests and (not network._chat_locks)
        assert client.get(f"/api/v1/sibyl/conversations/{session}").json()["turns"] == []
        assert (
            client.post(
                f"/api/v1/sibyl/conversations/{session}/cancel", json={"request_id": request_id}
            ).status_code
            == 202
        )
    finally:
        release.set()
    assert finished.wait(timeout=2)
    assert calls == [network.cards["sibyl"].url]
    assert client.get("/api/v1/runs?kind=agent").json() == []
    assert client.get(f"/api/v1/sibyl/conversations/{session}/activity").json()["status"] == "cancelled"


def test_progress_and_stop_preserve_completed_evidence_and_cancel_active_specialist(client, monkeypatch):
    network, session = prepare(client)
    started, release = threading.Event(), threading.Event()
    read = network.owner.services.market.candles

    def blocked(*args, **kwargs):
        started.set()
        release.wait(timeout=4)
        return read(*args, **kwargs)

    monkeypatch.setattr(network.owner.services.market, "candles", blocked)
    coordinator_factory(
        monkeypatch,
        lambda *a, **kw: create_llm(
            "mock",
            sequential_responses=[
                delegate("wiki", "Explain RSI"),
                delegate("analyst", "Observe ETH", context={"symbol": "ETH/USDT"}),
                "This answer should not be committed.",
            ],
        ),
    )
    request_id = uuid4().hex
    future = client.portal.start_task_soon(
        network.ask, SibylRequest(session_id=session, request_id=request_id, message="Compare observations")
    )
    assert started.wait(timeout=2)
    progress = client.get(f"/api/v1/sibyl/conversations/{session}/activity").json()
    assert progress["phase"] == "consulting"
    assert [entry["status"] for entry in progress["delegations"]] == ["completed", "running"]
    assert "evidence" not in progress["delegations"][0]
    stop = client.post(f"/api/v1/sibyl/conversations/{session}/cancel", json={"request_id": request_id})
    assert stop.status_code == 202
    assert future.result(timeout=2)["status"] == "cancelled"
    release.set()
    detail = client.get(f"/api/v1/sibyl/conversations/{session}/requests/{request_id}").json()
    assert detail["status"] == "cancelled"
    assert [entry["status"] for entry in detail["delegations"]] == ["completed", "cancelled"]
    assert detail["delegations"][0]["answer"] and detail["delegations"][0]["evidence"]
    assert client.get(f"/api/v1/sibyl/conversations/{session}").json()["turns"] == []


def test_a_stale_cancel_cannot_stop_a_new_request_or_another_conversation(client, monkeypatch):
    network, session = prepare(client)
    first = client.post("/api/v1/sibyl/ask", json={"session_id": session, "message": "First"}).json()
    other = network.conversations.create()["id"]
    started, release = (asyncio.Event(), asyncio.Event())

    async def waiting(request, configuration):
        started.set()
        await release.wait()
        return {"done": True}

    monkeypatch.setattr(network, "_answer_sibyl", waiting)
    request_id = uuid4().hex
    future = client.portal.start_task_soon(
        network.ask, SibylRequest(session_id=session, request_id=request_id, message="Second")
    )
    try:
        client.portal.call(started.wait)
        assert (
            client.post(
                f"/api/v1/sibyl/conversations/{session}/cancel", json={"request_id": first["request_id"]}
            ).status_code
            == 409
        )
        assert (
            client.post(
                f"/api/v1/sibyl/conversations/{other}/cancel", json={"request_id": request_id}
            ).status_code
            == 404
        )
        assert client.get(f"/api/v1/sibyl/conversations/{session}").json()["pending"]
    finally:
        client.portal.call(release.set)
        future.result(timeout=3)


def test_queued_requests_can_be_stopped_without_a_model_call(client, monkeypatch):
    network, session = prepare(client)
    coordinator_factory(monkeypatch, lambda *a, **kw: pytest.fail("Queued model was called"))
    client.portal.call(network.owner._semaphore.acquire)
    client.portal.call(network.owner._semaphore.acquire)
    request_id = uuid4().hex
    future = client.portal.start_task_soon(
        network.ask, SibylRequest(session_id=session, request_id=request_id, message="Wait for a slot")
    )
    try:
        queued = client.get(f"/api/v1/sibyl/conversations/{session}/activity").json()
        assert queued["status"] == "queued"
        assert (
            client.post(
                f"/api/v1/sibyl/conversations/{session}/cancel", json={"request_id": request_id}
            ).status_code
            == 202
        )
        assert future.result(timeout=2)["status"] == "cancelled"
    finally:
        client.portal.call(network.owner._semaphore.release)
        client.portal.call(network.owner._semaphore.release)
    assert not network._chat_locks


def test_restart_interrupts_unfinished_requests_without_replay(client, settings, monkeypatch):
    network, session = prepare(client)
    record = network.requests.start(session, "Do not replay this", "mock", "", None)
    network.requests.update(
        record["id"],
        status="running",
        phase="consulting",
        delegations=[
            {"name": "Wiki", "status": "completed", "evidence": {"observed": True}, "answer": "Already read"},
            {"name": "Analyst", "status": "running"},
        ],
    )
    coordinator_factory(monkeypatch, lambda *a, **kw: pytest.fail("Unexpected replay"))
    with TestClient(create_app(settings)) as restarted:
        detail = restarted.get(f"/api/v1/sibyl/conversations/{session}/requests/{record['id']}").json()
        assert detail["status"] == "interrupted"
        assert [entry["status"] for entry in detail["delegations"]] == ["completed", "interrupted"]
        assert detail["delegations"][0]["evidence"] == {"observed": True}
        assert not restarted.get(f"/api/v1/sibyl/conversations/{session}").json()["pending"]
        assert restarted.get(f"/api/v1/sibyl/conversations/{session}").json()["turns"] == []


def test_a_committed_answer_wins_over_a_late_stop(client, monkeypatch):
    network, session = prepare(client)
    committed, release = (asyncio.Event(), asyncio.Event())
    original = network._answer_sibyl

    async def delayed(request, configuration):
        result = await original(request, configuration)
        committed.set()
        await release.wait()
        return result

    monkeypatch.setattr(network, "_answer_sibyl", delayed)
    request_id = uuid4().hex
    future = client.portal.start_task_soon(
        network.ask, SibylRequest(session_id=session, request_id=request_id, message="An answer wins")
    )
    try:
        client.portal.call(committed.wait)
        assert client.get(f"/api/v1/sibyl/conversations/{session}/activity").json()["status"] == "completed"
        assert (
            client.post(
                f"/api/v1/sibyl/conversations/{session}/cancel", json={"request_id": request_id}
            ).status_code
            == 409
        )
        assert len(client.get(f"/api/v1/sibyl/conversations/{session}").json()["turns"]) == 1
    finally:
        client.portal.call(release.set)
        future.result(timeout=3)


def test_duplicate_request_id_cannot_submit_twice(client):
    network, session = prepare(client)
    payload = {"session_id": session, "request_id": uuid4().hex, "message": "One request"}
    assert client.post("/api/v1/sibyl/ask", json=payload).status_code == 200
    assert client.post("/api/v1/sibyl/ask", json=payload).status_code == 409
    assert len(network.conversations.get(session)["turns"]) == 1


@pytest.mark.parametrize("request_id", ["", "not-an-id", "a" * 33])
def test_cancel_ids_are_validated_before_dispatch(client, request_id):
    _, session = prepare(client)
    assert (
        client.post(
            f"/api/v1/sibyl/conversations/{session}/cancel", json={"request_id": request_id}
        ).status_code
        == 422
    )


def test_progress_history_and_stop_require_workspace_auth(settings):
    settings.api_token = SecretStr("local-token")
    with TestClient(create_app(settings)) as protected:
        prefix = "/api/v1/sibyl/conversations/" + "a" * 32
        for suffix in ("/activity", "/requests", "/requests/" + "b" * 32):
            assert protected.get(prefix + suffix).status_code == 401
        assert protected.post(prefix + "/cancel", json={"request_id": "b" * 32}).status_code == 401


def test_progress_is_bounded_and_never_loads_full_conversation_evidence(client, monkeypatch):
    network, session = prepare(client)
    assert client.get(f"/api/v1/sibyl/conversations/{session}/activity").json() is None
    for index in range(22):
        record = network.requests.start(session, f"Attempt {index}", "mock", "", None)
        network.requests.finish(record["id"], "failed")
    assert network.conversations.list()[0]["title"] == "Attempt 0"
    monkeypatch.setattr(network.conversations, "get", lambda *_: pytest.fail("Loaded all chat evidence"))
    prefix = f"/api/v1/sibyl/conversations/{session}"
    history = client.get(prefix + "/requests")
    assert len(history.json()) == 20
    assert history.json()[0]["question"] == "Attempt 21"
    for path in ("/activity", "/requests", f"/requests/{record['id']}"):
        response = client.get(prefix + path)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"


def test_roadmap_tracks_sibyl_separately_and_keeps_hosting_deferred(client):
    roadmap = client.get("/api/v1/roadmap").json()
    areas = {area["id"]: area for area in roadmap["areas"]}
    assert areas["sibyl"]["status"] == "partial"
    assert "Stop" in areas["sibyl"]["working"]
    assert any("unavailable" in item for item in areas["sibyl"]["pending"])
    assert areas["multi-user"]["status"] == areas["multi-user"]["priority"] == "deferred"
