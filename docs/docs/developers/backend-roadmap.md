# Backend implementation checklist

This is an audit of the current Python backend, not a release schedule. **The main dashboard modules already have backend services.** Most remaining work extends those services or connects them into complete workflows. Optional product expansions are identified separately.

## Audited snapshot — October 22, 2026

The dashboard’s **Coming soon → Implementation status** reads the same audited inventory through `GET /api/v1/roadmap`. This is a capability review, not a completion percentage or release schedule. Multi-user work is deferred and excluded from the local implementation sequence.

| Area                           | Current state | Next missing foundation                                                                               |
| ------------------------------ | ------------- | ----------------------------------------------------------------------------------------------------- |
| Account synchronization        | partial       | Import pagination and funding support for remaining providers; fiat, staking and subaccounts.         |
| Portfolio accounting           | partial       | Cross-market basis and historical third-currency/transfer-fee valuation.                              |
| Order management               | partial       | Broader discovery/recovery adapters, amendment handling and definitive fee/settlement reconciliation. |
| Market-data infrastructure     | partial       | Broader historical adapters, weighted quota policies, richer operational metrics and WebSockets.      |
| Alerts & local operations      | partial       | Portfolio-risk, strategy and connection-failure rules; operational diagnostics.                       |
| Automated strategy execution   | paper-only    | Bind strategies to exchange accounts and reconcile submitted orders/fills across restart.             |
| Strategy research              | partial       | Additional benchmarks, parameter optimization and walk-forward/out-of-sample tests.                   |
| Sibyl & messaging              | partial       | Token streaming, evaluated collaboration, resumable/scheduled investigations and messaging clients.   |
| ProtoLink workflows            | partial       | Richer scoped specialist tools, per-agent models and explicit approval/audit contracts.               |
| Forecasting                    | baseline      | Reproducible datasets, trained-model inference, artifacts and version registry.                       |
| Research & news                | partial       | Document ingestion, chunking, embeddings, hybrid RAG and cited web search.                            |
| Explorer, equities & analytics | basic         | Transaction/address inspection, historical datasets and additional chains.                            |
| Hosted multi-user support      | deferred      | User accounts, workspace ownership, permissions and tenant-isolated data/vaults.                      |

## Working foundations

- FastAPI routes, validated inputs, SQLite persistence and an encrypted credential vault.
- Twenty production spot-exchange clients, Binance Testnet, Coinbase Exchange Sandbox, and the persistent offline Demo account.
- Public markets, candles, order-book snapshots, indicators, correlations and account balance reads.
- Portfolio/account views, allocation, observed account-value snapshots and explicit unpriced holdings.
- Manual paper orders, virtual resting limits and guarded manual market/GTC limit orders for Binance, Coinbase, Kraken and the two dedicated test clients.
- Six rule-based strategies, historical backtests, durable paper jobs and their detailed monitor/journal.
- Sibyl orchestration and ten ProtoLink module agents with a startup runtime registry, client routing, contextual read-only tools, saved conversations and consultation evidence.
- Live Sibyl consultation progress, request-specific cancellation and retained outcomes/evidence for completed, stopped, failed or interrupted requests. Startup marks unfinished requests interrupted without replaying them.
- Encrypted LLM provider profiles, saved API keys and preset/custom model selection.
- Durable editable source-pinned level/crossing alerts with reset-based repetition, a persistent unread in-app inbox and sanitized retry/backoff evidence.
- Multi-publisher news ingestion, a persistent archive and filtered text sentiment, fetched crypto profiles/history, a glossary, recent Bitcoin blocks and optional equity research.

A paper strategy can consume live prices while still using virtual funds. Its running monitor does **not** mean it places exchange orders. Authenticated exchange acceptance testing remains outstanding despite implemented adapters and automated contract tests.

## Core data and trading work

### 1. Account synchronization — partial

There are on-demand balances, bounded fill/order reads, and a durable normalized fill ledger with background imports for seven clients/environments. See [account synchronization](account-sync.md). These are not a complete reconciled account history.

- [x] Persist normalized fills, native order references, fee currencies and rebates in a shared ledger.
- [x] Add durable native pagination and incremental imports for Demo, Binance, Binance.US, Binance Testnet, Coinbase Advanced Trade, Coinbase Sandbox and Kraken.
- [ ] Review durable import pagination for the remaining exchange providers.
- [x] Discover open/recent orders for the reviewed execution clients, retain native observations and link known Sibyl intents and shared fills. See [order discovery](order-discovery.md).
- [ ] Expand discovery beyond the reviewed providers/ranges and handle complete amendment/lifecycle history.
- [x] Add a normalized funding ledger and read-only range imports for Binance crypto deposits/withdrawals and Kraken deposit/withdrawal/transfer entries, retaining fee/rebate and status coverage. See [funding history](funding-history.md).
- [ ] Extend funding adapters to remaining exchanges, fiat, earn/staking and subaccounts; reconcile late/pending events.
- [x] Add bounded transfer suggestions, manual pairing, audited user confirmation, stale-source review and reversible link removal/restoration. See [transfer review](transfer-reconciliation.md).
- [x] Carry original acquisition lots/cost basis for current confirmed equal-amount, explicitly zero-fee transfers in one unambiguous exact market. See [carryover scope](transfer-cost-basis.md).
- [x] Add explicit balanced same-asset fee allocations, missing-fee assertions, distinct-charge acknowledgment and separate fee-unit inventory cost. See [transfer fees](transfer-fees.md).
- [ ] Add historical fee valuation, other fee currencies/rebates, split/merged transfers, cross-market basis and reviewed external-funding classifications.
- [x] Track per-market progress, successful pages/completed passes, failures and bounded retries; support pause/resume and restart recovery.
- [ ] Add full rescans, cash-event coverage and reconciliation status.
- [x] Match discovered native IDs to local submissions and resume saved discovery pages after restart; uncertain client IDs stay on the reviewed recovery path.
- [ ] Exercise authenticated reads and sandbox order lifecycles against actual test accounts.

### 2. Portfolio valuation and performance — partial

Valuation now discovers direct, inverse and short bridge routes for held assets from the selected feed, independently of watchlists. It uses observed stablecoin/fiat conversions, exposes paths and quote quality, and reports unavailable coverage explicitly. Historical observations require complete reads. See [portfolio valuation](portfolio-valuation.md).

- [x] Price arbitrary held assets through explicit quote/conversion routes, within the selected feed catalog and bounded read budgets.
- [x] Use observed native stablecoin and fiat conversion rates instead of assuming parity; unavailable routes remain unpriced.
- [x] Compute retained exact-market FIFO with base/quote fees and explicit gaps; offer balance-checked current reference marks. See [account performance](account-performance.md).
- [ ] Reconstruct cross-market cost basis and historical third-currency fee conversions for complete exchange P&L.
- [x] Persist audited opening quantity/cost assertions and disclose unknown basis, ambiguous ordering and incomplete coverage.
- [ ] Separate deposits/withdrawals from investment performance; implement cash-flow-aware returns.
- [ ] Extend wallet coverage to funding, earn/staking, subaccounts and supported unified-account variants.

### 3. Order management — partial

Reviewed market/GTC limit orders, exact precision checks, durable cancellation reviews, cumulative fill observations and restart-safe REST tracking are implemented for the existing execution allowlist. Demo reserves funds and matches/cancels virtual resting orders. Ambiguous writes are never automatically retried. See [order management](order-management.md).

Known orders now import native execution pages into the shared Account history ledger, compare quantity/cost and expose fee gaps in an in-place dialog. Three bounded terminal passes can pick up delayed evidence. [Client-ID recovery](order-recovery.md) now handles uncertain submissions on the reviewed clients with exact-detail checks and restart-safe bounded lookups; missing/ambiguous evidence remains uncertain. Complete settlement, broader provider support and authenticated acceptance remain pending. See [order/fill reconciliation](order-reconciliation.md).

- [ ] Review and enable execution for the remaining production providers; most added adapters are read-only.
- [x] Add GTC limit intents, typed cancellation, cumulative partial-fill monitoring and persisted automatic status checks.
- [ ] Add cancel/replace with venue-specific atomicity and reservation semantics.
- [ ] Add stop, take-profit, trailing, OCO, additional time-in-force, post-only and iceberg support where the venue permits it.
- [x] Import native individual fills for confirmed local orders, share history-ledger identities, compare cumulative quantities/costs and report fee gaps; retain lifecycle cancellation/rejection observations. See [order reconciliation](order-reconciliation.md).
- [x] Add combined/per-account open and recent order discovery for Binance/Testnet, Coinbase Advanced/Sandbox, Kraken and Demo, with read-only imported rows, persistent progress, filters and shared fill evidence. See [discovery coverage](order-discovery.md).
- [ ] Extend bounded late-fee checks to definitive settlement, execution bust/removal handling and broader discovery/adapters.
- [x] Recover uncertain submissions using reviewed client-ID lookups, immutable-detail validation, bounded persisted pagination and explicit abstention on missing/ambiguous evidence.
- [ ] Exercise authenticated recovery on actual sandbox/provider accounts, including delayed indexing, external amendments, permissions and retention.

### 4. Automated strategy execution — missing

The existing persistent strategy worker is paper-only.

- [ ] Bind a strategy run to a specific account, environment and execution broker.
- [ ] Implement a deliberate execution mode progression: paper, exchange test environment, production.
- [ ] Translate strategy decisions into reviewed execution intents and reconcile actual fills.
- [ ] Persist outstanding orders and recover coherently after process crashes or connectivity loss.
- [ ] Define stop/pause behavior for outstanding orders and existing positions.
- [ ] Add position/exposure limits, daily-loss limits and a kill switch before production automation.

### 5. Market-data infrastructure — partial

The backend uses cached REST snapshots, source-specific catalogs/capabilities and provider-sized candle pages. Settings selects public exchanges, saved account environments, or CryptoCompare/CoinGecko APIs with encrypted keys. Markets supports temporary overrides, exact pair analysis, timestamp/stale labels and quotes-only feeds. See [Market data](market-data.md).

- [x] Persist exact-source OHLCV, reviewed resumable backfills, coverage gaps, manual retention and immutable research snapshots. See [candle history](candle-history.md).
- [ ] Review historical pagination for the remaining providers and exercise authenticated provider acceptance.
- [ ] Add WebSocket market and account/order subscriptions with reconnection handling.
- [x] Add shared local read admission, bounded HTTP concurrency, conservative cross-client spacing and read-side cooldowns. See [provider control](provider-control.md).
- [ ] Review exact endpoint-weight/IP/account quota policies; coordinate multiple processes if hosted.
- [x] Expose observed connectivity, separate quote freshness, sanitized errors and queue state in Settings and feed status lines. Live session counters reset on API restart.
- [x] Persist bounded hourly HTTP read outcomes, success rate, mean/peak response time and sanitized errors; inspect 24-hour/7-day windows across restart. History never establishes current credential readiness or uptime. See [retained read history](provider-control.md#retained-read-history).
- [ ] Add richer latency distributions and application-wide operational metrics. Continuous availability monitoring remains a separate future capability.
- [x] Support held-asset valuation and editable watchlists beyond the six defaults with bounded provider reads; broader aggregator discovery remains future work.

### 6. Strategy research — partial

Six configurable strategies, fee/slippage-aware backtests, performance metrics and a paper monitor are implemented.

- [ ] Add walk-forward/out-of-sample evaluation and parameter optimization.
- [x] Retain immutable input datasets and enable offline backtest replay with recorded fingerprints and engine version; current-feed runs also retain their inputs.
- [ ] Add additional explicit benchmarks and strategy-version comparisons.
- [ ] Add multi-asset strategy execution and allocation rules if required.
- [ ] Define a plugin contract for custom strategies and optional Freqtrade integration.
- [ ] Implement the planned ML/RL strategies with their own training/evaluation pipeline.

## AI and research work

### 7. Sibyl and ProtoLink workflows — partial

Sibyl and the ten specialists start as native ProtoLink Agents with `.start()` and registry discovery. Each has its own file and prompt. ProtoLink automatically supplies discovered agents and handles native delegation for Sibyl; direct module requests use their specialist client. The agents have page context and read-only domain tools. They are request-driven assistants. Models choose evidence tools on demand. Reporter has cached news/article/source/index tools; Technician has setup guides and provider-specific instructions; other specialists include relevant method and capability help. One active workspace model profile is selected for inference.

- [x] Split each agent into its own native declaration with prompt and typed tools; remove consult gateways and per-request Agent construction.
- [x] Add on-demand evidence tools, cached Reporter reads and practical Technician setup guides.
- [ ] Expand investigations with deeper source-specific tools as domain features become available.
- [x] Sibyl uses native ProtoLink discovery/delegation, with delegation disabled for specialists; saved chats include collaboration evidence.
- [x] Show live consultation lifecycle events, allow stopping the exact queued/running request, and retain request outcomes and completed consultation evidence separately from successful chat turns.
- [x] Mark unfinished requests interrupted on startup; block late consultations/answers after Stop and preserve already committed answers.
- [ ] Add scheduled investigations and resumable long-running work. Retained request history is an audit, not workflow resumption.
- [ ] Add per-agent model/provider selection if different modules need different models.
- [ ] Add token-by-token answers, deeper internal tool traces, usage/cost reporting and evaluated routing/grounding. Current progress is lifecycle polling rather than token streaming.
- [ ] Implement WhatsApp, Telegram, Discord, Slack, Signal and Email clients, authenticated sender binding, conversation mapping and reliable delivery/retries. Settings previews the required fields without accepting credentials; all channels remain unavailable.
- [ ] Design approval/action contracts and audit records before introducing mutation tools.

### 8. Forecasting / Chronos — baseline only

The current forecast is an untrained log-return statistical baseline. It does not load or run the old TensorFlow models.

- [ ] Implement reproducible dataset preparation and model training.
- [ ] Add trained-model inference, model artifacts/versioning and a registry.
- [ ] Add out-of-sample comparisons, forecast calibration and drift monitoring.
- [ ] Connect the UI to actual model results and make baseline/model distinctions explicit.

### 9. Research knowledge and news — partial

Crypto profiles/history are fetched by the backend. Knowledge search is a curated glossary. News has five publisher RSS/Atom adapters, retained excerpts, deduplication, source health, backend filters, extractive summaries, VADER distributions/trends and contextual Reporter tools. See the [news backend](news.md).

- [ ] Add document ingestion, chunking, embeddings and retrieval storage.
- [ ] Implement hybrid RAG with attributable citations and optional web-search tools.
- [x] Add multiple news providers, deduplication, retained history, source health and filtered sentiment evidence.
- [ ] Add licensed full-article processing and evaluated finance-trained/entity-targeted sentiment models.
- [ ] Add configurable external research API credentials/endpoints where integrations need them.

### 10. Explorer, equities and advanced analytics — basic implementations

Recent Bitcoin blocks, optional equity quotes/history/statistics and Pearson/Spearman correlation exist.

- [ ] Add transaction/address inspection, historical chain datasets and additional chains.
- [ ] Implement the planned public-official portfolio/disclosure archive.
- [ ] Add distance correlation, MIC, Granger causality, regression and SHAP only with clear statistical assumptions.

## Cross-cutting and optional expansion

### 11. Alerts and operational jobs — partial

Basic [price alerts and the local inbox](alerts.md) are implemented. Their worker is a bounded domain loop, not a general-purpose job scheduler.

- [x] Persist exact-pair, source-pinned one-shot price rules, Demo attribution, pause/rearm/archive/restore and a 50-rule non-archived budget.
- [x] Evaluate fresh timestamped quotes with persisted scheduling/backoff; atomically save a trigger and its notification, including across restart and lifecycle races.
- [x] Add retained in-app notification history, pagination, unread/read state and a top-bar inbox alongside existing run activity.
- [x] Add revision-checked edits that save paused, inclusive level/observed crossing conditions, reset-based recurrence and persisted cooldowns; preserve original notification evidence.
- [ ] Add portfolio-risk, strategy and connection-failure conditions.
- [ ] Add optional external delivery integrations with explicit recipients, delivery attempts and retries.
- [ ] Add a general job queue/scheduler for tasks beyond the current domain workers.
- [ ] Add structured application/provider metrics, tracing and operational diagnostics beyond basic health/log output.
- [ ] Add managed backup/restore, notification retention/export and credential/key lifecycle tools.

### 12. Hosted/multi-user product — deferred

**Deferred by user request.** These items remain visible in Coming soon and are excluded from current implementation priorities. The present deployment is explicitly a single-user workspace with a bearer token and one API worker. These additions are necessary for a hosted multi-user product, not prerequisites for local use.

- [ ] User authentication, workspace ownership and per-account authorization.
- [ ] Role/permission enforcement and tenant-isolated data/vault handling.
- [ ] Database-backed job claims or a separate worker system before running multiple API workers.
- [ ] Deployment-specific rate limiting, retention, auditing and recovery operations.

Other optional expansions include derivatives, on-chain wallets/DeFi, exchange transfers, additional regional endpoints and managed local-model downloads/quantization. They should be scoped explicitly rather than counted as broken existing features.

## Local implementation sequence

1. **Market-data foundations:** durable candle archive, bounded backfills, gap/health diagnostics and shared read budgets.
2. **Expand synchronized accounting:** remaining provider imports/funding, fee conversion and complete reconciliation; validate authenticated test-account behavior.
3. **Close the order loop:** authenticated acceptance of status/fill/recovery/discovery, broader adapters and final-fee reconciliation, then provider-specific conditional and cancel/replace orders.
4. **Build on local alerts:** portfolio/strategy/connection conditions and operational diagnostics, then explicit external delivery and backup/restore.
5. **Sibyl and richer ProtoLink tools:** evaluated collaboration, scoped specialist tools, per-agent models and resumable investigations. Messaging clients remain a separately scoped future integration.
6. **Test-environment strategies:** reconcile actual orders/fills and implement risk controls before any production automation.
7. **Trained forecasts and advanced research:** benchmarked models, RAG, explorer/equities expansions and custom strategies.

Multi-user hosting is deferred. No user accounts, permissions, tenant isolation or distributed-worker work is included in this sequence.

The [feature coverage table](../guides/feature-coverage.md) tracks current user-facing scope. The [exchange reference](./exchange-clients.md) contains the provider matrix and exchange-specific backlog.
