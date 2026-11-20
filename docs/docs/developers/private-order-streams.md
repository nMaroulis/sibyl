# Private order signals

**Settings → Exchanges → Live order updates** offers opt-in private observers for Binance production, Binance Spot Testnet, Coinbase Advanced Trade production and Kraken production. They use native **CCXT Pro**, already included in the locked CCXT dependency. Coinbase Exchange sandbox and other providers are not enabled.

These are **read-only order signals backed by existing REST readers**, not a complete account stream, a financial ledger or a WebSocket execution engine. No stream method places, cancels or replaces orders.

## Enable and interpret

1. Save and check your exchange account, then activate it. Read-only credentials need the provider's private-order/WebSocket permissions; the app's balance check alone does not verify those permissions.
2. Expand **Live order updates** and choose **Enable signals** for that exact account. Saving this choice opens no socket in the HTTP request; the local worker owns authentication and subscriptions.
3. Separately enable the order-status/fill trackers or account order-discovery readers you want to run. A stream never overrides a paused reader. Unknown external orders require enabled discovery; they are not adopted directly from a message.
4. Inspect actual signal counts, connection attempts, last signal time, scheduling counts and sanitized errors. **Waiting for order signals** is not a verified subscription/uptime claim. **REST reads scheduled** does not mean that the reads completed or reconciled the account.
5. Pause to reject new signals immediately; the owner closes the native socket at its next local tick. Deactivating the account suspends the observer. Replacement API credentials invalidate it and require explicit re-enabling; local vault re-encryption alone does not change the provider-key identity.

There are at most eight enabled observers. Native authentication failures stop automatic retries until review and re-enabling. Network failures use bounded backoff. Original exceptions, authentication payloads and native tokens are never returned in diagnostics.

## Authority and recovery

A native normalized order identity only marks existing REST reads due. Stream-reported status, cumulative quantity, cost and timestamps are used for bounded duplicate fingerprints; they are **never merged into order or fill evidence**. Exact native REST observations continue through the existing lifecycle, reconciliation ledger and import checkpoints.

Restart, a new connection attempt or an observed stream error persists a full-account wakeup. Stream updates coalesce exact symbol/order targets. Every 60 seconds, a backstop also marks existing healthy enabled readers due. Existing failure backoff and explicit pauses remain in force. Completed terminal fill scans are not silently reopened; manual correction checks remain available. A scoped sweep considers at most 5,000 retained known orders, and existing workers still process one bounded item/page at a time.

The installed native SDK can reconnect internally without reporting every gap through `watch_orders`. The app therefore does not claim complete sequence tracking or exact reconnect coverage. Periodic REST scheduling is a backstop, not proof of complete history or final settlement. Closed orders outside retained/tracked windows, missed events and later fee corrections may require explicit history/reconciliation checks.

Targets, bounded duplicate fingerprints and wakeup acknowledgment are transactional in the workspace database. Restore disables observers and invalidates their generations. No pending stream data can automatically execute financial actions. Removing an account ends its observer; financial histories keep their existing retention rules.

## Native adapters

`exchanges/streams/clients.py` defines the small async `AccountOrderStream` interface and native CCXT-backed subclasses:

| Adapter | Native subscription |
| --- | --- |
| Binance / Spot Testnet | Native `userDataStream.subscribe.signature` on the environment's WebSocket API, using CCXT signing. No legacy spot listen-key implementation is added. |
| Coinbase Advanced | Native authenticated `user` channel and CDP JWT signing. The installed SDK uses the traditional Advanced WebSocket endpoint, which Coinbase documents as a supported alternative to the dedicated user endpoint. |
| Kraken | Native v2 `executions`, authenticated using Kraken's short-lived REST WebSocket token. |

Source contracts: [CCXT Pro manual](https://github.com/ccxt/ccxt/wiki/ccxt.pro.manual), [Binance user streams](https://developers.binance.com/docs/binance-spot-api-docs/websocket-api/user-data-stream-requests), [Coinbase WebSocket overview](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/websocket/websocket-overview), [Kraken executions](https://docs.kraken.com/exchange/api-reference/spot-websocket-v2/executions).

`exchanges/streams/service.py` owns opt-in state, clients and persistent wakeups; `wakeups.py` schedules existing domain reads. `GET /api/v1/account-streams` is passive; `PUT /api/v1/account-streams/{account_id}` uses an explicit enabled flag and displayed revision. Broker's native `private_order_signals` tool reads compact observations without opening a connection or changing settings.

Offline tests capture actual installed-SDK signed subscriptions/endpoints, including Testnet isolation, Coinbase signature verification and Kraken token requests. They also check duplicate messages, no stream-to-ledger writes, preserved pauses, credential changes, restart/backstop scheduling, authentication blocking, native close/drain and restored quarantine. No real account socket or order is used in these tests. Authenticated venue acceptance remains a separate deployment check.
