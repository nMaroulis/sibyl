# Backend implementation checklist

This is an audit of the current Python backend, not a release schedule. **The main dashboard modules already have backend services.** Most remaining work extends those services or connects them into complete workflows. Optional product expansions are identified separately.

## Working foundations

- FastAPI routes, validated inputs, SQLite persistence and an encrypted credential vault.
- Twenty production spot-exchange clients, Binance Testnet, Coinbase Exchange Sandbox, and the persistent offline Demo account.
- Public markets, candles, order-book snapshots, indicators, correlations and account balance reads.
- Portfolio/account views, allocation, observed account-value snapshots and explicit unpriced holdings.
- Manual paper orders and guarded manual market orders for Binance, Coinbase, Kraken and the two dedicated test clients.
- Six rule-based strategies, historical backtests, durable paper jobs and their detailed monitor/journal.
- Ten ProtoLink module agents with prompts, contextual read-only tools, saved conversations and optional LLM inference.
- Encrypted LLM provider profiles, saved API keys and preset/custom model selection.
- Multi-publisher news ingestion, a persistent archive and filtered text sentiment, fetched crypto profiles/history, a glossary, recent Bitcoin blocks and optional equity research.

A paper strategy can consume live prices while still using virtual funds. Its running monitor does **not** mean it places exchange orders. Authenticated exchange acceptance testing remains outstanding despite implemented adapters and automated contract tests.

## Core data and trading work

### 1. Account synchronization — partial

There are on-demand balances, bounded fill/order reads, and a durable normalized fill ledger with background imports for seven clients/environments. See [account synchronization](account-sync.md). These are not a complete reconciled account history.

- [x] Persist normalized fills, native order references, fee currencies and rebates in a shared ledger.
- [x] Add durable native pagination and incremental imports for Demo, Binance, Binance.US, Binance Testnet, Coinbase Advanced Trade, Coinbase Sandbox and Kraken.
- [ ] Review durable import pagination for the remaining exchange providers.
- [ ] Persist and synchronize complete exchange order lifecycles alongside fills.
- [ ] Import deposits, withdrawals, transfers, fees and rebates.
- [x] Track per-market progress, successful pages/completed passes, failures and bounded retries; support pause/resume and restart recovery.
- [ ] Add full rescans, cash-event coverage and reconciliation status.
- [ ] Reconcile remote records with locally submitted intents after disconnects or restarts.
- [ ] Exercise authenticated reads and sandbox order lifecycles against actual test accounts.

### 2. Portfolio valuation and performance — partial

Current valuation uses the six-asset reference watchlist plus approximate USD-stablecoin parity. Other quantities are reported as unpriced. The live history chart records observed account values and includes cash-flow effects.

- [ ] Price arbitrary held assets through explicit quote/conversion routes.
- [ ] Fetch actual stablecoin and fiat conversion rates instead of assuming parity.
- [ ] Calculate realized/unrealized exchange P&L from imported fills and fees.
- [ ] Handle opening inventory/cost basis and incomplete history explicitly.
- [ ] Separate deposits/withdrawals from investment performance; implement cash-flow-aware returns.
- [ ] Extend wallet coverage to funding, earn/staking, subaccounts and supported unified-account variants.

### 3. Order management — partial

Manual market-order previews, confirmation, expiry and at-most-once submission attempts exist. Status refresh is explicit, and ambiguous outcomes are not retried automatically.

- [ ] Review and enable execution for the remaining production providers; most added adapters are read-only.
- [ ] Add cancel/replace and resting limit-order lifecycle management.
- [ ] Add stop, take-profit, trailing, OCO, time-in-force, post-only and iceberg support where the venue permits it.
- [ ] Synchronize partial fills, final fees, rejects and cancellations into the account ledger.
- [ ] Reconcile uncertain submissions by supported provider order/client-ID lookups.

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

- [ ] Persist historical OHLCV with paginated backfill, retention and gap detection.
- [ ] Add WebSocket market and account/order subscriptions with reconnection handling.
- [ ] Centralize provider rate budgets, bounded concurrency and read-side backoff.
- [ ] Expose stale/unavailable market-data state and provider health consistently.
- [ ] Support reference data beyond the fixed watchlist without unbounded provider requests.

### 6. Strategy research — partial

Six configurable strategies, fee/slippage-aware backtests, performance metrics and a paper monitor are implemented.

- [ ] Add walk-forward/out-of-sample evaluation and parameter optimization.
- [ ] Compare strategy versions against explicit benchmarks and retained datasets.
- [ ] Add multi-asset strategy execution and allocation rules if required.
- [ ] Define a plugin contract for custom strategies and optional Freqtrade integration.
- [ ] Implement the planned ML/RL strategies with their own training/evaluation pipeline.

## AI and research work

### 7. ProtoLink workflows — partial

The agents are real ProtoLink agents with page context and read-only domain tools. They are request-driven assistants. Each module currently exposes one main tool, and one active workspace model profile is selected for inference.

- [ ] Give modules richer, narrowly scoped tools for multi-step investigations.
- [ ] Add explicit delegation/orchestration between modules where it improves a workflow.
- [ ] Add scheduled agent runs, durable task state and resumable long-running work.
- [ ] Add per-agent model/provider selection if different modules need different models.
- [ ] Add streaming responses and inspectable tool traces, usage and evaluation results.
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

### 11. Alerts and operational jobs — missing

- [ ] Implement durable price, portfolio-risk, strategy and connection-failure alert rules.
- [ ] Add notification history, deduplication, delivery state and user-configured delivery integrations.
- [ ] Add a job queue/scheduler for imports, alerts and other tasks that should outlive an HTTP request.
- [ ] Add structured application/provider metrics, tracing and operational diagnostics beyond basic health/log output.
- [ ] Add managed backup/restore and credential/key lifecycle tools.

### 12. Hosted/multi-user product — optional, missing

The present deployment is explicitly a single-user workspace with a bearer token and one API worker. These additions are necessary for a hosted multi-user product, not prerequisites for local use.

- [ ] User authentication, workspace ownership and per-account authorization.
- [ ] Role/permission enforcement and tenant-isolated data/vault handling.
- [ ] Database-backed job claims or a separate worker system before running multiple API workers.
- [ ] Deployment-specific rate limiting, retention, auditing and recovery operations.

Other optional expansions include derivatives, on-chain wallets/DeFi, exchange transfers, additional regional endpoints and managed local-model downloads/quantization. They should be scoped explicitly rather than counted as broken existing features.

## Suggested implementation order

1. **Account sync + normalized ledger**, validated first with exchange test accounts.
2. **Complete valuation + exchange P&L**, using that ledger rather than inferred history.
3. **Order lifecycle + execution reconciliation**, including limit/cancel support.
4. **Strategy execution on test environments + risk controls**, then deliberate production enablement.
5. **Richer ProtoLink tools, scheduled workflows and alerts**, operating on the synchronized data.
6. **Forecast training and advanced research modules**, followed by hosted infrastructure if that becomes the deployment goal.

The [feature coverage table](../guides/feature-coverage.md) tracks current user-facing scope. The [exchange reference](./exchange-clients.md) contains the provider matrix and exchange-specific backlog.
