# Conditional orders, OCO and replacement

Binance and the dedicated Binance Spot Testnet adapter implement native stop-loss/take-profit GTC limits, linked OCO limits and native unfilled-only cancel/replace. Other adapters and Demo do not simulate these features. Native instrument permissions are checked during review; an implemented adapter does not guarantee that every market/account allows an operation.

## Structure and contracts

`exchanges/binance_advanced.py` holds the provider's endpoint/field semantics. `services/trading/advanced/` holds OCO persistence, typed requests, conditional validation and replacement review. Ordinary single orders continue through `ExchangeTrading` and its existing lifecycle, client-ID recovery and native fill reconciliation. Domain agents remain read-only.

| Endpoint | Contract |
| --- | --- |
| `GET /connections/{id}/order-capabilities?symbol=BTC%2FUSDT` | Read native conditional types and OCO/replacement permission for the exact instrument. |
| `POST /exchange-orders/preview` | Existing contract, adding `stop_loss_limit` / `take_profit_limit` and required `trigger_price`. Every non-market type needs `limit_price`. |
| `POST /exchange-order-lists/preview` | `connection_id`, `symbol`, `side`, `quantity`, `take_profit_price`, stop `trigger_price`, stop `limit_price`, `idempotency_key`. |
| `POST /exchange-order-lists/{id}/confirm` | Only the displayed `confirmation`; commits one native list attempt. |
| `GET /exchange-order-lists/{id}` | Retained list command and two actual leg states; no provider refresh. |
| `POST /exchange-orders/{id}/replace/preview` | New total `quantity`, `limit_price`, fresh `idempotency_key`; reads original native status. |
| `POST /exchange-orders/{new-id}/confirm` | Existing confirmation contract for the saved replacement review. |

All paths above have the `/api/v1` prefix and existing workspace origin/token checks. Execution still requires an active account, `SIBYL_ALLOW_LIVE_TRADING=true`, an unexpired sixty-second review and its typed phrase. Reviews reserve no funds. Exact quantities/prices, market limits and a buy fee buffer are checked; the venue rechecks its actual dynamic filters at submission.

## Conditional limits

A buy stop triggers above the last traded price; a sell stop triggers below it. Take-profit directions are reversed. The review requires a limit at or above the trigger for a buy and at or below it for a sell. Triggers and limits must match native tick precision. Native `/api/v3/order` receives `STOP_LOSS_LIMIT` or `TAKE_PROFIT_LIMIT`, base quantity, `stopPrice`, price, `GTC` and a persisted client ID.

The trigger does not guarantee an execution or a loss bound. A resulting limit may remain partially or entirely unfilled. Sibyl never implements these as local price polling that submits a later market order.

## Linked OCO alternatives

One native `/api/v3/orderList/oco` call links a take-profit limit and stop-loss limit of the same side and quantity. Above/below fields are selected for the side. Take-profit trigger and limit share the entered take-profit price. The venue reserves one alternative quantity; it does not create two independent full-size reservations.

`order_groups` persists the list command and child identities. Both child intents and the list become `submitting` in one transaction before the native write. A child cannot be confirmed individually. Repeated list confirmation returns retained state without resending.

Submission responses reread the current child record before adopting native evidence. Delayed or lost acknowledgments cannot overwrite newer independently recovered fills/status; ordinary single-order identity and its validated observation also commit atomically.

Each child enters normal status/fill tracking and is labeled `origin: oco`, with `oco_group_id` and the confirmed native list ID when available. Activation/cancellation and partial fills remain native facts. Canceling one native OCO leg cancels its list; the sibling's status is observed separately. A group's submission state is not a claim that its executions or settlement are complete.

A lost response leaves the list uncertain. Each persisted child ID can be recovered through exact client-ID reads, including matching type, price and trigger. No match does not prove absence, and the list is never resubmitted automatically. A recovered child's actual observation can be known while the original group command still records its uncertain acknowledgment.

## Native replacement and reservation estimate

Only an open, wholly unfilled manual GTC limit is eligible. Imported orders, strategies, OCO children, partial orders and outstanding cancellation/replacement commands are excluded. The preview uses free funds plus the original order's estimated releasable reservation; this is not a reservation guarantee. It reviews the new **total** base quantity, not a hidden remaining-size calculation.

Confirmation refreshes the original, serializes both local records, latches its replacement command, and persists the new attempt before calling `/api/v3/order/cancelReplace`. It uses `STOP_ON_FAILURE`, `ONLY_NEW` and `DO_NOTHING` on rate-limit exceedance. A fill racing native cancellation prevents replacement under the unfilled-only restriction.

**This operation is not atomic.** The old order can cancel while the new order fails. Missing/exceptional compound outcomes remain uncertain; original and new client IDs must be inspected. Another replacement is blocked while the compound command is unresolved. No cancel/replace write is retried, no compensating buy/sell is submitted, and original native fill evidence is never discarded.

## Acceptance and remaining scope

Tests exercise actual installed SDK request generation and deterministic duplicate-confirmation, restart, lost-response, trigger-mismatch and partial-fill races. The bounded real [Testnet acceptance runner](exchange-acceptance.md#advanced-orders--november-6-2026) is separate evidence. Production order execution, genuine outages, intermediate native partial fills and late native fee corrections are not established by that check. Trailing stops, post-only/iceberg, other time-in-force choices, partial-order amendment and additional providers remain pending.

Reference: [Binance Spot trading endpoints](https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#trading-endpoints).
