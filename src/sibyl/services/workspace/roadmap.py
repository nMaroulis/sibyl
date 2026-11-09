"""Audited implementation scope, shared by the dashboard's pending-work view.

This is an explicit capability inventory, not dynamic completion detection or a
release schedule. Provider-specific acceptance and deployment scope stay visible.
"""

AREAS = [
    {
        "id": "accounts",
        "name": "Account synchronization",
        "status": "partial",
        "priority": "next",
        "working": "Durable selected-market fills including Bitstamp/Gemini with native ID/millisecond-edge checkpoints and explicit saturation/reversal limits; incremental sync and available-history rescans with correction counts and retained ranges; Binance/Kraken funding and Bybit on-chain withdrawals; reviewed transfers and fee allocations. Explicit per-account balance checkpoints compare observed native quantities with cross-market imported fills, native fees and eligible funding; saved reports expose gaps, timing ambiguity and wallet-scope changes. Funding effects support documented Kraken ledger fees, Binance wallet/completion facts and audited local wallet/fee-convention reviews with stale-source protection. Opt-in pending updates and Binance/Kraken/Bybit rolling recent-history scans resume saved pages, preserve manual ranges, track observed funding revisions and retain fetched-window gap warnings.",
        "pending": [
            "Remaining provider funding/history pagination, Bybit deposits/off-chain transfers, fiat, staking, subaccounts and older corrections outside selected lookbacks.",
            "Complete order amendment/lifecycle audits, execution bust/removal semantics and verified account-wide order/fill/funding/balance reconciliation beyond bounded observations.",
            "Broader authenticated read/import and failure-case acceptance; initial Binance/Coinbase balance and Binance Testnet lifecycle checks remain scoped evidence.",
        ],
    },
    {
        "id": "portfolio",
        "name": "Portfolio accounting",
        "status": "partial",
        "priority": "next",
        "working": "Combined/per-account valuation, observed conversion routes, exact-market FIFO and cross-pair account/asset books. Dated closed-candle conversions, foreign fees/rebates, audited opening assets and reviewed cross-market transfer lots retain explicit unknowns and price/fill fingerprints. Audited split/merged groups add exact principal matrices, shared pair/group reservations and whole-group source/version validation. Append-only fill observations retain material corrections atomically. Legacy exact-market opening basis and transfer carryover remain available. New measured periods add fresh fixed-account opening/closing valuations, source-bound user/manual cash-flow review, coverage gates, approximate Modified Dietz returns, per-account/combined evidence and native Accountant tools. Whole-basket value HHI, effective asset count and largest/top-three weights require complete valuation coverage. Explicit saved current-holding basket studies add observed conversion histories, common consecutive daily returns, covariance/correlations, volatility, empirical tails and variance contributions with subset boundaries and frozen inputs.",
        "pending": [
            "Complete accounting beyond retained cross-pair FIFO: broader fee conventions, independently established external-flow classification and wallet coverage.",
            "Provider-verified complete funding coverage, automatic historical flow conversion and complete account P&L beyond the new user-reviewed measured-period workflow.",
            "Broader funding fee/rebate policies and additional wallet types beyond the explicit same-asset group allocations.",
        ],
    },
    {
        "id": "orders",
        "name": "Order management",
        "status": "partial",
        "priority": "next",
        "working": "Manual market/GTC limits and cancellation for eight production providers and test clients; reviewed GTC limits/cancellation for the other twelve configured production providers. Binance/Testnet add native conditional GTC limits, linked OCO, child-ID recovery and reviewed unfilled-only native replacement with non-atomic outcomes. Actual Testnet checks cover conditional open/cancel, deliberately lost OCO response recovery, sibling cancellation, replacement and a fill-winning order. Per-exchange support tabs and per-instrument permissions keep limits explicit.",
        "pending": [
            "Broader discovery/recovery adapters, external amendment handling and definitive fee/settlement reconciliation.",
            "Conditional/OCO and replacement adapters for additional providers, partial-order amendment, trailing, post-only, iceberg and other time-in-force choices.",
            "Market execution, exact-order reconciliation and broader authenticated acceptance for Gate, Bitget, MEXC, HTX, Crypto.com, Bitfinex, CoinEx, BitMart, Phemex, Poloniex and Upbit. Their guarded GTC limit/cancel adapters are implemented.",
            "Client-ID recovery and account-wide discovery for OKX, Bybit, KuCoin, Bitstamp and Gemini.",
        ],
    },
    {
        "id": "market-data",
        "name": "Market-data infrastructure",
        "status": "partial",
        "priority": "next",
        "working": "Exact-source REST data, descriptive market statistics and explainable technical bias, region zoom, retained OHLCV/backfills and immutable inputs; shared read controls and retained HTTP diagnostics; on-demand Binance production/Testnet, Coinbase production and Kraken production public ticker/candle streams with bounded fanout, reconnect/freshness states and same-source REST fallback. Coinbase supports native five-minute candles only and refuses most public USDC-to-USD aliases; connection-wide sequence gaps reconnect without rewriting history. Closed-candle analysis stays separate. Retained fixed latency histograms report p50/p95 upper bounds and actual sample coverage, including legacy gaps. Native Binance/Testnet, Coinbase Advanced and Kraken private order signals persist restart/reconnect REST wakeups and periodic backstops; financial ledgers still require the separately enabled REST readers. Reviewed Binance Spot read weights and observed minute IP ceilings, conservative Kraken key-scoped counters and Coinbase Exchange Sandbox public/private/fills buckets add pre-sign quota deferral and passive UI/Technician evidence; native mutation retries remain unchanged.",
        "pending": [
            "Historical pagination and authenticated provider acceptance for remaining venues.",
            "Broader wallet/SAPI/provider/interval quota policies, discovered tiers/profile identities, live external acceptance, cross-process coordination, cross-request tracing and broader host diagnostics.",
            "Additional public providers, broader private balance/account streams and complete sequence-gap recovery; a scheduled REST wakeup is not reconciliation completion.",
        ],
    },
    {
        "id": "operations",
        "name": "Alerts & local operations",
        "status": "partial",
        "priority": "next",
        "working": "Editable source-pinned price/crossing rules, per-run strategy journal subscriptions and per-operation connection read-failure/recovery watches; revision checks, bounded evidence, atomic cursors, restart catch-up and a shared local inbox; fixed-account-set value-floor, asset/HHI/top-three concentration and observed-value drawdown watches with complete fresh valuations. Hourly current-weight historical basket volatility/95% daily expected-shortfall watches require fresh complete valuation and exact observed daily history. Opt-in per-rule Telegram delivery adds reviewed recipients, future-only admission, cooldown/expiry, durable receipts and pause controls. Per-account order/fill subscriptions add atomic observation receipts, future-only controls and existing Telegram delivery. Actual background-worker progress/fault/deadline monitoring, sanitized retained history, global UI notices and native Technician diagnostics are implemented. Passphrase-encrypted archives support inspection/download/import and validated separate-directory recovery with automation quarantined until review/restart. Workspace adds explicit bounded read-only SQLite quick checks and content-free downloadable health reports, plus current-process resource counters; notification exports and opt-in old-read retention protect unread/delivery evidence and monotonic cursors. All five rule kinds can select Telegram, Discord, Slack, Signal, WhatsApp or email through a reviewed private destination, a shared durable outbox and provider-specific text limits. Exact provider IDs, cancellation uncertainty, part review and future-only controls remain inspectable. An independent local observer retains worker incidents, completion-based recovery and explicit observation gaps. Durable bounded jobs and interruption-safe credential/vault rotation are implemented.",
        "pending": [
            "Broader correlation-aware enforcement, cross-request tracing, host diagnostics and external process/host outage monitoring.",
            "Live acceptance for the six private alert routes; generic webhooks and native push remain optional extensions. Scheduled research briefings can select any of the six checked private routes; text documents remain Telegram-only.",
            "Additional reviewed local job handlers and installation/service support. Provider credential revocation remains at the provider.",
        ],
    },
    {
        "id": "strategies",
        "name": "Automated strategy execution",
        "status": "partial",
        "priority": "later",
        "working": "Paper runs and approved exchange strategies for nine provider/environment variants. Scoped budgets, capped GTC limits, durable expiry, Stop & cancel and separate reviewed position exits; native fills/fees, restart pause, per-run guards, a durable global submission halt and opt-in shared capital/exposure/observed UTC daily-loss limits with dated conversions, native-write admission and later-day lock release/audit. Real Binance Testnet strategy entry/exit, restart, shared allocation rejection and controlled lost-response recovery have passed initial acceptance. Changed native totals or imported fills/fees reopen three matching cancellation checks, block new signals/exits and invalidate prepared submissions; identical reimports stay idempotent. Uncertain writes are never replayed. Optional account/base-asset exposure caps and sampled rolling-loss windows have persistent latches. Stop-distance entry-risk sizing caps the order budget; it does not install a native protective stop. On-demand native base-balance checks compare all same-account owners; reviewed manual adoption/release and exact-pair new-run handoffs preserve original basis, immutable receipts, flow-neutral shared P&L and source-correction guards.",
        "pending": [
            "Authenticated partial-fill, cancellation-race, late-correction and actual outage acceptance across more venues before deliberate production enablement.",
            "Reviewed correction/reversal across executed ownership descendants, verified manual-trade classifications, cash-flow-adjusted lifetime statistics, third-currency fee valuation and definitive execution bust/settlement handling.",
            "Multi-asset historical deployment/rebalancing, explicit allocation execution and any additional liquidation/coordination policy.",
        ],
    },
    {
        "id": "strategy-research",
        "name": "Strategy research",
        "status": "partial",
        "priority": "later",
        "working": "Six configurable algorithms, cost-aware backtests and paper runs; bounded grid or seeded finite random search with explicit budgets, recorded plans/coverage/fingerprints, chronological holdout/expanding walk-forward tests, fixed-setting/buy-and-hold comparisons, saved rankings/test executions, checked exact-study replay and read-only Broker evidence. Ordinary backtests add exact-window cost-aware cash/hold/installment/50-50 references, comparison metrics and selectable equity overlays. Optional nested selection retains each inner-window candidate score wholly inside outer training prefixes, with independent outer tests and bounded work. Trusted explicitly enabled installed Python plugins add research-only cost-aware backtests, immutable input/decision receipts, source pins and offline reruns. Native optional Optuna TPE/random numeric distributions add bounded train-only selection and independent chronological tests. Causal trusted plugins share that research engine and one-off pinned local jobs; source/sampler/engine versions and trial/test receipts support checked exact replay.",
        "pending": [
            "Multi-asset historical deployment/rebalancing and explicitly reviewed execution/allocation policies.",
            "Optional Freqtrade integration.",
            "Separate causal ML/RL training and evaluation pipelines.",
        ],
    },
    {
        "id": "sibyl",
        "name": "Sibyl & messaging",
        "status": "partial",
        "priority": "next",
        "working": "Native ProtoLink discovery/delegation, saved chats, native streamed Markdown answers and typed consultation activity, Stop/outcomes, native usage rollups and bounded group admission; read-only retained run subscriptions have independent cursors, explicit gaps and deletion guards; saved investigations with structured reports, actual tool-source receipts, frozen team models, versioned reruns, comparison and JSON export. Daily/weekly calendars add time zones, missed-run handling, retention and explicit six-channel private briefings with frozen acceptance-time route controls and durable part outcomes. Direct-HTTP Telegram adds opt-in bounded document imports, local photo OCR and whisper.cpp speech transcription into cited My research sources; installed processors are optional and accuracy is not guaranteed. It supports private-user binding, encrypted configuration and durable delivery outcomes, including optional outgoing text documents for long replies/briefings and grouped conversation receipts with exact queued-text inspection, atomic unsent withdrawal and separate user acknowledgments that never resend. Optional native durable investigations support human questions, exact local-note approvals, immutable team snapshots and explicit continuation. Discord private HTTP DMs, Slack Socket Mode, signed WhatsApp webhooks, paired TLS email and the local unofficial Signal bridge have checked private bindings and durable outcomes. Alert rules can select any of the six text channels without an LLM.",
        "pending": [
            "Broader provider/model, semantic-grounding and adversarial evaluation beyond the implemented native evidence-contract checks.",
            "Native group-continuation admission, checkpoint retention and budget-aware peer-card support where the SDK needs upstream APIs; no custom application runtime is added.",
            "Additional media beyond the Telegram adapters. Additional live acceptance is required for external services and attachment/processor accuracy; initial Telegram conversation acceptance is user-confirmed.",
        ],
    },
    {
        "id": "agents",
        "name": "ProtoLink workflows",
        "status": "partial",
        "priority": "later",
        "working": "Ten native specialists with purpose-focused tool descriptions, typed page-help topics and scoped evidence tools; ProtoLink 0.8.4 native thread execution and FIFO root admission, lazy request-local models, private context, AgentGroup lifecycle, SQLite conversations, run reports/evidence and invalid-selection correction. Per-agent model selection, encrypted profiles and frozen delegated snapshots; Broker reads saved experiments and retained order/fill evidence with accurate paper/exchange labels. Ollama settings detect models and manage an explicitly started local server. Native repeated evaluations compare actual tool/source selections, required readings/links, empty data and consultation receipts against saved score baselines. Recorded Gemma checks retain coordinator failures; broad answer reliability remains unproven.",
        "pending": [
            "Deeper domain-specific evidence tools as additional features become available.",
            "Broader model/provider, semantic claim-grounding and adversarial evaluation.",
            "Explicit scoped approval/audit contracts for any future financial or messaging mutation tool; ordinary agents remain read-only and durable research permits only an explicitly approved local note.",
        ],
    },
    {
        "id": "forecasting",
        "name": "Forecasting",
        "status": "partial",
        "priority": "later",
        "working": "Versioned direct autoregressive ridge models, immutable daily inputs, chronological 60/20/20 training/calibration/test evidence, naive/drift benchmarks, empirical bands, explicit saved/current-input forecasts, bounded historical expanding/fixed-window recipe evaluation with purged fold boundaries, pooled benchmarks, saved reports/reruns/exports and read-only Chronos tools. The untrained baseline remains separate. Prospective forecast tracking pins saved predictions to exact-source actuals, retains correction versions and compares equal-horizon model/naive/drift errors without inflating repeated target saves. Portable JSON bundles verify inputs and refit offline in an unverified import namespace; archive/restore keeps saved evidence and independent monitors intact. Optional returns-plus-context features add six causal trailing-price statistics with recipe-specific engine identity and the same evaluation boundaries. A bounded fixed-scale Huber family adds training-only median/MAD target scaling, deterministic IRLS, explicit convergence/downweight diagnostics and recipe-preserving rolling, portable and recalibration workflows. It retains all observations and does not make feature leverage robust. A bounded eight-unit tanh neural family uses real fixed-seed Adam fitting, training-only normalization, actual loss evidence and the same held-out/rolling/bundle contracts. Retained-source drift observations and revision-bound opt-in recalibration policies can train a new candidate, including through explicit local schedules, without promoting the parent model.",
        "pending": [
            "ARIMA and additional neural/model families beyond ridge/Huber/small-neural, broader assets/features and larger held-out/forward evaluation studies.",
            "Real-data calibration/threshold evaluation and broader managed model lifecycles; retained-source drift and explicit candidate recalibration are implemented.",
        ],
    },
    {
        "id": "research",
        "name": "Research & news",
        "status": "partial",
        "priority": "later",
        "working": "Publisher feeds/website collection/NewsAPI, archived excerpts, source health, VADER sentiment, Fear & Greed and fetched crypto profiles. Private PDF/text/Markdown imports, retained originals, exact page passages, BM25 search across uploads/news, source management and native Wiki/Reporter retrieval work without a chat LLM. Optional local Ollama embeddings add bounded checkpointed indexing, cosine search and hybrid rank fusion with actual coverage and exact citations. Owner-labeled retrieval suites compare methods on pinned corpus/index snapshots with saved rankings, citations, metrics, Stop, restart interruption and native agent evidence.",
        "pending": [
            "Broader real-model semantic relevance/grounding evaluation, calibrated no-answer thresholds, hosted embedding providers and cited web search; local semantic/hybrid retrieval and exact citations are implemented.",
            "Licensed full-article processing and evaluated entity/finance sentiment.",
            "Additional reviewed research integrations and credentials as needed.",
        ],
    },
    {
        "id": "explorer",
        "name": "Explorer, equities & analytics",
        "status": "partial",
        "priority": "later",
        "working": "Bitcoin mainnet transaction/address inspection with checksum validation, exact satoshi fees, observed confirmations, paged inputs/outputs and confirmed activity, bounded pending observations, explicit paged output-spend checks with spending-transaction links, JSON exports, independent Demo and native Explorer tools; recent blocks, optional equity research and Pearson/Spearman/distance dependence with descriptive same-interval return regression. Fixed-order Granger research adds training-only F/Bonferroni evidence, residual qualifications and independent later-target comparisons without causal/profit claims.",
        "pending": [
            "Historical chain datasets, additional chains, wallet aggregation, durable spend/reorg watches and local chain verification.",
            "Public-official disclosure archives and advanced portfolio analytics.",
            "MIC, SHAP, robust/nonlinear causal inference and broader real-data evaluation. Fixed-order Granger training/holdout evidence is implemented with classical inference limits.",
        ],
    },
    {
        "id": "multi-user",
        "name": "Hosted multi-user support",
        "status": "deferred",
        "priority": "deferred",
        "working": "Local single-user workspace with optional bearer token and one API worker.",
        "pending": [
            "User accounts, workspace ownership, permissions and tenant-isolated data/vaults.",
            "Distributed worker coordination and hosted deployment controls.",
        ],
        "note": "Deferred by request. These are not prerequisites for the current local workspace.",
    },
]


def implementation_status() -> dict:
    """Return a human-audited inventory without provider reads or fake completion percentages."""
    return {
        "reviewed_on": "2026-11-09",
        "scope": "Local single-user workspace",
        "areas": AREAS,
        "current_focus": "v2.4.0 is in development. Delivered foundations include cross-pair FIFO and split/merged transfer groups, fill revisions, native private order signals with REST wakeups and reviewed read quota evidence, shared strategy exposure/rolling-loss controls and reviewed position ownership/handoff, Optuna/plugin research jobs, native durable research approvals, Telegram attachments, six private text clients, six-channel alert/briefing delivery with acceptance-time consent, forecast drift/recalibration and robust Huber fits, retained worker incidents and credential rotation. Remaining work is listed by area below and in the release checklist: wider funding/venue coverage, advanced orders, ownership correction/return coverage, multi-asset and ML/RL research, broader semantic/model evaluation, additional media, research/chain integrations, tracing/service distribution and live external acceptance. Multi-user hosting and cited web research remain deferred.",
        "execution_note": "Paper strategies remain the default. Supported exchange strategies require explicit scoped approval and both backend execution flags. Agents remain read-only. Initial Binance Testnet strategy acceptance passed; broader failure-case/venue acceptance and production execution acceptance remain outstanding.",
        "release_dates": None,
    }
