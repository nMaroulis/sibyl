# Account synchronization and fill ledger

Account imports are read-only, resumable jobs for explicitly selected spot markets. They are independent of public market-data mode. An import never places an order, changes a paper balance, or infers portfolio performance from a preview.

Open **Trade → Account history**, or **Settings → Exchanges → Connected accounts → Account history**. Choose an account and one of its exact spot markets, then press **Sync market history**. **Sync again** collects new fills from the saved checkpoint. This is user-triggered incremental synchronization, not continuous private-account polling.

## Implemented adapters

| Client                               | Pagination                                                                         | Scope                                                          |
| ------------------------------------ | ---------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| Demo                                 | `(created_at, id)` keyset                                                          | Existing manual paper fills; timestamp ties are retained       |
| Binance, Binance.US, Binance Testnet | Native `fromId`, beginning at zero; next highest trade ID plus one                 | Exact spot market; continues until an empty page               |
| Coinbase Advanced Trade              | Native opaque cursor in a fixed time window                                        | Spot fills for the selected product and permissioned portfolio |
| Coinbase Exchange Sandbox            | Native `CB-AFTER` response header and `after` parameter                            | Selected sandbox product                                       |
| Kraken                               | `with_cursor`, `cursor.next`, fixed time window, exact pair and `type=no position` | Non-position spot fills; requests individual taker fills       |

Other clients retain balance, order and bounded-fill reads. Durable imports explicitly show **Coming soon**. CCXT's `fetchMyTrades` capability alone does not establish safe historical pagination. The provider catalog reports `history_import` separately.

Subsequent Coinbase and Kraken passes overlap one day to pick up late/corrected observations. Native IDs deduplicate or update existing records. Older late records/corrections can still be missed; full rescans and reconciliation remain future work. Coinbase's custom `sort_by` is omitted because its documentation warns about unstable pagination for sorted results.

Offline tests exercise actual installed CCXT parsers and native requests with final transports replaced. **Authenticated private-account acceptance tests remain outstanding.** Provider retention, permissioned portfolio and active/delisted markets constrain coverage.

References: [CCXT pagination](https://github.com/ccxt/ccxt/wiki/Manual#pagination), [Binance account trades](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/ws-api/account), [Binance.US account trades](https://github.com/binance-us/binance-us-api-docs/blob/master/rest-api.md#account-trade-list-user_data), [Coinbase fills](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/orders/list-fills), [Coinbase Exchange cursor headers](https://docs.cdp.coinbase.com/exchange/rest-api/pagination), [Kraken trade history](https://docs.kraken.com/api-reference/account-data/get-trades-history).

## Ownership and persistence

- `exchanges/history.py` defines `TradePage` and reviewed native page adapters. `ExchangeClient.fetch_trade_page()` is separate from bounded `fetch_my_trades()`.
- `services/ledger.py` owns `account_fills` and `account_sync` in workspace `sibyl.db`. Fills retain execution values, source/environment, native fill/order IDs, and fee currencies/signs. Raw provider responses and credentials are excluded.
- `services/account_sync.py` validates selections, schedules pages, sanitizes failures and exposes public progress. Opaque cursors and a short cursor-loop guard stay server-side.
- A separate lifespan worker attempts one page per second, fairly across queued markets. Pages contain at most 100 fills; existing CCXT rate limits and client locks also apply. Run one API process; this is not a distributed scheduler.

Identity is `(account_id, exact_symbol, trade_id)`, so accounts/environments cannot collapse together. Every page's upserts and next checkpoint commit in one transaction. Validation failure rejects the entire page and preserves the prior checkpoint. A crash before commit repeats the page safely. Startup returns interrupted `running` jobs to `queued` at their saved checkpoints.

Pause prevents further pages. An already in-flight successful page may commit its fills and cursor while staying paused. Resume uses that checkpoint. Disconnect removes saved credentials, stops imports and retains local fill history. Retained records do not count as current holdings or reconstruct balances.

## Progress and failures

States are **Queued**, **Importing**, **Waiting to retry**, **Caught up**, **Paused**, **Needs attention**, and **Disconnected**. Progress includes retained fills, cumulative pages, inserted/updated counts, last successful page, last completed pass, safe errors and retry time.

Transport/rate-limit failures retry up to five times after the initial attempt, after 15, 30, 60, 120 and 240 seconds. Authentication, unavailable markets, unsupported operations and malformed pages wait for explicit retry. Non-advancing/recently repeated cursors stop imports. Private provider error text never reaches the UI or agents. Technician can read import status through its existing ProtoLink tool; it cannot mutate imports.

**Caught up** means the available selected-market range was exhausted. Every ledger/job response retains `complete_history: false`; this does not establish coverage of every account event, historical instrument or opening lot.

## Ledger semantics

Execution timestamps differ from first/last local observation times. Amount is in base units; price/notional are in the quote. Notional may be unavailable. Numeric values use the unified client/CCXT representation, not a tax-grade decimal accounting engine.

Fees keep reported currencies and signs. Negative values are rebates. Missing amounts/currencies remain unavailable with an incomplete-data flag. Totals group by currency over the full filtered selection, independently of pagination. Currencies are never added together or assumed to equal the trade quote.

The UI filters by account, market, side and environment. It reads 50 fills per page; **Export this page** exports that page with IDs, fee currencies and completeness flags. Previews remain in **Executions**. Demo imports copy existing manual paper fills into this read-only ledger; they create no new trades/balances. Strategy fills stay in their isolated monitor.

Retained fills now feed [market FIFO performance](account-performance.md), including audited opening inventory and optional balance-checked current marks. Deposits, withdrawals, transfers, order/intent reconciliation and complete cross-market account performance remain unimplemented. See the [backend checklist](backend-roadmap.md).

## HTTP contracts

All paths use `/api/v1` and normal workspace access controls.

| Method | Path                                           | Purpose                                                                      |
| ------ | ---------------------------------------------- | ---------------------------------------------------------------------------- |
| GET    | `/account-sync`                                | Accounts, import support and public progress; no provider calls              |
| GET    | `/connections/{id}/markets`                    | Exact active spot symbols at the account's venue/environment                 |
| POST   | `/connections/{id}/sync`                       | Queue/resume `{"symbols":["BTC/USDT"]}`; 1–12 canonical symbols; returns 202 |
| POST   | `/connections/{id}/sync/pause?symbol=BTC/USDT` | Pause one market; omit `symbol` for all account imports                      |
| GET    | `/account-ledger/fills`                        | Retained fills, total count, native-currency fee totals and limits           |

Ledger filters: `account_id`, optional exact `symbol`, `side` (`buy`/`sell`), `environment` (`demo`/`test`/`production`), `limit` (1–100, default 50), and `offset` (0–1,000,000). Sort is execution time and stable local ID, newest first. New imports may shift offset page boundaries. Caller-supplied provider cursors, arbitrary endpoints and CCXT parameters are not accepted.

Run `uv run pytest tests/test_account_sync.py` for offline pagination, parser, checkpoint, recovery, fee, isolation and API tests.
