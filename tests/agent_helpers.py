"""Script provider I/O while keeping native ProtoLink discovery/delegation real."""

import asyncio
import json
import threading
from contextlib import contextmanager

from protolink import Task, create_llm, current_request_context

PRIMARY = {
    "oracle": "portfolio_snapshot",
    "accountant": "accountant_snapshot",
    "analyst": "market_analysis",
    "broker": "strategy_context",
    "chronos": "price_forecast",
    "reporter": "news_briefing",
    "technician": "connection_status",
    "wiki": "search_knowledge",
    "explorer": "bitcoin_lookup",
    "stocks": "equity_quote",
}


def delegate(agent_id, question, context=None):
    """A genuine SDK agent_call; structured prose here is only a deterministic model-test fixture."""
    name = f"sibyl-{agent_id}" if agent_id in PRIMARY else agent_id
    return {
        "type": "agent_call",
        "agent": name,
        "action": "infer",
        "prompt": json.dumps({"question": question, "selection": context or {}}),
    }


def coordinator_factory(monkeypatch, factory):
    """Script Sibyl; specialists ask for real tools using selections in the delegated prompt."""

    def build(*args, **kwargs):
        module = current_request_context().get("agent_id", "")
        if module == "sibyl":
            return factory(*args, **kwargs)

        def respond(history, prompt):
            if any(m.get("role") == "assistant" for m in history.messages):
                return "A specialist answer using observed data; demo/paper evidence is illustrative."
            query = next((m["content"] for m in reversed(history.messages) if m.get("role") == "user"), "")
            try:
                selection = json.loads(query).get("selection", {})
            except (ValueError, AttributeError):
                selection = {}
            arguments = {}
            if module in {"analyst", "broker", "chronos"}:
                arguments = {
                    key: value
                    for key, value in selection.items()
                    if key in {"symbol", "timeframe", "horizon", "job_id", "parameters"}
                }
                if module == "analyst" and selection.get("market_source"):
                    arguments["source"] = selection["market_source"]
            elif module == "reporter":
                arguments = {"mode": selection.get("news_mode", "demo")}
            elif module == "wiki":
                arguments = {"query": "RSI"}
            return {"type": "tool_call", "tool": PRIMARY[module], "args": arguments}

        return create_llm("mock", response_callback=respond)

    monkeypatch.setattr("sibyl.agents.utils.registry.create_llm", build)


@contextmanager
def busy_agents(client, monkeypatch):
    """Occupy native root slots with gated read-only tools, without contacting a model."""
    network = client.app.state.services.agents.network
    tool = network.agents["reporter"].tools["page_help"]
    original = tool.func
    entered = [threading.Event(), threading.Event()]
    release = threading.Event()
    lock = threading.Lock()
    calls = 0

    def hold(**_kwargs):
        nonlocal calls
        with lock:
            index = calls
            calls += 1
        entered[index].set()
        assert release.wait(timeout=10)
        return {"held": True}

    monkeypatch.setattr(tool, "func", hold)

    async def start():
        return [
            network.group.run(network.agents["reporter"], Task.create_tool_call("page_help"))
            for _ in entered
        ]

    handles = client.portal.call(start)
    try:
        assert all(event.wait(timeout=3) for event in entered)
        assert network.group.snapshot().active_runs == 2
        yield handles
    finally:
        release.set()

        async def finish():
            await asyncio.gather(*(handle.result() for handle in handles))

        client.portal.call(finish)
        monkeypatch.setattr(tool, "func", original)
