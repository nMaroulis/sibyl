# Sibyl

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

## Legacy Streamlit version

The original Sibyl dashboard, built entirely in Python with Streamlit, is available at [nMaroulis/sibyl-streamlit](https://github.com/nMaroulis/sibyl-streamlit). This repository contains the React frontend, Python API and AI agents powered by ProtoLink.

## Workspace navigation

Portfolio is the home screen. The floating dock opens Markets, Trade, Strategies, Agents, Forecasting, News, and Settings. Settings combines **Exchanges**, **AI models**, **News**, **Market data**, and **Workspace** in a matching top tab bar. Form drafts remain in memory while switching Settings sections. AI models saves encrypted provider keys and activates preset/custom models immediately through ProtoLink. News saves collector choices and encrypted optional NewsAPI keys. Market data saves its public source for the next API restart. See the [Settings guide](docs/docs/guides/settings.md).

## News and sentiment

**News** collects five public publisher feeds through the Python backend, with a persistent deduplicated archive, source health, search/asset/publisher/date filters, and VADER text polarity distributions and trends. Public news works while exchange accounts stay in demo mode. Ask Reporter reads the selected story or filters through ProtoLink. Publisher RSS needs no key; CryptoSlate web collection and encrypted optional NewsAPI access are also supported. Full articles open at the publisher. Alternative.me supplies the attributed Fear & Greed index. See the [News backend guide](docs/docs/developers/news.md).

## Crypto research

**Research → Crypto profiles** covers 20 familiar assets with backend-fetched project information, history excerpts, market/supply figures, contributors, and source links. CoinPaprika and Wikipedia public data work in either demo or live trading mode. Independent persistent caches and explicit stale/unavailable states keep provider failures visible. **Ask Wiki** reads the selected profile through ProtoLink. See the [Research guide](docs/docs/guides/research.md).

## Exchange clients

A shared `ExchangeClient` interface now backs **20 real spot providers plus an offline `DemoClient`**. Explicit CCXT subclasses normalize markets, quotes, candles, books, balances, order status, open orders and bounded fill history. The demo client is a normal saved connection with a Demo badge, a persistent paper wallet and simulated fills through the same interface. All fixtures and seed balances live in Python; Portfolio reads the same backend APIs for demo and real accounts. Exchange logos are self-hosted app assets. Settings loads the searchable exchange catalog and credential requirements from the backend; OKX/KuCoin/Bitget passphrases and BitMart API memos are supported.

Implemented adapters: Binance, Binance.US, Coinbase, Kraken, OKX, Bybit, KuCoin, Gate, Bitget, MEXC, HTX, Crypto.com Exchange, Bitstamp, Gemini, Bitfinex, CoinEx, BitMart, Phemex, Poloniex and Upbit. Newly added production providers are read-only; production manual market-order execution remains limited to the original Binance/Coinbase/Kraken reviewed flow. Authenticated accounts and real orders have not been acceptance-tested.

See the [client reference, provider matrix and remaining implementation checklist](docs/docs/developers/exchange-clients.md). Missing work includes authenticated provider validation, new-provider execution, cancel/limit orders, full fill imports and reconciliation, streaming, additional wallet/account variants and broader valuation. `GET /api/v1/exchanges` reports the installed SDK's capabilities and remaining unconfigured exchange IDs.

Dedicated **Binance Testnet** and **Coinbase Sandbox** options are also available in Settings. They have separate credentials, forced sandbox routing and test-funds badges. Coinbase Sandbox uses the Coinbase Exchange API, separate from Advanced Trade. Test accounts are visible individually in Account balances and excluded from real portfolio totals. See the [test-environment setup guide](docs/docs/guides/exchanges.md#test-environments-and-orders).

## Python package

| File/module                    | Responsibility                                                                                    |
| ------------------------------ | ------------------------------------------------------------------------------------------------- |
| `config.py`                    | Validated environment configuration, with no import-time network work                             |
| `models.py`                    | Strict request models, enum-like IDs, canonical symbol validation                                 |
| `storage.py`                   | Short-lived SQLite connections, transactions, credentials, paper ledger, runs                     |
| `services/market.py`           | Client ownership, closed candles, source labels and bounded cache                                 |
| `services/portfolio.py`        | Aggregate account balances, valuation, history, incomplete-account reporting                      |
| `services/analytics.py`        | Pure indicator, correlation, and baseline forecasting functions                                   |
| `services/strategies.py`       | Strategy catalog, signal functions, backtest mechanics, durable paper jobs                        |
| `services/strategy_monitor.py` | Atomic run journal, bounded quote observations, monitor snapshots, paged events and streaming CSV |
| `services/trading.py`          | Exchange preview validation, intent expiry, at-most-once submission attempts                      |
| `services/research.py`         | Bounded source-labeled research reads                                                             |
| `news/`                       | Public publisher ingestion, SQLite news archive, source health, filtering and text sentiment |
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

Monitor regression tests cover read-only polling, quote updates without duplicate decisions, restart persistence, skip/hold reasons, slippage signs and fee accounting, terminal/idempotent Stop, pause/source-change handling, rollback after an uncommitted fill, paged cursors, full CSV and its export boundary, retention, earlier-run honesty, concurrent worker calls, custom indicator periods, rolling metric baselines, and run-specific Broker context.

### Open a running strategy

Go to **Strategies → Monitor → Open monitor**. Each run has observed price/equity/drawdown charts, execution and skipped-signal markers, a durable filtered journal, full log export, account/performance details, immutable launch parameters, and its own Broker context. Pause/Resume retain the paper position; Stop is terminal and performs no liquidation. Browser refresh is five seconds, worker observations are every 30 seconds, and signals evaluate once per newly closed candle. See the [strategy monitor guide](docs/docs/guides/strategy-monitor.md).
