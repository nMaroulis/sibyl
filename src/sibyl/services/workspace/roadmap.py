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
            "Import pagination and funding support for remaining providers; fiat, staking and subaccounts.",
            "Older funding outside selected lookbacks, native bust/removal handling and versioned fill/order correction audits and complete order/fill/funding/balance reconciliation beyond bounded observed checkpoints; additional provider fee rules, earn/staking and wallet coverage remain incomplete.",
            "Broader authenticated read/import acceptance. Initial Binance/Coinbase balance reads and manual/strategy Binance Testnet lifecycles have been checked.",
        ],
    },
    {
        "id": "portfolio",
        "name": "Portfolio accounting",
        "status": "partial",
        "priority": "next",
        "working": "Combined/per-account valuation, observed conversion routes, exact-market FIFO, opening basis and reviewed transfer carryover. New measured periods add fresh fixed-account opening/closing valuations, source-bound user/manual cash-flow review, coverage gates, approximate Modified Dietz returns, per-account/combined evidence and native Accountant tools. Whole-basket value HHI, effective asset count and largest/top-three weights require complete valuation coverage.",
        "pending": [
            "Cross-market basis and historical third-currency/transfer-fee valuation.",
            "Provider-verified complete funding coverage, automatic historical flow conversion and complete account P&L beyond the new user-reviewed measured-period workflow.",
            "Split/merged transfers, broader fee/rebate cases and wallet types.",
        ],
    },
    {
        "id": "orders",
        "name": "Order management",
        "status": "partial",
        "priority": "next",
        "working": "Manual market/GTC limits and cancellation for eight production providers, Gemini limits, and test clients. Binance/Testnet add native conditional GTC limits, linked OCO, child-ID recovery and reviewed unfilled-only native replacement with non-atomic outcomes. Actual Testnet checks cover conditional open/cancel, deliberately lost OCO response recovery, sibling cancellation, replacement and a fill-winning order. Per-exchange support tabs and per-instrument permissions keep limits explicit.",
        "pending": [
            "Broader discovery/recovery adapters, external amendment handling and definitive fee/settlement reconciliation.",
            "Conditional/OCO and replacement adapters for additional providers, partial-order amendment, trailing, post-only, iceberg and other time-in-force choices.",
            "Execution adapters for Gate, Bitget, MEXC, HTX, Crypto.com, Bitfinex, CoinEx, BitMart, Phemex, Poloniex and Upbit; broader authenticated venue acceptance beyond the initial Binance Testnet lifecycles.",
            "Client-ID recovery and account-wide discovery for OKX, Bybit, KuCoin, Bitstamp and Gemini.",
        ],
    },
    {
        "id": "market-data",
        "name": "Market-data infrastructure",
        "status": "partial",
        "priority": "next",
        "working": "Exact-source REST data, descriptive market statistics and explainable technical bias, region zoom, retained OHLCV/backfills and immutable inputs; shared read controls and retained HTTP diagnostics; on-demand Binance production/Testnet and Kraken production public ticker/candle streams with bounded fanout, reconnect/freshness states and same-source REST fallback. Closed-candle analysis stays separate. Retained fixed latency histograms report p50/p95 upper bounds and actual sample coverage, including legacy gaps.",
        "pending": [
            "Review historical pagination for remaining providers and authenticated provider acceptance.",
            "Reviewed endpoint-weight/IP/account quotas, distributed tracing and broader host diagnostics. Fixed latency histograms and current-process resource metrics are implemented.",
            "Additional public-provider and private account/order WebSocket streams, and persisted reconnect-gap recovery.",
        ],
    },
    {
        "id": "operations",
        "name": "Alerts & local operations",
        "status": "partial",
        "priority": "next",
        "working": "Editable source-pinned price/crossing rules, per-run strategy journal subscriptions and per-operation connection read-failure/recovery watches; revision checks, bounded evidence, atomic cursors, restart catch-up and a shared local inbox; fixed-account-set value-floor, asset/HHI/top-three concentration and observed-value drawdown watches with complete fresh valuations. Opt-in per-rule Telegram delivery adds reviewed recipients, future-only admission, cooldown/expiry, durable receipts and pause controls. Per-account order/fill subscriptions add atomic observation receipts, future-only controls and existing Telegram delivery. Actual background-worker progress/fault/deadline monitoring, sanitized retained history, global UI notices and native Technician diagnostics are implemented. Passphrase-encrypted archives support inspection/download/import and validated separate-directory recovery with automation quarantined until review/restart. Workspace exposes bounded current-process resource counters; notification exports and opt-in old-read retention protect unread/delivery evidence and monotonic cursors.",
        "pending": [
            "Return/correlation-aware risk metrics, external uptime monitoring and richer operational metrics. Shared strategy capital/exposure/daily-loss enforcement is a separate implemented policy; alerts never change it.",
            "Additional external alert channels and richer delivery review; real Telegram alert-delivery acceptance remains a deployment check.",
            "General durable task scheduling, tracing and credential/key rotation beyond implemented encrypted backup/recovery. Current-process resources, filtered inbox exports and opt-in bounded read-history retention are implemented.",
        ],
    },
    {
        "id": "strategies",
        "name": "Automated strategy execution",
        "status": "partial",
        "priority": "later",
        "working": "Paper runs and approved exchange strategies for nine provider/environment variants. Scoped budgets, capped GTC limits, durable expiry, Stop & cancel and separate reviewed position exits; native fills/fees, restart pause, per-run guards, a durable global submission halt and opt-in shared capital/exposure/observed UTC daily-loss limits with dated conversions, native-write admission and later-day lock release/audit. Real Binance Testnet strategy entry/exit, restart, shared allocation rejection and controlled lost-response recovery have passed initial acceptance. Changed native totals or imported fills/fees reopen three matching cancellation checks, block new signals/exits and invalidate prepared submissions; identical reimports stay idempotent. Uncertain writes are never replayed.",
        "pending": [
            "Extend authenticated acceptance to partial fills, cancellation races, late corrections, real connectivity failures and other venues before deliberate production enablement. Initial Binance Testnet checks use actual signals, native orders and controlled entry-response loss.",
            "Broader concentration/risk-sizing/loss-window policies, archived accounting beyond current bounds and distributed coordination. Shared strategy capital/exposure/daily-loss controls and global halt are implemented; residual exits need fresh approvals; no automatic liquidation.",
            "Reviewed residual/dust ownership handoff to new runs, third-currency fee valuation, manual position reconciliation/adoption, settlement corrections and more execution providers.",
        ],
    },
    {
        "id": "strategy-research",
        "name": "Strategy research",
        "status": "partial",
        "priority": "later",
        "working": "Six configurable algorithms, cost-aware backtests and paper runs; bounded grid or seeded finite random search with explicit budgets, recorded plans/coverage/fingerprints, chronological holdout/expanding walk-forward tests, fixed-setting/buy-and-hold comparisons, saved rankings/test executions, checked exact-study replay and read-only Broker evidence. Ordinary backtests add exact-window cost-aware cash/hold/installment/50-50 references, comparison metrics and selectable equity overlays.",
        "pending": [
            "Continuous rebalanced deployment simulation, nested validation and Bayesian/distribution-based optimization. Fixed cost-aware cash, hold, installment and 50/50 research references are implemented.",
            "Custom strategy plugins, optional Freqtrade and multi-asset allocation.",
            "Separate ML/RL training and evaluation pipelines.",
        ],
    },
    {
        "id": "sibyl",
        "name": "Sibyl & messaging",
        "status": "partial",
        "priority": "next",
        "working": "Native ProtoLink discovery/delegation, saved chats, streamed consultation activity, Stop/outcomes and native run details; saved investigations with structured reports, actual tool-source receipts, frozen team models, versioned reruns, comparison and JSON export. Daily/weekly calendars add time zones, missed-run handling, retention and explicit Telegram briefings with durable part outcomes. Direct-HTTP Telegram supports private-user binding, encrypted configuration and durable delivery outcomes.",
        "pending": [
            "User-facing token streaming, broader provider/model and semantic-grounding evaluation and upstream owned-subagent usage metrics (unavailable in ProtoLink 0.8.3). Repeatable native evidence-contract checks and baseline comparisons are implemented; small-model coordinator failures remain documented.",
            "Resumable multi-stage investigations; stopped or interrupted inference is not replayed. General-purpose durable jobs remain separate from implemented daily/weekly research calendars.",
            "WhatsApp, Discord, Slack, Signal and Email clients remain unavailable. Telegram: real scheduled-briefing acceptance, richer media and delivery review controls; initial conversation acceptance is user-confirmed, and ambiguous sends are never auto-retried.",
        ],
    },
    {
        "id": "agents",
        "name": "ProtoLink workflows",
        "status": "partial",
        "priority": "later",
        "working": "Ten native specialists with purpose-focused tool descriptions, typed page-help topics and scoped evidence tools; ProtoLink 0.8.3 native worker admission, lazy request-local models, private context, AgentGroup lifecycle, SQLite conversations, run reports/evidence and invalid-selection correction. Per-agent model selection, encrypted profiles and frozen delegated snapshots; Broker reads saved experiments and retained order/fill evidence with accurate paper/exchange labels. Ollama settings detect models and manage an explicitly started local server. Native repeated evaluations compare actual tool/source selections, required readings/links, empty data and consultation receipts against saved score baselines. Recorded Gemma checks retain coordinator failures; broad answer reliability remains unproven.",
        "pending": [
            "Deeper domain investigation tools as features expand; native live-stream and conditional/OCO/replacement evidence/help are implemented.",
            "Broader provider/model coverage, semantic claim grounding and adversarial examples beyond the implemented bounded native evidence-contract cases; complete upstream owned-subagent usage metrics.",
            "Explicit approvals and audit contracts before mutation tools.",
        ],
    },
    {
        "id": "forecasting",
        "name": "Forecasting",
        "status": "partial",
        "priority": "later",
        "working": "Versioned direct autoregressive ridge models, immutable daily inputs, chronological 60/20/20 training/calibration/test evidence, naive/drift benchmarks, empirical bands, explicit saved/current-input forecasts, bounded historical expanding/fixed-window recipe evaluation with purged fold boundaries, pooled benchmarks, saved reports/reruns/exports and read-only Chronos tools. The untrained baseline remains separate. Prospective forecast tracking pins saved predictions to exact-source actuals, retains correction versions and compares equal-horizon model/naive/drift errors without inflating repeated target saves. Portable JSON bundles verify inputs and refit offline in an unverified import namespace; archive/restore keeps saved evidence and independent monitors intact.",
        "pending": [
            "Neural/ARIMA and additional model families, broader assets and training inputs.",
            "Calibrated drift monitoring, automatic recalibration and larger managed model lifecycles.",
        ],
    },
    {
        "id": "research",
        "name": "Research & news",
        "status": "partial",
        "priority": "later",
        "working": "Publisher feeds/website collection/NewsAPI, archived excerpts, source health, VADER sentiment, Fear & Greed and fetched crypto profiles. Private PDF/text/Markdown imports, retained originals, exact page passages, BM25 search across uploads/news, source management and native Wiki/Reporter retrieval work without a chat LLM. Optional local Ollama embeddings add bounded checkpointed indexing, cosine search and hybrid rank fusion with actual coverage and exact citations.",
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
        "working": "Bitcoin mainnet transaction/address inspection with checksum validation, exact satoshi fees, observed confirmations, paged inputs/outputs and confirmed activity, bounded pending observations, explicit paged output-spend checks with spending-transaction links, JSON exports, independent Demo and native Explorer tools; recent blocks, optional equity research and Pearson/Spearman/distance dependence with descriptive same-interval return regression.",
        "pending": [
            "Historical chain datasets, additional chains, wallet aggregation, durable spend/reorg watches and local chain verification.",
            "Public-official disclosure archives and advanced portfolio analytics.",
            "MIC, Granger and SHAP with evaluated assumptions; distance dependence and descriptive OLS are implemented without significance or causal claims.",
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
        "reviewed_on": "2026-11-06",
        "scope": "Local single-user workspace",
        "areas": AREAS,
        "current_focus": "v2.3.0 adds on-demand Binance production/Testnet live market previews, native conditional/OCO orders, unfilled-only manual cancel/replace and matching native Analyst/Broker tools and guides. Actual Testnet lifecycle checks include controlled OCO response loss and exact child recovery, not intermediate partial-fill, late-correction or genuine outage acceptance. Remaining work includes broader provider/private streams, advanced-order adapters, accounting/reconciliation and model/semantic evaluation. Additional research/operations work adds comparable reference portfolios, portable and archived forecast research, protected inbox retention/export and scoped process/latency diagnostics. This batch also adds Bitstamp/Gemini fill imports/reconciliation, native Kraken public previews, bounded nonlinear relationships/return regression and value diversification metrics/alerts. Multi-user support stays deferred.",
        "execution_note": "Paper strategies remain the default. Supported exchange strategies require explicit scoped approval and both backend execution flags. Agents remain read-only. Initial Binance Testnet strategy acceptance passed; broader failure-case/venue acceptance and production execution acceptance remain outstanding.",
        "release_dates": None,
    }
