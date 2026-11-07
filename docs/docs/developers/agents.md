---
title: ProtoLink agents
hide_title: true
---

import { DocHero, DocCards } from '@site/src/components/DocBlocks';

<DocHero title="ProtoLink agents" eyebrow="Developers · ProtoLink" icon="spark" facts={["One file per agent", "Typed tools", "Request-local models"]}>

Sibyl uses `protolink[http]>=0.8.4,<0.9`, locked to 0.8.4. Every specialist has its own file, system prompt and ordinary typed tool functions. ProtoLink owns tool execution, request-local model instances, native delegation, session history, event correlation and run reports. There is no application tool wrapper or LLM subclass.

</DocHero>

<DocCards
  items={[
    {
      title: 'Agent definitions',
      text: 'Prompts and tools stay with each specialist.',
      icon: 'code',
      to: '#ordinary-tool-declarations',
    },
    {
      title: 'Model choices',
      text: 'Workspace defaults and per-agent overrides.',
      icon: 'spark',
      to: '/developers/agent-models',
    },
    {
      title: 'Acceptance checks',
      text: 'Inspect evaluated runtime behavior and limits.',
      icon: 'shield',
      to: '/developers/agent-acceptance',
    },
  ]}
/>

The migration uses [ProtoLink 0.8.4](https://pypi.org/project/protolink/0.8.4/) and its native [runtime APIs](https://nmaroulis.github.io/protolink/docs/runtime/), checked against the installed source and the published SDK's streaming example. The HTTP extra supplies the dependencies used by its HTTP model adapters, including `httpx2`.

## Files and responsibilities

Paths below are relative to `src/sibyl/agents/`. The top-level Python files declare
the agents. Shared runtime/model code lives in `utils/`, and page-help content stays
in `guides/`.

| File                                             | Responsibility                                                                  |
| ------------------------------------------------ | ------------------------------------------------------------------------------- |
| `<module>.py`                                    | Specialist declaration, prompt and typed read-only functions                    |
| `sibyl.py`                                       | Coordinator prompt; native delegation enabled                                   |
| `guides/`                                        | Curated page instructions retrieved through help tools                          |
| `utils/common.py`                                | Domain service references, immutable snapshots and private page defaults        |
| `utils/registry.py`                              | Domain wiring, lazy model factory and UI reply projection                       |
| `utils/network.py`                               | `AgentGroup`, admission, private scope, native handles and UI chat coordination |
| `utils/model_selection.py`, `utils/providers.py` | Model assignments, provider catalog and passive readiness                       |
| `utils/presentation.py`                          | Format native events and `ToolEvidence` into consultation cards                 |
| `utils/reporting.py`, `utils/streaming.py`       | Public run summaries and streaming response formatting                          |
| `utils/retrieval.py`                             | Shared native Wiki/Reporter research tools, schemas and source-evidence reads     |
| `utils/snapshots.py`                             | Deterministic factual formatting when no model is selected                      |
| `utils/conversations.py`, `utils/requests.py`    | UI chat cards, queued-request IDs, progress and durable outcomes                |

`background_tool`, `WorkspaceLLM`, the custom `Turn`/`ContextVar` and `ChatTelemetry` have been removed. UI records do not supply model conversation history or collect tool execution receipts.

## Ordinary tool declarations

Each module follows this pattern:

```python
from protolink import Agent
from sibyl.agents.utils.common import COMMON_PROMPT, Services, selected


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

## Per-tool execution and reusable tools

Agent factories return unstarted native `Agent` objects; `AgentGroup` supplies lifecycle and runtime options. Domain reads inherit `sync_execution="thread"` and four bounded workers. Static guides and methodology use native `Tool.from_callable(..., sync_execution="inline")`, so they do not consume those workers. Inline tools still obey validation, policy and applicable group admission; they must remain short and free of blocking I/O. New database, provider or computational work should use the default worker policy.

Wiki and Reporter register the same five research capabilities from `utils/retrieval.py` through `research_tools(library)`. These are ordinary typed functions adapted by native `Tool.from_callable`, with original names/docstrings and private page defaults. There is no callable decorator wrapper or second dispatcher. Each specialist still owns its prompt and module-specific tools. A shared definition keeps research citations, corrections and schemas consistent between them.

`Annotated`/Pydantic `Field` bounds describe research query lengths, result limits, document offsets and accounting flow pagination. ProtoLink validates explicit arguments before domain execution and supplies its native inference correction loop. Dynamic selections and unavailable retained records remain domain checks using `ToolRejectedError`; operational failures retain their ordinary failure behavior. For retrieval evaluations, omitting `evaluation_id` follows the page while `evaluation_id=''` lists reports, allowing a missing selection to be corrected without inventing another report.

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

`RunPresentation` consumes `handle.events()` solely to format saved consultation cards. Native `PresentationEvent` supplies lifecycle classification; child final text and questions remain application display policy. Cards update only on meaningful changes, so raw model chunks do not produce SQLite writes. Native child identifiers, delegation IDs and final answers drive the cards. `result.tool_evidence` / `handle.report.tool_evidence` supply validated arguments, actual returned values, timing and outcomes. Failed, rejected, canceled or omitted results are never presented as completed observations. The executing agents explicitly enable `expose_tool_results=True`; every tool must therefore return only data appropriate for the authorized workspace UI.

Native evidence retains the actual JSON-safe return before history hooks or context truncation. No function wrapper records evidence. Consultation envelopes are not counted as tool executions, and native deduplication prevents a forwarded live event plus final receipt becoming two observations.

The browser consumes `POST /agents/ask/stream` and `POST /sibyl/ask/stream` as NDJSON. `streaming.py` forwards `handle.answer_events()` and `handle.presentation_events()` through a bounded HTTP bridge. Their typed dictionaries are carried unchanged in `answer`/`activity` frames. There is no application answer projector, raw-event classifier, model-protocol flag or model wrapper. Native answer events support JSON-mode and native-provider streaming, preserve Markdown/Unicode, exclude thoughts, action envelopes and child answers, and apply cross-chunk redaction. Structured investigations suppress answer frames; their validated reports keep their own application rendering.

`delta` appends content; `replacement` replaces it. Native `completed` contains authoritative text after successful execution; it is distinct from Sibyl's final `reply`, which confirms the application chat record was saved. JSON endpoints and saved replies also use that same native authoritative text. The browser batches token bursts per animation frame and uses the existing safe Markdown renderer for provisional and final text. HTML is excluded and generated images are not fetched.

**Run details** reads `GET /agents/runs/{run_id}/summary`. The SDK's `RunReport.from_events()` pairs historical/dedicated call receipts, and `report.usage(scope="tree" | "root" | "children")` supplies deduplicated rollups. Provider-reported, estimated and unknown calls remain separate; costs keep their currencies and estimation flags. Sibyl formats these results and defensively checks displayed numbers. It does not estimate tokens, maintain a pricing table or recalculate aggregates. The old owned-agent metrics omission is resolved; see [native usage contracts](protolink-metrics.md).

## Admission, retained subscriptions and identity

`AgentGroup` uses `GroupLimits(max_concurrent_runs=2, max_queued_runs=16, queue_timeout=30)`. The SDK owns FIFO root admission and queued cancellation; consultations share their parent's slot. Sibyl no longer has an admission semaphore. Frozen model/page snapshots are bound before group submission, and queued work never constructs a provider. The SDK's admission events set the UI's actual queued/running phase. Full or expired queues produce a sanitized HTTP 503 (or streamed error). Overall request deadlines remain 95 seconds for a specialist and 150 seconds for Sibyl, including queue time.

Group registration readiness and active/queued/retained root counts come from `group.snapshot()`, exposed in `/system` as `agent_runtime` and `/sibyl` as `runtime`. They are not provider availability probes or Python-thread occupancy measurements. The group retains at most 20 completed handles; active runs are not evicted. Each raw event replay window is bounded to 4,096 events; complete persisted reports remain available separately.

Sibyl passes a conversation-scoped request ID to `group.run()`. Native reuse is limited to retained identical submissions in that group. Private dependencies are not part of the SDK fingerprint. Sibyl keeps its own durable conversation/request guards and one-pending-turn rule; replaying an HTTP Ask does not bypass them. This is not exactly-once external execution or cross-process idempotency.

`GET /agents/runs/{run_id}/stream?after=0&answer_after=0` observes `group.get_run(run_id)` without submitting work. It forwards native presentation and answer updates, then a native `result` status. `after` is the raw-event sequence used by presentation events; `answer_after` is an independent answer sequence. Retention gaps are explicit frames. Unknown, evicted or deleted runs return 404. A viewer disconnect stops only its subscriptions; it does not cancel the execution. This endpoint does not make initiating Ask requests survive disconnects, persist partial browser text, recover a run after process restart, or replace saved conversation APIs. Structured report JSON is excluded from answer replay.

An explicit Sibyl Stop cancels the exact outer request; specialist Stop aborts its stream, and disconnect cancellation drains the producer and its native handle. Closing a module dialog preserves its ongoing request. Navigating away from the Sibyl page aborts its stream. In each case, native `RunHandle.cancel()` propagates cancellation and the group owns drain/shutdown. Queued requests can stop before calling a provider. Completed consultation evidence remains visible on later failure or cancellation. UI answer commit and request completion remain one application transaction, preventing a late reply after Stop.

A running synchronous Python thread cannot be killed. Its native worker slot remains occupied until it returns, while canceled awaits finish promptly and late results are discarded. This does not undo side effects; all current tools are read-only. Only outer requests acquire application admission; child consultations use ProtoLink's native budget/supervision. Specialist tasks allow eight model steps/calls, six tool calls and 80 seconds; page requests wait up to 95 seconds. Sibyl's root budget allows twelve steps, ten model/tool calls and 140 seconds, within a 150-second outer request timeout, including native queue admission.

## Domain tools

The SDK additionally advertises `read_context_artifact` for bounded model context.

| Agent          | Sibyl-defined tools                                                                                                                                                                                           |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Oracle         | `portfolio_snapshot`, `page_help`                                                                                                                                                                             |
| Accountant     | `accountant_snapshot`, `account_history`, `risk_alerts`, `page_help`                                                                                                                                          |
| Analyst        | `market_analysis`, `analysis_help`, `page_help`                                                                                                                                                               |
| Broker         | `strategy_context`, `strategy_guide`, `execution_controls`, `strategy_alerts`, `exchange_support`, `backtest_report`, `validation_report`, `exit_readiness`, `recorded_orders`, `trade_help`, `strategy_help` |
| Chronos        | `price_forecast`, `forecast_method`, `page_help`                                                                                                                                                              |
| Reporter       | `news_briefing`, `read_article`, `news_sources`, `fear_and_greed`, `page_help`                                                                                                                                |
| Technician     | `connection_status`, `connection_alerts`, `settings_guide`, `exchange_setup`                                                                                                                                  |
| Wiki           | `search_knowledge`, `crypto_catalog`, `page_help`                                                                                                                                                             |
| Explorer       | `bitcoin_blocks`, `blockchain_help`, `page_help`                                                                                                                                                              |
| Equity Analyst | `equity_quote`, `equity_help`, `page_help`                                                                                                                                                                    |
| Sibyl          | No custom tools; native discovery/delegation and SDK context retrieval                                                                                                                                        |

Reporter reads the retained News archive and attributed index; publisher collection remains with News/background ingestion. Empty live sources stay empty. Broker's `recorded_orders` applies filters before its ten-order limit and returns at most ten fills for a selected record, retaining comparison totals and truncation flags. It never refreshes providers or changes tracking. Unknown/mismatched IDs use native `ToolRejectedError` for bounded correction.

## Help and tool-description contracts

Every specialist has a typed help tool: `page_help`, Broker's `trade_help` / `strategy_help`, or Technician's `settings_guide`. `Literal` choices become native enum schemas. `overview` lists topics; another topic returns one workflow, concrete steps, a destination and limitations. Instructions do not read keys/funds/providers or claim the user completed setup. How-to interpretation requires a model; no-model Tool snapshots retain deterministic evidence behavior.

Tool docstrings should lead with the question answered and information returned, explain meaningful arguments/defaults and known ID sources, and distinguish observations from instructions/methodology. Use native annotations and bounds; keep cache/worker mechanics in developer docs. Update the owning prompt and `guides/` records with each module change. Do not describe planned controls as implemented.

## Verification and remaining scope

`tests/test_application_runtime.py` exercises native lazy factories, immutable/transport-isolated context, frozen queued choices, correlated and untruncated reports, four-worker admission after cancellation, no late success, group shutdown, credential redaction, session restart and deletion. Existing agent/model/Stop tests keep the real native runtime and script only provider I/O.

`tests/test_agent_streaming.py` additionally checks native activity and correlated summaries, early progress during a blocked tool, disconnect cancellation without late success, sanitized failures, missing/estimated usage, partial coverage and per-currency costs. Browser fixtures cover NDJSON parsing and uncertain connection outcomes without automatic retries.

`tests/test_agent_answer_streaming.py` checks real native text/JSON-mode generation before completion, cancellation and root/child isolation. `tests/test_agent_replay.py` checks native cursor replay/gaps, viewer detachment, queue bounds, idempotent handles, authoritative saved text after hooks, and deletion privacy. Browser tests verify incremental/replaced/final Markdown, Unicode boundaries, Stop, activity phases and native usage labels.

`tests/test_agent_tool_contracts.py` exercises native pre-execution schema rejection/correction, concurrent shared research defaults, static help with all evidence workers occupied, missing-report recovery and token-free consultation persistence.

No paid provider, actual exchange order or external message is used for these checks. Broader real-model routing/grounding and venue acceptance remain separate work. Existing daily/weekly research calendars are unchanged. Retained handles are process-local observations; they do not enable durable workflow resumption.
