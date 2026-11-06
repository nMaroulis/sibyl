# Live market previews

Binance public spot feeds and saved Binance/Testnet market sources support on-demand ticker and candle streams. Other feeds keep their existing REST snapshots. Account/order subscriptions and streaming execution decisions are not implemented.

## Ownership and transport

`market_data/streams.py` owns `LiveMarkets`. It starts no network activity at import or application startup. The first viewer resolves an exact source/environment, validates the spot instrument and interval through the existing client, then leases a channel. Matching viewers share one upstream socket; the last viewer disconnect cancels and drains it. Lifespan drains every socket before closing market clients.

The upstream uses aiohttp WebSockets with native ping/pong handling. Fixed endpoints are `wss://data-stream.binance.vision/stream` for production public data and `wss://stream.testnet.binance.vision/stream` for Testnet. Source identities remain distinct even for identical symbols. No API key, raw provider response or arbitrary endpoint enters a browser stream. Provider instrument IDs come from that environment's actual catalog.

The normal authenticated HTTP API delivers bounded newline-delimited JSON to the dashboard. This supports bearer headers without putting tokens in WebSocket URLs. Reverse proxies must permit streaming and disable buffering; responses send `Cache-Control: no-store` and `X-Accel-Buffering: no`.

| Endpoint | Behavior |
| --- | --- |
| `GET /api/v1/markets/live?source=binance&symbol=BTC%2FUSDT&timeframe=1m` | Lease one exact display stream; disconnect releases it. |
| `GET /api/v1/markets/live/status?source=binance` | Read observed active-channel status and latest preview evidence; opens no socket. |

Events are `status`, `ticker` or `candle`. Status includes source/environment, state, last receipt time, reconnect count and validation rejects. Ticker and candle events include native observation time. Candles retain native `closed` separately from their OHLCV preview. An empty health result means no active viewer, not a provider outage.

## Bounds, failure and freshness

At most sixteen channels and thirty-two viewers per channel are admitted. Each viewer has an eight-event queue; slow viewers lose old display updates rather than accumulating memory. Upstream messages are capped at 64 KiB. Invalid symbols, intervals, non-finite/negative prices, malformed OHLC ranges and implausibly dated observations never become display evidence. Older per-event-type updates are ignored.

A channel becomes live only after a valid market message, becomes stale after fifteen seconds without valid data, and reconnects with bounded exponential backoff and jitter after close, timeout or provider shutdown. These are observed stream states, not an uptime guarantee. The stream revalidates its selected source every ten seconds, including busy feeds; revoking an account source ends that display stream.

The browser releases its lease in a background tab and reconnects when visible. Selection changes discard previous preview state. Interrupted streams retain normal same-source REST polling. Reconnection never substitutes another exchange or Demo, invents missing candles, submits an order or replays a strategy signal.

## Analysis boundary

Only the chart's displayed price and forming-candle preview change with stream events. Closed REST candles continue to drive statistics, technical bias, correlations, retained history, backtests and Analyst's numerical analysis. Preview updates do not manufacture indicator values or silently enter immutable research inputs. REST refresh closes any reconnect gaps when the provider supplies them.

Analyst's native `live_market_status` tool reads this same bounded evidence. Its prompt/help distinguish transient previews from closed-candle analysis and from private account/order tracking.

## Verification

Deterministic tests cover exact symbols/intervals, invalid values/timestamps, queue bounds, shared leases, Testnet routing, shutdown/backoff and HTTP access controls. Public production and Testnet ticker events were observed on November 6, 2026. This does not establish continuous availability or private subscriptions.

Provider references: [Binance public streams](https://github.com/binance/binance-spot-api-docs/blob/master/web-socket-streams.md), [Spot Testnet streams](https://github.com/binance/binance-spot-api-docs/blob/master/testnet/web-socket-streams.md).
