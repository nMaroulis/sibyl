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
        "working": "Durable selected-market fills for eleven clients/environments; incremental sync and available-history rescans with correction counts and retained ranges; Binance/Kraken funding and Bybit on-chain withdrawals; reviewed transfers and fee allocations.",
        "pending": [
            "Import pagination and funding support for remaining providers; fiat, staking and subaccounts.",
            "Scheduled refresh of old/pending events, execution bust/removal handling, versioned correction audits and complete order/fill/funding/balance reconciliation.",
            "Broader authenticated read/import acceptance. Initial Binance/Coinbase balance reads and the manual Binance Testnet lifecycle have been checked.",
        ],
    },
    {
        "id": "portfolio",
        "name": "Portfolio accounting",
        "status": "partial",
        "priority": "next",
        "working": "Combined/per-account valuation, observed conversion routes, exact-market FIFO, opening basis and reviewed transfer carryover.",
        "pending": [
            "Cross-market basis and historical third-currency/transfer-fee valuation.",
            "Returns adjusted for external deposits/withdrawals and complete account P&L.",
            "Split/merged transfers, broader fee/rebate cases and wallet types.",
        ],
    },
    {
        "id": "orders",
        "name": "Order management",
        "status": "partial",
        "priority": "next",
        "working": "Manual market/GTC limits and cancellation for eight production providers, Gemini limits, and test clients. Per-exchange support tabs; selected providers have fill reconciliation, recovery and discovery.",
        "pending": [
            "Broader discovery/recovery adapters, external amendment handling and definitive fee/settlement reconciliation.",
            "Cancel/replace, stop/OCO, trailing, post-only, iceberg and other time-in-force choices.",
            "Execution adapters for Gate, Bitget, MEXC, HTX, Crypto.com, Bitfinex, CoinEx, BitMart, Phemex, Poloniex and Upbit; broader authenticated venue acceptance beyond the initial manual Binance Testnet lifecycle.",
            "Detailed fill reconciliation and resumable imports for Bitstamp/Gemini; client-ID recovery and account-wide discovery for OKX, Bybit, KuCoin, Bitstamp and Gemini.",
        ],
    },
    {
        "id": "market-data",
        "name": "Market-data infrastructure",
        "status": "partial",
        "priority": "next",
        "working": "Exact-source REST data, descriptive market statistics and explainable technical bias, region zoom, retained OHLCV/backfills and immutable inputs; shared read controls and retained HTTP diagnostics.",
        "pending": [
            "Review historical pagination for remaining providers and authenticated provider acceptance.",
            "Reviewed endpoint-weight/IP/account quotas, richer latency distributions and application-wide operational diagnostics.",
            "WebSocket prices and private account/order streams with reconnect recovery.",
        ],
    },
    {
        "id": "operations",
        "name": "Alerts & local operations",
        "status": "partial",
        "priority": "next",
        "working": "Editable source-pinned price/crossing rules, per-run strategy journal subscriptions and per-operation connection read-failure/recovery watches; revision checks, bounded evidence, atomic cursors, restart catch-up and a shared local inbox; fixed-account-set value-floor, concentration and observed-value drawdown watches with complete fresh valuations.",
        "pending": [
            "Broader risk metrics, optional fill/order policies and silent-worker outage detection; operational diagnostics. Shared strategy capital/exposure/daily-loss enforcement is a separate implemented policy; alerts never change it.",
            "Optional external delivery with retries and delivery state.",
            "General durable task scheduling, metrics/diagnostics and managed backup/restore.",
        ],
    },
    {
        "id": "strategies",
        "name": "Automated strategy execution",
        "status": "partial",
        "priority": "later",
        "working": "Paper runs and approved exchange strategies for nine provider/environment variants. Scoped budgets, capped GTC limits, durable expiry, Stop & cancel and separate reviewed position exits; native fills/fees, restart pause, per-run guards, a durable global submission halt and opt-in shared capital/exposure/observed UTC daily-loss limits with dated conversions, native-write admission and later-day lock release/audit. Uncertain writes are never replayed.",
        "pending": [
            "Authenticated test-environment/provider acceptance before deliberate production enablement.",
            "Broader concentration/risk-sizing/loss-window policies, archived accounting beyond current bounds and distributed coordination. Shared strategy capital/exposure/daily-loss controls and global halt are implemented; residual exits need fresh approvals; no automatic liquidation.",
            "Reviewed residual/dust ownership handoff to new runs, third-currency fee valuation, manual position reconciliation/adoption, settlement corrections and more execution providers.",
        ],
    },
    {
        "id": "strategy-research",
        "name": "Strategy research",
        "status": "partial",
        "priority": "later",
        "working": "Six configurable algorithms, cost-aware backtests and paper runs; bounded grid search, chronological holdout/expanding walk-forward tests, fixed-setting/buy-and-hold comparisons, saved rankings/test executions, exact-study replay and read-only Broker evidence.",
        "pending": [
            "Additional benchmarks, continuous rebalanced deployment simulation, nested validation and broader optimization methods.",
            "Custom strategy plugins, optional Freqtrade and multi-asset allocation.",
            "Separate ML/RL training and evaluation pipelines.",
        ],
    },
    {
        "id": "sibyl",
        "name": "Sibyl & messaging",
        "status": "partial",
        "priority": "next",
        "working": "Native ProtoLink discovery/delegation, saved chats, streamed tool/consultation activity, Stop/outcomes and on-demand native run details with available token/cost metrics, and a direct-HTTP Telegram client with private-user binding, encrypted configuration and durable delivery outcomes.",
        "pending": [
            "User-facing token streaming, broader repeated/model-specific routing and grounding evaluation and upstream owned-subagent usage metrics (unavailable in ProtoLink 0.8.3).",
            "Scheduled and resumable investigations; stopped or interrupted requests are not replayed.",
            "WhatsApp, Discord, Slack, Signal and Email clients remain unavailable. Telegram: live bot acceptance testing, richer media and delivery review controls; ambiguous sends are never auto-retried.",
        ],
    },
    {
        "id": "agents",
        "name": "ProtoLink workflows",
        "status": "partial",
        "priority": "later",
        "working": "Ten native specialists with purpose-focused tool descriptions, typed page-help topics and scoped evidence tools; ProtoLink 0.8.3 native worker admission, lazy request-local models, private context, AgentGroup lifecycle, SQLite conversations, run reports/evidence and invalid-selection correction. Per-agent provider/model selection, encrypted shared profiles and frozen delegated request snapshots; Broker reads saved experiments and bounded retained order/fill evidence. Ollama settings detect models, configure a shared context window aligned with native input budgets, and can manage an explicitly started local server. Initial real Gemma acceptance covers evidence, coordinator tool/inference consultations, memory, cancellation and persistence; broader reliability remains unproven.",
        "pending": [
            "Deeper domain investigation tools as features expand.",
            "Evaluated tool/source selection, inspected internal traces and collaboration budgets.",
            "Explicit approvals and audit contracts before mutation tools.",
        ],
    },
    {
        "id": "forecasting",
        "name": "Forecasting",
        "status": "baseline",
        "priority": "later",
        "working": "An explicitly untrained statistical log-return baseline.",
        "pending": [
            "Reproducible datasets, trained-model inference, artifacts and version registry.",
            "Out-of-sample comparison, calibration, drift monitoring and model-backed UI results.",
        ],
    },
    {
        "id": "research",
        "name": "Research & news",
        "status": "partial",
        "priority": "later",
        "working": "Publisher feeds/website collection/NewsAPI, archived excerpts, source health, VADER sentiment, Fear & Greed and fetched crypto profiles.",
        "pending": [
            "Document ingestion, chunking, embeddings, hybrid RAG and cited web search.",
            "Licensed full-article processing and evaluated entity/finance sentiment.",
            "Additional reviewed research integrations and credentials as needed.",
        ],
    },
    {
        "id": "explorer",
        "name": "Explorer, equities & analytics",
        "status": "basic",
        "priority": "later",
        "working": "Recent Bitcoin blocks, optional equity quotes/history/statistics and Pearson/Spearman correlations.",
        "pending": [
            "Transaction/address inspection, historical datasets and additional chains.",
            "Public-official disclosure archives and advanced portfolio analytics.",
            "Distance/MIC/Granger/regression/SHAP with evaluated assumptions.",
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
        "reviewed_on": "2026-10-27",
        "scope": "Local single-user workspace",
        "areas": AREAS,
        "current_focus": "Initial manual Binance Testnet acceptance is recorded. Next foundations: automated-strategy test-environment acceptance, broader account reconciliation and venue acceptance. Market analytics and local alerts are implemented. Multi-user support is deferred.",
        "execution_note": "Paper strategies remain the default. Supported exchange strategies require explicit scoped approval and both backend execution flags. Agents remain read-only. Initial manual Binance Testnet acceptance is recorded; automated-strategy and broader venue acceptance remain outstanding.",
        "release_dates": None,
    }
