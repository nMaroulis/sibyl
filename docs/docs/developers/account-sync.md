# Account synchronization and fill ledger

Account imports are read-only, resumable jobs for explicitly selected spot markets. They are independent of public market-data mode. An import never places an order, changes a paper balance, or infers portfolio performance from a preview.

Open **Trade → Account history**, or **Settings → Exchanges → Connected accounts → Account history**. Choose an account and one of its exact spot markets, then press **Sync market history**. **Sync again** collects new fills from the saved checkpoint. This is user-triggered incremental synchronization, not continuous private-account polling.

## Implemented adapters

| Client                               | Pagination                                                                         | Scope                                                                                             |
| ------------------------------------ | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- |
| Demo                                 | `(created_at, id)` keyset                                                          | Existing manual paper fills; timestamp ties are retained                                          |
| Binance, Binance.US, Binance Testnet | Native `fromId`, beginning at zero; next highest trade ID plus one                 | Exact spot market; continues until an empty page                                                  |
| Coinbase Advanced Trade              | Native opaque cursor in a fixed time window                                        | Spot fills for the selected product and permissioned portfolio                                    |
| Coinbase Exchange Sandbox            | Native `CB-AFTER` response header and `after` parameter                            | Selected sandbox product                                                                          |
| Kraken                               | `with_cursor`, `cursor.next`, fixed time window, exact pair and `type=no position` | Non-position spot fills; requests individual taker fills                                          |
| OKX                                  | `after` with native `billId`, frozen `begin`/`end`                                 | Cash spot fills; requests the last 89 days within three-month retention                           |
| Bybit UTA                            | `nextPageCursor` inside contiguous seven-day windows                               | UTA spot fills; requests the last 730 days; pre-upgrade/classic and margin excluded               |
| KuCoin classic                       | HF endpoint `lastId`, frozen `startAt`/`endAt`                                     | Last seven days; inactive orders have a seven-day retention limit; no abandoned endpoint fallback |
| Bitget classic                       | `idLessThan` using the returned `tradeId`, frozen `startTime`/`endTime`            | Last 89 days within 90-day retention; no UTA/margin substitution                                  |
| MEXC                                 | Frozen millisecond windows split at the native response cap                    | Rolling 27 days. Uses deal and order IDs together to distinguish self-trade legs. |
| CoinEx                               | Page numbers with native `pagination.has_next` and frozen millisecond bounds | Initial query covers 30 days, with a one-day overlap on subsequent passes. Native retention can limit coverage. |
| Poloniex                             | Exact native `pageId` with fixed millisecond bounds and inclusive-edge handling | Initial seven-day cash query, then one-day overlap. Each distinct parent must prove unborrowed scope; unavailable parents require review. At most 20 fills are committed per page. |
| Bitfinex                             | Frozen execution ranges split at the native response cap, with one-day incremental overlap | Initial 90-day query for cash EXCHANGE fills. Margin fills are excluded; missing type evidence needs review. Native IDs share exact-order imports. |
| Phemex                               | Frozen seven-day selected-pair query with native offsets | Spot endpoints; one-day overlap; currency scale gaps stay unknown. |
| Gate                                 | Frozen seven-day second-based query with native page numbers | Cash parents verified; at most 20 fills and parent reads per page. |
| HTX                                  | Seven-day query in saved 48-hour ranges, split at saturation | Exact spot wallet and parents verified; at most 20 fills/parent reads per page. |
| Upbit Korea                          | Saved regular open/closed-order listings and per-parent UUID pages | Current open orders plus closed orders created within seven days. Older closed orders and per-fill fees remain incomplete. |
| BitMart                              | Frozen millisecond ranges split at the native response cap | Initial query covers seven days, followed by one-day incremental overlap. Unsplittable timestamp boundaries stop for review. |

Bitstamp and Gemini now also have the reviewed contracts below. Other clients retain balance, order and bounded-fill reads; their unimplemented durable imports explicitly show **Coming soon**. CCXT's `fetchMyTrades` capability alone does not establish safe historical pagination. The provider catalog reports `history_import` separately.

Subsequent Coinbase, Kraken, OKX, Bybit, KuCoin, Bitget, MEXC, CoinEx, BitMart, Poloniex and Bitfinex passes overlap one day to pick up late/corrected observations. Binance and Demo resume native identity checkpoints. Native IDs deduplicate or update existing records. Coinbase's custom `sort_by` is omitted because its documentation warns about unstable pagination for sorted results.

**Rescan available history** restarts the selected market at its adapter's available-history boundary. Pause active work first. Rescans keep existing evidence, upsert returned corrections and report new/corrected fill counts per completed pass. They do not delete an old fill because the provider omits it. Records and corrections outside current retention can remain unavailable; rescanning is not proof of complete history or final settlement. There is no automatic periodic rescan.

OKX cursors use bill IDs while execution timestamps use reported `fillTime`, falling back to `ts` when absent. KuCoin uses the account fill-detail `id` as ledger identity: both legs of a self-trade can share a match `tradeId`. Bybit retains only explicitly reported fee currencies instead of the SDK's inference. Unsupported margin, special execution, tax and extra-fee cases reject the page rather than silently dropping charges. Bitget Classic exact-order reconciliation shares these ledger identities. Currency effects from unverified Bitget discount fees stay unknown.

Offline tests exercise actual installed CCXT parsers and native requests with final transports replaced. **Authenticated private-account acceptance tests remain outstanding.** Provider retention, permissioned portfolio and active/delisted markets constrain coverage.

References: [CCXT pagination](https://github.com/ccxt/ccxt/wiki/Manual#pagination), [Binance account trades](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/ws-api/account), [Binance.US account trades](https://github.com/binance-us/binance-us-api-docs/blob/master/rest-api.md#account-trade-list-user_data), [Coinbase fills](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/orders/list-fills), [Coinbase Exchange cursor headers](https://docs.cdp.coinbase.com/exchange/rest-api/pagination), [Kraken trade history](https://docs.kraken.com/api-reference/account-data/get-trades-history).

Additional native contracts: [OKX fill history](https://www.okx.com/docs-v5/en/#order-book-trading-trade-get-transaction-details-last-3-months), [Bybit executions](https://bybit-exchange.github.io/docs/v5/order/execution), [KuCoin classic HF fills](https://www.kucoin.com/docs-new/rest/spot-trading/orders/get-trade-history), [Bitget classic fills](https://www.bitget.com/docs/catalog/classic-spot-trade/classic-spot-trade).

MEXC reports a one-month API history limit. Sibyl requests a rolling 27 days, saves split windows across restarts and overlaps one day on each incremental pass. A capped single millisecond or a frozen window that ages out stops the import with the saved checkpoint intact. Account and exact-order imports keep the venue’s native deal IDs, order IDs and reported fees. [MEXC account trade list](https://www.mexc.com/api-docs/spot-v3/spot-account-trade/account-trade-list).

CoinEx requests selected-market cash spot fills with `market_type=SPOT`, freezing `start_time` and `end_time` across native numbered pages. A rescan starts a new 30-day query. This requested range describes the adapter’s scope, and CoinEx’s available retention can shorten it. Deal IDs remain visible, while their native order ID also scopes ledger identity. Native `has_next=false` ends the selected pass. [CoinEx user executions](https://docs.coinex.com/api/v2/spot/deal/http/list-user-deals).

Poloniex requests the exact selected symbol and freezes a seven-day initial fill window. Its pagination field `pageId` differs from the execution's `id`; only `pageId` advances native history. Native trade/order IDs identify ledger entries shared with exact-order reconciliation. An inclusive repeated page edge is filtered without skipping the next execution. Each distinct parent is checked once per page for explicit cash spot evidence because trade rows do not report borrowing. Batches retain at most 20 fills, with at most 20 parent reads. Borrowed or missing/archived parents stop the page for review. This short requested window does not claim all retained venue history. Native fee signs/currencies and absent fields remain explicit. [Poloniex trades](https://api-docs.poloniex.com/spot/api/private/trade#trade-history).

Bitfinex selected-market imports freeze an initial 90-day execution-time range and save splits when a response reaches the 100-fill page cap. Native `EXCHANGE` order types establish the exchange-wallet scope; margin types are excluded, and missing/unknown cash evidence stops for review. Native fees are wallet effects, so negative charges become positive ledger costs and positive rebates become negative costs. Currency aliases use the native adapter's currency mapping; absent fee evidence stays unknown. Native trade/order IDs and fee corrections are shared with exact-order reads. This initial range does not claim complete venue history. [Bitfinex authenticated trades](https://docs.bitfinex.com/reference/rest-auth-trades-by-symbol).

Phemex selected-pair imports freeze seven days and advance native `offset` by raw page size. Exact-order checks use the dedicated spot trades-by-order-ID endpoint. Both paths keep native execution/order UUIDs; verified currency `valueScale` decodes fees, while missing scale/currency metadata stays unknown. [Phemex spot history](https://phemex-docs.github.io/#query-trade-history).

Upbit imports regular current open orders and regular closed orders created in the selected seven-day range, then checks each parent’s native execution list. Listing and execution UUID checkpoints survive restart and exact checks share the same ledger identities. A native trade-count discrepancy stops for review. Orders closed after being created before the range may be missing. `paid_fee` is an order total, so individual execution fees remain unknown; it is not divided across fills. This path uses native order APIs without claiming the SDK has generic trade-history support. [Upbit order details](https://docs.upbit.com/kr/reference/get-order).

## Ownership and persistence

- `exchanges/history.py` defines `TradePage` and original native page adapters; `exchanges/spot_history.py` implements the four additional reviewed contracts and provider limits. `ExchangeClient.fetch_trade_page()` is separate from bounded `fetch_my_trades()`.
- `services/accounts/ledger.py` owns `account_fills` and `account_sync` in workspace `sibyl.db`. Fills retain execution values, source/environment, native fill/order IDs, and fee currencies/signs. Raw provider responses and credentials are excluded.
- `services/accounts/sync.py` validates selections, schedules pages, sanitizes failures and exposes public progress. Opaque cursors and a short cursor-loop guard stay server-side.
- A separate lifespan worker attempts one page per second, fairly across queued markets. Pages contain at most 100 fills; existing CCXT rate limits and client locks also apply. Run one API process; this is not a distributed scheduler.

Identity is `(account_id, exact_symbol, trade_id)`, so accounts/environments cannot collapse together. Every page's upserts and next checkpoint commit in one transaction. Validation failure rejects the entire page and preserves the prior checkpoint. A crash before commit repeats the page safely. Startup returns interrupted `running` jobs to `queued` at their saved checkpoints.

Each new pass has a private revision; a new rescan invalidates an old in-flight success or failure. Duplicate identities within a page, repeated normalized pages and non-advancing cursors reject the page. A 10,000-page budget bounds each pass. Retained ranges show earliest/latest execution timestamps, not continuous coverage. Counts are observations and correction counts, not an archive of previous payload versions.

Pause prevents further pages. An already in-flight successful page may commit its fills and cursor while staying paused. Resume uses that checkpoint. Disconnect removes saved credentials, stops imports and retains local fill history. Retained records do not count as current holdings or reconstruct balances.

## Progress and failures

States are **Queued**, **Importing**, **Waiting to retry**, **Caught up**, **Paused**, **Needs attention**, and **Disconnected**. Progress includes retained fills, cumulative pages, inserted/updated counts, last successful page, last completed pass, safe errors and retry time.

Transport/rate-limit failures retry up to five times after the initial attempt, after 15, 30, 60, 120 and 240 seconds. Authentication, unavailable markets, unsupported operations and malformed pages wait for explicit retry. Non-advancing/recently repeated cursors stop imports. Private provider error text never reaches the UI or agents. Technician can read import status through its existing ProtoLink tool; it cannot mutate imports.

**Caught up** means the available selected-market range was exhausted. Every ledger/job response retains `complete_history: false`; this does not establish coverage of every account event, historical instrument or opening lot.

## Ledger semantics

Execution timestamps differ from first/last local observation times. Amount is in base units; price/notional are in the quote. Notional may be unavailable. Numeric values use the unified client/CCXT representation, not a tax-grade decimal accounting engine.

Fees keep reported currencies and signs. Negative values are rebates. Missing amounts/currencies remain unavailable with an incomplete-data flag. Totals group by currency over the full filtered selection, independently of pagination. Currencies are never added together or assumed to equal the trade quote.

The UI filters by account, market, side and environment. It reads 50 fills per page; **Export this page** exports that page with IDs, fee currencies and completeness flags. Previews remain in **Executions**. Demo imports copy existing manual paper fills into this read-only ledger; they create no new trades/balances. Strategy fills stay in their isolated monitor.

Retained fills feed [market FIFO performance](account-performance.md), including audited opening inventory and optional balance-checked current marks. Separate [funding range imports](funding-history.md) cover Binance crypto deposits/withdrawals, Kraken deposit/withdrawal/transfer entries and Bybit on-chain withdrawals plus same-UID UNIFIED wallet transfers. [Order/fill reconciliation](order-reconciliation.md) shares these fill identities. Full funding coverage, account-wide balance reconciliation and complete cross-market performance remain pending. Accountant's native ProtoLink `account_history` tool reads bounded retained fills, import progress and provider limits without private network calls or mutations. See the [backend checklist](backend-roadmap.md).

## HTTP contracts

All paths use `/api/v1` and normal workspace access controls.

| Method | Path                                           | Purpose                                                                                                                             |
| ------ | ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| GET    | `/account-sync`                                | Accounts, import support and public progress; no provider calls                                                                     |
| GET    | `/connections/{id}/markets`                    | Exact active spot symbols at the account's venue/environment                                                                        |
| POST   | `/connections/{id}/sync`                       | Queue/resume `{"symbols":["BTC/USDT"],"mode":"incremental"}` or restart with `"mode":"rescan"`; 1–12 canonical symbols; returns 202 |
| POST   | `/connections/{id}/sync/pause?symbol=BTC/USDT` | Pause one market; omit `symbol` for all account imports                                                                             |
| GET    | `/account-ledger/fills`                        | Retained fills, total count, native-currency fee totals and limits                                                                  |

Ledger filters: `account_id`, optional exact `symbol`, `side` (`buy`/`sell`), `environment` (`demo`/`test`/`production`), `limit` (1–100, default 50), and `offset` (0–1,000,000). Sort is execution time and stable local ID, newest first. New imports may shift offset page boundaries. Caller-supplied provider cursors, arbitrary endpoints and CCXT parameters are not accepted.

Run `uv run pytest tests/test_account_sync.py tests/test_extended_account_history.py` for offline pagination, parser, retention, rescan races, recovery, fee, isolation and API tests.

BitMart v4 selected-market imports pin `orderMode=spot` and freeze their seven-day initial query across split ranges. A small overlap around each native timestamp boundary keeps records available when an endpoint includes a boundary. Capped boundaries report a coverage limit. Rescans start a new initial query, and reported native trade/order IDs deduplicate imports and fee corrections. [BitMart account trades](https://developer-pro.bitmart.com/en/spot/#account-trade-list-v4-signed).

## Exact-order coverage

Gate and HTX now support selected-market cash fill imports as well as exact-order checks. Both verify parent wallet scope and start with seven days. Gate retains native numbered pages; HTX retains 48-hour ranges and splits saturated timestamps. Missing parents or unverified wallet effects need review. Neither import proves complete account coverage. [Read contracts](order-reconciliation.md#gate-and-htx-order-executions).

## Bitstamp and Gemini

`exchanges/venue_history.py` adds both native adapters while preserving the existing at-most-100-fill page commit, checkpoint transaction, restart and rescan behavior.

- **Bitstamp:** requests ascending selected-market user transactions from `since_id`. The provider can return 1,000 records; each app page consumes at most 100 native records and advances their IDs, including nontrade records. Only spot trade rows become ledger fills. Native transaction IDs and signed amounts preserve fill identity, side and reported quote fees. Resume starts at the next ID; explicit rescan revisits older corrections.
- **Gemini:** requests selected-market trades from an inclusive millisecond boundary and retains IDs already consumed at that edge. A native batch has at most 500 trades; app commits stay within 100. Fully saturated timestamp groups stop for review rather than skipping unseen same-time fills. A reported full trade bust voids the fill in accounting while preserving its original observation. Manual and unverified breaks are retained for review, with affected balances and net results qualified. New break evidence at the current timestamp boundary is imported even when the original fill was already seen. Use an available-history rescan or an exact-order check for older evidence. Master-key subaccount routing is outside this adapter; use an account-scoped key.

Caught up means available pages were exhausted, not complete account history. Exact-order reconciliation uses each venue’s embedded native trade list; see [order reconciliation](order-reconciliation.md). SDK/parser tests cover native IDs/fees, tied timestamps, saturation, restart and malformed pages. Authenticated Bitstamp/Gemini acceptance remains pending. Contracts: [Bitstamp API](https://www.bitstamp.net/api/), [Gemini past trades](https://developer.gemini.com/trading/rest-api/orders/list-past-trades).
