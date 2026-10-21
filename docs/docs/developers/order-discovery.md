# Exchange order discovery

Trade → Executions combines Sibyl submissions with **read-only imported orders**. Discovery reads existing exchange orders; it never places, cancels, replaces or retries an order. It works while new native execution is disabled. Demo discovery reads the actual virtual order tables and does not seed examples or advance the matcher.

## Provider coverage

| Client                    | Open orders                             | Recent history                                                                                                |
| ------------------------- | --------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| Binance / Binance Testnet | Account-wide spot snapshot              | Up to 12 explicitly selected exact pairs; blank means open orders only                                        |
| Coinbase Advanced Trade   | Account-level Advanced Trade spot pages | Orders created in the selected range, in the key's permitted portfolio and `RETAIL_ADVANCED` placement source |
| Coinbase Exchange Sandbox | Default open/pending/active order pages | Native `status=all` pages with date bounds                                                                    |
| Kraken                    | Account-wide orders without leverage    | Orders closed in the selected range, including older orders closed recently                                   |
| Demo                      | Actual resting virtual orders           | Actual virtual orders created in the selected range                                                           |

Other providers remain unsupported for discovery. Authenticated venue acceptance is still pending. The adapter excludes unknown, delisted and unsupported markets and Kraken margin orders, and reports an exclusion count. A successful pass does **not** establish complete historical coverage or final settlement. Coinbase Simple Trade, other portfolios, derivatives and archived/delisted instruments are outside this contract.

## Durable scheduling

The user explicitly starts discovery for one active supported account, or all currently active supported accounts (at most 20). This selection is saved per account; subsequently connected accounts are not silently added. No account is activated by discovery.

The initial pass reads open orders, then a frozen recent window of 1, 3 or 7 days. One native page is read per worker tick. A completed enabled job starts another rolling pass about five minutes later. Individual order status/fill tracking is independent, so a discovered open order can still reach its terminal state after it disappears from an open snapshot.

SQLite stores each account's private cursor, stream, range, counters, configuration revision and next attempt. Orders, reconciliation scheduling and the page checkpoint commit in one transaction. Invalid evidence rolls back the page. Interrupted reads resume from the committed checkpoint. Configuration changes invalidate an older in-flight page; pause preserves an in-flight successful checkpoint without re-enabling the job. Inactive accounts wait; disconnected accounts stop and retain their evidence.

Five failed transient reads stop automatic discovery until an explicit resume. Provider admission/cooldowns preserve that failure budget. Authentication, malformed evidence and unsupported operations need attention immediately. Error messages are fixed and sanitized; opaque cursors never appear in API responses.

Each pass is bounded to 100 pages and 10,000 returned observations. Unpaginated Binance/Kraken open snapshots are limited to 1,000 orders. Binance recent requests use at most 24-hour windows; full 1,000-row windows are bisected until unambiguous, rather than skipping timestamp ties. A saturated one-millisecond window stops with a coverage limit. Coinbase uses native cursor/header pagination; Kraken uses native closed-order offsets/counts. These mutable exchange listings are observations, not transactionally consistent exchange snapshots. Repeat passes overlap the selected window to pick up changes.

## Identity and execution evidence

Account ID, exact spot symbol and native order ID define a retained order. A native ID already attached to a Sibyl intent updates that row, preserving its reviewed request and origin. A client ID matching an uncertain Sibyl submission defers the discovered row to the existing [reviewed recovery](order-recovery.md) workflow; discovery does not adopt an identity on client ID alone.

New imported rows use a deterministic internal ID in `exchange_orders`, with `origin: imported` and `read_only: true`. Importing the same native order again updates it. Individual native fills use the existing shared [Account history identities](account-sync.md), so discovery itself never fabricates executions, duplicates fills or changes balances. The existing [execution dialog](order-reconciliation.md) links retained fills immediately and can import additional exact-order execution pages.

Missing quantities, creation times, prices and fees remain unknown. Quote-sized or conditional orders can be inspected without pretending that an original base quantity or GTC instruction was reported. Imported amount/price amendments update the read-only observation; older cumulative fills or reopened terminal observations are rejected. Amendments to reviewed Sibyl intents require separate handling and are not silently substituted for the reviewed request. An absent order never implies cancellation. Fees/settlement, execution busts and general amendment reconciliation remain incomplete.

Both UI controls and backend services reject submission/cancellation of imported rows. Status and execution checks remain read-only, including manual checks of saved inactive accounts. Pause discovery stops future discovery pages; pause tracking stops that order's status reads. Neither action cancels a native order.

## HTTP contract

All paths use `/api/v1`. Read responses have `Cache-Control: no-store`.

| Method | Path                                            | Effect                                                                                                                                                      |
| ------ | ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GET    | `/exchange-orders/monitor`                      | Paginated local/imported monitor; filters `account_id`, `exchange`, `origin` (`sibyl`/`imported`), `status` (`active`/`terminal`), `limit` (1–50), `offset` |
| GET    | `/exchange-orders/discovery`                    | Local supported-account metadata and public progress; no provider reads                                                                                     |
| POST   | `/exchange-orders/discovery`                    | Start/resume with `account_id` (blank: active supported accounts), `days` (1–7), `symbols` (up to 12 Binance history pairs)                                 |
| POST   | `/exchange-orders/discovery/{account_id}/pause` | Persist a discovery pause                                                                                                                                   |
| POST   | `/exchange-orders/{id}/refresh`                 | Observe native status and one execution page, including imported rows                                                                                       |
| GET    | `/exchange-orders/{id}/reconciliation`          | Inspect retained order/fill evidence without provider reads                                                                                                 |

The existing `GET /exchange-orders` and trading report retain their latest-100 **Sibyl submission** contract; imported observations appear in the combined monitor and their executions in Account history. Monitor filters are applied before pagination. Combined views include separately labeled production, test, Demo and retained inactive/disconnected records; they do not sum their funds.

Provider contracts: [Binance account endpoints](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/account), [Coinbase Advanced List Orders](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/orders/list-orders), [Exchange Get all orders](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/orders/get-all-orders), [Kraken Open Orders](https://docs.kraken.com/api-reference/account-data/get-open-orders) and [Closed Orders](https://docs.kraken.com/api-reference/account-data/get-closed-orders).
