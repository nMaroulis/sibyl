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

Market/GTC limit orders and cancellation are implemented for Binance, Binance.US, Coinbase Advanced, Kraken, OKX, Bybit UTA, KuCoin classic and Bitstamp, plus the dedicated test clients. Gemini supports GTC limits and cancellation only. Other production providers remain read-only. Settings → Exchanges shows the current support and gaps for each provider.

Restart the API, connect an account with the appropriate spot trading permission, and use the separate **Exchange execution** section. Choose the account and its production/sandbox environment carefully. This flow can spend actual exchange funds.

The preview validates market availability, active spot status, base-quantity precision, amount/cost limits, and available balance. Buy previews require a 1% balance buffer for price movement and fees. It creates a server-side intent that expires after **60 seconds**. It does not reserve funds or submit a provider test order.

Review the reference notional and type the displayed confirmation, such as `BUY BTC`. Select **Market** or **Limit · GTC**, supply a limit price for a limit order, then confirm once. Real fills and exchange fees can differ from the reference quote; Sibyl does not impose a market-price slippage bound.

## Retry and uncertain outcomes

Before contacting the exchange, Sibyl persists the intent as `submitting`. A repeated confirmation returns the persisted state and never creates a second order. Provider failures with an ambiguous outcome become `unknown`. A process crash can leave an intent as `submitting`, which also requires reconciliation.

**Check the exchange before creating another order after an uncertain outcome.** Where the provider implements client-ID recovery (Binance/Binance.US/Testnet, Coinbase Advanced/Sandbox, Kraken and Demo), use **Recover order** to read existing orders by the saved client ID. Other execution providers require manual inspection at the exchange after an ambiguous submission. A matching account, client ID, market, side, quantity and order type are required before Sibyl attaches a native ID and resumes status/fill checks. Continue lookup advances unfinished history reads. No match is not proof that no order exists; ambiguous, incomplete or mismatched evidence still needs venue inspection. Nothing is automatically resubmitted. See [recovery behavior and provider limits](../developers/order-recovery.md).

The exchange receives a `clientOrderId` where supported by the adapter. Application-level duplicate protection remains the primary protection because exchange support differs.

Only this reviewed manual endpoint can submit exchange orders. Oracle agents and paper strategies cannot call it.

## Public order book

The Trade screen shows bids, asks, spread, provider, and observation time for the chart's selected market. Choose 5, 10, 25, or 50 levels. Refresh manually or opt into ten-second polling. Live snapshots cache for five seconds. Demo levels are explicitly synthetic. A snapshot is not an executable quote or a slippage guarantee.

## Execution records and account history

Open **Trade → Executions**. Search by account, symbol, or record ID, and filter mode, side, status, or start date. Status bars follow table filters; CSV exports the filtered records. Previous `/reports` links redirect here, preserving account/history selections. The dock has one Trade destination.

**Executions** contains local paper fills and exchange intents. **Account history** is a separate retained fill ledger. Choose a connected account and one of its exact spot markets to start a background import. Progress saves per page and survives restarts. Pause/resume retains imported fills; **Sync again** collects new fills after a pass completes. Connected-account cards in Settings link directly to this view.

Imports support Demo, Binance, Binance.US, Binance Testnet, Coinbase Advanced Trade, Coinbase Exchange Sandbox and Kraken. Other venues show **Coming soon** for durable imports while existing account reads remain available. Demo reads your manual paper fills without generating trades. Test, demo and production records are labeled separately.

Filter retained fills by account, market, direction and environment. Original fill/order IDs and fees appear beside execution values. Fees keep their currencies; negative fees are rebates and unknown data stays explicit. Fee totals cover the complete filtered selection. **Export this page** exports the displayed page. Disconnecting stops imports/removes saved credentials while retained history stays readable.

**Caught up** describes the selected provider range, not complete account history. Separate funding range imports are available below; complete account returns remain unimplemented. Retained market FIFO and editable opening inventory are available in **Account history → Performance**. Imports never change balances or infer settlements from previews. See [account synchronization](../developers/account-sync.md) for coverage and recovery details.

The report combines the latest 200 manual paper fills and 100 exchange intents. Manual paper realized P&L matches recorded buys and sells FIFO, allocating buy and sell fees per unit. Opening seed balances have no recorded cost basis. Sales without matching recorded buys are excluded, and truncation of retained history can omit earlier lots. The P&L curve and currency selector use the full retained paper ledger, independently of table filters. Different quote currencies are never added together. Strategy-job fills remain in their isolated console.

Exchange rows include unsubmitted previews as well as submissions; their notional is labeled **Preview reference**, even when an observed average fill price exists. P&L is not inferred from exchange previews. **Refresh records** reloads local history. **Check exchange** reads a known exchange order ID, persisting its native observation and one execution page. Read checks remain available if new execution is disabled. For uncertain submissions without an ID, **Recover order** performs a bounded lookup; inspect the venue if it cannot verify one match.

## Resting limits and the order monitor

**Paper limit orders** uses the active Demo wallet. Choose a side, market, base quantity and limit price, review, then type the displayed phrase. Placement reserves virtual funds; market orders show only the remaining available balance. The separate Demo bid/ask feed matches a crossing order in full at its limit, with a 0.1% quote fee. It does not simulate queues or partial fills.

The **Order monitor** in Trade and Executions lists submitted orders, cumulative filled/remaining quantities, average fill, status and tracking preference. A native `open` order with some fills appears as **Partially filled**. Its **Executions** column opens an in-place comparison with retained native fill IDs, quantities, reported cost and fees. **Check executions** imports one exact-order page; enabled background checks continue unfinished pages. Missing executions, incomplete fees and differing evidence are shown explicitly. **View example** demonstrates these details without changing any data; sample mutation/check controls are disabled.

**Cancel…** reads the latest native state and opens an in-place review. Type the displayed cancellation phrase. Acknowledgment is not proof of cancellation; the status read determines whether cancellation or a fill won the race. An uncertain attempt is shown clearly and never automatically retried.

Tracking reads status approximately every 20 seconds on the server, with increasing delays on errors. It survives restart, pauses for inactive accounts and can be paused/resumed per order. Pausing does not cancel a native order. Known-ID checks and reviewed cancellation remain available if new exchange execution is disabled. Execution checks share Account history's ledger, so importing through both paths does not duplicate a fill. Terminal orders receive three bounded follow-up passes for late fee updates. You can pause/resume fill checks or recheck later. A match compares available evidence and never guarantees final settlement. Demo fills appear only once in execution history. See [reconciliation details and limits](../developers/order-reconciliation.md).

GTC remains open until filled or canceled; the 60-second deadline applies to the review, not the submitted order. Stop/OCO, cancel/replace, post-only, iceberg and other time-in-force choices remain **Coming soon**. See [order contracts, provider support and recovery](../developers/order-management.md).

## Active accounts and first use

With no active accounts, order entry shows Connect exchange accounts and the smaller Preview with Demo action. **Executions** and **Account history** remain readable, including isolated order examples, without activating any account. Demo activates the virtual order form with a persistent preview banner. Real/test selections show exchange order entry for active accounts; the virtual form is absent. Execution still requires its separate server enablement, review and confirmation. Deactivated accounts cannot review new orders or confirm an earlier preview. Independent strategy simulations use isolated capital and do not activate a Demo wallet.

## Retained account performance

In **Account history**, choose **Performance**. Account, exact-market and environment filters apply to all retained buys and sells; fill-table direction and pagination do not affect matching. Totals stay separate by environment and quote currency. Expand **Calculation details** to inspect the matched-result curve, native-currency fees, excluded unknown-cost units and the latest 100 disposal calculations. **Export summary** downloads per-market results with coverage notes.

Use **Opening inventory** for holdings acquired before the retained history. Enter quantity, optional total cost in that pair’s quote currency and a date before the first retained fill. Blank cost means unknown; zero means known zero cost. Existing market cards have **Opening basis** for editing/removing the assertion and reviewing recent changes. These edits never rewrite imported fills.

Net matched P&L remains unavailable when fees, ordering or cross-market coverage are unresolved. Unknown-cost sales are always excluded from the matched result. It is not your complete account return. A newly imported earlier fill can invalidate an opening date; the card will explain that it was ignored.

**Refresh current marks** reads active account balances and current reference prices. Unrealized figures require known basis, usable conversion rates and a matching base balance. The source, conversion evidence and unavailable reasons remain visible; marks exclude future disposal fees. **Recalculate** uses only local retained history and clears an earlier mark.

**View example** demonstrates four sample fills without creating trades, imports or account data. Close it to return to your report. **Ask about this report** opens Accountant in place, using this report’s selection through ProtoLink, with or without an LLM. The assistant never edits cost basis or fetches private balances for this view. See [calculation rules and limits](../developers/account-performance.md).

## Funding movements

Open **Trade → Account history → Funding**. Select an active supported account, choose the offered streams and a historical range shorter than 90 days, then **Import range**. Binance imports crypto deposits/withdrawals; Kraken imports posted deposit/withdrawal/transfer ledger entries. Other providers show their current limits. Demo imports an actual empty history; **View example** demonstrates sample records without creating account transactions.

**Pause/Resume** keeps progress. Pause an active stream before changing its date range. **Rescan range** revisits a completed range to update statuses, fees or late records. Older ranges stay retained even when you select a new range. **Range fetched** refers only to that provider range, not complete account history.

Filter by account, asset, movement, status or environment. Completed summaries include all matching pages and keep currencies and directions separate. Pending, restricted and failed observations are absent from completed totals. Amounts and fees stay separate because fee inclusion is not inferred. An internal-at-venue marker does not prove an own-account transfer. **Export this page** downloads displayed records; **Ask about funding** uses the same selection through ProtoLink.

Funding observations flag affected FIFO coverage; they do not supply cost basis or investment returns. No funding control deposits, withdraws or transfers money. See [funding support, permissions and limits](../developers/funding-history.md).

## Review transfers between your accounts

From **Funding**, choose **Reconcile transfers**. Review a suggested pair or use **Match records** to search older native IDs/accounts. Account filters match either side. Suggestions expose timing, reported amount/fee differences and competing counterparts; nothing is automatically paired.

Choose **Confirm own-account transfer** after reviewing the current source records. Differing amounts or unusual timing require a review note. A later source correction marks the saved link **Needs review**. Open it to compare current/saved evidence and explicitly reconfirm. **Remove link** releases the records while preserving history; enable **Include removed links** to review and restore one.

Funding-row classification links open the saved review. Classifications change neither native amount totals nor FIFO lots. Unmatched funding is unreviewed, not automatically external cash flow. **View example** is isolated and cannot save links; **Ask about transfers** reads the selected local evidence through ProtoLink. See [transfer review limits](../developers/transfer-reconciliation.md).

### Preserve basis when moving between accounts

After reviewing an own-account pair in Funding, open **Performance** and recalculate. Equal-amount, explicitly zero-fee confirmed pairs can carry the original acquisition lots and costs between accounts. Expand **Carried lots & unapplied links** to inspect original dates, source record IDs and reasons a link could not apply. Filtering to the receiving account still reads required donor/intermediate history.

**Transfer example** demonstrates a sale of an older transferred lot and a newer local purchase, without changing account records. Unsupported fees/amount differences, missing history and cross-market ambiguity remain provisional. This is market FIFO, not full account returns. See [carryover rules](../developers/transfer-cost-basis.md).

To carry lots for a fee-bearing transfer, open its review and select **Review amount & fee allocation**. Choose both amount conventions, verify missing fee quantities and distinct charges, then check the allocation and explain it in the review note. Performance shows received lots and fee-unit inventory cost separately. Historical fee valuation remains unavailable, so final net stays provisional. **Transfer example → With a transfer fee** demonstrates this without account writes. See [fee review](../developers/transfer-fees.md).

## Orders placed outside Sibyl

In **Trade → Executions → Order monitor**, choose **Sync exchange orders**. Select one active supported account or all of them, then a recent range. Binance history additionally needs exact pairs such as `BTC/USDT`; leaving that field blank still discovers all supported open Binance orders. Coinbase and Kraken read their account-level recent pages. Demo reads actual virtual orders.

Imported rows have an **Imported · read-only** badge. Use the exchange, account, origin and status filters to compare venues, or open execution evidence to inspect linked native fills and fees. Manage imported orders directly at the exchange. **Pause discovery** stops discovery pages; each order has a separate status-tracking preference. Neither control cancels orders. Enabled discovery repeats about every five minutes while accounts are active.

Progress, errors, exclusions and checkpoints survive restart. Missing orders are not assumed canceled; incomplete or unavailable amounts stay unknown. This is bounded open/recent coverage, not a complete account-history guarantee. See [provider-specific coverage and limitations](../developers/order-discovery.md).

## Refresh imported history

In **Account history → Fills & imports**, choose an active account and exact spot market. The form explains that provider’s retention. **Sync market history** starts an import or resumes its saved checkpoint; **Sync again** collects new observations. To recheck older fees or delayed fills, pause active work and choose **Rescan available history**. Rescans keep local history and update returned records by native identity. The progress list shows retained dates and new/corrected fills in the last completed pass; dates do not establish gap-free coverage. Records outside provider retention may be unavailable.

OKX covers the last 89 days, Bybit UTA traverses up to 730 days in seven-day windows, KuCoin classic exposes seven days of inactive-order fills, and Bitget classic covers 89 days. Authenticated account validation remains outstanding; these are implemented read contracts, not verified connectivity for a particular account. See [provider contracts](../developers/account-sync.md).
