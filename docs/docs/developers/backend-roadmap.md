# Backend implementation checklist

This is an audit of the current Python backend, not a release schedule. **The main dashboard modules already have backend services.** Most remaining work extends those services or connects them into complete workflows. Optional product expansions are identified separately.

## Audited snapshot — November 6, 2026

The dashboard’s **Coming soon → Implementation status** reads the same audited inventory through `GET /api/v1/roadmap`. This is a capability review, not a completion percentage or release schedule. Unchecked entries bundle broad follow-up scopes and acceptance work; completing an extension does not necessarily close its whole parent entry. Multi-user work is deferred and excluded from the local implementation sequence.

| Area                           | Current state | Next missing foundation                                                                                                    |
| ------------------------------ | ------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Account synchronization        | partial       | Import pagination and funding support for remaining providers; fiat, staking and subaccounts.                              |
| Portfolio accounting           | partial       | Cross-market basis and historical third-currency/transfer-fee valuation.                                                   |
| Order management               | partial       | Broader conditional/replacement adapters, amendment handling and definitive fee/settlement reconciliation.                 |
| Market-data infrastructure     | partial       | Broader historical adapters, quota metrics and private/additional-provider WebSockets.                                     |
| Alerts & local operations      | partial       | Broader risk metrics, external uptime monitoring, tracing and more delivery channels.                                      |
| Automated strategy execution   | partial       | Broader venue/failure-case acceptance, risk policies, residual exit handling and fee valuation.                            |
| Strategy research              | partial       | Continuous deployment simulation and broader optimization; nested chronological selection is implemented.                                              |
| Sibyl & messaging              | partial       | Native answer-only streaming for JSON-mode models, evaluated collaboration, resumable investigations and additional messaging clients.                       |
| ProtoLink workflows            | partial       | Richer scoped specialist tools, evaluated routing and explicit approval/audit contracts.                                   |
| Forecasting                    | partial       | More model families, automatic recalibration and calibrated drift monitoring; prospective outcome tracking is implemented. |
| Research & news                | partial       | Broader semantic quality evaluation, hosted embeddings, calibrated relevance and cited web search.                         |
| Explorer, equities & analytics | partial       | Historical chain datasets, additional chains, wallet aggregation and disclosure archives.                                  |
| Hosted multi-user support      | deferred      | User accounts, workspace ownership, permissions and tenant-isolated data/vaults.                                           |

## Working foundations

- FastAPI routes, validated inputs, SQLite persistence and an encrypted credential vault.
- Twenty production spot-exchange clients, Binance Testnet, Coinbase Exchange Sandbox, and the persistent offline Demo account.
- Public markets, candles, order-book snapshots, indicators, correlations and account balance reads.
- Portfolio/account views, allocation, observed account-value snapshots and explicit unpriced holdings.
- Manual paper orders, virtual resting limits and guarded manual market/GTC limit orders for Binance, Binance.US, Coinbase, Kraken, OKX, Bybit UTA, KuCoin classic, Bitstamp and the two dedicated test clients; GTC limits and cancellation for Gemini. Settings shows app-level support and gaps per exchange.
- Six rule-based strategies, cost-aware historical backtests, exact-input reruns, chart execution overlays, round-trip accounting, comparable saved runs and explicit Demo research/paper runs.
- Sibyl orchestration and ten ProtoLink module agents with a startup runtime registry, client routing, contextual read-only tools, saved conversations and consultation evidence.
- Live Sibyl consultation progress, request-specific cancellation and retained outcomes/evidence for completed, stopped, failed or interrupted requests. Startup marks unfinished requests interrupted without replaying them.
- Encrypted LLM provider profiles, saved API keys and preset/custom model selection.
- Durable editable source-pinned level/crossing alerts, strategy journal subscriptions and per-operation connection read-failure/recovery watches; a shared persistent unread in-app inbox and bounded sanitized evidence.
- Multi-publisher news ingestion, a persistent archive and filtered text sentiment, fetched crypto profiles/history, a glossary, Bitcoin transaction/address inspection and recent blocks, plus optional equity research.

A paper strategy can consume live prices while still using virtual funds. Its running monitor does **not** mean it places exchange orders. Initial authenticated balance reads, manual Binance Testnet orders and automated strategy entry/exit/restart with controlled lost-response recovery are recorded in [exchange acceptance](exchange-acceptance.md). Partial-fill/cancellation-race acceptance, broader venues and production execution acceptance remain outstanding.

## Core data and trading work

### 1. Account synchronization — partial

There are on-demand balances, bounded fill/order reads, and a durable normalized fill ledger with background imports including Bitstamp and Gemini, with provider retention shown in the UI. See [account synchronization](account-sync.md). These are not a complete reconciled account history.

- [x] Persist normalized fills, native order references, fee currencies and rebates in a shared ledger.
- [x] Add explicit observed balance checkpoints and per-asset quantity comparisons across imported markets, native fees/rebates and eligible funding, with gap/timing/scope checks, saved reports, CSV export and read-only Accountant evidence. See [balance checks](balance-checks.md). This does not establish complete account history or settlement.
- [x] Apply documented Kraken ledger fee effects, retain Binance wallet/completion facts, and add source-version-checked local wallet/amount reviews for ambiguous funding; preserve native observations, audit withdrawal and provenance in Balance checks, exports and read-only Accountant evidence. See [funding effects](funding-effects.md).
- [x] Add durable native pagination and incremental imports for Demo, Binance, Binance.US, Binance Testnet, Coinbase Advanced Trade, Coinbase Exchange Sandbox, Kraken, OKX, Bybit UTA, KuCoin classic and Bitget classic.
- [ ] Review durable import pagination for the remaining exchange providers.
- [x] Discover open/recent orders for the reviewed execution clients, retain native observations and link known Sibyl intents and shared fills. See [order discovery](order-discovery.md).
- [ ] Expand discovery beyond the reviewed providers/ranges and handle complete amendment/lifecycle history.
- [x] Add a normalized funding ledger and read-only range imports for Binance crypto deposits/withdrawals, Kraken deposit/withdrawal/transfer entries and Bybit master-UID on-chain withdrawals, retaining fee/rebate and status coverage. See [funding history](funding-history.md).
- [x] Add opt-in, durable pending-record updates for Binance crypto deposits/withdrawals and Bybit on-chain withdrawals, independent of manual import ranges; bounded pagination/retries, missing-source review, control/account revision guards and read-only Accountant status. See [pending updates](funding-pending-updates.md).
- [x] Add opt-in rolling recent funding sync for implemented Binance/Kraken/Bybit streams, completed-record corrections, persistent fetched-window gaps, concurrent-source guards, lazy pass reports and append-only observed funding revisions across all imports. See [recent sync](funding-recent-sync.md). A bounded authenticated Binance deposit-history read is recorded; live correction behavior and other venues still need acceptance.
- [ ] Extend funding adapters to remaining exchanges, Bybit deposits/off-chain transfers, fiat, earn/staking and subaccounts; discover older arrivals/corrections outside selected lookbacks and implement native removal/bust semantics.
- [x] Add bounded transfer suggestions, manual pairing, audited user confirmation, stale-source review and reversible link removal/restoration. See [transfer review](transfer-reconciliation.md).
- [x] Carry original acquisition lots/cost basis for current confirmed equal-amount, explicitly zero-fee transfers in one unambiguous exact market. See [carryover scope](transfer-cost-basis.md).
- [x] Add explicit balanced same-asset fee allocations, missing-fee assertions, distinct-charge acknowledgment and separate fee-unit inventory cost. See [transfer fees](transfer-fees.md).
- [ ] Add historical fee valuation, other fee currencies/rebates, split/merged transfers, cross-market basis and reviewed external-funding classifications.
- [x] Track per-market progress, successful pages/completed passes, failures and bounded retries; support pause/resume and restart recovery.
- [x] Add available-history rescans, revision guards for stale in-flight responses, repeated-page protection, correction counts and retained execution ranges.
- [ ] Add complete cash-event coverage, account-wide balance reconciliation, execution bust/removal handling and versioned fill/order correction audits beyond observed funding revisions.
- [x] Match discovered native IDs to local submissions and resume saved discovery pages after restart; uncertain client IDs stay on the reviewed recovery path.
- [ ] Exercise authenticated reads and sandbox order lifecycles against actual test accounts.

### 2. Portfolio valuation and performance — partial

Valuation now discovers direct, inverse and short bridge routes for held assets from the selected feed, independently of watchlists. It uses observed stablecoin/fiat conversions, exposes paths and quote quality, and reports unavailable coverage explicitly. Historical observations require complete reads. See [portfolio valuation](portfolio-valuation.md).

- [x] Price arbitrary held assets through explicit quote/conversion routes, within the selected feed catalog and bounded read budgets.
- [x] Use observed native stablecoin and fiat conversion rates instead of assuming parity; unavailable routes remain unpriced.
- [x] Compute retained exact-market FIFO with base/quote fees and explicit gaps; offer balance-checked current reference marks. See [account performance](account-performance.md).
- [ ] Reconstruct cross-market cost basis and historical third-currency fee conversions for complete exchange P&L.
- [x] Persist audited opening quantity/cost assertions and disclose unknown basis, ambiguous ordering and incomplete coverage.
- [x] Add new measured periods with fresh opening/closing valuations, user-reviewed external flows, source-bound completeness assertions, manual missing-flow inputs and combined/per-account Modified Dietz estimates. See [measured evidence contracts](performance-outcomes-alerts.md).
- [ ] Automate independently verified historical flow conversion and wider wallet/accounting coverage; measured returns currently depend on explicit user assertions.
- [ ] Extend wallet coverage to funding, earn/staking, subaccounts and supported unified-account variants.

### 3. Order management — partial

Reviewed market/GTC limit orders, exact precision checks, durable cancellation reviews, cumulative fill observations and restart-safe REST tracking are implemented for the existing execution allowlist. Demo reserves funds and matches/cancels virtual resting orders. Ambiguous writes are never automatically retried. See [order management](order-management.md).

Known orders now import native execution pages into the shared Account history ledger, compare quantity/cost and expose fee gaps in an in-place dialog. Three bounded terminal passes can pick up delayed evidence. [Client-ID recovery](order-recovery.md) now handles uncertain submissions on the reviewed clients with exact-detail checks and restart-safe bounded lookups; missing/ambiguous evidence remains uncertain. Complete settlement, broader provider support and authenticated acceptance remain pending. See [order/fill reconciliation](order-reconciliation.md).

- [ ] Review and enable execution for the remaining production providers; most added adapters are read-only.
- [x] Add GTC limit intents, typed cancellation, cumulative partial-fill monitoring and persisted automatic status checks.
- [x] Add native Binance/Testnet unfilled-only manual GTC replacement with estimated reservation release, STOP_ON_FAILURE/ONLY_NEW, durable compound-command admission and retained non-atomic outcomes. See [advanced orders](advanced-orders.md).
- [ ] Extend replacement to additional providers, partially filled orders and complete amendment/lifecycle history.
- [x] Add native Binance/Testnet stop-loss/take-profit GTC limits and linked two-leg OCO, exact trigger validation, independent fill tracking and child-ID recovery after a lost response.
- [ ] Add these advanced orders to more providers; implement trailing, additional time-in-force, post-only and iceberg support.
- [x] Extend exact-order fill imports to OKX, Bybit UTA and KuCoin classic; retain their provider limits and fee gaps. Bitstamp/Gemini now also have bounded native imports and exact-order reconciliation, with explicit saturation/reversal/retention limits.
- [x] Import native individual fills for confirmed local orders, share history-ledger identities, compare cumulative quantities/costs and report fee gaps; retain lifecycle cancellation/rejection observations. See [order reconciliation](order-reconciliation.md).
- [x] Add combined/per-account open and recent order discovery for Binance/Testnet, Coinbase Advanced/Sandbox, Kraken and Demo, with read-only imported rows, persistent progress, filters and shared fill evidence. See [discovery coverage](order-discovery.md).
- [ ] Extend bounded late-fee checks to definitive settlement, execution bust/removal handling and broader discovery/adapters.
- [x] Recover uncertain submissions using reviewed client-ID lookups, immutable-detail validation, bounded persisted pagination and explicit abstention on missing/ambiguous evidence.
- [x] Exercise actual Binance Testnet client-ID recovery after deliberately discarding a successful strategy-entry response, without a second buy.
- [x] Exercise real Testnet conditional open/cancel, native OCO with deliberately lost response, exact child recovery, sibling cancellation, unfilled cancel/replace, duplicate approval identities and a fill-winning marketable-limit observation. Intermediate partial fills, true outages, late fee corrections and other venues remain unaccepted.
- [ ] Extend authenticated recovery to delayed indexing, external amendments, permissions, retention and additional providers.

### 4. Automated strategy execution — partial

[Exchange strategy execution](../guides/strategy-execution.md) is implemented for nine provider/environment variants, alongside the isolated paper worker.

- [x] Bind a run to a fixed account, environment, exact pair and allocated budget with expiring typed approval.
- [x] Keep paper as the default; require both execution flags for exchange test/production runs.
- [x] Submit price-capped GTC intents through the shared at-most-once order pipeline and derive ownership from native fills/fees.
- [x] Persist plans/client IDs and pause on restart; reconcile existing orders without replaying old signals or uncertain writes.
- [x] Define Pause/Stop: prevent future submissions and retain holdings; previously approved expiry continues.
- [x] Persist optional order lifetimes at submission; cancel due remainders through the shared pipeline, retain partial fills and recover uncertain attempts by reading only.
- [x] Add separate typed Stop & cancel approval, durable restart recovery, bounded late native status checks, monitor evidence and journal/CSV events.
- [x] Add separately reviewed position exits for stopped/completed runs: current owned-fill evidence, fresh native book/funds/precision checks, guarded at-most-once submission and realized P&L/residual monitoring. Partial fills and native caps never cause automatic replacement sells.
- [x] Enforce per-order notional, allocated-loss latch, spread/freshness and rolling order-count limits; retain fee/precision dust explicitly.
- [x] Exercise the manual Binance Spot Testnet limit/cancel and market buy/sell lifecycle, native fills/fees, client-ID lookup, duplicate confirmations and retained state after restart; verify read access on one Binance and Coinbase production account.
- [x] Exercise real Binance Testnet strategy signals and capped orders, duplicate approvals, owned fill/fee accounting, paused restart, shared capital rejection, global halt and a separately reviewed owned-position exit; recover a deliberately discarded entry response by exact native client ID without resubmission.
- [x] Harden partial-fill/cancellation races with deterministic scenarios: matching follow-up counters, atomic per-order fill revisions, renewed checks after history-import corrections, invalidated exit readiness, final-submission guards, fill-before-cancel-rejection recovery, restart with writes off and idempotent reimports. Running strategies wait for cancellation evidence before another signal order. These are controlled application tests, not authenticated venue race acceptance.
- [ ] Extend authenticated acceptance to observed partial fills, cancellation/fill races, late corrections, real connectivity failures and other venues before deliberate production enablement. Controlled response loss does not establish general outage behavior.
- [x] Add a durable global strategy submission halt: atomically pause exchange runs, invalidate old reviews/unsent signal plans, enforce the shared write boundary, retain audit history and require revision-bound typed release. Release never resumes runs; approved cancellations/manual orders/separately reviewed exits remain available.
- [x] Add opt-in shared allocated-capital, gross-exposure and observed UTC daily-loss policies across accounts, separately for production/test funds; fresh actual conversion paths, retained/pending exposure, native-write transaction admission, persisted daily baselines/locks, deliberate later-day release, bounded audit and read-only Broker evidence. See [portfolio limits](portfolio-limits.md).
- [ ] Add broader policy options (asset/account concentration, configurable loss windows and risk sizing), archived-run accounting beyond current bounds, and distributed coordination. Any future automatic multi-order liquidation needs its own explicit policy; current residual exits need fresh reviews.
- [ ] Add reviewed residual/dust ownership handoff to new runs; value third-currency fees; reconcile/adopt manual position changes; handle definitive settlement/busts and more providers.

### 5. Market-data infrastructure — partial

The backend uses cached REST snapshots, source-specific catalogs/capabilities and provider-sized candle pages. Settings selects public exchanges, saved account environments, or CryptoCompare/CoinGecko APIs with encrypted keys. Markets supports temporary overrides, exact pair analysis, timestamp/stale labels and quotes-only feeds. Descriptive statistics, a versioned explainable technical-bias score and lightweight drag-region chart zoom are implemented; see [statistics scope and formulas](../guides/market-statistics.md). See [Market data](market-data.md).

- [x] Persist exact-source OHLCV, reviewed resumable backfills, coverage gaps, manual retention and immutable research snapshots. See [candle history](candle-history.md).
- [ ] Review historical pagination for the remaining providers and exercise authenticated provider acceptance.
- [x] Add on-demand Binance production/Testnet public ticker/candle WebSockets, shared bounded queues, reconnect/freshness status, exact-source REST fallback and native Analyst evidence. See [live previews](live-markets.md).
- [x] Add Kraken v2 public ticker/OHLC previews with exact symbols, native interval filtering, explicit receipt timing and shared lifecycle/fallback.
- [x] Add Coinbase production public tickers and native five-minute candle previews, connection-wide sequence checks, exact-product alias rejection and REST fallback.
- [ ] Add private account/order streams, additional public providers and persisted reconnect-gap recovery.
- [x] Add shared local read admission, bounded HTTP concurrency, conservative cross-client spacing and read-side cooldowns. See [provider control](provider-control.md).
- [ ] Review exact endpoint-weight/IP/account quota policies; coordinate multiple processes if hosted.
- [x] Expose observed connectivity, separate quote freshness, sanitized errors and queue state in Settings and feed status lines. Live session counters reset on API restart.
- [x] Persist bounded hourly HTTP read outcomes, success rate, mean/peak response time and sanitized errors; inspect 24-hour/7-day windows across restart. History never establishes current credential readiness or uptime. See [retained read history](provider-control.md#retained-read-history).
- [x] Add fixed provider latency histograms with p50/p95 upper bounds and legacy sample coverage, plus current-process CPU/memory/threads, database/WAL and free-volume metrics. External uptime and distributed tracing remain pending.
- [x] Support held-asset valuation and editable watchlists beyond the six defaults with bounded provider reads; broader aggregator discovery remains future work.

### 6. Strategy research — partial

Six configurable strategies, fee/slippage-aware backtests, performance metrics and a paper monitor are implemented.

- [x] Add bounded grid search, chronological holdout/expanding walk-forward evaluation, fixed-settings comparisons, recorded training rankings/test executions, exact-study reruns and Broker evidence tools. See [validation](../guides/strategy-validation.md).
- [x] Add reproducible seeded finite random search with an explicit candidate budget, full-space validation, coverage/fingerprints, saved plans, exact-study replay checks and native Broker evidence.
- [x] Add optional nested chronological candidate selection, retained inner metrics, bounded work and independent outer tests.
- [x] Add continuous single-market walk-forward replay carrying one cash/asset balance and entry cost across chosen-parameter windows, with actual fills, transition balances, fixed-setting comparison and native Broker evidence.
- [ ] Add multi-asset deployment/rebalancing and Bayesian/distribution-based optimization; repeated user experiments can still overfit.
- [x] Retain immutable input datasets and enable offline backtest replay with recorded fingerprints and engine version; current-feed runs also retain their inputs.
- [x] Add exact-window cost-aware cash, buy-and-hold, scheduled-installment and 50/50 asset/cash references, selectable equity overlays and actual cost/metric summaries. Saved same-input strategy comparisons remain available; continuous deployment simulation is separate.
- [ ] Add multi-asset strategy execution and allocation rules if required.
- [x] Add an explicitly enabled installed-Python research plugin contract, bounded numeric controls, causal prefix observations, source pins, actual cost-aware backtests, saved inputs/signals, exact reruns, charts/exports and Broker evidence.
- [ ] Extend custom plugins to validation/jobs when reviewed; optional Freqtrade integration remains pending.
- [ ] Implement the planned ML/RL strategies with their own training/evaluation pipeline.

## AI and research work

### 7. Sibyl and ProtoLink workflows — partial

Sibyl and the ten specialists start through ProtoLink 0.8.3 `AgentGroup` with registry discovery. Each has its own file and prompt. ProtoLink automatically supplies discovered agents and handles native delegation for Sibyl; module requests use native group handles for their registered specialist; owned local consultations inherit explicit private context. The agents have page context and read-only domain tools. They are request-driven assistants. Models choose evidence tools on demand. Every specialist has topic-based page help; Broker can also inspect retained order/fill reconciliation evidence. Tool descriptions explain purpose, arguments and returned information. Agents inherit a workspace model default or use an explicit per-agent provider/model override. Each request freezes the whole team’s configuration; profiles retain shared encrypted provider keys/endpoints.

- [x] Adopt ProtoLink 0.8.3 native thread execution, lazy model factories, private request context, group lifecycle, SQLite conversations and correlated report/evidence APIs. Remove application tool wrappers, LLM adapter and telemetry reconstruction; keep UI projections only.
- [x] Split each agent into its own native declaration with prompt and typed tools; remove consult gateways and per-request Agent construction.
- [x] Add on-demand evidence tools, cached Reporter reads and practical Technician setup guides.
- [x] Review model-facing tool docstrings; add typed, focused help/FAQ tools for every specialist, including Trade history, backtesting, chart controls and source setup. Keep instructions separate from observations and update guides with module changes.
- [x] Let Broker inspect bounded, filtered retained order/fill evidence, with native ProtoLink correction for invalid record selections and no provider refresh or mutation.
- [x] Add native Analyst live-stream evidence and Broker OCO/conditional/replacement evidence, with typed practical help and explicit read-only boundaries.
- [ ] Expand investigations with deeper source-specific tools as domain features become available.
- [x] Sibyl uses native ProtoLink discovery/delegation, with delegation disabled for specialists; saved chats include collaboration evidence.
- [x] Show live consultation lifecycle events, allow stopping the exact queued/running request, and retain request outcomes and completed consultation evidence separately from successful chat turns.
- [x] Mark unfinished requests interrupted on startup; block late consultations/answers after Stop and preserve already committed answers.
- [x] Add daily/weekly investigation calendars, time-zone/DST handling, frozen accepted model choices, bounded waiting, restart/missed-time handling, retention and explicit Telegram briefing delivery with real part outcomes. See [briefing contracts](briefings.md).
- [ ] Add resumable long-running work. Retained request history is an audit, not workflow resumption.
- [x] Add saved investigations with progressive starting context, native specialist collaboration, structured report validation, recorded source receipts, versioned reruns, comparison, JSON export, cancellation and restart interruption. See [report contracts](investigations.md). Reruns use newly available evidence; workflow resumption remains pending.
- [x] Add Ollama installation/server/model detection and explicit local server Start/Stop ownership controls, with setup links.
- [x] Add per-agent provider/model overrides with shared encrypted profiles, preset/custom IDs, revision-checked edits, frozen delegated request snapshots and accurate model attribution. See [contracts](agent-models.md).
- [x] Stream native tool/consultation lifecycle activity into browser chats; retain polling for reopened Sibyl requests and cancel native work on stream disconnect. Show safe on-demand run summaries with tool timing/outcomes and available per-call token/cost metrics, labeled estimated, partial or unavailable.
- [x] Run an initial real Ollama/Gemma acceptance pass for specialist evidence, native coordinator tool/inference consultations, memory/isolation, Stop and persistence; align provider/context-policy windows and preserve setup instructions in native previews. See [findings and remaining limits](agent-acceptance.md).
- [x] Add repeatable native ProtoLink evaluations with scoped specialist evidence, source/selection checks, missing-data and untrusted-excerpt cases, coordinator delegation receipts, bounded repetitions, private local fixtures, native report export and baseline score comparisons. Record actual small-model successes and coordinator failures. See [agent evaluation](agent-evaluation.md).
- [x] Use native correctable rejections for missing retained articles, trained models, strategy runs and investigations/calendars; preserve operational errors and selected-source boundaries. Broker's deterministic summaries distinguish paper, test and production exchange runs.
- [x] Display native-provider answer text progressively in Sibyl and module chats, with shared safe Markdown, root/child isolation, bounded previews, cross-chunk key masking, Stop and authoritative saved final replies. JSON-mode/action-like chunks wait for native final output.
- [ ] Add native answer-only deltas for JSON-mode providers upstream, broader provider/model and semantic-grounding evaluation and fix the [upstream owned-subagent metrics gap](protolink-metrics.md). Activity streaming does not expose raw model chunks or internal action JSON. Narrow contract checks do not establish general answer reliability.
- [x] Implement direct-HTTP Telegram polling, private-user binding, encrypted credentials, conversation mapping and durable delivery outcomes. Explicit rate limits retry; ambiguous sends never auto-retry.
- [x] Retain initial user-confirmed Telegram conversation acceptance. Automated briefing delivery is tested with a mock HTTP transport; real scheduled-delivery acceptance remains a deployment check.
- [x] Add app-origin Telegram delivery review with exact text/target inspection, unsent withdrawal and separate user acknowledgments preserving native outcomes.
- [x] Add grouped conversation-reply receipts, original-target metadata, exact text inspection, atomic unsent withdrawal, separate user acknowledgments and UTF-16-safe chunking.
- [x] Add opt-in outgoing UTF-8 text documents for long replies and scheduled briefings, with bounded complete content, original recipient binding and durable native outcomes.
- [ ] Add incoming Telegram documents, audio/photos and broader media. WhatsApp, Discord, Slack, Signal and Email remain unavailable previews.
- [ ] Design approval/action contracts and audit records before introducing mutation tools.

### 8. Forecasting / Chronos — partial

v2.1.0 adds direct autoregressive ridge models over immutable daily input, alongside the separate untrained baseline. See the [user workflow](../guides/forecasting.md) and [engine contracts](forecasting.md).

- [x] Implement reproducible daily dataset preparation and real numerical model fitting, with explicit synthetic Demo input through the same engine.
- [x] Add JSON coefficients/scalers, source and engine fingerprints, numbered model versions, exact-input reruns, current/saved-input inference and retained forecast observations.
- [x] Add chronological 60/20/20 training/calibration/test partitions, purged boundary-crossing targets, naive/drift comparisons and independent test metrics/empirical band coverage.
- [x] Connect the UI to trained results, explicit baseline/model tabs, test/forecast charts, exports and native read-only Chronos registry/report tools.
- [x] Expose descriptive lag-feature departures from training ranges without claiming a calibrated drift detector.
- [x] Add bounded expanding/fixed-window historical rolling evaluation of a saved recipe, with causal refits/calibration, purged test boundaries, pooled benchmark metrics, immutable reports/reruns, per-fold charts/exports and native Chronos evidence. This is historical research, not live forward performance.
- [x] Add prospective exact-source outcome tracking with original-save-time eligibility, corrected actual receipts, equal-horizon benchmarks, pause/resume, explicit refresh and native evidence.
- [x] Add bounded portable JSON model/input bundles with integrity validation, offline local refitting, unverified imported namespaces and deduplication; archive/restore model versions without deleting evidence or silently stopping monitors.
- [ ] Add calibrated drift monitoring, automated recalibration and larger managed lifecycles.
- [x] Add an optional causal returns-plus-context ridge recipe with six trailing-price features, retained through rolling evaluation, predictions and portable refits.
- [x] Add a small fixed-seed NumPy tanh neural model with training-only normalization, purged chronological calibration/testing, actual training-loss evidence, rolling refits and portable recipe validation.
- [ ] Add ARIMA and other neural/model families, additional inputs and larger evaluation studies. Historical held-out results do not establish future profitability.

### 9. Research knowledge and news — partial

Crypto profiles/history are fetched by the backend. Knowledge search is a curated glossary. News has five publisher RSS/Atom adapters, retained excerpts, deduplication, source health, backend filters, extractive summaries, VADER distributions/trends and contextual Reporter tools. See the [news backend](news.md).

- [x] Add bounded PDF/text/Markdown ingestion, original retention, page-bounded exact passages, SQLite full-text retrieval across uploads and retained news, stable citation management, source reader/delete/reindex controls and native Wiki/Reporter tools. See [library contracts](research-library.md).
- [x] Add optional local Ollama embeddings, bounded checkpointed indexing, cosine search, hybrid reciprocal-rank fusion, exact citations and native search/status tools with visible partial coverage and model-change rejection.
- [x] Add owner-labeled saved retrieval evaluations over pinned corpora/indexes, exact rankings/citations and precision/recall/MRR/nDCG/hit-rate reports.
- [ ] Evaluate semantic relevance and answer grounding across real models/corpora, add calibrated no-answer thresholds and support reviewed hosted embedding providers. Controlled-vector tests establish contracts, not real-model relevance.
- [ ] Add cited web-search tools; local hybrid retrieval is implemented.
- [x] Add multiple news providers, deduplication, retained history, source health and filtered sentiment evidence.
- [ ] Add licensed full-article processing and evaluated finance-trained/entity-targeted sentiment models.
- [ ] Add configurable external research API credentials/endpoints where integrations need them.

### 10. Explorer, equities and advanced analytics — partial

Recent Bitcoin blocks, mainnet transaction/address inspection, optional equity quotes/history/statistics and Pearson/Spearman/distance dependence and descriptive return regressions exist.

- [x] Add read-only mainnet transaction/address inspection with checksum validation, exact fee/confirmation evidence, paged inputs/outputs and confirmed activity, separate pending observations, source-labeled UI/exports, independent Demo and native Explorer tools. See [Bitcoin explorer contracts](bitcoin-explorer.md).
- [x] Add explicit, bounded Bitcoin output-spend observations with confirmed/pending/unspent/unknown states, spending-transaction links, page exports, synthetic graph examples and native Explorer tools. No spendability proof or durable watch is claimed.
- [ ] Add historical chain datasets, additional chains, wallet aggregation, durable spend/reorg watches and local chain verification.
- [ ] Implement the planned public-official portfolio/disclosure archive.
- [x] Add bounded unsigned distance dependence and same-interval return OLS, explicit undefined/gap states, scatter inspection/export and native Analyst evidence.
- [x] Add bounded fixed-order Granger tests with training-only classical inference, request-family adjustment, residual qualifications, independent later-target errors and exact-source UI/agent evidence.
- [ ] Add MIC, SHAP, robust/nonlinear causal inference and broader real-data/model evaluation.

## Cross-cutting and optional expansion

### Distribution — Python package ready; publication pending

The release path is a complete Python wheel and source archive published from the existing repository. Source checkout and local Docker Compose remain available. No Homebrew repository or registry is required; see [distribution](distribution.md).

- [x] Bundle React in wheels/source archives, resolve installed assets, add a per-user installed workspace and launcher, and preserve source workspaces.
- [x] Synchronize release metadata and lock entries in one version command; derive current docs/install examples from metadata while preserving history.
- [x] Exercise a clean installed wheel and add Linux, Windows and both Mac architectures to package CI.
- [x] Add a Python-package release workflow with dry-run artifacts, checksums and GitHub Release uploads.
- [ ] Complete remote CI acceptance and publish the wheel/source assets.
- [ ] Add Homebrew optionally after the package release; a recipe can live in this repository or a separate tap.
- [ ] Validate local Docker runtime and optionally publish prebuilt amd64/arm64 registry images in a separate workflow.
- [ ] Decide whether to claim a PyPI distribution name and configure trusted publishing.
- [ ] Consider signed desktop installers and optional background-service setup.

### 11. Alerts and operational jobs — partial

Basic [price, strategy and connection alerts](alerts.md), [account-risk watches](account-risk.md) and the local inbox are implemented. Their worker is a bounded domain loop, not a general-purpose job scheduler.

- [x] Persist exact-pair, source-pinned one-shot price rules, Demo attribution, pause/rearm/archive/restore and a 50-rule non-archived budget.
- [x] Evaluate fresh timestamped quotes with persisted scheduling/backoff; atomically save a trigger and its notification, including across restart and lifecycle races.
- [x] Add retained in-app notification history, pagination, unread/read state and a top-bar inbox alongside existing run activity.
- [x] Add revision-checked edits that save paused, inclusive level/observed crossing conditions, reset-based recurrence and persisted cooldowns; preserve original notification evidence.
- [x] Add per-run journal subscriptions for pauses/errors/recovery and lifecycle changes, atomic cursors/notifications, restart catch-up, revision-checked controls and monitor links. See [strategy alerts](alerts.md#strategy-journal-subscriptions).
- [x] Add connection read-failure/recovery rules per operation, bounded credential-free evidence, atomic cursor/inbox commits, restart catch-up and revision-checked controls. No polling/uptime claim; see [connection alerts](alerts.md#connection-read-subscriptions).
- [x] Add fixed-account-set value floors, asset concentration and observed-value drawdown watches with complete fresh valuation, recovery/cooldown, atomic evidence/inbox commits and read-only Accountant tools. See [account risk](account-risk.md).
- [x] Add per-account order/fill subscriptions over atomic local observation receipts, future-only controls, retained inbox and optional existing Telegram delivery.
- [x] Add whole-basket HHI/effective-asset/largest/top-three value concentration and optional HHI/top-three alerts, gated on complete fresh valuations.
- [x] Add saved explicit current-holding basket studies with observed historical conversion routes, consecutive sample covariance/correlations, volatility, empirical tails, variance contributions, full input export and native Accountant evidence.
- [x] Add hourly current-weight basket volatility and historical 95% daily expected-shortfall alerts, explicit asset/window selection, complete fresh valuation, exact observed history and retained scope/input evidence.
- [ ] Add broader correlation-aware enforcement and silent-worker outage detection. Shared strategy exposure/daily-loss enforcement is implemented separately; alerts do not change execution policy.
- [x] Add opt-in Telegram delivery per price/risk/strategy/connection rule, reviewed recipients, future-only cursors, transactional admission, cooldown suppression, expiry and actual part outcomes. See [contracts](alert-delivery.md).
- [x] Add app-origin delivery text/target inspection, queued-remainder withdrawal and separate user review history with optimistic evidence tokens.
- [x] Extend the review contract to grouped conversation replies while preserving native delivery outcomes and unknown legacy bot identities.
- [ ] Add other external alert channels; live alert-delivery acceptance remains a deployment check.
- [ ] Add a general job queue/scheduler for tasks beyond the current domain workers.
- [x] Supervise actual background iterations with fault/overdue states, sanitized retained fault history, explicit retries, shutdown draining and Workspace/global UI indicators. Technician can inspect progress through native tools. See [operations](workspace-operations.md).
- [x] Add lightweight process resource counters and fixed latency histograms with scoped, honest coverage.
- [x] Add explicit read-only bounded SQLite quick checks and privacy-allowlisted downloadable workspace health reports, with passive native Technician evidence.
- [ ] Add tracing, broader host diagnostics and external uptime monitoring.
- [x] Add passphrase-encrypted managed archives, authenticated inspection/download/import and validated separate-directory restore. Recovery quarantines automatic work and requires explicit review/restart.
- [x] Add private filtered notification JSON/CSV exports and opt-in bounded read-history retention, protected unread/delivery evidence, cleanup receipts and monotonic cursor-safe notification sequences.
- [ ] Add credential/key rotation tools beyond encrypted backup/restore.

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
4. **Build on local alerts:** broader risk metrics, strategy-event policies and operational diagnostics, then explicit external delivery and backup/restore.
5. **Sibyl and richer ProtoLink tools:** evaluated collaboration, scoped specialist tools and resumable investigations; per-agent models are implemented. Messaging clients remain a separately scoped future integration.
6. **Test-environment strategies:** reconcile actual orders/fills and implement risk controls before any production automation.
7. **Trained forecasts and advanced research:** benchmarked models, RAG, explorer/equities expansions and custom strategies.

Multi-user hosting is deferred. No user accounts, permissions, tenant isolation or distributed-worker work is included in this sequence.

The [feature coverage table](../guides/feature-coverage.md) tracks current user-facing scope. The [exchange reference](./exchange-clients.md) contains the provider matrix and exchange-specific backlog.

Prospective forecast tracking, measured cash-flow review and execution notifications are described together in [their domain contracts](performance-outcomes-alerts.md). Real forward forecast skill, broad authenticated execution acceptance and complete provider funding accounting remain deployment/evaluation work.

### Additional v2.3.0 scope

- [x] Add native Bitstamp/Gemini spot-history checkpoints and exact-order fee evidence; native retention/saturation/reversal limits stay explicit and private authenticated acceptance is pending. See [import scope](account-sync.md#bitstamp-and-gemini).
- [x] Add Kraken public live previews through the shared runtime; private-account streams and persisted gap recovery remain pending.
- [x] Add distance dependence and contemporaneous return-regression evidence; MIC/Granger/SHAP and out-of-sample inference remain outside this feature.
- [x] Add whole-basket value-concentration metrics and HHI/top-three alerts; broader return/correlation-aware risk and enforcement policies remain separate.
