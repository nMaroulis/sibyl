# ProtoLink 0.8.3 owned-agent metrics

Verified against the installed PyPI release `protolink==0.8.3`. This is an upstream limitation, not an application token estimate.

A root with owned subagents uses the SDK's managed unary execution path. Its native `llm.call.completed` event retains provider, model and latency metadata but has `metrics: null`. Direct specialist streaming supplies usage metrics. The same difference occurs before making any consultation: adding an owned child is sufficient. Enabling the LLM's metrics flag does not override the unary engine's explicit `event_metrics=False` selection.

## Minimal offline reproducer

Run with Python 3.12 and ProtoLink 0.8.3. The Mock provider performs no network requests, requires no credentials and incurs no provider charge.

```python
import asyncio
from uuid import uuid4
from protolink import Agent, AgentGroup, Task, create_llm


async def check(owned):
    prefix = f"runtime://metrics-{uuid4().hex}"
    child = Agent(name="child", transport="runtime", url=f"{prefix}/child", verbosity=0)
    root = Agent(
        name="root", transport="runtime", url=f"{prefix}/root", verbosity=0,
        llm_factory=lambda: create_llm("mock", default_response="Hello"),
        subagents=[child] if owned else [],
    )
    group = AgentGroup([root, child])
    await group.start()
    try:
        handle = group.run(root, Task.create_infer("Say hello"))
        async for _ in handle.events():
            pass
        assert (await handle.result()).status == "completed"
        calls = [e for e in handle.report.events if e.type == "llm.call.completed"]
        print("owned=", owned, "metrics=", calls[0].payload["metadata"]["metrics"])
    finally:
        await group.close()


async def main():
    await check(False)
    await check(True)

asyncio.run(main())
```

Expected observation on 0.8.3:

```text
owned= False metrics= {'usage': {..., 'estimated': True, 'source': 'estimate'}, ...}
owned= True metrics= None
```

In `protolink/agents/engine.py`, `run_task_streaming` takes the managed `run_task` branch for owned subagents; `_run_infer` enables event metrics only for `self.telemetry or event_callback`. That branch has no direct event callback despite having a native run event sink. An upstream fix should preserve native metrics through this path, including inferred owned-child calls, without requiring application telemetry or synthetic usage.

Sibyl displays missing usage/cost as **unavailable** and retains the native call timing/model attribution. It does not mutate the SDK, attach dummy telemetry, estimate tokens itself or treat missing prices as zero. `tests/test_agent_streaming.py` checks this behavior. Update that acceptance expectation when a verified SDK release supplies the metrics.
