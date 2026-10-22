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
        "working": "Durable selected-market fills for seven clients/environments; Binance/Kraken funding ranges; reviewed transfers and fee allocations.",
        "pending": [
            "Import pagination and funding support for remaining providers; fiat, staking and subaccounts.",
            "Full rescans, late-event updates and order/fill/funding reconciliation.",
            "Authenticated read and sandbox lifecycle acceptance tests.",
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
        "working": "Reviewed market/GTC limits, cancellation, status/fill tracking, client-ID recovery and read-only combined account order discovery with shared execution evidence.",
        "pending": [
            "Broader discovery/recovery adapters, external amendment handling and definitive fee/settlement reconciliation.",
            "Cancel/replace, stop/OCO, trailing, post-only, iceberg and other time-in-force choices.",
            "Execution review for additional providers and authenticated venue acceptance.",
        ],
    },
    {
        "id": "market-data",
        "name": "Market-data infrastructure",
        "status": "partial",
        "priority": "next",
        "working": "Exact-source REST data and retained OHLCV; resumable backfills, immutable inputs, shared read admission/cooldowns and observed source diagnostics.",
        "pending": [
            "Review historical pagination for remaining providers and authenticated provider acceptance.",
            "Reviewed endpoint-weight/IP/account quota policies and durable operational health history.",
            "WebSocket prices and private account/order streams with reconnect recovery.",
        ],
    },
    {
        "id": "operations",
        "name": "Alerts & local operations",
        "status": "partial",
        "priority": "next",
        "working": "Editable source-pinned level/crossing rules, reset-based repeats/cooldowns, revision checks, durable in-app notifications and unread state.",
        "pending": [
            "Portfolio-risk, strategy and connection-failure rules; operational diagnostics.",
            "Optional external delivery with retries and delivery state.",
            "General durable task scheduling, metrics/diagnostics and managed backup/restore.",
        ],
    },
    {
        "id": "strategies",
        "name": "Automated strategy execution",
        "status": "paper-only",
        "priority": "later",
        "working": "Persistent isolated paper runs, worker recovery, fills, journals, charts and lifecycle controls.",
        "pending": [
            "Bind strategies to exchange accounts and reconcile submitted orders/fills across restart.",
            "Exposure/position limits, daily-loss controls, kill switch and explicit stop semantics.",
            "Validate test-environment execution before deliberate production enablement.",
        ],
    },
    {
        "id": "strategy-research",
        "name": "Strategy research",
        "status": "partial",
        "priority": "later",
        "working": "Six configurable algorithms, fee/slippage-aware backtests, buy-and-hold comparison and immutable input snapshots with offline replay.",
        "pending": [
            "Additional benchmarks, parameter optimization and walk-forward/out-of-sample tests.",
            "Custom strategy plugins, optional Freqtrade and multi-asset allocation.",
            "Separate ML/RL training and evaluation pipelines.",
        ],
    },
    {
        "id": "sibyl",
        "name": "Sibyl & messaging",
        "status": "partial",
        "priority": "next",
        "working": "Registry-discovered collaboration, saved chats, live consultation progress, request-specific Stop and durable completed/stopped/failed/interrupted request history.",
        "pending": [
            "Token-by-token answers, richer internal tool traces, usage/cost reporting and evaluated routing/grounding.",
            "Scheduled and resumable investigations; stopped or interrupted requests are not replayed.",
            "WhatsApp, Telegram, Discord and Slack clients, authenticated sender binding, conversation mapping and reliable delivery; setup previews remain unavailable.",
        ],
    },
    {
        "id": "agents",
        "name": "ProtoLink workflows",
        "status": "partial",
        "priority": "later",
        "working": "Ten read-only specialists, startup ProtoLink runtime registry/client routing, contextual tools and shared API/local model profiles.",
        "pending": [
            "Richer narrowly scoped specialist tools and per-agent model/provider selection.",
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
        "reviewed_on": "2026-10-22",
        "scope": "Local single-user workspace",
        "areas": AREAS,
        "current_focus": "Foundational local data and operations, plus observable and cancellable Sibyl requests. Multi-user support is deferred.",
        "execution_note": "Strategies remain paper-only; agents remain read-only. Authenticated venue acceptance is outstanding.",
        "release_dates": None,
    }
