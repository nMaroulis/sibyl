# Market data sources

Market data is independent from account mode and execution permissions. A workspace can hold Demo balances while reading public exchange prices. Market preferences never enable exchange orders. See the [Markets guide](../guides/markets.md) and [source settings](../guides/settings.md#market-data).

## Available sources

| Source | Credentials | Implemented reads |
| --- | --- | --- |
| Sibyl Demo | None | Offline deterministic quotes, OHLCV and synthetic order books |
| 20 public exchanges | None for public endpoints | Active spot catalog, quotes, provider-supported OHLCV and order-book snapshots |
| Saved exchange account | Existing encrypted exchange credentials | Its exchange and production/test environment; capabilities depend on that client |
| CryptoCompare / CoinDesk CCCAGG | Provider API key | Six reference assets, direct-pair quotes and OHLCV |
| CoinGecko Demo API | Free Demo-plan API key | Six reference assets quoted in USD; quotes only |
| CoinGecko Pro API | Paid Pro API key | The same quote contract on the separate Pro endpoint |

The reference assets are BTC, ETH, SOL, LINK, AVAX and DOT. Exchange spot catalogs are broader. Aggregators do not expose an exchange order book. CoinGecko's **Demo API plan supplies live data**; it is separate from Sibyl's offline Demo fixtures. Its adapter intentionally has no candles: simple-price observations do not contain OHLCV, and snapshot volume is not candle volume.

Public availability, geography, rate limits, history depth and key requirements depend on the provider. Anonymous CryptoCompare price/history checks returned HTTP 401 on October 20, 2026, so its source requires a key; it is not presented as a keyless service. Discovery inspects the installed exchange adapter capabilities without making network calls. A selectable card is not proof of successful connectivity or account authorization.

Provider contracts: [CoinGecko simple price](https://docs.coingecko.com/demo/reference/simple-price), [CoinGecko Pro](https://docs.coingecko.com/reference/simple-price), [CoinDesk legacy historical data](https://developers.coindesk.com/documentation/legacy/Historical/dataHistominute).

## Configuration API

- `GET /api/v1/settings/market` returns `active`, `catalog`, `account_mode` and `restart_required: false`. Source metadata includes identity, kind, provider, environment, capabilities and key presence. These responses use `Cache-Control: no-store`.
- `POST /api/v1/settings/market` accepts `{"source":"kraken"}` or `{"source":"coingecko","api_key":"YOUR_KEY"}`. A blank field should be omitted. Omission preserves a previously saved key. The change applies to subsequent reads immediately.
- `DELETE /api/v1/settings/market/{provider}/key` removes an encrypted API credential. Select another default before removing a key required by the active provider.

Source IDs are `demo`, public exchange IDs, `connection:<saved-account-id>`, `cryptocompare`, `coingecko` and `coingecko-pro`. Connected-account identities are stable account IDs, not labels. Disconnecting the selected account makes the source unavailable until the user chooses another. No fallback to fixtures occurs.

Profiles are encrypted by `Store` using the existing local vault key. API keys are write-only, sent only in headers to fixed provider hosts, and never included in response metadata, prompts or URL query parameters. CryptoCompare uses `Authorization: Apikey …`; CoinGecko uses its separate Demo/Pro headers. API adapters reject redirects, bound response size, impose finite timeouts and sanitize provider errors.

## Consistent reads

`Market.snapshot(source=None)` freezes the selected profile, environment and cache namespace for a complete operation. Nested reads reuse that profile. A concurrent preference save affects the next operation; it cannot relabel data already being read. Cache namespaces include source identity and credential version. Private account adapters and balance caches remain separate.

All Markets endpoints accept an optional `source` query parameter: watchlist, symbols, analysis, correlation and order book. This overrides only that request. The dashboard puts the override in the page URL and supplies the same ID in Analyst's validated `context.market_source`. Analyst's native ProtoLink tool reads that source and returns either real indicators or an explicit quotes-only snapshot. No provider key enters agent context.

Analysis, correlations and order-book endpoints validate **exact provider pairs**. They do not substitute USD for USDT. The six-asset watchlist can choose USD/USDC when USDT is absent and returns the actual `symbol` and `quote`. Existing portfolio/paper reference valuation still approximates USD stablecoins at parity; actual exchange execution uses exact markets and account clients.

A running paper strategy pauses when its workspace reference source changes. A temporary Markets override does not change strategy sources. Observed portfolio snapshots are partitioned by account mode and source; historical Demo reconstruction is only used with Demo accounts and Demo prices.

## Data quality and limits

Watchlist quotes cache for 30 seconds, adapter quote batches for up to 60 seconds, candles for 60 seconds and catalogs for ten minutes. Markets polls quotes once per minute. `observed_at` is provider time; `as_of` is response assembly time. A timestamp older than five minutes is marked stale and rejected for reference-price operations. Undated quotes are labeled accordingly. Missing change/volume remain `null`, never invented zeros. An unavailable mini-chart does not hide a valid quote.

Only closed candles enter analysis. CryptoCompare requests direct pairs with `tryConversion=false`; it validates OHLCV, preserves base-asset volume and omits empty zero-price placeholder bars. Aggregation is restricted to at most 2,000 underlying intervals per request. `/markets/symbols` returns per-timeframe `candle_limits`, which the UI uses to constrain sample choices. Provider plan limits can be stricter.

Live errors stay errors; there is no automatic Demo fallback. Durable historical backfill, WebSockets, global provider budgets and automatic source failover remain future work. Tests use mocked native responses and isolated Demo stores; authenticated provider acceptance testing still needs user-supplied accounts.
