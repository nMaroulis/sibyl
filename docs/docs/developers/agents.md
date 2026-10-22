# ProtoLink integration

The engine dependency is `protolink>=0.8.2,<0.9`. Sibyl uses public ProtoLink `Agent`, `AgentCard`, `AgentClient`, `Registry`, `RegistryServer`, `AgentServer`, `RuntimeTransport` and `RunBudget` interfaces. Provider construction uses `create_llm`. There is no parallel agent framework.

## Lifecycle and discovery

FastAPI's lifespan constructs `AgentRegistry`, starts `AgentNetwork`, then starts the domain workers. The network starts a real ProtoLink registry server and eleven agent servers on **in-process runtime transports**: ten specialists and Sibyl. Each card is registered through the native registry client. Startup does not construct a hosted model, contact its provider, or start autonomous inference.

Application-unique `runtime://sibyl-<uuid>/...` namespaces isolate simultaneous app instances and tests. No additional TCP ports, unauthenticated agent listeners or public registry routes are opened. Existing workspace access controls protect the browser-facing API.

Shutdown unregisters the cards and stops each agent server, registry server and client transport. `GET /sibyl` reports network readiness separately from model configuration readiness. `GET /agents` remains the ten-specialist catalog and includes runtime registration status; `/system` reports eleven agents including Sibyl.

## Persistent gateways, isolated reasoning

Each persistent ProtoLink gateway exposes a typed asynchronous `consult(message, session_id, context, request_id)` tool. Only Sibyl uses the request ID for progress tracking. Its closure fixes the receiving module; a user cannot change a tool argument to impersonate another agent. Native `AgentClient.peer(card).call_tool("consult", ...)` creates serialized ProtoLink tasks and executes the receiving agent's validation and tool runtime.

A request then composes a fresh reasoning Agent with that role's prompt, native tools and an immutable model/provider/key snapshot. This separation keeps the gateway available throughout the application lifetime without sharing an LLM's conversation state between users' chats or page selections. Saving model settings applies to the next request without restarting the registry. A Sibyl turn and all of its consultations use the same model snapshot even if settings change midway through the request.

## Module tools

| Agent          | Initial domain tool   |
| -------------- | --------------------- |
| Oracle         | `portfolio_snapshot`  |
| Accountant     | `accountant_snapshot` |
| Analyst        | `market_analysis`     |
| Broker         | `strategy_context`    |
| Chronos        | `price_forecast`      |
| Reporter       | `news_briefing`       |
| Technician     | `connection_status`   |
| Wiki           | `search_knowledge`    |
| Explorer       | `bitcoin_blocks`      |
| Equity Analyst | `equity_quote`        |

Functions have typed arguments and docstrings; ProtoLink derives schemas and validates calls. Domain tools call the same services as the HTTP API. Broker only reads strategy state, never starts a job or places an order.

Direct module requests validate `AgentRequest` and `AgentContext`, acquire a shared two-request semaphore, and call that module through the agent client. The receiver maps page selections to initial native tool arguments, executes blocking reads in a worker thread, and either formats a factual snapshot or runs isolated model inference. Model inference uses six steps/calls/tool calls and an 80-second runtime budget, with a 90-second inference wait and 95-second outer client deadline.

Selected Accountant report views retain their fixed-evidence override: the inference agent cannot switch an offline funding/performance/transfer selection into private balance reads. Prior turns match session, module and exact context.

## Sibyl's collaboration tools

`AgentNetwork._answer_sibyl` creates a reasoning Agent with two tools:

- `discover_agents()` queries `RegistryClient.discover` for current specialist cards and returns their roles and supported context field names.
- `ask_agent(agent_id, question, context)` queries the registry again, accepts only an application-owned registered specialist card, validates context using `AgentContext`, then calls that card through `AgentClient`.

The LLM chooses its own collaborators; there is no keyword routing or fixed sequence. Sibyl can also answer without delegation. Self-delegation, unknown IDs, external URLs and foreign registry cards cannot be dispatched. Its reasoning card disables native unrestricted delegation so model-generated `agent_call` actions cannot bypass the bounded consultation tool.

Each turn permits four consultation attempts, ten model/tool calls, twelve steps and 140 seconds of ProtoLink runtime. A specialist consultation waits at most 45 seconds; the complete client request waits at most 150 seconds including shared-semaphore queue time. Failed consultations return sanitized unavailable observations and the model can continue with other specialists. Like existing module inference, a blocking provider thread can finish after its wait expires; it only has read-only tools.

Blocking model/provider calls run in worker threads. `RuntimeBridge` sends consultation tools back to the application event loop so clients and transport limits stay on their owning loop; cancellation closes the bridge and cancels outstanding consultations. Provider threads may finish, but cannot start late consultations after the request closes.

Only outer user requests acquire the shared semaphore. Delegated consultations use the existing slot, preventing orchestration deadlocks when two Sibyl chats run concurrently. Per-chat locks reject simultaneous turns and deletion while a request is pending.

The persisted delegation trail contains actual requests, validated selections, initial observations, responses and completion/unavailable status. It excludes private reasoning and does not claim to capture every internal specialist tool call.

## Persistence and API

`agents/conversations.py` owns `sibyl_conversations` and `sibyl_turns` SQLite tables. Completed answers and delegation evidence are committed together with the conversation's title/update. Conversation reads also expose transient pending state, allowing the page to recover a running chat after navigation. The UI reads the latest 100 turns; model context includes the latest six. Conversation lists are capped at 100. Specialist runs keep their existing separate rolling run history. Deleting a Sibyl chat does not delete those module runs.

`agents/requests.py` owns the durable `sibyl_requests` audit. Requests transition from `queued` to `running`, optionally `cancelling`, then `completed`, `cancelled`, `failed` or `interrupted`. A partial unique index permits only one active request per chat; client-supplied duplicate IDs cannot create a second inference. Answer persistence and request completion share a SQLite transaction, so Stop cannot erase a committed answer. Late progress writes cannot change terminal outcomes. Startup marks unfinished rows interrupted and retains completed consultations without replaying inference.

`GET /sibyl/conversations/{id}/activity` returns the latest request stage and consultation summaries, excluding answer/evidence payloads. The UI polls this once a second only while following work, then reloads completed turns; it does not repeatedly transfer full chat evidence. `GET .../requests` returns the latest 20 summaries and `GET .../requests/{request_id}` loads full observations on demand. This records actual lifecycle events, not private reasoning, token streaming or all internal tool calls.

`POST .../cancel` requires the exact request ID. It cancels queued or running child work, closes the runtime bridge and retains completed observations. Stale IDs cannot cancel later turns; completed requests return 409, unknown/foreign IDs return 404, and already cancelled requests are idempotent. The original Ask returns a `cancelled` result without a fabricated saved turn. A provider call already in flight may finish or incur charges, but it cannot start new consultations or commit a late answer. This is cooperative cancellation, not provider-side billing cancellation or resumable scheduling.

`SibylRequest` accepts a nonblank message of at most 4,000 characters and optional 32-character hexadecimal session/request IDs. Unknown fields are rejected. Missing model setup returns 409 before a chat or provider request is created; unknown session IDs return 404. Provider failures return a generic 502 without reflecting adapter exceptions or credentials. Conversation and request access use the same local workspace token as all versioned routes. Deleting a chat also removes its retained request audit.

`MessagingSettings` is a read-only catalog of provider-specific setup fields. WhatsApp, Telegram, Discord, Slack, Signal and Email always report `unavailable` and `connected: false`. The disabled UI accepts no credentials; there are no save/draft endpoints. No channel adapter, token handling, webhook, background receiver, or message-sending tool exists yet.

## Extending and testing

Add a module ID, a `ROLES` entry, a typed read-only function and its `_tools` mapping. The network creates its gateway/card automatically at startup; discovery and the directory then expose it. Add frontend module names, suggestions and an `AgentButton` with typed page context. New mutation tools require a separate explicit execution/approval design.

`tests/test_sibyl.py` uses the installed ProtoLink runtime, registry, clients, servers and tools. Only provider I/O is replaced by scripted Mock LLM responses. Tests exercise multi-specialist collaboration, startup/shutdown isolation, model gating, shared configuration snapshots, bounded dispatch, unavailable evidence, durable chat separation, and unavailable channel requirements and rejected writes. Existing module API tests still execute all ten specialists through native tool tasks.

`tests/test_sibyl_requests.py` adds real-runtime progress, partial-evidence retention, cancellation while queued/consulting/in a provider call, blocked late dispatch, stale Stop races, atomic completion, sanitized failures, restart interruption and workspace access-control checks.
