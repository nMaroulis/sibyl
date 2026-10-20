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

**Caught up** describes the selected provider range, not complete account history. Deposits, withdrawals and complete account returns remain unimplemented. Retained market FIFO and editable opening inventory are available in **Account history → Performance**. Imports never change balances or infer settlements from previews. See [account synchronization](../developers/account-sync.md) for coverage and recovery details.

The report combines the latest 200 manual paper fills and 100 exchange intents. Manual paper realized P&L matches recorded buys and sells FIFO, allocating buy and sell fees per unit. Opening seed balances have no recorded cost basis. Sales without matching recorded buys are excluded, and truncation of retained history can omit earlier lots. The P&L curve and currency selector use the full retained paper ledger, independently of table filters. Different quote currencies are never added together. Strategy-job fills remain in their isolated console.

Exchange rows include unsubmitted previews as well as submissions; their notional is labeled **Preview reference**, even when an observed average fill price exists. P&L is not inferred from exchange previews. **Refresh records** reloads local history. **Check exchange** uses read-only `fetch_order` for a known exchange order ID, persisting the observed status, filled quantity, average price, and refresh timestamp. This remains available if new execution is disabled. If an uncertain submission has no exchange order ID, reconcile directly at the exchange using the client order ID; it is never resubmitted by refresh.

Advanced order types from the earlier UI are clearly marked **Coming soon**: limit, stop, take-profit, trailing, OCO, TIF, post-only, and iceberg. Current execution is market-only.

## Active accounts and first use

With no active accounts, Trade shows Connect exchange accounts and the smaller Preview with Demo action. Demo activates the virtual order form with a persistent preview banner. Real/test selections show exchange order entry for active accounts; the virtual form is absent. Execution still requires its separate server enablement, review and confirmation. Deactivated accounts cannot review new orders or confirm an earlier preview. Retained execution records remain stored. Independent strategy simulations use isolated capital and do not activate a Demo wallet.

## Retained account performance

In **Account history**, choose **Performance**. Account, exact-market and environment filters apply to all retained buys and sells; fill-table direction and pagination do not affect matching. Totals stay separate by environment and quote currency. Expand **Calculation details** to inspect the matched-result curve, native-currency fees, excluded unknown-cost units and the latest 100 disposal calculations. **Export summary** downloads per-market results with coverage notes.

Use **Opening inventory** for holdings acquired before the retained history. Enter quantity, optional total cost in that pair’s quote currency and a date before the first retained fill. Blank cost means unknown; zero means known zero cost. Existing market cards have **Opening basis** for editing/removing the assertion and reviewing recent changes. These edits never rewrite imported fills.

Net matched P&L remains unavailable when fees, ordering or cross-market coverage are unresolved. Unknown-cost sales are always excluded from the matched result. It is not your complete account return. A newly imported earlier fill can invalidate an opening date; the card will explain that it was ignored.

**Refresh current marks** reads active account balances and current reference prices. Unrealized figures require known basis, usable conversion rates and a matching base balance. The source, conversion evidence and unavailable reasons remain visible; marks exclude future disposal fees. **Recalculate** uses only local retained history and clears an earlier mark.

**View example** demonstrates four sample fills without creating trades, imports or account data. Close it to return to your report. **Ask about this report** opens Accountant in place, using this report’s selection through ProtoLink, with or without an LLM. The assistant never edits cost basis or fetches private balances for this view. See [calculation rules and limits](../developers/account-performance.md).
