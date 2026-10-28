# Real-model agent acceptance

These opt-in checks exercise Sibyl's actual HTTP handlers, native ProtoLink agents, tool execution, discovery, sessions and reports against a running local Ollama model. They use a disposable workspace with Demo market/news data, no exchange accounts and both execution flags off. Socket connections are restricted to the selected loopback Ollama port. The ordinary test suite remains offline.

## Repeat the checks

With development dependencies installed and an existing model available:

```bash
uv run python scripts/check_agents.py \
  --model gemma4:e4b \
  --context-window 32768 \
  --output /tmp/sibyl-agent-acceptance.json
```

Use repeated `--case` options for `setup`, `history`, `news`, `market`, `sibyl`, `consultation`, `memory` or `stop`. The script never downloads a model, starts/stops Ollama, uses the main workspace or automatically retries a failed model question. Context size must fit the model and host memory.

The JSON receipt preserves questions, answers, actual tool evidence, native action records, available metrics, stream activity and explicit checks. Missing expected tools, paths or marker text produce a nonzero exit. These checks are narrow acceptance assertions, not an LLM judge or a general answer-quality score. Read the answers and compare their claims with the evidence. A completed HTTP request alone is insufficient.

## October 27, 2026 observations

Tested with **Ollama 0.40.6**, **gemma4:e4b** and **ProtoLink 0.8.3**. These observations establish this configuration's behavior for the recorded questions, not all providers, model sizes, prompts or languages.

| Check                            | Observed result                                                                                                                                                   |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Technician / Binance setup       | Called `exchange_setup`; after prioritizing setup guidance in the native preview, returned `/settings?tab=exchanges` correctly. Focused retest: about 20 seconds. |
| Broker / account history         | Called `trade_help` and returned the correct history destination. About 22 seconds.                                                                               |
| Reporter / available news        | Called `news_briefing`, identified the illustrative Demo source and did not claim current reporting. About 34 seconds.                                            |
| Analyst / ETH                    | Used ETH/USDT, 1d, 60 candles and Demo; reported Bearish consistently with the calculation and rejected probability-of-profit interpretation. About 32 seconds.   |
| Sibyl / Broker tool consultation | Native `agent.call` to Broker's `trade_help(history)` completed, retained the consultation and returned the correct page path. About 25 seconds.                  |
| Sibyl / reasoning consultation   | Native inference delegation to Broker completed; Broker used strategy help and Sibyl synthesized its response. About 83 seconds.                                  |
| Conversation memory              | Recalled a synthetic label in the same session; a fresh session did not know it.                                                                                  |
| Stop and responsiveness          | Stop accepted after real inference started; no saved answer after cancellation or restart. Health responded in about 8 ms during inference.                       |
| Persistence and boundaries       | Reports survived app restart; no exchange accounts or orders were created.                                                                                        |

Earlier checks deliberately remain part of the findings: Gemma invented links when the returned URL was outside the visible tool preview, and coordinator attempts called a specialist tool locally, omitted agents or requested an invalid context artifact. A later successful consultation does not establish reliable routing across arbitrary prompts. Broader repeated evaluation remains pending.

## Changes prompted by the checks

- Ollama uses ProtoLink's native `tool_calling="auto"`; capable models receive native tool declarations, while unknown/unsupported capabilities retain the SDK's conservative fallback.
- The former Ollama default requested 8,192 tokens while the native coordinator manifest contained about 15,000 estimated tokens. The provider profile now has an explicit context window, defaulting to 32,768, passed to both Ollama `num_ctx` and ProtoLink `configure_metrics(context_window=...)`. The native context policy protects input using the same ceiling. Generation is bounded to 2,048 tokens, matching the policy's output reservation.
- Settings exposes this under **Ollama → Advanced model settings**. The requested window must fit the chosen model and memory; saving it performs no inference. Undersized protected context returns clear HTTP 409 guidance, or a terminal 409 error frame after a stream starts.
- Technician puts setup paths, steps and credential guidance before the large exchange matrix. Native context previews keep useful instructions, while UI evidence retains the full result. No answer rewriting or custom tool wrapper is involved.
- Prompts require exact returned paths and distinguish local tools from specialist tools reached through native delegation. Models remain responsible for following them.
- Application error handling reads native `RunResult.error` as well as event errors; pre-inference context failures need not emit an `llm.call.failed` event.

## Remaining ProtoLink feedback

The [owned-agent usage metrics gap](protolink-metrics.md) remains. Two additional useful SDK improvements are a compact native discovery representation for small models and bounded correction for unavailable context-artifact IDs. Sibyl continues to use automatic discovery and the SDK's own context retrieval tool.

The following offline reproducer shows the artifact behavior on 0.8.3. A missing ID is a fatal `RuntimeError` wrapping `ValueError`, so the scripted recovery answer is never reached. An upstream improvement could classify invalid/evicted IDs as recoverable rejections under the existing correction budget. Do not override the SDK tool inside Sibyl.

```python
import asyncio
from uuid import uuid4
from protolink import Agent, AgentGroup, ContextPolicy, Task, create_llm

async def main():
    prefix = f"runtime://artifact-check-{uuid4().hex}"
    child = Agent(name="child", transport="runtime", url=f"{prefix}/child", verbosity=0)
    root = Agent(
        name="root", transport="runtime", url=f"{prefix}/root", verbosity=0,
        context_policy=ContextPolicy(), subagents=[child],
        llm_factory=lambda: create_llm("mock", sequential_responses=[
            {"type": "tool_call", "tool": "read_context_artifact",
             "args": {"artifact_id": "missing"}},
            "Recovered after the invalid ID",
        ]),
    )
    async with AgentGroup([root, child]) as group:
        handle = group.run(root, Task.create_infer("Use the available tool."))
        async for _ in handle.events():
            pass
        result = await handle.result()
        print(result.status, result.error)

asyncio.run(main())
```
