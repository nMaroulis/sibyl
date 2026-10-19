# Spot trading

Sibyl separates a virtual paper wallet from manual exchange execution. These are independent ledgers and workflows, even when paper fills use live market quotes.

## Paper orders

Choose an asset, buy or sell, and enter a base-asset quantity. **Review paper order** shows a reference price, notional, 0.1% fee, and estimated debit or credit. **Confirm paper buy/sell** executes against a fresh quote and atomically updates the virtual balances.

Fees are charged in the quote asset. Buys require sufficient quote balance including fees; sells require enough of the base asset. Overspending and overselling are rejected.

The client creates an idempotency key for the reviewed order. Retrying the same request returns the original fill and does not spend twice. Reusing the key with different order details is rejected. Paper fills do not reproduce real liquidity or queue priority.

Order history persists locally and can be exported as CSV. Manual paper orders do not spend paper-strategy job capital.

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

## Trading report

Open **More → Trading report**, or the link below the trading workspace. Search by account, symbol, or record ID, and filter mode, side, status, or start date. Status bars follow table filters; CSV exports the filtered records.

The report combines the latest 200 manual paper fills and 100 exchange intents. Manual paper realized P&L matches recorded buys and sells FIFO, allocating buy and sell fees per unit. Opening seed balances have no recorded cost basis. Sales without matching recorded buys are excluded, and truncation of retained history can omit earlier lots. The P&L curve and currency selector use the full retained paper ledger, independently of table filters. Different quote currencies are never added together. Strategy-job fills remain in their isolated console.

Exchange rows include unsubmitted previews as well as submissions; their notional is labeled **Preview reference**, even when an observed average fill price exists. P&L is not inferred from exchange previews. **Refresh records** reloads local history. **Check exchange** uses read-only `fetch_order` for a known exchange order ID, persisting the observed status, filled quantity, average price, and refresh timestamp. This remains available if new execution is disabled. If an uncertain submission has no exchange order ID, reconcile directly at the exchange using the client order ID; it is never resubmitted by refresh.

Advanced order types from the earlier UI are clearly marked **Coming soon**: limit, stop, take-profit, trailing, OCO, TIF, post-only, and iceberg. Current execution is market-only.
