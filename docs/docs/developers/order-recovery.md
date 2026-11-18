# Recovering uncertain order submissions

When a provider accepts an order but its acknowledgment is lost, Sibyl can retain `unknown` or `submitting` without a native order ID. **Recover order** in Trade → Order monitor now reads existing orders using the exact saved client ID. It never retries the create/cancel request. A verified match joins normal native status tracking and [execution reconciliation](order-reconciliation.md).

## Reviewed providers

| Client                                 | Lookup                                                                                                                                              |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Binance / Binance.US / Binance Testnet | Direct native order read using `origClientOrderId` and the exact spot symbol.                                                                       |
| Coinbase Exchange Sandbox              | Direct client-ID namespace lookup through the installed Exchange SDK adapter.                                                                       |
| Coinbase Advanced                      | Native order-history pages for one exact product and creation-time window, filtering the returned `client_order_id` exactly.                        |
| Kraken                                 | Client-filtered open orders, followed by client-filtered closed-order pages within an opening-time window. Uses `cl_ord_id`, not numeric `userref`. |
| OKX                                    | Direct `GET /api/v5/trade/order` with `instId` and `clOrdId` for cash spot orders. The native endpoint returns the latest match. |
| Bybit UTA                              | Exact `orderLinkId` in V5 realtime. A miss continues through dated spot history with saved cursors. |
| KuCoin Classic                         | HF spot client-ID lookup for the exact symbol. A miss checks the legacy client-ID endpoint used by older submissions. |
| Gemini                                 | Exact `client_order_id` details for reviewed spot GTC limits. Original size, limit price, venue flags and creation time must match. |
| Gate                                   | Exact native `text` ID and cash spot pair for reviewed GTC limits. A provider-reported miss checks recent finished orders for that pair. |
| Bitget Classic                         | Exact `clientOid` through Classic spot order details. API-cancelled orders are retained for up to two hours. |
| MEXC                                   | Exact pair and `origClientOrderId` through the spot order query. The native lookup covers up to seven days. |
| HTX                                    | Exact `clientOrderId` through spot order details. Native coverage is eight hours, with API-cancelled orders unavailable after two hours. |
| CoinEx                                 | Client-filtered pending spot orders, followed by a bounded exact-pair finished-order scan. Cancelled orders with no fills are removed by CoinEx. |
| Demo                                   | Local virtual limit lookup by its persisted client key. No matching or wallet mutation occurs in the lookup itself.                                 |
| BitMart                               | Exact client-ID query for a regular spot limit. BitMart limits queries for unfilled API-cancelled orders to 20 minutes. |
| Poloniex                              | Exact `cid:` order-detail lookup for API-origin cash spot GTC limits, requiring explicit unborrowed evidence. |
| Upbit Korea                           | Exact `identifier` details for regular spot GTC limits. Non-GTC, reserved and self-match-prevention instructions are excluded. |
| Bitfinex                              | Exact saved int45 cid filtered across the symbol's open snapshot and bounded creation-time closed pages. Ordinary API-origin EXCHANGE LIMIT/MARKET terms with original signed base size. |
| Phemex                               | Exact pair and saved clOrdID through the native spot order-detail endpoint. Requires base-sized GTC limit or IOC market terms, original baseQtyEv and creation time. |
| Crypto.com Exchange                    | Exact saved `client_oid`, explicit regular cash scope and original GTC limit or base-sized IOC market terms. |
| Other clients                          | Explicitly unsupported; no generic scan or production/Demo fallback.                                                                                |

Contracts follow the [Binance order query](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/account), [Coinbase Exchange single-order read](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/orders/get-single-order), [Coinbase Advanced list-orders API](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/orders/list-orders), and Kraken [open](https://docs.kraken.com/api-reference/account-data/get-open-orders) / [closed](https://docs.kraken.com/api-reference/account-data/get-closed-orders) order reads. [OKX Order Details](https://www.okx.com/docs-v5/en/#order-book-trading-trade-get-order-details) returns only the latest order for a reused client ID. Sibyl requires exact cash spot scope and native order type, then checks the saved intent's side, quantity, price for limits and creation window. Cash spot market recovery requires a requested base quantity. Attached or triggered algo orders remain outside this recovery contract. Coinbase Advanced does not provide the same direct client-ID endpoint as Exchange Sandbox. The provider's permissions, retention, clock and pagination behavior still apply; authenticated venue acceptance is outstanding.

## Acceptance rules

`services/trading/recovery.py` accepts an ID only when:

- The local intent is `unknown` or `submitting`, without a saved native ID. Previews and explicitly rejected orders cannot be recovered.
- The saved account ID, exchange and sandbox environment still agree. Automatic checks require an active account; explicit manual checks may read a saved inactive one.
- The returned client ID, exact symbol, side, order type and base quantity match the reviewed request. Limits also require the exact reviewed price; a reported non-GTC time-in-force is rejected.
- The returned order creation time is known and lies within the bounded review/submission window.
- The complete bounded pass found exactly one native ID. Repeated observations of that same ID are deduplicated. A second native ID is ambiguous, even if its client ID matches.
- Another local intent on that account has not already claimed the native ID.

New submissions save `submitted_at` before the network write. Older intents use their saved review expiry as the upper anchor. The creation window starts five minutes before review and ends fifteen minutes after submission/expiry; the submission anchor must be within two minutes of review. This allows modest clock skew without scanning arbitrary account history. Missing identity/quantity/time evidence, external amendments or creation outside the window require venue inspection rather than a guessed match.

Adoption, normalized native observation and public `found` state commit in the same SQLite transaction. Invalid cumulative quantities or a database failure roll back that attribution. Import scheduling joins that transaction. Lookup checkpoints retain only normalized candidate evidence; raw provider responses and exception messages are not stored. Opaque tokens and candidates remain private server state. GET only reads safe progress and never starts a lookup.

## Bounded reads and restart behavior

`ExchangeClient.fetch_order_lookup_page(client_id, symbol, cursor, start, end)` returns an `OrderLookupPage`: candidates, private cursor, and an end-of-pass flag. Each check reads one page. Coinbase pages contain at most 100 orders; Kraken's closed-order page contains at most 50. Kraken open and closed reads are separate pages. Native reads share the existing admission limits, cooldowns and safe read retry policy.

At most ten pages are read in a pass. A found candidate waits for pass exhaustion before adoption, so a later page can still reveal ambiguity. A page-limit or repeated-cursor failure does not attach an ID. Checkpoint/candidate state survives restart. The single API worker processes uncertain tracked intents through the existing order worker, without the monitor's latest-100 display limit.

Completed no-match passes wait at least 60 seconds, then 300 seconds. After three no-match passes, automatic tracking pauses. Five consecutive failed reads also pause it; errors back off to at most fifteen minutes. Provider deferrals preserve the failure budget. Pause/Resume controls the persisted read preference. An explicit resume renews failed/no-match budgets, retaining unfinished valid pages. A manual Recover order starts or continues a bounded lookup without silently enabling paused tracking.

**An empty result is not proof that no order was placed.** Coinbase Exchange can return 404 for a canceled order without matches. Provider retention, missing permissions or delayed indexing can also hide evidence. No-match, ambiguous, incomplete and mismatch states retain the uncertain intent. Never infer a rejection, release external funds, or automatically submit a replacement from those outcomes.

BitMart’s v4 client-order query reads both open and historical states when `queryState` is omitted. Sibyl requires the returned `orderMode=spot`, exact client ID, instrument, regular limit type and original reviewed terms. Native query misses preserve the uncertain outcome. [BitMart client-ID query](https://developer-pro.bitmart.com/en/spot/#query-order-by-clientorderid-v4-signed).

## Dashboard and HTTP

The monitor offers **Recover order** or **Continue lookup** for supported uncertain submissions. The in-place execution dialog shows the same recovery message. A successful recovery displays its timestamp. The isolated LINK example demonstrates an uncertain submission without creating an account, job, reservation or order; all sample actions are disabled.

- `POST /api/v1/exchange-orders/{id}/recover` reads one lookup page. It retains the verified native status at adoption and checks one execution page. The response is the managed order with safe `recovery` and `reconciliation` summaries, and `Cache-Control: no-store`.
- `GET /api/v1/exchange-orders` and `GET /api/v1/exchange-orders/{id}/reconciliation` include safe recovery state, message, eligibility, support, page/pass counts and timestamps. They perform no remote reads.
- Existing status refresh can attempt one lookup before requiring a native ID. An unfinished/no-match lookup does not become a fabricated native status.
- Existing tracking Resume renews the bounded recovery budget. Repeat confirmation still returns the persisted submission and never writes a second order.

Recovery states are `available`, `searching`, `found`, `not_found`, `ambiguous`, `incomplete`, `mismatch`, `error`, `unsupported`, or `not_needed`. They remain separate from the exchange order's lifecycle status. After Demo identity recovery, the ordinary managed-status check can match a virtual resting order; the lookup itself never advances that matcher.

Bybit recovery is scoped to regular cash spot orders. Market results must identify their original quantity as base units. The realtime cache can lose terminal rows after a provider restart, and historical availability depends on status and age. KuCoin requires Classic spot evidence, and its legacy endpoint can miss settled orders. [Bybit realtime orders](https://bybit-exchange.github.io/docs/v5/order/open-order), [Bybit history](https://bybit-exchange.github.io/docs/v5/order/order-list), [KuCoin HF client ID](https://www.kucoin.com/docs-new/rest/spot-trading/orders/get-order-by-clientoid), [KuCoin legacy client ID](https://www.kucoin.com/docs-new/abandoned-endpoints/spot-trading/orders/get-order-by-clientoid-old).

Gemini recommends unique client IDs within each trading session. Sibyl uses its generated, persisted client ID and requires explicit original size, the regular spot limit type and an empty native options list before attaching the returned order. [Gemini client order IDs](https://developer.gemini.com/client-order-id), [Gemini order status](https://developer.gemini.com/trading/rest-api/orders/get-order-status).

Gate documents direct client-ID lookup for pending orders. After a provider-reported miss, Sibyl checks finished cash spot orders for the exact pair within a bounded seven-day window. It verifies that the complete scan contains a unique match and checks the original reviewed terms before attaching the native ID. [Gate spot API](https://www.gate.com/docs/developers/apiv4/en/spot/).

Bitget Classic requires an API-origin regular spot limit with matching original size and price and no attached trigger. Some native detail rows omit time in force. Sibyl uses the exact saved client ID and the other original terms, and rejects any explicit non-GTC instruction. MEXC requires an explicit `GTC` limit, accepts the documented `Qty` or `origQty` field and treats the documented missing-record code as a lookup miss. [Bitget order info](https://www.bitget.com/legacy-docs/classic/spot/trade/Get-Order-Info) · [Bitget cancellation retention](https://www.bitget.com/support/articles/12560603823155) · [MEXC order query](https://www.mexc.com/api-docs/spot-v3/spot-account-trade/query-order).

HTX recovery requires the same verified spot wallet as placement, an API-origin regular limit and the exact saved client ID. Original quantity, price and creation time must match the reviewed intent. A missing client ID leaves the submission uncertain. [HTX client-ID details](https://huobiapi.github.io/docs/spot/v1/en/#get-the-order-detail-of-an-order-based-on-client-order-id).

Sibyl treats repeated CoinEx client IDs as potentially ambiguous and checks both pending and finished pages for the exact pair before accepting a unique candidate with the reviewed side, original quantity, limit price and creation time. A partial scan stays incomplete. The shared ten-page recovery budget applies, and a missing cancelled record keeps the outcome uncertain. [CoinEx pending client filter](https://docs.coinex.com/api/v2/spot/order/http/list-pending-order) · [CoinEx finished orders](https://docs.coinex.com/api/v2/spot/order/http/list-finished-order).

Poloniex uses `GET /orders/cid:{clientOrderId}` and requires the exact saved client ID, symbol, API origin, explicit unborrowed spot scope and original regular GTC limit terms. Shared acceptance rules still verify side, size, price and creation time. Missing or archived records remain uncertain. A pending cancellation is still active, while `FAILED` is rejected. Market submission and automated strategy execution remain outside this adapter. Separately reviewed exact-order fills and cash Account imports are available. [Poloniex order details](https://api-docs.poloniex.com/spot/api/private/order#order-details).

Upbit Korea sends only the exact saved `identifier` to `GET /v1/order`, without a UUID that could override that filter. Native UUID, market, side, regular limit type, original base size, price and creation time must match the intent. Ordinary limits omit `time_in_force`; explicit non-GTC or self-match-prevention instructions are rejected. Typed native misses retain the uncertain outcome without resubmission. [Upbit order lookup](https://docs.upbit.com/kr/reference/get-order).

Bitfinex scans the exact symbol's bounded active snapshot and the complete bounded closed creation window, filtering the saved positive int45 `cid`. A candidate waits for both phases, so a second native ID remains ambiguous. Recovery requires API origin, ordinary `EXCHANGE LIMIT`, unchanged base quantity/price and creation time, and no flags, hidden/group/linked, expiry or prior-type instructions. Date-range splits survive restart under the shared ten-page recovery budget. Known-order tracking uses an exact native ID active read with a closed-history fallback. Missing/expired records stay unconfirmed. [Bitfinex active orders](https://docs.bitfinex.com/reference/rest-auth-retrieve-orders) · [Bitfinex symbol history](https://docs.bitfinex.com/reference/rest-auth-orders-history-by-symbol).

Phemex uses `api-data/spots/orders/by-order-id` with the exact native symbol and saved `clOrdID`, without an order ID that could override the client filter. Only original `ByBase` regular `Limit` / `GoodTillCancel` terms are accepted. Exact client identity, source creation time, side, size and price must match. Absent or incomplete evidence retains uncertainty. Spot values use native scale metadata and exact nanosecond timestamps. [Phemex order details](https://phemex-docs.github.io/#query-orders-by-order-id-or-client-order-id).

## Remaining work

Actual authenticated sandbox/provider acceptance, broader recovery adapters, delisted markets, externally amended orders, all-account order discovery and broader private streams remain pending. Optional [private order signals](private-order-streams.md) wake existing REST readers. A match proves identity within the inspected evidence, not final settlement, complete account history or final fee valuation. Approved [exchange strategies](../guides/strategy-execution.md) reuse this recovery pipeline; agents cannot submit orders.

Controlled tests cover lost acknowledgments, crash recovery, duplicate confirmations, concurrent lookups, pagination across restart, immutable-field rejection, ambiguous IDs, attribution collisions, transaction rollback, inactive accounts, paused fill tracking, bounded reads, sanitized failures and provider request contracts.

## Crypto.com identity recovery

The native `private/get-order-detail` call uses only the saved `client_oid`. The returned account must be present, the spot market must match, `exec_inst` must be explicitly empty, and native terms must describe the original ordinary GTC limit or base-sized IOC market order. Original quantity must be reported; notional-only sizing cannot recover a base-sized intent. The shared acceptance transaction verifies side, base quantity, price for limits and creation window before attaching an ID. A provider miss or insufficient evidence keeps the submission uncertain; no write is retried. [Crypto.com order detail](https://exchange-developer.crypto.com/exchange/v1/docs/api/rest-single-page/#privateget-order-detail).

## Cash market recovery

Bitfinex verifies the same native cash/API-origin evidence as its GTC lookup, accepts ordinary `EXCHANGE MARKET` and compares the original signed amount to the reviewed side and base quantity. Both open and bounded closed scans must finish before adopting a unique cid match. Phemex requires `ordType=Market`, `qtyType=ByBase`, `timeInForce=ImmediateOrCancel` and an explicit positive original `baseQtyEv`. Crypto.com requires `order_type=MARKET`, `time_in_force=IMMEDIATE_OR_CANCEL`, positive native `quantity` and an explicitly empty execution-instruction list. Market price fields may be absent or informational; the shared recovery check compares price only for limit orders. The shared acceptance transaction rejects a market candidate for a limit intent, or the reverse. None of these reads resubmits the order. Controlled tests cover buys/sells, restart, zero-fill cancellation, individual fees and rejection of missing original sizing; live venue acceptance remains pending.
