"""Actual native streaming with delayed adapters, plus adversarial display boundaries."""

import asyncio
import json
import threading

import pytest
from protolink import RedactionPolicy, create_llm, current_request_context
from protolink.core.events import RunEvent
from protolink.llms.actions import FinalAction, LLMActionResult

from sibyl.agents.utils.conversations import SibylRequest
from sibyl.agents.utils.streaming import AnswerStream, stream_reply
from sibyl.models import AgentRequest


def event(kind, content=None, *, task="root", **extra):
    return RunEvent(
        type="llm.stream",
        task_id=task,
        run_id="run",
        payload={"llm_event_type": kind, **({"content": content} if content is not None else {}), **extra},
    )


def collect(preview, fragments):
    frames = [frame for text in fragments if (frame := preview.consume(event("llm_chunk", text)))]
    text = ""
    for frame in frames:
        text = frame["text"] if frame["operation"] == "replace" else text + frame["text"]
    return text, frames


def test_json_actions_are_never_parsed_by_the_application():
    for action in (
        {"thought": "PRIVATE REASONING", "type": "final", "content": "Final answer"},
        {"type": "tool_call", "tool": "page_help", "args": {"content": "PRIVATE"}},
        {"type": "agent_call", "agent": "sibyl-reporter", "prompt": "PRIVATE"},
    ):
        preview = AnswerStream("root", RedactionPolicy())
        assert collect(preview, list(json.dumps(action))) == ("", [])
        assert preview.consume(event("llm_final", "Final answer"))["text"] == "Final answer"


@pytest.mark.parametrize("native", [False, True])
def test_children_reasoning_wrappers_and_repaired_json_wait_for_native_final(native):
    for text in (
        '<think>PRIVATE</think>{"type":"final","content":"Answer"}',
        '```json\n{"type":"final","content":"Answer"}\n```',
    ):
        preview = AnswerStream("root", RedactionPolicy())
        preview.native = native
        assert collect(preview, list(text)) == ("", [])
        assert preview.consume(event("llm_final", "PRIVATE", task="child")) is None
        assert preview.consume(event("llm_final", "Answer"))["text"] == "Answer"


def test_native_text_uses_public_content_and_is_replaced_after_tool_actions_or_parse_correction():
    preview = AnswerStream("root", RedactionPolicy())
    preview.native = True
    assert preview.consume(event("llm_chunk", "Checking the sources"))["text"] == "Checking the sources"
    assert preview.consume(event("llm_action", action="tool_call")) == {
        "type": "answer",
        "operation": "replace",
        "text": "",
    }
    assert preview.consume(event("llm_chunk", "A provisional answer"))
    assert preview.consume(event("llm_parse_error"))["operation"] == "replace"
    assert preview.consume(event("llm_final", "Corrected final answer"))["text"] == "Corrected final answer"


@pytest.mark.parametrize("secret", ["PRIVATE-KEY", "abcabc"])
def test_configured_credentials_are_masked_across_native_text_chunk_boundaries(secret):
    preview = AnswerStream("root", RedactionPolicy(sensitive_values=frozenset({secret})))
    preview.native = True
    text, frames = collect(preview, list("Result " + secret + " end"))
    assert text == "Result [REDACTED] end"
    assert secret not in json.dumps(frames)
    assert all(not frame["text"].endswith(secret[:4]) for frame in frames)


def test_preview_bound_still_accepts_the_native_final_and_no_plain_text_for_unknown_protocol():
    preview = AnswerStream("root", RedactionPolicy())
    assert preview.consume(event("llm_chunk", "PRIVATE TEXT")) is None
    assert preview.consume(event("llm_chunk", "x" * 130_000)) is None
    assert preview.consume(event("llm_final", "Native validated answer"))["text"] == "Native validated answer"


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("cancel", [False, True])
@pytest.mark.parametrize("module", ["chronos", "sibyl"])
def test_real_native_handle_yields_answer_before_generation_finishes_and_cancels_without_a_saved_success(
    client, monkeypatch, native, cancel, module
):
    owner = client.app.state.services.agents
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    entered, release = threading.Event(), threading.Event()
    answer = "## Forecast\n\nA **clear signal** with uncertainty. 🌍"

    def factory(*_a, **_kw):
        model = create_llm("mock", default_response=answer)

        async def chunks(_history):
            yield '{"thought":"PRIVATE","type":"final","content":"## Forecast\\n\\nA **clear'
            entered.set()
            while not release.is_set():
                await asyncio.sleep(0.01)
            yield ' signal** with uncertainty. 🌍"}'

        async def native_chunks(_history, *, chunk_callback, **_kwargs):
            await chunk_callback("## Forecast\n\nA **clear")
            entered.set()
            while not release.is_set():
                await asyncio.sleep(0.01)
            await chunk_callback(" signal** with uncertainty. 🌍")
            return LLMActionResult(FinalAction(content=answer), answer, native=True)

        if native:
            # A controlled native adapter; orchestration/events still belong to ProtoLink.
            monkeypatch.setattr(type(model), "uses_native_action_prompt", property(lambda _self: True))
            monkeypatch.setattr(model, "call_action_stream", native_chunks)
        else:
            monkeypatch.setattr(model, "call_stream", chunks)
        return model

    monkeypatch.setattr("sibyl.agents.utils.registry.create_llm", factory)

    session = client.post("/api/v1/sibyl/conversations").json()["id"] if module == "sibyl" else None

    def saved():
        if session:
            return client.get(f"/api/v1/sibyl/conversations/{session}").json()["turns"]
        return client.get("/api/v1/runs?kind=agent").json()

    async def start():
        if session:
            return stream_reply(
                lambda: owner.network.ask(SibylRequest(message="Explain", session_id=session))
            )
        return stream_reply(lambda: owner.ask(AgentRequest(module="chronos", message="Explain")))

    stream = client.portal.call(start)
    try:
        assert json.loads(client.portal.call(anext, stream))["status"] == "queued"
        assert entered.wait(timeout=2)
        if native:
            frame = json.loads(client.portal.call(anext, stream))
            assert frame["type"] == "answer" and frame["text"] == "## Forecast\n\nA **clear"
        else:
            frame = {"type": "status", "status": "queued"}
        assert client.get("/health").status_code == 200
        assert saved() == []
        if cancel:
            client.portal.call(stream.aclose)
            report = owner.network.run_store.get_report(
                owner.network.run_store.list_report_records()[0].run_id
            )
            assert report.final_task["state"] == "canceled"
        else:
            release.set()
            frames = []

            async def remaining():
                return [json.loads(row) async for row in stream]

            frames = client.portal.call(remaining)
            assert frames[-1]["type"] == "reply"
            assert frames[-1]["reply"]["answer"] == answer
            assert "PRIVATE" not in json.dumps([frame, *frames])
            assert len(saved()) == 1
    finally:
        release.set()
        client.portal.call(stream.aclose)
    if cancel:
        assert saved() == []


def test_owned_specialists_cannot_set_the_roots_protocol_or_stream_their_answer(client, monkeypatch):
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    factories = []

    def factory(*_a, **_kw):
        private = current_request_context()
        module = private["agent_id"]
        factories.append((module, bool(private.get("answer_stream"))))
        return create_llm(
            "mock",
            sequential_responses=[
                {"type": "agent_call", "agent": "sibyl-reporter", "action": "infer", "prompt": "Help"},
                "Root answer",
            ]
            if module == "sibyl"
            else ["Child answer stays in consultation"],
        )

    monkeypatch.setattr("sibyl.agents.utils.registry.create_llm", factory)
    frames = [
        json.loads(line)
        for line in client.post("/api/v1/sibyl/ask/stream", json={"message": "News"}).text.splitlines()
    ]
    assert frames[-1]["reply"]["answer"] == "Root answer"
    assert frames[-1]["reply"]["delegations"][0]["answer"] == "Child answer stays in consultation"
    assert ("sibyl", True) in factories and ("reporter", False) in factories
    assert "Child answer" not in json.dumps([frame for frame in frames if frame["type"] == "answer"])


def test_structured_investigation_answers_do_not_stream_as_chat_text(client, monkeypatch):
    from protolink import request_context

    owner = client.app.state.services.agents
    client.post("/api/v1/settings/llm", json={"provider": "mock"})
    monkeypatch.setattr(
        "sibyl.agents.utils.registry.create_llm",
        lambda *_a, **_kw: create_llm("mock", default_response='{"summary":"Report"}'),
    )

    async def invoke():
        with request_context(
            {
                "response_schema": {
                    "type": "object",
                    "properties": {"summary": {"type": "string"}},
                    "required": ["summary"],
                }
            }
        ):
            return await owner.network.ask(SibylRequest(message="Report"))

    async def run():
        return [json.loads(row) async for row in stream_reply(invoke)]

    frames = client.portal.call(run)
    assert frames[-1]["type"] == "reply"
    assert not any(frame["type"] == "answer" for frame in frames)
