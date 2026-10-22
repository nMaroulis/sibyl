"""User-facing Sibyl features, kept separate from the SDK's raw capabilities.

A CCXT method existing is sufficient for shared bounded reads, but never enables
submission, resumable imports or recovery. Those require Sibyl's explicit gates.
"""

from sibyl.exchanges.funding import funding_streams
from sibyl.exchanges.order_discovery import DISCOVERY_PROVIDERS
from sibyl.exchanges.order_lookup import RECOVERY_PROVIDERS

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
    return [
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
                    True,
                    "Check access reads balances only. It does not verify trading permissions or place an order.",
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
                    "trade_history",
                    "Recent trade reads",
                    "A bounded page of fills for a selected spot pair; this is not a full historical import.",
                ),
                feature(
                    "history_import",
                    "Resumable trade imports",
                    bool(history),
                    "Selected-market imports, native fees, checkpoints and incremental sync; exchange retention still applies."
                    if history
                    else "Durable pagination and checkpoints are not implemented for this exchange.",
                ),
                feature(
                    "fill_reconciliation",
                    "Order fill reconciliation",
                    bool(history) and spec.spot_trading,
                    "Match native fills and fees to orders with bounded, resumable pages."
                    if history and spec.spot_trading
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
                    "Deposit / withdrawal history",
                    "deposit" in funding and "withdrawal" in funding,
                    "Read-only funding imports; unavailable in optional sandboxes."
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
                    demo
                    or spec.id
                    in {"binance", "binanceus", "binance-testnet", "coinbase", "coinbase-sandbox", "kraken"},
                    "Persisted historical candles with reviewed native pagination and gap inspection.",
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
                    False,
                    "Running strategies are paper-only; they cannot submit exchange orders.",
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
