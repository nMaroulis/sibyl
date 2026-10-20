# Spot trading

Sibyl separates a virtual paper wallet from manual exchange execution. These are independent ledgers and workflows, even when paper fills use live market quotes.

**Trade** has three centered tabs: **Trade** for order entry and the order book, **Executions** for recorded paper fills, exchange intents and matched paper results, and **Account history** for imported exchange fills. Order drafts and record filters stay in memory when switching tabs; inactive history/order-book polling pauses.

## Paper orders

Choose an asset, buy or sell, and enter a base-asset quantity. **Review paper order** shows a reference price, notional, 0.1% fee, and estimated debit or credit. **Confirm paper buy/sell** executes against a fresh quote and atomically updates the virtual balances.

Fees are charged in the quote asset. Buys require sufficient quote balance including fees; sells require enough of the base asset. Overspending and overselling are rejected.

The client creates an idempotency key for the reviewed order. Retrying the same request returns the original fill and does not spend twice. Reusing the key with different order details is rejected. Paper fills do not reproduce real liquidity or queue priority.

Order history persists locally in **Executions** and can be exported as CSV. Manual paper orders do not spend paper-strategy job capital.

## Exchange orders

Exchange execution is disabled by default. To enable it, set:

```dotenv
SIBYL_ALLOW_LIVE_TRADING=true
```

Restart the API, connect an account with the appropriate spot trading permission, and use the separate **Exchange execution** section. Choose the account and its production/sandbox environment carefully. This flow can spend actual exchange funds.

The preview validates market availability, active spot status, base-quantity precision, amount/cost limits, and available balance. Buy previews require a 1% balance buffer for price movement and fees. It creates a server-side intent that expires after **60 seconds**. It does not reserve funds or submit a provider test order.

Review the reference notional and type the displayed confirmation, such as `BUY BTC`. Confirmation submits one market order. Real fills and exchange fees can differ from the reference quote; Sibyl does not impose a market-price slippage bound.

## Retry and uncertain outcomes

Before contacting the exchange, Sibyl persists the intent as `submitting`. A repeated confirmation returns the persisted state and never creates a second order. Provider failures with an ambiguous outcome become `unknown`. A process crash can leave an intent as `submitting`, which also requires reconciliation.

**Check the exchange before creating another order after an uncertain outcome.** Use the displayed client order ID and exchange order ID when available. The current version does not continuously synchronize order status, cancel orders, or automatically reconcile ambiguous submissions. The reported state is a submission snapshot, not a guarantee of final settlement.

The exchange receives a `clientOrderId` where supported by the adapter. Application-level duplicate protection remains the primary protection because exchange support differs.

Only this reviewed manual endpoint can submit exchange orders. Oracle agents and paper strategies cannot call it.

## Public order book

The Trade screen shows bids, asks, spread, provider, and observation time for the chart's selected market. Choose 5, 10, 25, or 50 levels. Refresh manually or opt into ten-second polling. Live snapshots cache for five seconds. Demo levels are explicitly synthetic. A snapshot is not an executable quote or a slippage guarantee.

## Execution records and account history

Open **Trade → Executions**. Search by account, symbol, or record ID, and filter mode, side, status, or start date. Status bars follow table filters; CSV exports the filtered records. Previous `/reports` links redirect here, preserving account/history selections. The dock has one Trade destination.

**Executions** contains local paper fills and exchange intents. **Account history** is a separate retained fill ledger. Choose a connected account and one of its exact spot markets to start a background import. Progress saves per page and survives restarts. Pause/resume retains imported fills; **Sync again** collects new fills after a pass completes. Connected-account cards in Settings link directly to this view.

Imports support Demo, Binance, Binance.US, Binance Testnet, Coinbase Advanced Trade, Coinbase Exchange Sandbox and Kraken. Other venues show **Coming soon** for durable imports while existing account reads remain available. Demo reads your manual paper fills without generating trades. Test, demo and production records are labeled separately.

Filter retained fills by account, market, direction and environment. Original fill/order IDs and fees appear beside execution values. Fees keep their currencies; negative fees are rebates and unknown data stays explicit. Fee totals cover the complete filtered selection. **Export this page** exports the displayed page. Disconnecting stops imports/removes saved credentials while retained history stays readable.

**Caught up** describes the selected provider range, not complete account history. Deposits, withdrawals, opening inventory and exchange P&L remain unimplemented. Imports never change balances or infer settlements from previews. See [account synchronization](../developers/account-sync.md) for coverage and recovery details.

The report combines the latest 200 manual paper fills and 100 exchange intents. Manual paper realized P&L matches recorded buys and sells FIFO, allocating buy and sell fees per unit. Opening seed balances have no recorded cost basis. Sales without matching recorded buys are excluded, and truncation of retained history can omit earlier lots. The P&L curve and currency selector use the full retained paper ledger, independently of table filters. Different quote currencies are never added together. Strategy-job fills remain in their isolated console.

Exchange rows include unsubmitted previews as well as submissions; their notional is labeled **Preview reference**, even when an observed average fill price exists. P&L is not inferred from exchange previews. **Refresh records** reloads local history. **Check exchange** uses read-only `fetch_order` for a known exchange order ID, persisting the observed status, filled quantity, average price, and refresh timestamp. This remains available if new execution is disabled. If an uncertain submission has no exchange order ID, reconcile directly at the exchange using the client order ID; it is never resubmitted by refresh.

Advanced order types from the earlier UI are clearly marked **Coming soon**: limit, stop, take-profit, trailing, OCO, TIF, post-only, and iceberg. Current execution is market-only.
