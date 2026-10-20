# Architecture

The design favors ordinary functions and a few small services. Business logic is independent of React and FastAPI; ProtoLink composes existing read-only functions rather than becoming a second application backend.

```text
React pages + shared UI
          │ same-origin /api/v1
FastAPI routes + validated request models
          │
          ├── Market ── ExchangeClient ── public prices / private balances
          ├── Portfolio ── Market + Store
          ├── Analytics ── pure Pandas/NumPy functions
          ├── Strategies ── backtests + persistent paper worker
          ├── ExchangeTrading ── reviewed intents + CCXT create_order
          ├── Research ── glossary / RSS / blocks / optional equities
          └── AgentRegistry ── ProtoLink Agent + read-only tools
                       │
              Store: SQLite + Fernet vault
```

## Python package

| File/module                    | Responsibility                                                                                    |
| ------------------------------ | ------------------------------------------------------------------------------------------------- |
| `config.py`                    | Validated environment configuration, with no import-time network work                             |
| `models.py`                    | Strict request models, enum-like IDs, canonical symbol validation                                 |
| `storage.py`                   | Short-lived SQLite connections, transactions, credentials, paper ledger, runs                     |
| `services/market.py`           | Client ownership, closed candles, source labels and bounded cache                                 |
| `services/accounts.py` | Saved versus active accounts, exclusive Demo preview and combined/exchange/account scopes |
| `services/valuation.py` | Exact direct/inverse/bridge routes, quote freshness, bounded reads and aligned conversion histories |
| `services/portfolio.py`        | Aggregate account balances, valuation, history, incomplete-account reporting                      |
| `services/analytics.py`        | Pure indicator, correlation, and baseline forecasting functions                                   |
| `services/strategies.py`       | Strategy catalog, signal functions, backtest mechanics, durable paper jobs                        |
| `services/strategy_monitor.py` | Atomic run journal, bounded quote observations, monitor snapshots, paged events and streaming CSV |
| `services/trading.py`          | Exchange preview validation, intent expiry, at-most-once submission attempts                      |
| `services/account_sync.py`     | Durable selected-market fill imports, native cursors, bounded retries, pause/resume and progress  |
| `services/ledger.py`           | Normalized fill storage, native-currency fees, atomic page/checkpoint commits and ledger queries  |
| `services/research.py`         | Bounded source-labeled research reads                                                             |
| `agents/providers.py`          | ProtoLink provider capabilities, model presets, dependency metadata                               |
| `services/llm_settings.py`     | Encrypted provider profiles, active selection, request-scoped adapter configuration               |
| `news/`                        | Public publisher ingestion, SQLite news archive, source health, filtering and text sentiment      |
| `agents/registry.py`           | Roles, native tools, optional model composition, request limits, factual snapshots                |
| `api/app.py`                   | Factory, lifespan, service composition, worker ownership, access/error handling, static SPA       |
| `api/routes.py`                | Thin versioned HTTP routes                                                                        |

`create_app(settings)` accepts explicit Settings, making tests independent of the developer's `.env`. Lifespan creates service instances, initializes storage, starts a paper worker and a separate news collector, and cancels both during shutdown. Importing the package does not connect to an exchange or initialize a model.

## Frontend

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
