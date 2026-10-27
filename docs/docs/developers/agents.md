# ProtoLink agents

Sibyl uses `protolink[http]>=0.8.3,<0.9`, locked to 0.8.3. Every specialist has its own file, system prompt and ordinary typed tool functions. ProtoLink owns tool execution, request-local model instances, native delegation, session history, event correlation and run reports. There is no application tool wrapper or LLM subclass.

The migration follows the published [application-runtime guide](https://github.com/nMaroulis/protolink/blob/v0.8.3/docs/content/application-runtime.md) and [FastAPI example](https://github.com/nMaroulis/protolink/blob/v0.8.3/examples/application_runtime.py), checked against the installed PyPI package. The HTTP extra supplies the dependencies used by its HTTP model adapters, including `httpx2`.

## Files and responsibilities

| File | Responsibility |
| --- | --- |
| `<module>.py` | Specialist declaration, prompt and typed read-only functions |
| `sibyl.py` | Coordinator prompt; native delegation enabled |
| `guides/` | Curated page instructions retrieved through help tools |
| `common.py` | Domain service references, immutable snapshots and private page defaults |
| `registry.py` | Domain wiring, lazy model factory and UI reply projection |
| `network.py` | `AgentGroup`, admission, private scope, native handles and UI chat coordination |
| `presentation.py` | Format native events and `ToolEvidence` into consultation cards |
| `snapshots.py` | Deterministic factual formatting when no model is selected |
| `conversations.py`, `requests.py` | UI chat cards, queued-request IDs, progress and durable outcomes |

`background_tool`, `WorkspaceLLM`, the custom `Turn`/`ContextVar` and `ChatTelemetry` have been removed. UI records do not supply model conversation history or collect tool execution receipts.

## Ordinary tool declarations

Each module follows this pattern:

```python
from protolink import Agent
from sibyl.agents.common import COMMON_PROMPT, Services, selected


def create_agent(services: Services, **runtime) -> Agent:
    def news_briefing(asset: str | None = None) -> dict:
        """Find publisher excerpts mentioning an asset, with dates, links and sentiment.

        Omit asset to follow the News page filter. Use for actual reporting.
        """
        return services.research.news(
            asset=selected("news_asset", asset, ""), refresh=False, limit=8
        )

    agent = Agent(
        name="sibyl-reporter",
        description="Explain sourced crypto reporting.",
        tools=[news_briefing],
        system_prompt=COMMON_PROMPT + "Cite returned publishers and dates.",
        **runtime,
    )
    agent.card.capabilities.delegation = False
    return agent
```

`AgentNetwork.options()` supplies these native settings:

```python
{
    "llm_factory": lambda: owner.model_for(module),
    "sync_execution": "thread",
    "max_sync_workers": 4,
    "expose_tool_results": True,
    "state": native_state,
    "context_policy": ContextPolicy(preserve_recent=6),
}
```

ProtoLink infers schemas/descriptions from the original annotations and docstrings, validates and authorizes calls, then admits blocking functions to its worker pool. Async tools are awaited directly. No agent has order submission, cancellation, credential, shell, file or messaging tools. The model chooses domain reads; nothing preloads balances, prices or news just to answer a conceptual or navigation question.

## Readiness and native runs

All eleven agents register in a workspace-specific `protolink.discovery.Registry` with `runtime://` URLs. `AgentGroup` owns registry startup, registration readiness, partial-start rollback, native run cancellation and resource shutdown. Startup never constructs a provider through the model factory or runs inference.

The coordinator receives the same registered specialist objects through native `subagents=[...]`. ProtoLink merges owned specialists with registry discovery and supplies native `agent_call`; additional registry peers remain automatically discoverable. Only Sibyl has delegation enabled. There are no custom discovery/consultation tools or manually parsed model actions.

Browser requests use `group.run(agent, Task.create_infer(...))` or an explicit tool task. They address their specialist directly; page Ask does not pass through Sibyl. The resulting native handle supplies one event stream and a terminal `RunResult`. Independent `AgentClient` requests can still address every registered URL. No production path uses direct `Agent.invoke`.

Local owned execution is deliberate: ProtoLink clears private request dependencies across **every transport boundary, including `runtime://`**. A receiving specialist resolves current server model settings for an independent client request. It does not inherit the caller's credentials or page context. External discovered peers likewise do not receive the application's private team configuration.

## Frozen model and page dependencies

Before entering the shared two-request admission semaphore, the app reads the whole team's provider/model/key/endpoint settings and recursively freezes the nested mappings. Once admitted it binds:

```python
with request_context(
    {"models": frozen_team, "page": frozen_selection},
    inherit=("models", "page"),
):
    handle = group.run(agent, task)
```

Tools read page defaults through `current_request_context()`; explicit tool arguments take precedence. `Agent(llm_factory=...)` lazily constructs an independent real ProtoLink provider for that agent/task from the accepted snapshot. No shared `agent.llm` is mutated. Native provider tool protocols, streaming and usage metadata remain available; an application LLM adapter no longer forces the portable JSON protocol.

Only owned local specialists inherit the named private keys. Keys are never added to task metadata, model prompts, report configuration or conversations. Settings edits and key removal apply to later requests; an already accepted request retains its snapshot. Plain transported requests without an application scope resolve current settings independently. See [per-agent model contracts](agent-models.md).

Accountant's selected offline funding, transfer or performance view remains fixed: tool arguments cannot switch it into balance reads or another report/example selection. An explicit Wiki glossary query overrides a page-selected project.

## Sessions and reports

Native `State`/`SQLiteStorage` stores conversation histories in `agent-runtime.sqlite` under the configured data directory. Specialist session IDs partition the UI session by module and validated page selection. Sibyl uses a separate root session; native child conversations remain independent. The application no longer injects six prior UI replies into each prompt.

`ContextPolicy(preserve_recent=6)` applies ProtoLink's bounded-context policy. It preserves recent turns while pruning to the provider context ceiling (or SDK fallback); it is not a fixed six-turn history limit. Large model observations may be represented by native context artifacts. The SDK advertises its own `read_context_artifact` tool; Sibyl has no custom retrieval wrapper.

Each native handle writes its complete correlated report through `SQLiteRunStore`. Replies include `run_id`; `GET /api/v1/agents/runs/{run_id}` reads the persisted native report with `Cache-Control: no-store`, without running a model. Missing reports return 404. Reports retain native events, outcomes, tool evidence and available provider metrics. UI-facing `/runs?kind=agent` and saved chats remain presentation records, not a second source of execution evidence.

The handle/store use a request-specific `RedactionPolicy` including known configured provider keys. Private dependencies never enter serialized task envelopes. Reports and conversation histories can contain questions, financial observations and internal action JSON; these local SQLite files are not encrypted. Protect/back up the whole workspace. Deleting a Sibyl chat clears its root/retained child native sessions and native reports as well as its UI conversation. This is logical deletion, not secure erasure or deletion of backups.

## Events, evidence and cancellation

`RunPresentation` consumes `handle.events()` solely to format consultation/progress cards. Native child identifiers, delegation IDs and final answers drive the cards. `result.tool_evidence` / `handle.report.tool_evidence` supply validated arguments, actual returned values, timing and outcomes. Failed, rejected, canceled or omitted results are never presented as completed observations. The executing agents explicitly enable `expose_tool_results=True`; every tool must therefore return only data appropriate for the authorized workspace UI.

Native evidence retains the actual JSON-safe return before history hooks or context truncation. No function wrapper records evidence. Consultation envelopes are not counted as tool executions, and native deduplication prevents a forwarded live event plus final receipt becoming two observations.

The UI displays the root final answer, never raw `llm_chunk` fragments, which can contain action JSON. Its existing progress polling remains; this migration does not add token-by-token browser answers. Native reports make provider metrics available, but a usage/cost UI and real-model grounding evaluations remain pending.

An explicit UI Stop cancels the exact outer request; native `RunHandle.cancel()` propagates cancellation and the group owns drain/shutdown. Queued requests can stop before calling a provider. Completed consultation evidence remains visible on later failure or cancellation. UI answer commit and request completion remain one application transaction, preventing a late reply after Stop.

A running synchronous Python thread cannot be killed. Its native worker slot remains occupied until it returns, while canceled awaits finish promptly and late results are discarded. This does not undo side effects; all current tools are read-only. Only outer requests acquire application admission; child consultations use ProtoLink's native budget/supervision. Specialist tasks allow eight model steps/calls, six tool calls and 80 seconds; page requests wait up to 95 seconds. Sibyl's root budget allows twelve steps, ten model/tool calls and 140 seconds, within a 150-second outer request timeout.

## Domain tools

The SDK additionally advertises `read_context_artifact` for bounded model context.

| Agent | Sibyl-defined tools |
| --- | --- |
| Oracle | `portfolio_snapshot`, `page_help` |
| Accountant | `accountant_snapshot`, `account_history`, `risk_alerts`, `page_help` |
| Analyst | `market_analysis`, `analysis_help`, `page_help` |
| Broker | `strategy_context`, `strategy_guide`, `execution_controls`, `strategy_alerts`, `exchange_support`, `backtest_report`, `validation_report`, `exit_readiness`, `recorded_orders`, `trade_help`, `strategy_help` |
| Chronos | `price_forecast`, `forecast_method`, `page_help` |
| Reporter | `news_briefing`, `read_article`, `news_sources`, `fear_and_greed`, `page_help` |
| Technician | `connection_status`, `connection_alerts`, `settings_guide`, `exchange_setup` |
| Wiki | `search_knowledge`, `crypto_catalog`, `page_help` |
| Explorer | `bitcoin_blocks`, `blockchain_help`, `page_help` |
| Equity Analyst | `equity_quote`, `equity_help`, `page_help` |
| Sibyl | No custom tools; native discovery/delegation and SDK context retrieval |

Reporter reads the retained News archive and attributed index; publisher collection remains with News/background ingestion. Empty live sources stay empty. Broker's `recorded_orders` applies filters before its ten-order limit and returns at most ten fills for a selected record, retaining comparison totals and truncation flags. It never refreshes providers or changes tracking. Unknown/mismatched IDs use native `ToolRejectedError` for bounded correction.

## Help and tool-description contracts

Every specialist has a typed help tool: `page_help`, Broker's `trade_help` / `strategy_help`, or Technician's `settings_guide`. `Literal` choices become native enum schemas. `overview` lists topics; another topic returns one workflow, concrete steps, a destination and limitations. Instructions do not read keys/funds/providers or claim the user completed setup. How-to interpretation requires a model; no-model Tool snapshots retain deterministic evidence behavior.

Tool docstrings should lead with the question answered and information returned, explain meaningful arguments/defaults and known ID sources, and distinguish observations from instructions/methodology. Use native annotations and bounds; keep cache/worker mechanics in developer docs. Update the owning prompt and `guides/` records with each module change. Do not describe planned controls as implemented.

## Verification and remaining scope

`tests/test_application_runtime.py` exercises native lazy factories, immutable/transport-isolated context, frozen queued choices, correlated and untruncated reports, four-worker admission after cancellation, no late success, group shutdown, credential redaction, session restart and deletion. Existing agent/model/Stop tests keep the real native runtime and script only provider I/O.

No paid provider, actual exchange order or external message is used for these checks. Real-provider/sandbox acceptance, real-model routing/grounding evaluation, browser token streaming and usage/cost presentation remain separate work. Scheduled or resumable investigations are not enabled by this migration; saved request history is still an audit, not a scheduler.
