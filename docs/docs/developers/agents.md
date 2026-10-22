# ProtoLink agents

Each specialist lives in its own file under `src/sibyl/agents/`. The file defines its prompt, typed tools and an ordinary ProtoLink `Agent`. Business logic stays in the existing domain services; tools call those services when the model needs evidence.

The dependency is `protolink>=0.8.2,<0.9`. In this version, local in-process transport is named **`runtime`**, and the discovery entry point is **`protolink.discovery.Registry`**.

## Files and responsibilities

| File | Owns |
| --- | --- |
| `oracle.py` | Portfolio perspective and `portfolio_snapshot` |
| `accountant.py` | Holdings and selected local performance, funding and transfer reports |
| `analyst.py` | Market indicators and analysis-method help |
| `broker.py` | Selected paper jobs/backtests and strategy rules |
| `chronos.py` | Forecast observations and baseline-method explanation |
| `reporter.py` | Cached news, selected articles, publisher attribution and cached Fear & Greed |
| `technician.py` | Connection metadata, settings guides and provider-specific setup instructions |
| `wiki.py` | Glossary, supported crypto IDs and sourced crypto profiles |
| `explorer.py` | Recent Bitcoin blocks and blockchain help |
| `stocks.py` | Equity quote/history and provider setup help |
| `sibyl.py` | Native coordinator declaration and prompt; delegation enabled |
| `telemetry.py` | Observe native task lifecycle for existing chat progress and saved evidence |
| `common.py` | Service references, shared read-only instructions and request-local selections/observations |
| `runtime.py` | Small request-scoped provider adapter; no agent orchestration |
| `network.py` | Native startup/shutdown, client task submission and chat lifecycle |
| `registry.py` | Module wiring, model configuration and HTTP response persistence |
| `snapshots.py` | Deterministic tool selection/formatting when no model is configured |
| `conversations.py`, `requests.py` | Durable chats and request outcome audit |

There is no `consult` gateway agent and no per-request Agent construction. The registered agents are the reasoning agents.

## A module declaration

The pattern used by the modules is deliberately small:

```python
from protolink import Agent
from sibyl.agents.common import COMMON_PROMPT, Services, background_tool, selected

SYSTEM_PROMPT = (
    "Explain the requested news using news_briefing. Cite returned publishers and dates. "
    "Read only the retained archive; never invent full article text."
)


def create_agent(services: Services, **runtime) -> Agent:
    def news_briefing(asset: str | None = None) -> dict:
        """Read already-fetched news mentioning an asset; do not refresh publishers."""
        return services.research.news(
            asset=selected("news_asset", asset, ""), refresh=False, limit=8
        )

    return Agent(
        name="sibyl-reporter",
        description="Explain sourced crypto reporting.",
        tools=[background_tool(news_briefing)],
        system_prompt=COMMON_PROMPT + SYSTEM_PROMPT,
        **runtime,
    )
```

The actual Reporter has four tools. Python annotations and docstrings become ProtoLink tool schemas. `background_tool` preserves that signature, moves blocking service reads off the API event loop, and records completed results for evidence inspection. It does not choose or dispatch tools. Sibyl has no custom consultation tools; delegation is a native SDK action.

`selected()` uses an explicit tool argument first, then the validated page selection, then the documented default. Omitted arguments can therefore inspect the current ETH chart without silently switching to BTC. If the user asks about another asset, the agent can supply a different symbol. Accountant's selected offline report is deliberately fixed: tool arguments cannot switch it into private balance reads or change its account/example filters.

## Startup and local URLs

FastAPI starts one native discovery registry and eleven native agents before accepting API traffic:

```python
from protolink.discovery import Registry

registry = Registry(transport="runtime", url="runtime://workspace/registry")
registry.start(background=True)
agent = Agent(
    name="reporter", url="runtime://workspace/reporter",
    transport="runtime", registry=registry,
    llm=llm, tools=[news_briefing], system_prompt=SYSTEM_PROMPT,
)
agent.start(background=True)
```

The application performs these blocking lifecycle calls in worker threads. ProtoLink's `.start()` owns its server and registration; the app does not construct `AgentServer` or `RegistryServer` manually. Startup checks that every expected URL is discoverable. Shutdown calls each `.stop()`, stops the registry and releases the client transport.

Actual URLs use an application-unique `runtime://sibyl-<uuid>/...` namespace. Simultaneous app instances do not share agents, and no extra TCP ports are exposed. Registry cards carry specialist/coordinator tags. `GET /agents` includes the native URL, complete tool list and registration state. `GET /sibyl` separates network readiness from model setup; `/system` reports eleven agents.

Startup registers agents without constructing a hosted model, contacting a model provider or running autonomous inference.

## Requests use AgentClient

The browser-facing API sends native tasks to the selected agent URL:

```python
from protolink import Task, RunBudget
from protolink.client import AgentClient

client = AgentClient("runtime", url="runtime://workspace/client")
task = Task.create_infer(
    "Explain the latest news",
    budget=RunBudget(max_steps=8, max_llm_calls=8, max_tool_calls=6),
)
result = await client.send_task(agent.card.url, task)
result.raise_for_status()
answer = result.get_last_part_content()
```

Production paths use `Task.create_infer` / `Task.create_tool_call` and `AgentClient.send_task`, not direct `Agent.invoke`. A page's Ask button addresses its specialist directly. It does not route through Sibyl.

Model requests include the question, validated selection defaults and up to six matching saved turns. **No initial domain snapshot is fetched or embedded.** The agent decides whether and which tools to call. A conceptual question can be answered without reading balances or news. Responses retain actual tool names, arguments and returned observations; an answer without tool reads is identified in the dialog.

With no model configured, module dialogs submit a single native tool task and format its result as a **Tool snapshot**. This factual mode does not interpret arbitrary questions. `snapshots.py` maps validated selections to the appropriate tool arguments and formats existing domain results. Sibyl itself requires a configured model.

## Models and concurrent requests

`WorkspaceLLM` uses ProtoLink's standard portable JSON action loop with the selected ProtoLink provider's text-generation interface. It delegates action parsing, schema validation, tool dispatch, task-local history and budgets to ProtoLink. It does not implement another reasoning loop. Provider-native function-call envelopes and token streaming are not used on this path.

Each turn lazily constructs its provider adapters from one frozen settings snapshot. Each participating agent has its own adapter; child tasks keep native SDK history isolation. The registered Agent remains the same. The adapters stay in private request-local context; credentials are never copied into native task payloads, model messages or tool outputs. Saving a model applies to later turns without restarting agents. Sibyl and its consultations share the same configuration snapshot even if settings change midway.

ProtoLink supplies task-local LLM history. A `ContextVar` holds the current page selection, per-agent provider adapters and completed observations, so simultaneous requests to the same agent do not share selections or chat state. Blocking provider I/O runs in a worker; transports and async tools remain on the API loop. There is no custom cross-loop runtime bridge.

Only outer user requests acquire the shared two-request semaphore. Native delegated child tasks do not acquire another application slot. Specialist tasks allow eight model steps/calls, six tool calls and 80 seconds of runtime; the outer page request waits at most 95 seconds.

## Domain tools

| Agent | Native tools |
| --- | --- |
| Oracle | `portfolio_snapshot` |
| Accountant | `accountant_snapshot` |
| Analyst | `market_analysis`, `analysis_help` |
| Broker | `strategy_context`, `strategy_guide` |
| Chronos | `price_forecast`, `forecast_method` |
| Reporter | `news_briefing`, `read_article`, `news_sources`, `fear_and_greed` |
| Technician | `connection_status`, `settings_guide`, `exchange_setup` |
| Wiki | `search_knowledge`, `crypto_catalog` |
| Explorer | `bitcoin_blocks`, `blockchain_help` |
| Equity Analyst | `equity_quote`, `equity_help` |
| Sibyl | No custom tools; ProtoLink supplies discovered agents and native `agent_call` |

Reporter uses the same archive/filter service as News with `refresh=False`. Publisher collection stays with the News page/background worker. An empty live archive remains empty live evidence; it never silently becomes demo reporting. Article tools return retained publisher excerpts, not an invented full article. Fear & Greed reads its attributed cache without refreshing the external provider.

Technician's help covers every Settings tab. `exchange_setup("binance")` returns required fields, the app's connection steps, activation behavior and the Settings URL. Exchange-specific fields come from the same catalog as connection forms, including passphrases, API memos and test environments. Help never reads exchange credentials or claims a connection was checked.

All tools remain read-only. There are no agent tools for order execution, job control, credentials, arbitrary files, shell commands or messaging.

## Native discovery and delegation

Sibyl's declaration passes the native registry to `Agent` and enables delegation:

```python
agent = Agent(
    name="sibyl-sibyl",
    registry=registry,
    transport="runtime",
    url="runtime://workspace/sibyl",
    llm=llm,
    system_prompt=SYSTEM_PROMPT,
)
agent.card.capabilities.delegation = True
```

There is no discovery or consultation tool. Before inference, ProtoLink automatically discovers registry cards, includes advertised agents/tools in the model context, and provides its native `agent_call` action. The model can request specialist inference or an advertised specialist tool. ProtoLink resolves the target through the registry, validates the action and tool arguments, creates a correlated child task, sends it through the agent's client, and returns the observation to Sibyl.

All ten specialist declarations explicitly set `agent.card.capabilities.delegation = False`. They receive only their own tools, do not discover peers during inference, and cannot delegate to another specialist or back to Sibyl. SDK validation rejects unavailable agents, direct URLs and cycles. Registering a new agent with this app's private registry makes it automatically visible to Sibyl without editing a routing table or discovery tool.

Delegated inference carries the question and exact market/account/source details in its prompt. The specialist chooses explicit typed tool arguments from that question; there is no application-specific `ask_agent(context=...)` protocol. A direct delegated tool call is checked against its advertised schema by ProtoLink. Browser module questions still use validated `AgentContext` for their page defaults.

`RunBudget` governs the native run and propagated child budgets: Sibyl has twelve steps, ten model calls, ten tool calls and 140 seconds of runtime. The complete browser request waits at most 150 seconds including queue time. There is no separate application consultation loop, four-call limit, specialist dispatch timeout or custom cancellation bridge. An execution failure can end the native parent task; prior completed observations remain in the failed-request audit.

`ChatTelemetry` observes native task lifecycle hooks and delegation events to project actual child tasks into the existing consultation panel and saved run history. It never discovers, selects or dispatches agents, intercepts model actions, or mutates task execution. The saved trail includes native task IDs, actual questions/tool calls, timestamps, returned answers and evidence. It excludes private reasoning. Cancellation propagation, child task relationships and dispatch belong to ProtoLink.

## Chats, progress and Stop

`conversations.py` owns completed chat turns; `requests.py` owns queued/running/completed/cancelled/failed/interrupted attempts. A chat permits one active turn. Saving an answer and marking its request completed share one SQLite transaction. Stop cannot erase an already committed answer.

`GET /sibyl/conversations/{id}/activity` returns lightweight lifecycle progress. `GET .../requests` returns the latest 20 summaries; `GET .../requests/{request_id}` loads retained evidence on demand. Stop requires the exact request ID; stale IDs cannot cancel later turns. Chat deletion is blocked while work is pending and removes that chat's request audit afterward.

Cancelling a client wait propagates to the native task and active specialist work. Completed consultation evidence is retained; cancelled worker results cannot become late observations or saved answers. A provider/network read already in a worker can finish and may incur provider charges. Startup marks unfinished requests interrupted without replaying them. These records are an audit, not resumable scheduling.

Messaging settings remain unavailable previews for WhatsApp, Telegram, Discord, Slack, Signal and Email. No clients, credentials, receivers or delivery are implemented.

## Keeping agents current

When adding or changing a module feature:

1. Update the corresponding agent file's prompt and tool docstrings. Describe supported behavior and actual limits.
2. Add a narrowly scoped typed tool that calls the existing service. Keep credentials and mutation methods out of its return value.
3. Add it to that file's `Agent(tools=[...])`. Discovery and the directory expose the current roster automatically.
4. Pass any new page selection through `AgentContext` and the module's Ask button. For factual mode, update `snapshots.py` when needed.
5. Update this tool table/user guide and test the path through real `AgentClient` tasks with a scripted ProtoLink Mock provider. Assert that facts are read on demand and unavailable sources stay explicit.

For a new dashboard module, add its declaration to `registry.MODULES` and its module ID/frontend entry. The network starts and registers it automatically. Independently registered agents are also visible to Sibyl through native discovery. New mutation tools need a separate explicit approval/action design.

`test_native_agents.py` covers on-demand news reads, no eager portfolio reads, practical setup guides, native guide tools, fixed offline accounting selections, same-agent concurrent history/selection isolation and cancellation during a real specialist tool. Existing chat/request tests cover startup/shutdown, native clients, model snapshots, propagated SDK budgets, persistence and Stop races. Additional tests register a new agent without changing Sibyl and verify that specialists never attempt discovery/delegation. Tests replace provider I/O, not ProtoLink's runtime.
