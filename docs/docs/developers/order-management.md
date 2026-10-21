# Order management

Sibyl persists reviewed spot **market and GTC limit orders**, cumulative native observations, tracking preferences and cancellation commands. This is a local, single-API-worker workflow. It does not connect automated strategies or ProtoLink tools to execution.

## Provider scope

| Provider                                   | Market                     | GTC limit             | Reviewed cancel      | Status                              |
| ------------------------------------------ | -------------------------- | --------------------- | -------------------- | ----------------------------------- |
| Binance, Coinbase Advanced Trade, Kraken   | Yes                        | Yes                   | Yes                  | REST native order ID                |
| Binance Testnet, Coinbase Exchange Sandbox | Yes                        | Yes                   | Yes                  | REST native order ID                |
| Demo                                       | Existing paper market form | Virtual resting order | Virtual cancellation | Local synthetic matcher             |
| Other configured exchanges                 | No                         | No                    | No                   | Read-only adapter capabilities vary |

Native account acceptance testing remains outstanding. Contract tests use controlled transports; they do not establish production account permissions, regional availability or authenticated exchange acceptance. Coinbase Advanced and Coinbase Exchange Sandbox use different APIs.

The adapter sends a base-quantity limit with `timeInForce=GTC`, an exact price and a generated client ID. Coinbase Advanced uses native `client_order_id` because its SDK path drops the unified spelling. There are no user-supplied transport flags, derivative orders or silent precision rounding. Preview checks exact quantity/price precision, active spot status, native amount/cost/price limits and free funds. Native buys require a conservative 1% buffer; this is neither a fee quote nor a slippage guarantee. Actual venue requirements still apply.

## Durable submission

`ExchangeTrading.preview()` records an intent with a 60-second confirmation deadline. Limit notional is quantity × limit price; market notional is a side-of-book reference. A preview reserves nothing. Confirmation must match the displayed phrase and the account must still be active. New native orders also require `SIBYL_ALLOW_LIVE_TRADING=true`.

Before sending, SQLite commits `submitting`, the submission time, tracking preference and the client ID. Duplicate confirmation returns the persisted intent without sending again. A network timeout or unclear response becomes `unknown`, never a retry. The application may have stopped after the venue accepted but before its ID was saved. Reviewed clients now offer bounded [client-ID recovery](order-recovery.md). Only an exact ID/details match is attached; missing or ambiguous evidence still requires venue inspection.

A returned native ID allows later read-only recovery. Status observations validate identity and bounded cumulative filled/remaining quantities. A regressed fill is rejected, retaining the previous observation. Terminal orders cannot reopen, though a later explicit completed-fill observation can supersede a canceled observation. No individual fill IDs or final fees are fabricated from aggregate quantities. Exact-order [execution reconciliation](order-reconciliation.md) now imports native fill IDs into the shared Account history ledger, compares quantities/cost and exposes reported-fee gaps.

## Tracking and restart

A dedicated application worker checks at most **one due order per second**, separate from account imports and strategy jobs. A successful observation schedules the next check 20 seconds later. Failures retain the last observation, show a sanitized error and back off exponentially up to 15 minutes. Tracking and next-check times persist across restarts. Only active accounts are automatically checked. Pause/Resume in the monitor changes the local read preference; pausing never cancels an order at a venue.

Known-ID manual reads and reviewed cancellation remain available when new native execution is disabled. Manual checks can inspect a saved inactive account; the worker cannot. A disconnected account cannot be read or canceled until its credentials are available. Shutdown waits for an in-flight check before closing adapters. Workers never submit, replace or retry native orders/cancellations.

The combined monitor now also shows [read-only discovered orders](order-discovery.md), with exchange/account/origin/status filters applied before pagination. Discovery is explicitly enabled for reviewed active accounts and bounded recent ranges. Imported orders cannot be submitted or canceled through Sibyl. The legacy submissions endpoint retains its latest-100 contract; workers query due tracked records without that display limit. Run a single API worker: distributed coordination is not implemented.

## Cancellation review

1. **Cancel…** first reads native status and requires an observed open order.
2. The server saves a separate 60-second review with the native ID, account, market and observed filled/remaining quantities.
3. Type `CANCEL BTC/USDT` (or the displayed market) to confirm.
4. The server commits the attempt before one native cancellation call. Repeating that command never sends again.

A cancellation acknowledgment is shown as **requested**, not automatically **canceled**. Only an explicit terminal native observation changes order status. Fills can race cancellation. A timeout becomes cancellation **unknown** while retaining the previous order state. Tracking continues; a fresh status read and a new explicit review are required for another manual attempt. Raw provider errors are not returned or persisted. A canceled partially filled order retains its cumulative filled quantity.

## Demo wallet and reservations

`PaperLimits` uses `paper_limits`, the existing `balances` wallet and the existing `orders` fill ledger. Placement atomically reserves quote quantity × limit × 1.001 for a buy, or base quantity for a sell. Total balance stays unchanged; `free` excludes holds and `used` reports them. Paper market orders cannot spend reserved funds. Holds persist until fill or cancellation, including across restart or account deactivation.

Reading an order does not itself fill it. The explicit managed-order check or worker advances the matcher while Demo is active. A Demo ask at or below a buy limit, or bid at or above a sell limit, fills the whole quantity **at the limit** with a 0.1% quote fee. Fill, wallet change and hold release commit atomically. Cancellation releases funds once and cannot undo a fill. The resulting paper fill references the native virtual order ID and can be imported by Account history. Execution reports include this fill once, not again as an exchange intent.

This is a deliberately simple fixture simulator: no queue, liquidity, partial-fill, latency or price-improvement modeling. Its deterministic Demo bid/ask is independent of the selected public market-data source. Actual providers' partial fills are displayed, but Demo does not generate them. A lost virtual ID can be recovered from the exact local client key and reviewed details without resubmitting.

**View example** returns four read-only illustrative monitor rows, including a partial fill, an imported order and an uncertain submission. It creates no account, reservation, order or fill; its action buttons are disabled.

## HTTP contract

All paths have `/api/v1` prefix.

| Method | Path                                   | Body / effect                                                                                    |
| ------ | -------------------------------------- | ------------------------------------------------------------------------------------------------ |
| POST   | `/exchange-orders/preview`             | Existing order fields plus `order_type: market` or `limit`, and `limit_price` exactly for limits |
| POST   | `/exchange-orders/{id}/confirm`        | `confirmation` phrase                                                                            |
| GET    | `/exchange-orders`                     | Latest 100 local intents, including previews                                                     |
| GET    | `/exchange-orders/example`             | Isolated illustrative observations                                                               |
| POST   | `/exchange-orders/{id}/refresh`        | Read native ID; advance only virtual Demo matcher                                                |
| POST   | `/exchange-orders/{id}/tracking`       | `enabled: true` or `false`                                                                       |
| POST   | `/exchange-orders/{id}/cancel/preview` | Fresh status read and cancellation review                                                        |
| POST   | `/exchange-orders/{id}/cancel`         | `cancel_id`, `confirmation`                                                                      |
| GET    | `/paper/balances`                      | `balances` = available, `total` and `used` = virtual holds                                       |

## Still missing

Cancel/replace, stop/trigger, OCO, trailing, post-only, iceberg, IOC/FOK limits, streaming private updates, broader provider execution/recovery, broader account order discovery, amendment handling and complete fill/fee/settlement reconciliation remain separate work. Authenticated acceptance remains outstanding. Strategies stay paper-only; agents stay read-only.

Implementation is informed by the [CCXT manual](https://docs.ccxt.com/docs/manual), [Binance Spot API](https://developers.binance.com/en/docs/products/spot/rest-api), [Coinbase Advanced create-order reference](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/orders/create-order), and Kraken's [add-order](https://docs.kraken.com/api-reference/trading/add-order) / [cancel-order](https://docs.kraken.com/api-reference/trading/cancel-order) references.
