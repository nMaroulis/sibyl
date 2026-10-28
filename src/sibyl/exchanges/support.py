"""User-facing Sibyl features, kept separate from the SDK's raw capabilities.

A CCXT method existing is sufficient for shared bounded reads, but never enables
submission, resumable imports or recovery. Those require Sibyl's explicit gates.
"""

from sibyl.exchanges.data import CANDLE_HISTORY_PROVIDERS
from sibyl.exchanges.funding import funding_streams
from sibyl.exchanges.order_discovery import DISCOVERY_PROVIDERS
from sibyl.exchanges.order_fills import ORDER_FILL_KINDS
from sibyl.exchanges.order_lookup import RECOVERY_PROVIDERS
from sibyl.exchanges.spot_history import history_note

KEY_STORAGE = (
    "API keys are stored locally and encrypted on the machine running Sibyl's Python backend. "
    "Only the backend uses them to authenticate with your exchange; they are never returned "
    "by the API or passed to AI agents. A separate local vault key unlocks the stored credentials."
)


def support_groups(spec, capabilities: dict, history: str | None) -> list[dict]:
    """Describe implemented app paths and explicit gaps without probing private accounts."""
    demo = spec.simulated

    def feature(identity, label, available, detail, *, unavailable=False):
        return {
            "id": identity,
            "label": label,
            "status": "simulated"
            if available and demo
            else "available"
            if available
            else "unavailable"
            if unavailable
            else "pending",
            "detail": detail,
        }

    def read(identity, label, detail):
        supported = capabilities.get(identity) in {"native", "emulated", "simulated"}
        return feature(identity, label, supported, detail, unavailable=not supported)

    funding = funding_streams(spec.id)
    market_orders = spec.market_orders or demo
    balance_reads = capabilities.get("balances") in {"native", "emulated", "simulated"}
    backfills = (demo or spec.id in CANDLE_HISTORY_PROVIDERS) and capabilities.get("candles") in {
        "native",
        "emulated",
        "simulated",
    }
    groups = [
        {
            "id": "account",
            "label": "Account overview",
            "features": [
                read(
                    "balances",
                    "Balances & portfolio",
                    spec.account
                    + ". Combine active accounts or select one account/exchange; test funds stay separate.",
                ),
                feature(
                    "multiple_accounts",
                    "Multiple accounts",
                    not demo,
                    "Demo uses one persistent virtual wallet per workspace."
                    if demo
                    else "Save separate keys and labels for multiple accounts on this exchange.",
                    unavailable=demo,
                ),
                feature(
                    "permissions",
                    "Credential check",
                    balance_reads,
                    "Check access reads balances only. It does not verify trading permissions or place an order."
                    if balance_reads
                    else "Balance verification is unavailable through this adapter.",
                    unavailable=not balance_reads,
                ),
            ],
        },
        {
            "id": "spot",
            "label": "Spot trading",
            "features": [
                feature(
                    "market_orders",
                    "Market buy & sell",
                    market_orders,
                    "Reviewed base-asset quantity; preview and explicit confirmation required."
                    if market_orders
                    else "Native market orders are unavailable through the installed Gemini adapter; GTC limits are available."
                    if spec.id == "gemini"
                    else "Sibyl submission adapter has not been reviewed for this exchange.",
                    unavailable=spec.id == "gemini",
                ),
                feature(
                    "limit_orders",
                    "Limit buy & sell · GTC",
                    spec.spot_trading,
                    "An explicit limit price and base quantity; no automatic resubmission."
                    if spec.spot_trading
                    else "Limit order submission is not implemented in Sibyl for this exchange.",
                ),
                feature(
                    "cancel_orders",
                    "Cancel a Sibyl order",
                    spec.spot_trading,
                    "Preview and confirm cancellation of a known open order; fills can race cancellation."
                    if spec.spot_trading
                    else "Cancellation is not enabled in Sibyl for this exchange.",
                ),
                feature(
                    "advanced_orders",
                    "Stop / OCO / cancel-replace",
                    False,
                    "These order types and amendments are not implemented in Sibyl, even where the exchange offers them.",
                ),
            ],
        },
        {
            "id": "history",
            "label": "History & synchronization",
            "features": [
                read(
                    "order_status",
                    "Order status & partial fills",
                    "Bybit status reads cover the last 500 account orders; older orders may require checking at the exchange. Detailed fill evidence is listed under History."
                    if spec.id == "bybit"
                    else "Read cumulative execution status for a known order ID. Detailed fill evidence is listed under History.",
                ),
                read(
                    "open_orders",
                    "Read open orders",
                    "Read a bounded snapshot for an exact spot pair; account-wide discovery is listed under History.",
                ),
                read(
                    "trade_history",
                    "Recent trade reads",
                    "A bounded page of fills for a selected spot pair; this is not a full historical import.",
                ),
                feature(
                    "history_import",
                    "Resumable trade imports",
                    bool(history),
                    "Selected-market imports, native fees, checkpoints, incremental sync and full available-history rescans. "
                    + history_note(spec.id)
                    if history
                    else "Durable pagination and checkpoints are not implemented for this exchange.",
                ),
                feature(
                    "fill_reconciliation",
                    "Order fill reconciliation",
                    (demo or history in ORDER_FILL_KINDS) and spec.spot_trading,
                    "Match native fills and fees to orders with bounded, resumable pages. "
                    + history_note(spec.id)
                    if (demo or history in ORDER_FILL_KINDS) and spec.spot_trading
                    else "Detailed fill/fee reconciliation is pending; cumulative native order status is separate.",
                ),
                feature(
                    "recovery",
                    "Recover uncertain submissions",
                    spec.id in RECOVERY_PROVIDERS,
                    "Read existing orders by the persisted client ID; never resubmit an uncertain order."
                    if spec.id in RECOVERY_PROVIDERS
                    else "Automatic client-ID recovery is pending. Resolve an ambiguous submission at the exchange; never retry it blindly.",
                ),
                feature(
                    "discovery",
                    "Import account orders",
                    spec.id in DISCOVERY_PROVIDERS,
                    "Read-only discovery of account orders, including orders placed outside Sibyl."
                    if spec.id in DISCOVERY_PROVIDERS
                    else "Account-wide order discovery is not implemented; exact-pair open-order reads are separate.",
                ),
                feature(
                    "funding",
                    "On-chain withdrawal history"
                    if funding == ["withdrawal"]
                    else "Deposit / withdrawal history",
                    "deposit" in funding or "withdrawal" in funding,
                    "Master-UID on-chain withdrawal reads, native cursors and status/fee rescans. Deposits, off-chain transfers, additional tax charges and sub-UID reads remain pending; unavailable in optional sandboxes."
                    if spec.id == "bybit" and funding
                    else "Read-only funding imports; unavailable in optional sandboxes."
                    if funding
                    else "Funding history imports are not implemented for this provider/environment.",
                ),
                feature(
                    "transfers",
                    "Transfer history",
                    "transfer" in funding,
                    "Read-only transfer ledger imports; unavailable in optional sandboxes."
                    if "transfer" in funding
                    else "Transfer history imports are not implemented for this provider/environment.",
                ),
            ],
        },
        {
            "id": "market",
            "label": "Market data",
            "features": [
                read("ticker", "Prices & tickers", "Public spot prices; no account API key required."),
                read(
                    "candles",
                    "Candlestick charts",
                    "REST OHLCV snapshots and the provider's available intervals.",
                ),
                read("order_book", "Order book", "Bounded REST bid/ask depth snapshots."),
                feature(
                    "backfills",
                    "Historical candle backfills",
                    backfills,
                    "Persisted historical candles with reviewed native pagination and gap inspection."
                    if backfills
                    else "Historical pagination is not implemented for this provider; current chart samples can still be retained.",
                ),
                feature(
                    "websocket",
                    "Live WebSocket streams",
                    False,
                    "Prices and account updates currently use REST; WebSocket streams are pending.",
                ),
            ],
        },
        {
            "id": "limits",
            "label": "Automation & limits",
            "features": [
                feature(
                    "automated",
                    "Automated exchange strategies",
                    not demo and spec.spot_trading and history in ORDER_FILL_KINDS,
                    "Account-bound, approved price-capped GTC strategies with native fill accounting, restart pause and risk limits. Both execution flags are required; private venue acceptance is pending."
                    if not demo and spec.spot_trading and history in ORDER_FILL_KINDS
                    else "Demo uses isolated paper strategy runs."
                    if demo
                    else "Automated exchange strategies require implemented order submission and exact-order native fill imports.",
                ),
                feature(
                    "derivatives",
                    "Margin / futures / options",
                    False,
                    "Sibyl exchange trading is spot-only.",
                    unavailable=True,
                ),
                feature(
                    "withdrawals",
                    "Send withdrawals or transfers",
                    False,
                    "Sibyl never initiates withdrawals or wallet transfers. Keep these API permissions disabled.",
                    unavailable=True,
                ),
            ],
        },
    ]

    for group in groups:
        group["summary"] = category_summary(group["features"])
    return groups


def category_summary(features: list[dict]) -> dict:
    """Count every listed feature; missing/unsupported rows cannot turn a category green.

    This is implementation coverage, never network health, credential verification
    or a guarantee that an exchange grants access to a particular user's account.
    """
    total = len(features)
    implemented = sum(row["status"] in {"available", "simulated"} for row in features)
    simulated = any(row["status"] == "simulated" for row in features)
    status = (
        "unsupported"
        if not implemented
        else "simulated"
        if simulated
        else "supported"
        if implemented == total
        else "partial"
    )
    return {"status": status, "implemented": implemented, "total": total}
