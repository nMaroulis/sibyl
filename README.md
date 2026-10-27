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
          ├── PriceAlerts ── editable level/crossing rules + persistent local inbox
          ├── ExchangeTrading ── reviewed intents + CCXT create_order
          ├── Research ── glossary / RSS / blocks / optional equities
          └── AgentRegistry ── ProtoLink runtime registry + agent clients
                              ├── Sibyl ── discover & consult
                              └── Ten specialists + read-only tools
                       │
              Store: SQLite + Fernet vault
```

The **original legacy Sibyl** dashboard, built entirely in Python with Streamlit, is available at [nMaroulis/sibyl-streamlit](https://github.com/nMaroulis/sibyl-streamlit). This repository contains the React frontend, Python API and AI agents powered by ProtoLink.

## Workspace navigation

Account is the home screen. New workspaces start with no active accounts. Connect multiple exchange accounts to combine their holdings, then filter by exchange or individual account. Activation controls keep saved credentials separate from active accounts. Demo is a clearly labeled optional preview and switches off when an exchange activates. The floating dock opens **Sibyl**, Markets, Trade, Strategies, Forecasting, News, and Settings. **More** expands to Agents, Alerts, Research and Coming soon. Settings combines **Exchanges**, **AI models**, **News**, **Market data**, **Messaging**, and **Workspace** in a matching top tab bar. Form drafts remain in memory while switching Settings sections. AI models saves encrypted provider profiles, a workspace default and optional per-agent provider/model overrides. Preset/custom IDs apply to new ProtoLink requests, which freeze the team configuration through delegated consultations. Profiles can be saved without changing the default; keys/endpoints are shared per provider. See [model contracts](docs/docs/developers/agent-models.md). News saves collector choices and encrypted optional NewsAPI keys. Market data selects public exchange feeds, saved account environments, or CryptoCompare/CoinGecko APIs with encrypted keys, applied immediately. Markets can override the feed for its own charts and Analyst without changing the default. Its editable watchlists persist per feed, with add/remove/reorder controls and Quick look cards following the saved order. See [market sources](docs/docs/developers/market-data.md). See the [Settings guide](docs/docs/guides/settings.md).

**Sibyl** is the lead ProtoLink agent: ProtoLink automatically exposes registered specialists and handles native delegation as Sibyl chooses whom to consult, combining their evidence in a dedicated chat with saved conversations and a consultation trail. Live progress shows the specialists at work; Stop cancels the exact request, and request history retains completed observations and stopped/failed/interrupted outcomes. Unfinished requests are marked interrupted after restart without automatic replay. All eleven agents start through ProtoLink `AgentGroup`; module Ask buttons run their registered specialist through a native handle. Each agent has its own Python file, prompt and ordinary typed tools. Native model factories use frozen private request context; owned local specialists inherit explicit dependencies while independent transport clients remain isolated. Models fetch evidence on demand instead of receiving preloaded module snapshots. Reporter reads retained news and Technician provides practical settings/setup guides. Sibyl requires a configured API or local model and links to setup when one is missing. Mock responses are explicitly simulated. **Settings → Messaging** shows app icons and the required setup fields for WhatsApp, Telegram, Discord, Slack, Signal and Email. Telegram is implemented with encrypted bot configuration, private-user binding, polling and durable delivery. Other channels remain unavailable previews. See [Telegram setup](docs/docs/guides/telegram.md), the [Sibyl guide](docs/docs/guides/sibyl.md) and [agent architecture](docs/docs/developers/agents.md).

## Strategy execution

Strategies starts with historical research and isolated paper runs. Expand **Run on a connected exchange** for account/pair selection, native quote budgets, risk limits and an optional order lifetime. Nine provider/environment variants use price-capped GTC orders and the shared native order/fill pipeline. Both backend execution flags and a typed scoped approval are required; startup pauses new submissions while approved expiry continues. The monitor offers **Stop & cancel orders**, then a separately reviewed **Close position** sell once outstanding evidence is reconciled. Exits use only strategy-owned units, reserve base fees and retain any partial-fill/precision residual for a fresh approval. Uncertain writes are never automatically repeated. Agents remain read-only. A durable **Halt automation** control pauses all exchange runs, blocks new signal orders, invalidates unused reviews and retains an audit. Typed release keeps every run paused for individual review/Resume. Manual Trade, approved cancellation policies and separately reviewed position exits retain their existing permissions. Portfolio-wide exposure/daily-loss policies and authenticated venue acceptance remain pending. See the [exchange strategy guide](docs/docs/guides/strategy-execution.md).

Expand **Validate on unseen data** for bounded parameter search on earlier candles and independent later-window tests. Saved immutable inputs support chronological holdouts and expanding walk-forward evaluation, fixed-settings and cost-aware buy-and-hold comparisons, test-chart executions, training rankings, exact-study reruns and JSON/CSV evidence. Research never changes or starts a trading strategy. See [validation setup and interpretation](docs/docs/guides/strategy-validation.md).

## Portfolio valuation

Portfolio prices actual held assets through exact direct, inverse or short conversion routes from the selected market feed. Stablecoins and fiat use observed rates; no parity is assumed. Holdings expose conversion evidence and coverage, and unavailable quantities stay visible. Complete account observations form the history. The Demo wallet exercises an extra coin, stablecoin and fiat through the same engine. See [portfolio valuation](docs/docs/developers/portfolio-valuation.md).

## Funding history

**Trade → Account history → Fills & imports** supports durable selected-market fills for eleven clients/environments, including OKX, Bybit UTA, KuCoin classic and Bitget classic. Incremental sync resumes checkpoints; **Rescan available history** checks older available fills for fee/data corrections while retaining local observations. Provider retention, retained execution ranges and per-pass corrections remain explicit. OKX, Bybit and KuCoin also support exact-order fill reconciliation. See [account imports](docs/docs/developers/account-sync.md).

**Trade → Account history → Funding** adds read-only range imports for Binance crypto deposits/withdrawals, Kraken deposit/withdrawal/transfer ledger entries and Bybit master-UID on-chain withdrawals. Checkpoints, pause/resume, rescans and sanitized retries retain native IDs, statuses, amounts and fees. Summaries keep accounts, environments and assets separate. Demo has an actual empty funding history plus a standalone example. Ask Accountant reads the selected local observations through ProtoLink. Funding gaps flag affected market FIFO as provisional; unsupported transfer/funding cases and cash-flow-adjusted returns remain future work. See [funding contracts, provider limits and remaining work](docs/docs/developers/funding-history.md).

## Transfer review

**Funding → Reconcile transfers** suggests possible own-account pairs, exposes competing matches and supports manual search of older records. Explicit confirmation stores source-version snapshots and an audit trail. Corrections flag links for review; removal/restoration is reversible and a source record can belong to one active link. Funding rows show the classification without changing their amounts. ProtoLink Accountant reads the same local evidence. **Performance** now carries original acquisition lots across eligible current confirmed zero-fee pairs or explicit, balanced same-asset fee allocations. It shows carried cost, original dates and unapplied reasons, and includes a separate transfer example. Review amount conventions and missing-fee assertions in the same dialog. Fee units and their historical inventory cost stay separate; final net remains provisional without historical fee valuation. Split/merged transfers, other fee currencies/rebates, cross-market basis and account returns remain future work. See [fee allocation contracts](docs/docs/developers/transfer-fees.md). See [carryover rules](docs/docs/developers/transfer-cost-basis.md). See [transfer review and limits](docs/docs/developers/transfer-reconciliation.md).

## Local alerts and pending work

**More → Alerts** saves editable level/crossing rules for an exact pair/feed, with one-time or reset-based repetition, cooldowns, explicit Demo labeling, pause/rearm/archive/restore and a persistent in-app inbox. Edits save paused and retain past notification evidence; crossing rules require newer ordered quotes and do not infer moves across gaps. The bell counts unread notifications while retaining agent/backtest activity. The API must be running; stale/undated quotes do not trigger, failures back off, and missed offline crossings are not reconstructed. No trade or external message is sent. See the [user guide](docs/docs/guides/alerts.md) and [backend contracts](docs/docs/developers/alerts.md).

**Coming soon → Implementation status** now lists what works and what remains across all 13 areas, including a dedicated **Sibyl & messaging** backlog, served by the backend’s audited inventory. **Multi-user support is deferred** and appears in Coming soon rather than the active implementation sequence. Candle history, reviewed resumable backfills, coverage gaps, retention and immutable backtest datasets are now implemented. Shared local read limits, cooldowns and observed source diagnostics are now implemented too. Next foundations include broader account reconciliation, authenticated order recovery/discovery validation, exact weighted quota policies and richer operational metrics. See the [complete refreshed checklist](docs/docs/developers/backend-roadmap.md).

## News and sentiment

**News** collects five public publisher feeds through the Python backend, with a persistent deduplicated archive, source health, search/asset/publisher/date filters, and VADER text polarity distributions and trends. Public news works while exchange accounts stay in demo mode. Ask Reporter reads the selected story or filters through ProtoLink. Publisher RSS needs no key; CryptoSlate web collection and encrypted optional NewsAPI access are also supported. Full articles open at the publisher. Alternative.me supplies the attributed Fear & Greed index. See the [News backend guide](docs/docs/developers/news.md).

## Crypto research

**Research → Crypto profiles** covers 20 familiar assets with backend-fetched project information, history excerpts, market/supply figures, contributors, and source links. CoinPaprika and Wikipedia public data work in either demo or live trading mode. Independent persistent caches and explicit stale/unavailable states keep provider failures visible. **Ask Wiki** reads the selected profile through ProtoLink. See the [Research guide](docs/docs/guides/research.md).

## Exchange clients

A shared `ExchangeClient` interface now backs **20 real spot providers plus an offline `DemoClient`**. Explicit CCXT subclasses normalize markets, quotes, candles, books, balances, order status, open orders and bounded fill history. The demo client is a normal saved connection with a Demo badge, a persistent paper wallet and simulated fills through the same interface. All fixtures and seed balances live in Python; Account reads the same backend APIs for demo and real accounts. Exchange logos are self-hosted app assets. Settings loads the searchable exchange catalog and credential requirements from the backend; OKX/KuCoin/Bitget passphrases and BitMart API memos are supported.

Implemented adapters: Binance, Binance.US, Coinbase, Kraken, OKX, Bybit, KuCoin, Gate, Bitget, MEXC, HTX, Crypto.com Exchange, Bitstamp, Gemini, Bitfinex, CoinEx, BitMart, Phemex, Poloniex and Upbit. Manual market/GTC limit orders and cancellation are implemented for Binance, Binance.US, Coinbase Advanced, Kraken, OKX, Bybit UTA, KuCoin classic and Bitstamp; Gemini supports GTC limits and cancellation only. Other production clients remain read-only. Click any provider in Settings for its account, spot, history, market-data and automation support, including explicit gaps. Authenticated accounts and real orders have not been acceptance-tested.

See the [client reference, provider matrix and remaining implementation checklist](docs/docs/developers/exchange-clients.md). Missing work includes authenticated provider validation, new-provider execution, cancel/replace and conditional orders, broader fill imports and complete reconciliation, streaming, additional wallet/account variants and broader valuation. `GET /api/v1/exchanges` reports the installed SDK's capabilities and remaining unconfigured exchange IDs.

Dedicated **Binance Testnet** and **Coinbase Sandbox** options are also available in Settings. They have separate credentials, forced sandbox routing and test-funds badges. Coinbase Sandbox uses the Coinbase Exchange API, separate from Advanced Trade. Test accounts are visible individually in Account balances and excluded from real portfolio totals. See the [test-environment setup guide](docs/docs/guides/exchanges.md#test-environments-and-orders).

## Order management

**Trade → Order monitor** now follows reviewed market and GTC limit orders, cumulative partial fills, cancellation requests and persisted status tracking. Native writes remain limited to Binance, Coinbase Advanced, Kraken and the dedicated test clients. Unknown writes are never automatically retried. **Recover order** now looks up uncertain submissions by saved client ID for these clients and Demo, with exact reviewed-detail checks, durable bounded pagination and explicit no-match/ambiguous states. A verified ID rejoins status/fill tracking without resubmitting. See [recovery contracts](docs/docs/developers/order-recovery.md). Demo supports resting GTC limits with atomic virtual-wallet reservations, matching and cancellation; its fills enter the same paper ledger. **View example** changes no account records. Stop/OCO and cancel/replace remain future work. See [order-management contracts and limits](docs/docs/developers/order-management.md).

**Sync exchange orders** in **Trade → Executions** now discovers open/recent orders from Binance/Testnet, Coinbase Advanced/Sandbox, Kraken and Demo. The combined monitor filters by exchange, account, origin and status, with paginated read-only imported rows, saved sync progress and shared fill identities. Binance recent history uses explicitly selected pairs; native coverage/retention limits remain visible. See [discovery contracts](docs/docs/developers/order-discovery.md).

Open an order's **Executions** evidence to compare native filled quantity with imported fill IDs, reported cost and native-currency fees. Exact-order imports share Account history's identities, commit each page with its restart checkpoint, and make three bounded terminal passes for delayed fee evidence. Checks never retry an order submission. Missing fills/fees remain visible, and a match is not a final-settlement guarantee. Demo and isolated examples use the same detail view. See [reconciliation contracts and remaining scope](docs/docs/developers/order-reconciliation.md).

## Python package

| File/module                                      | Responsibility                                                                                    |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| `config.py`                                      | Validated environment configuration, with no import-time network work                             |
| `models.py`                                      | Strict request models, enum-like IDs, canonical symbol validation                                 |
| `storage.py`                                     | Short-lived SQLite connections, transactions, credentials, paper ledger, runs                     |
| `services/market.py`                             | Client ownership, closed candles, source labels and bounded cache                                 |
| `services/portfolio.py`                          | Aggregate account balances, valuation, history, incomplete-account reporting                      |
| `services/analytics.py`                          | Pure indicator, correlation, and baseline forecasting functions                                   |
| `strategies/`                                    | Strategy catalog, signal functions, backtest mechanics, durable paper jobs                        |
| `strategies/journal.py`                          | Atomic run journal, bounded quote observations, monitor snapshots, paged events and streaming CSV |
| `services/trading.py`                            | Exchange preview validation, intent expiry, at-most-once submission attempts                      |
| `services/import_worker.py`                      | Shared one-page scheduling, transport failure handling and safe shutdown                          |
| `services/transfer_reconciliation.py`            | Bounded suggestions, explicit transfer assertions, source-version checks, reservations and audit  |
| `services/funding_sync.py`                       | Explicit-range funding jobs, rescans, active-account gating and isolated examples                 |
| `services/funding_ledger.py`                     | Validated funding facts, atomic checkpoints and native completed-quantity summaries               |
| `services/account_sync.py`                       | Durable selected-market imports, retries, pause/resume and progress                               |
| `services/fifo.py`, `services/transfer_basis.py` | Shared decimal FIFO books, dependency replay and original-lot transfer carryover                  |
| `services/performance.py`                        | Decimal market FIFO, audited opening inventory and opt-in reconciled reference marks              |
| `services/ledger.py`                             | Normalized fills, native-currency fees and atomic import checkpoints                              |
| `services/research.py`                           | Bounded source-labeled research reads                                                             |
| `news/`                                          | Public publisher ingestion, SQLite news archive, source health, filtering and text sentiment      |
| `agents/<module>.py`                             | Each native ProtoLink agent, its prompt and typed read-only tools                                 |
| `agents/guides/`                                 | Focused page instructions/FAQ topics retrieved through each specialist's native help tools         |
| `agents/registry.py`, `agents/network.py`        | AgentGroup lifecycle, native run handles, lazy model factories and UI request limits                             |
| `api/app.py`                                     | Factory, lifespan, service composition, worker ownership, access/error handling, static SPA       |
| `api/routes.py`                                  | Thin versioned HTTP routes                                                                        |

`create_app(settings)` accepts explicit Settings, making tests independent of the developer's `.env`. Lifespan creates service instances, initializes storage, and owns separate paper-strategy, news and account-import workers. Shutdown waits for an in-flight account read before closing its transport. Importing the package does not connect to an exchange or initialize a model.

Account history now has a persistent fill ledger and resumable selected-market imports for Demo, Binance/Binance.US/Testnet, Coinbase Advanced Trade/Sandbox and Kraken. Open **Trade → Account history** or its connected-account shortcut in Settings. Imports retain native IDs, fee currencies and rebates, with pause/resume, restart recovery and explicit coverage limits. Imports never place orders. The Performance view computes retained exact-market FIFO, with editable opening inventory, fee coverage, optional balance-checked current marks, CSV summaries and contextual Accountant assistance. Full cash-flow-adjusted account returns remain future work. See [account synchronization](docs/docs/developers/account-sync.md) and [account performance](docs/docs/developers/account-performance.md).

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

### Retained market history and interactive charts

**Markets → History & datasets** inspects locally retained exact-source candles, imports reviewed historical ranges with pause/resume/restart checkpoints, reports gaps and supports deliberate retention. Complete ranges can be frozen into immutable datasets with content fingerprints and JSON export. Backtests now retain their exact input; saved-dataset runs work offline with up to 20,000 consecutive candles. Line/candlestick charts add zoom, drag-to-pan, OHLCV inspection, volume, a navigator and visible CSV export, with at most 600 candles rendered and no new charting dependency. See the [user guide](docs/docs/guides/market-history.md), [backend contracts](docs/docs/developers/candle-history.md) and [updated pending checklist](docs/docs/developers/backend-roadmap.md).

### Provider reliability and diagnostics

Market-owned clients share read admission, conservative transport spacing, bounded concurrency and cooldowns. Interactive reads precede queued background work; identical market cache misses coalesce. **Settings → Market data → Source health** separates connectivity from quote freshness and shows safe errors, response times and queue counts without probing providers. Demo stays explicitly offline. Session counters reset on restart; bounded hourly read history, timings and sanitized errors persist locally, alongside import checkpoints. Expand a source to inspect 24-hour or 7-day history. These observations measure actual read traffic, not uptime or current credential validity. See [provider control and remaining scope](docs/docs/developers/provider-control.md).

### Market statistics

**Markets** now includes server-calculated returns/distributions, trend/momentum, volatility, sample drawdowns and tail risk, volume/flow and mechanical price references. An explainable technical-bias score exposes its votes and weights; it rates direction, not investment quality or profit probability. Gaps, stale samples and insufficient inputs are explicit. Charts support drag-to-select time-region zoom, pan, reset and CSV export with no new chart library. Statistics retain the full consecutive analysis sample when you zoom. See [metrics, formulas and score rules](docs/docs/guides/market-statistics.md).

### Strategy notifications

**Alerts → Strategy alerts** watches future journal events from a selected paper or exchange run: pauses/errors/recovery, resumes/stops and completion. Rules have revision-checked edit/pause/resume/archive controls; armed cursors and notifications commit together for restart catch-up without duplicates. The shared inbox/bell retains original event evidence and links to the exact monitor, with Paper/Exchange and Demo/test attribution. **Run alerts** opens setup from a monitor. Alerts make no provider calls, change no execution controls and deliver only inside Sibyl. See [setup and limits](docs/docs/guides/alerts.md#strategy-alerts) and [backend contracts](docs/docs/developers/alerts.md#strategy-journal-subscriptions).

**Alerts → Connections** watches consecutive recorded transport failures and successful reads of the same operation, without polling or activating sources. Configurable thresholds, revision-checked controls, bounded evidence and atomic cursor/inbox commits support restart catch-up. Notices share the bell/inbox and retain original observation times; they do not establish uptime, current credentials or data validity. Source health links to setup, and Technician can read the evidence through ProtoLink. See [setup and limits](docs/docs/guides/alerts.md#connection-read-failure-alerts) and [contracts](docs/docs/developers/alerts.md#connection-read-subscriptions).

**Alerts → Account risk** watches fixed account groups for a value floor, asset concentration or drawdown from an observed value peak. Complete fresh spot valuation is required; missing coverage never triggers a partial-total notice. Recovery levels, cooldowns, revision-checked controls, retained snapshots and native read-only Accountant tools are implemented. **Risk alerts** opens setup from Account. These notices never control trading; observed-value drawdown includes cash movements and is not investment return. See [setup](docs/docs/guides/account-risk.md), [backend contracts](docs/docs/developers/account-risk.md) and the [updated pending checklist](docs/docs/developers/backend-roadmap.md).

ProtoLink **0.8.3** now owns blocking tool execution, lazy per-request models, private request context, owned local consultations, session history and correlated execution reports. Sibyl retains its domain services and UI chat records. Each reply includes a native `run_id`; `/api/v1/agents/runs/{run_id}` reads the retained report. See [agent runtime contracts](docs/docs/developers/agents.md).
