# Architecture

The design favors ordinary functions and focused domain modules. React renders the workspace, FastAPI validates requests, and Python owns calculations, persistence and execution. ProtoLink agents use the same domain evidence through typed read-only tools.

![Sibyl v2.0.0 architecture: application entry points, Python domain modules, the native ProtoLink team, data sources, local storage and configured language models.](/img/architecture.svg)

The dashboard and optional Telegram client enter the Python application. Sibyl discovers and consults the ten specialists through ProtoLink; specialists do not delegate or submit orders. Exchange writes use the separately reviewed trading pipeline. Domain services and the agent runtime retain their own state in the local workspace.

The [editable diagram topology](/img/architecture.mmd) accompanies the SVG used here and in the repository README.

## Python package

| File/module                               | Responsibility                                                                                      |
| ----------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `config.py`                               | Validated environment configuration, with no import-time network work                               |
| `models.py`                               | Strict request models, enum-like IDs, canonical symbol validation                                   |
| `storage.py`                              | Short-lived SQLite connections, transactions, credentials, paper ledger, runs                       |
| `services/market.py`                      | Client ownership, closed candles, source labels and bounded cache                                   |
| `services/accounts.py`                    | Saved versus active accounts, exclusive Demo preview and combined/exchange/account scopes           |
| `services/valuation.py`                   | Exact direct/inverse/bridge routes, quote freshness, bounded reads and aligned conversion histories |
| `services/portfolio.py`                   | Aggregate account balances, valuation, history, incomplete-account reporting                        |
| `services/analytics.py`                   | Pure indicator, correlation, and baseline forecasting functions                                     |
| `strategies/`                             | Strategy catalog, signal functions, backtest mechanics, durable paper jobs                          |
| `strategies/journal.py`                   | Atomic run journal, bounded quote observations, monitor snapshots, paged events and streaming CSV   |
| `services/trading.py`                     | Exchange preview validation, intent expiry, at-most-once submission attempts                        |
| `services/account_sync.py`                | Durable selected-market fill imports, native cursors, bounded retries, pause/resume and progress    |
| `services/ledger.py`                      | Normalized fill storage, native-currency fees, atomic page/checkpoint commits and ledger queries    |
| `services/research.py`                    | Bounded source-labeled research reads                                                               |
| `agents/providers.py`                     | ProtoLink provider capabilities, model presets, dependency metadata                                 |
| `services/llm_settings.py`                | Encrypted provider profiles, active selection, request-scoped adapter configuration                 |
| `news/`                                   | Public publisher ingestion, SQLite news archive, source health, filtering and text sentiment        |
| `agents/<module>.py`                      | Native Agent declarations, module prompts and typed read-only tools                                 |
| `agents/registry.py`, `agents/network.py` | Wiring, AgentGroup lifecycle, native run handles and UI request persistence                                      |
| `api/app.py`                              | Factory, lifespan, service composition, worker ownership, access/error handling, static SPA         |
| `api/routes.py`                           | Thin versioned HTTP routes                                                                          |

`create_app(settings)` accepts explicit Settings, making tests independent of the developer's `.env`. Lifespan creates service instances, initializes storage, starts the domain workers and the in-process ProtoLink agent network, and stops them during shutdown. The network starts Sibyl and ten persistent native specialist Agents using ProtoLink `.start()`. Each agent has its own file, prompt and tools. Native client tasks and task-local history isolate requests; tools fetch evidence on demand. See [agent lifecycle and collaboration](./agents.md). Importing the package does not connect to an exchange or initialize a model.

## Frontend

`strategies/execution/` separates strict authorization contracts, read-only approval creation, exact venue observations/sizing, native fill accounting and the execution runner. It reuses the shared `ExchangeTrading` intents and native reconciliation ledger. Exchange runs pause at startup and cannot replay missed signals or uncertain writes. See [exchange strategy execution](../guides/strategy-execution.md). Agents remain read-only.

The header wordmark and favicon are served locally from `frontend/public/brand/`, copied unchanged from the original `assets/` files. Docusaurus uses matching copies in `docs/static/img/brand/`. Original assets remain available for future branding work.

`pages/` owns domain screens. `components/ui.tsx` defines shared controls and notifications; `charts.tsx` wraps chart rendering; `ExchangeExecution.tsx` isolates the actual-funds review flow. `lib/types.ts` documents response contracts, `lib/api.ts` sends authenticated JSON requests, and `useResource` owns fetching, refresh, stale-response handling, and optional polling.

Routes are browser history routes. Vite proxies the API in development. The Python app serves a built `frontend/dist` with a history fallback in a source checkout/container. Production compilation separates feature bundles through lazy page imports.

## State and concurrency

SQLite transactions serialize manual paper fills. One idempotency key maps to one order and immutable order details. Paper jobs use a service lock and persisted candle markers. Exchange intents atomically transition to submitting before network execution.

This implementation assumes one API process and worker. It is not a distributed scheduler. Multiple backend workers could duplicate paper-job evaluation and should not be used without database-backed job claims.

## Source boundaries

Demo prices come from an explicit DemoClient and research fixtures have their own demo boundary; live errors never trigger fixture substitution. A portfolio records incomplete accounts and unpriced assets. A model-backed answer and the initial native tool evidence have separate labels. Charts show observed or simulated values with the relevant assumptions.

Strategy monitoring components are split into the run list, detail workspace, decision journal, and chart. The builder and monitor share the `/strategies` route with query selections. Run detail polling reads persisted observations; it never fetches provider quotes or executes paper fills. The worker saves each successful quote sample and commits new-candle decisions with the updated account/cursor in one SQLite transaction. Stop and pause use the same service lock as evaluation.

Model profiles store encrypted JSON in `model_profiles`; the active ID is committed in the same transaction in `workspace_settings`. The model settings service owns key resolution and sanitized metadata. Provider keys are constructor arguments or authorization headers only, never process-wide environment mutations. Registry requests resolve a configuration once before fetching evidence and keep it throughout inference, including its response provider label.

`services/crypto_library.py` owns the fixed asset selection, normalized CoinPaprika/Wikipedia reads, bounded HTTP responses, per-source single-flight locks, and atomic public JSON cache files. Research creates it without fetching data on startup. Only the requested asset is fetched; trading/demo settings do not alter public educational sources. Wiki's native tool can resolve a validated `crypto_id` to the same profile.

Native ProtoLink 0.8.3 owns threaded tool/provider execution, private `request_context`, owned local delegation, SQLite sessions and correlated run reports. `agents/presentation.py` formats its events/evidence for the existing UI. See [runtime contracts](agents.md).
