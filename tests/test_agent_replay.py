"""Read-only native subscriptions, lifecycle bounds and authoritative saved answers."""

import json

from agent_helpers import busy_agents
from protolink import AgentHooks, Task, create_llm
from protolink.llms.actions import FinalAction, LLMActionResult

from sibyl.agents.utils.streaming import retained_run


def frames(response):
    assert response.status_code == 200, response.text
    return [json.loads(line) for line in response.text.splitlines()]


def test_retained_run_replays_native_cursors_without_repeating_execution(client, monkeypatch):
    calls = []
    client.post("/api/v1/settings/llm", json={"provider": "mock"})

    def factory(*_args, **_kwargs):
        calls.append(True)
        return create_llm("mock", default_response="## Answer\n\n**Observed** 🌍")

    monkeypatch.setattr("sibyl.agents.utils.registry.create_llm", factory)
    reply = client.post("/api/v1/agents/ask", json={"module": "wiki", "message": "Explain"}).json()
    path = f"/api/v1/agents/runs/{reply['run_id']}/stream"
    first = frames(client.get(path))
    assert first[-1] == {"type": "result", "status": "completed"}
    answers = [row["update"] for row in first if row["type"] == "answer"]
    assert answers[-1]["type"] == "completed" and answers[-1]["content"] == reply["answer"]
    activities = [row["update"] for row in first if row["type"] == "activity"]
    assert all("payload" not in row and "arguments" not in row for row in activities)
    after = max(row["sequence"] for row in activities)
    answer_after = answers[-1]["sequence"]
    assert frames(client.get(path, params={"after": after, "answer_after": answer_after})) == [first[-1]]
    assert calls == [True]
    assert client.get(path).headers["Cache-Control"] == "no-store"
    assert client.get(path, params={"after": -1}).status_code == 422
    invalid = frames(client.get(path, params={"answer_after": answer_after + 1}))
    assert invalid[-1]["type"] == "error" and invalid[-1]["status"] == 400


def test_native_buffer_gaps_are_explicit_and_do_not_submit_new_work(client, monkeypatch):
    network = client.app.state.services.agents.network
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    calls = []

    def factory(*_args, **_kwargs):
        calls.append(True)
        return create_llm("mock", default_response="Safe answer")

    monkeypatch.setattr("sibyl.agents.utils.registry.create_llm", factory)

    async def start():
        handle = network.group.run(
            network.agents["wiki"], Task.create_infer("Hello"), store=network.run_store, event_buffer_size=1
        )
        await handle.result()
        return handle.context.run_id

    run_id = client.portal.call(start)
    replay = frames(client.get(f"/api/v1/agents/runs/{run_id}/stream"))
    assert replay[-1]["type"] == "gap"
    assert replay[-1]["first_available"] > 1
    assert calls == [True]


def test_a_secondary_viewer_disconnect_does_not_cancel_the_observed_native_run(client, monkeypatch):
    with busy_agents(client, monkeypatch) as handles:
        handle = handles[0]

        async def observe():
            return retained_run(handle)

        stream = client.portal.call(observe)
        row = json.loads(client.portal.call(anext, stream))
        assert row["type"] == "activity"
        client.portal.call(stream.aclose)
        assert not handle.task.is_terminal
        assert client.app.state.services.agents.network.group.snapshot().active_runs == 2
    assert client.portal.call(handle.result).status == "completed"


def test_native_queue_bounds_are_visible_and_full_requests_return_503(client, monkeypatch):
    owner = client.app.state.services.agents
    monkeypatch.setattr(
        "sibyl.agents.utils.registry.create_llm",
        lambda *_a, **_kw: (_ for _ in ()).throw(AssertionError("No provider needed")),
    )
    with busy_agents(client, monkeypatch):

        async def fill():
            return [
                owner.network.group.run(
                    owner.network.agents["reporter"], Task.create_tool_call("news_briefing")
                )
                for _ in range(16)
            ]

        waiting = client.portal.call(fill)
        try:
            state = client.get("/api/v1/system").json()["agent_runtime"]
            assert state["active_runs"] == 2 and state["queued_runs"] == 16
            response = client.post("/api/v1/agents/ask", json={"module": "wiki", "message": "Hello"})
            assert response.status_code == 503 and "queue is full" in response.json()["detail"]
            assert client.get("/health").status_code == 200
        finally:

            async def cancel():
                for handle in waiting:
                    await handle.cancel()
                    assert (await handle.result()).status == "canceled"

            client.portal.call(cancel)


def test_sdk_idempotency_reuses_the_accepted_handle_within_the_retention_window(client, monkeypatch):
    network = client.app.state.services.agents.network
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    calls = []

    def factory(*_args, **_kwargs):
        calls.append(True)
        return create_llm("mock", default_response="One run")

    monkeypatch.setattr("sibyl.agents.utils.registry.create_llm", factory)

    async def run():
        agent = network.agents["wiki"]
        first = network.group.run(agent, Task.create_infer("Same input"), request_id="workspace:example")
        second = network.group.run(agent, Task.create_infer("Same input"), request_id="workspace:example")
        assert first is second
        assert (await first.result()).status == "completed"
        assert network.group.get_run(first.context.run_id) is first

    client.portal.call(run)
    assert calls == [True]


def test_saved_answers_use_sdk_authoritative_text_after_hooks_without_private_reasoning(client, monkeypatch):
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    owner = client.app.state.services.agents
    raw = "<think>PRIVATE REASONING</think>## Visible\n\n**Markdown**"

    def factory(*_args, **_kwargs):
        model = create_llm("mock")

        async def native_stream(_history, *, chunk_callback, **_kwargs):
            for text in ("<think>PRIVATE REASONING</think>", "## Visible\n\n**Markdown**"):
                await chunk_callback(text)
            return LLMActionResult(FinalAction(content=raw), raw, native=True)

        monkeypatch.setattr(model, "call_action_stream", native_stream)
        return model

    monkeypatch.setattr("sibyl.agents.utils.registry.create_llm", factory)

    def finish(reply):
        reply.content = "Validated:\n\n" + reply.content

    monkeypatch.setattr(owner.agents["wiki"], "hooks", (AgentHooks(before_complete=finish),))
    response = client.post("/api/v1/agents/ask/stream", json={"module": "wiki", "message": "Hello"})
    updates = frames(response)
    reply = updates[-1]["reply"]
    assert reply["answer"] == "Validated:\n\n## Visible\n\n**Markdown**"
    assert "PRIVATE" not in response.text
    saved = client.get("/api/v1/runs?kind=agent").json()[0]
    assert saved["payload"]["answer"] == reply["answer"]


def test_deleted_chat_is_not_replayable_from_a_retained_handle(client, monkeypatch):
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    monkeypatch.setattr(
        "sibyl.agents.utils.registry.create_llm",
        lambda *_a, **_kw: create_llm("mock", default_response="Deleted answer"),
    )
    reply = client.post("/api/v1/sibyl/ask", json={"message": "Hello"}).json()
    path = f"/api/v1/agents/runs/{reply['run_id']}/stream"
    assert client.get(path).status_code == 200
    assert client.delete(f"/api/v1/sibyl/conversations/{reply['session_id']}").status_code == 204
    assert client.get(path).status_code == 404
