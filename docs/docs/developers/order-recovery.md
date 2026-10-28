# Recovering uncertain order submissions

When a provider accepts an order but its acknowledgment is lost, Sibyl can retain `unknown` or `submitting` without a native order ID. **Recover order** in Trade → Order monitor now reads existing orders using the exact saved client ID. It never retries the create/cancel request. A verified match joins normal native status tracking and [execution reconciliation](order-reconciliation.md).

## Reviewed providers

| Client | Lookup |
| --- | --- |
| Binance / Binance.US / Binance Testnet | Direct native order read using `origClientOrderId` and the exact spot symbol. |
| Coinbase Exchange Sandbox | Direct client-ID namespace lookup through the installed Exchange SDK adapter. |
| Coinbase Advanced | Native order-history pages for one exact product and creation-time window, filtering the returned `client_order_id` exactly. |
| Kraken | Client-filtered open orders, followed by client-filtered closed-order pages within an opening-time window. Uses `cl_ord_id`, not numeric `userref`. |
| Demo | Local virtual limit lookup by its persisted client key. No matching or wallet mutation occurs in the lookup itself. |
| Other clients | Explicitly unsupported; no generic scan or production/Demo fallback. |

Contracts follow the [Binance order query](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/account), [Coinbase Exchange single-order read](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/orders/get-single-order), [Coinbase Advanced list-orders API](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/orders/list-orders), and Kraken [open](https://docs.kraken.com/api-reference/account-data/get-open-orders) / [closed](https://docs.kraken.com/api-reference/account-data/get-closed-orders) order reads. Coinbase Advanced does not provide the same direct client-ID endpoint as Exchange Sandbox. The provider's permissions, retention, clock and pagination behavior still apply; authenticated venue acceptance is outstanding.

## Acceptance rules

`services/order_recovery.py` accepts an ID only when:

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

## Dashboard and HTTP

The monitor offers **Recover order** or **Continue lookup** for supported uncertain submissions. The in-place execution dialog shows the same recovery message. A successful recovery displays its timestamp. The isolated LINK example demonstrates an uncertain submission without creating an account, job, reservation or order; all sample actions are disabled.

- `POST /api/v1/exchange-orders/{id}/recover` reads one lookup page. After adoption it checks known native status and one execution page. The response is the managed order with safe `recovery` and `reconciliation` summaries, and `Cache-Control: no-store`.
- `GET /api/v1/exchange-orders` and `GET /api/v1/exchange-orders/{id}/reconciliation` include safe recovery state, message, eligibility, support, page/pass counts and timestamps. They perform no remote reads.
- Existing status refresh can attempt one lookup before requiring a native ID. An unfinished/no-match lookup does not become a fabricated native status.
- Existing tracking Resume renews the bounded recovery budget. Repeat confirmation still returns the persisted submission and never writes a second order.

Recovery states are `available`, `searching`, `found`, `not_found`, `ambiguous`, `incomplete`, `mismatch`, `error`, `unsupported`, or `not_needed`. They remain separate from the exchange order's lifecycle status. After Demo identity recovery, the ordinary managed-status check can match a virtual resting order; the lookup itself never advances that matcher.

## Remaining work

Actual authenticated sandbox/provider acceptance, broader recovery adapters, delisted markets, externally amended orders, all-account order discovery and private streams remain pending. A match proves identity within the inspected evidence, not final settlement, complete account history or final fee valuation. Approved [exchange strategies](../guides/strategy-execution.md) reuse this recovery pipeline; agents cannot submit orders.

Controlled tests cover lost acknowledgments, crash recovery, duplicate confirmations, concurrent lookups, pagination across restart, immutable-field rejection, ambiguous IDs, attribution collisions, transaction rollback, inactive accounts, paused fill tracking, bounded reads, sanitized failures and provider request contracts.
