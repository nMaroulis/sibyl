# Order and fill reconciliation

**Trade → Order monitor → Executions** compares a local or read-only imported order's cumulative native observation with individual executions in the shared account ledger. The detail dialog shows native and imported base quantities, their difference, reported quote cost, execution IDs and native-currency fees. Opening it only reads SQLite. **Check executions** explicitly refreshes native status and imports one bounded fill page.

This is execution-evidence reconciliation, not a guarantee of settlement, complete account history or exchange P&L. Approved [exchange strategies](../guides/strategy-execution.md) attribute ownership from these native fills; agents remain read-only. Uncertain submissions without a confirmed order ID can now use bounded [client-ID recovery](order-recovery.md). A match joins this execution workflow; missing or ambiguous evidence still requires venue inspection. Neither feature retries a write.

Demo's explicit Check executions action includes the existing managed-status check, which can match a virtual resting order before reading its fill. The execution-page method itself never advances the matcher. Native checks only read provider state.

## Provider reads

`ExchangeClient.fetch_order_fill_page(order_id, symbol, cursor, limit=100)` returns a `TradePage`. `exchanges/order_fills.py` implements reviewed pagination; the shared request coordinator admits these reads under the existing provider budgets and cooldowns.

| Client                    | Read contract                                                                                                                                                                                              |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Binance / Binance Testnet | Exact `orderId` and `fromId`, increasing native trade IDs; an empty page ends a pass.                                                                                                                      |
| Coinbase Advanced Trade   | Native `order_ids` and `product_ids`, with the returned opaque cursor.                                                                                                                                     |
| Coinbase Exchange Sandbox | Native `order_id` and `product_id`, with `CB-AFTER` response-header pagination.                                                                                                                            |
| Kraken                    | Query one order with individual, unconsolidated trade IDs; snapshot at most 10,000 IDs, then query batches of at most 20 IDs. A new pass snapshots the IDs again.                                          |
| OKX                       | Cash spot `ordId`/`instId`, native bill-ID pages within the adapter's 89-day window. Uses reported execution time rather than bill-generation time.                                                        |
| Bybit UTA                 | Spot `orderId`, native execution cursor and seven-day slices beginning one day before the local intent's creation. Exact symbol/order checks still apply because native order-ID filtering takes priority. |
| KuCoin classic            | Exact HF `orderId`/`symbol` and native `lastId`; seven-day inactive-order retention. Ledger identity is the account fill-detail ID.                                                                        |
| Demo                      | Read the exact virtual order's persisted paper fill. Reading executions never advances the matcher.                                                                                                        |
| Other adapters            | Explicitly unsupported; no all-account scan or Demo fallback.                                                                                                                                              |

Provider permissions, retention and actual authenticated account acceptance still require testing. Coinbase Advanced and Exchange Sandbox are different APIs. Native read contracts follow the [Binance account trade list](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/account), [Coinbase Advanced fills](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/orders/list-fills), Kraken's [order queries](https://docs.kraken.com/api-reference/account-data/query-orders-info) and [trade queries](https://docs.kraken.com/api-reference/account-data/query-trades-info). The installed CCXT Exchange adapter supplies sandbox fill parsing and authenticated transport.

## Identity, validation and atomicity

`services/order_reconciliation.py` owns the import checkpoints in `order_fill_sync`. Each successful page validates every row before committing any execution. Account identity comes from the reviewed intent, and the saved exchange/environment must still match the connection. Rows must have the exact symbol, side and native order ID, a usable native fill ID, finite positive quantity/price, valid execution time and bounded fee records. Conflicting duplicate IDs and IDs already attributed to another order reject the page. Repeated or cyclic cursors reject the page.

The page's upserts and cursor commit in one SQLite transaction. A failed transaction repeats that page after restart. `AccountLedger.upsert_fills()` shares the existing account + exact market + native fill identity with ordinary Account history imports, so either path can revisit or correct the same execution without doubling it. Reconciliation never manufactures a fill from cumulative quantity, average price or an order preview. Canceled/rejected orders remain lifecycle observations; only actual executions enter the fill ledger.

Fee corrections update existing observations. Fees and negative rebates keep their reported currencies. Unknown values stay unknown; no historical conversion or final-fee claim is made. Reconciliation summaries read current ledger facts in a coherent SQLite snapshot, so later general-history corrections are reflected without a second remote check.

## Scheduling and recovery

Observing a confirmed native order schedules its local execution-read job atomically. The application worker imports at most one due order-fill page per second, in addition to its existing order-status check. A pass has at most 100 pages of at most 100 fills each; Kraken pages contain at most 20 queried IDs. Opaque cursors stay server-side.

Open orders start another pass about 20 seconds after the previous pass ends. Terminal orders receive **three complete passes**: the next due pass, another at least 60 seconds later, and a third at least 300 seconds after that. These bounded follow-ups allow delayed fills/fee updates to appear; they do not prove that no later corrections can occur. The job then stops automatic checks even if evidence is incomplete. The dialog retains explicit gap/fee/error states and allows another manual check or Resume.

Manual checks read one page and preserve the automatic-check preference. If automatic checks are paused, use Continue to request further pages. Resume resets the terminal-pass counter. Pausing ordinary open-order tracking also pauses its fill job; the dialog's fill pause/resume changes only execution-read scheduling. An inactive account waits without provider reads; manual checks may inspect a saved inactive account. A disconnected account needs its saved credentials restored before remote checks work. Old terminal intents become eligible on an explicit status check rather than silently importing all historical orders.

Checkpoint, enabled state and next attempt survive restart. Failures retain the last valid fills/cursor and back off to at most 15 minutes; five consecutive failures stop automatic reads until explicit Resume. Shared provider deferrals use their retry time without consuming this failure budget. Unsupported adapters stop immediately. Provider exception text and cursor contents are neither exposed nor persisted as public errors. Shutdown waits for the in-flight fill read before releasing shared clients. Use one API worker.

## Evidence states

The ledger maintains an order execution revision keyed by account, exact pair and native order ID. New or changed fills advance that revision in the same transaction as the execution upsert. Identical reimports do not advance it; a rolled-back import changes neither data nor revision. Both account-history and exact-order imports use this writer. The retained detail response includes `fill_revision`, read in the same SQLite snapshot as its fills and native observation.

Strategy cancellation follow-ups compare this revision and the native status/quantity/cost with the evidence they checked. A later imported execution or fee correction reopens completed follow-ups and blocks another strategy signal/position exit immediately, before the strategy worker refreshes its saved monitor. Three matching native checks against unchanged evidence are required again; mismatches never exhaust the follow-up counter. This does not create an unlimited settlement scanner or remove executions omitted from later pages.

| State                        | Meaning                                                                                                                                                                                     |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `matched`                    | Retained gross quantity matches native filled quantity within tolerance, available native quote costs agree, fee fields are known, and the order is terminal. This is not final settlement. |
| `pending`                    | Order remains nonterminal, or an import pass is unfinished.                                                                                                                                 |
| `missing_fills`              | Retained gross quantity is below the native cumulative quantity.                                                                                                                            |
| `fees_missing`               | Matching quantities have one or more executions with incomplete fee evidence.                                                                                                               |
| `mismatch`                   | Excess quantity, conflicting account/side/environment evidence, or a reported quote-cost difference.                                                                                        |
| `unverified` / `not_checked` | No usable native cumulative quantity / no retained execution check.                                                                                                                         |
| `limit_reached`              | More than 10,000 retained fills match this order; comparison is bounded and must not be treated as complete.                                                                                |

Quantities use Decimal comparisons with tolerance `max(1e-10, requested quantity × 1e-8)`. Native quote-cost comparison uses `max(1e-8, abs(native cost) × 1e-6)` for venue rounding. The full bounded selection supplies totals; the dialog displays at most its first 200 fills. Fee totals stay separate by asset, and base-asset fees do not alter gross executed quantity. Every summary reports `settlement_final: false`.

## HTTP contracts

All paths start with `/api/v1`.

| Method | Path                                           | Effect                                                                                  |
| ------ | ---------------------------------------------- | --------------------------------------------------------------------------------------- |
| GET    | `/exchange-orders`                             | Latest 100 intents, enriched with local reconciliation summaries. No remote reads.      |
| GET    | `/exchange-orders/{id}/reconciliation`         | Coherent `{order, fill_revision, reconciliation, fills, has_more}` retained snapshot; no new jobs. |
| POST   | `/exchange-orders/{id}/reconcile`              | Native status check and one exact-order execution page.                                 |
| POST   | `/exchange-orders/{id}/refresh`                | Existing status-check response, now with one execution page and reconciliation summary. |
| POST   | `/exchange-orders/{id}/reconcile/tracking`     | `{enabled: boolean}` changes only persisted execution-read scheduling.                  |
| GET    | `/exchange-orders/example/{id}/reconciliation` | Isolated illustrative evidence, without account/ledger writes.                          |

## Remaining work

Broader recovery adapters, private streams, additional provider adapters, execution bust/removal handling, fee-currency valuation, unlimited historical imports and definitive settlement reconciliation remain separate work. Automatic scans upsert returned facts; they do not delete a retained execution merely because a later page omits it. Initial Binance Testnet native workflows have [scoped acceptance results](exchange-acceptance.md); authenticated partial-fill/cancellation-race, late-correction and broader venue acceptance remain pending. Controlled tests cover identity rejection, pagination, restart, transaction rollback, duplicate imports, partial cancellation, late fee corrections, inactive accounts, renewed matching follow-ups, final-submission evidence changes and isolated Demo/example contracts.

[Account order discovery](order-discovery.md) links native IDs to this same evidence without creating duplicate executions. Imported orders are read-only, including when checked from this dialog.
