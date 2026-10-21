# API reference

The versioned base path is `/api/v1`. See the running service's `/docs` and `/openapi.json` for exact request schemas and validation rules. When a workspace token is configured, use `Authorization: Bearer YOUR_TOKEN` on versioned routes.

## Endpoints

| Method     | Path                            | Purpose                                                                                  |
| ---------- | ------------------------------- | ---------------------------------------------------------------------------------------- |
| GET        | `/health` (unversioned)         | Process readiness and package version                                                    |
| GET        | `/system`                       | Safe workspace configuration                                                             |
| GET        | `/settings/llm`                 | Provider catalog, active model, saved metadata; keys are write-only                      |
| POST       | `/settings/llm`                 | Save encrypted profile and activate for new requests                                     |
| DELETE     | `/settings/llm/{provider}/key`  | Remove stored key; fall back to tool mode if active required key is unavailable          |
| GET        | `/portfolio/accounts`           | Per-account free/reserved/total and conversion rates                                     |
| GET        | `/markets/symbols`              | Active spot catalog and available timeframes                                             |
| GET        | `/markets/orderbook`            | Public snapshot: symbol, depth 5–50                                                      |
| GET        | `/reports/trading`              | Combined records and matched paper FIFO P&L                                              |
| POST       | `/exchange-orders/{id}/refresh` | Read a known exchange order status; never resubmit                                       |
| GET        | `/portfolio`                    | Priced balances, allocation, history, warnings                                           |
| GET        | `/markets`                      | Saved watchlist quotes, order and source labels                                          |
| GET        | `/markets/analysis`             | `symbol`, `timeframe`, `limit` 60–720                                                    |
| GET        | `/markets/correlation`          | 2–8 symbols, timeframe, limit, method, transform                                         |
| GET        | `/exchanges`                    | Provider catalog, credential fields, capabilities, execution policy and unconfigured IDs |
| GET        | `/connections/{id}/balances`    | One account's normalized balances                                                        |
| GET        | `/connections/{id}/open-orders` | One exact market's open orders (`symbol`)                                                |
| GET        | `/connections/{id}/trades`      | Bounded fill page (`symbol`, `since` milliseconds, `limit` 1–500)                        |
| GET        | `/connections/{id}/markets`     | Saved account's exact spot symbols and environment                                       |
| GET        | `/account-sync`                 | Import support/progress without provider calls                                           |
| POST       | `/connections/{id}/sync`        | Queue/resume fill imports (`symbols`, 1–12); returns 202                                 |
| POST       | `/connections/{id}/sync/pause`  | Pause one `symbol`, or all account imports                                               |
| GET        | `/account-ledger/fills`         | Retained normalized fills, native-currency fees, filters and bounded pagination          |
| GET / POST | `/connections`                  | List metadata / save encrypted credentials                                               |
| DELETE     | `/connections/{id}`             | Remove a connection                                                                      |
| POST       | `/connections/{id}/check`       | Read-only credential verification                                                        |
| GET        | `/paper/balances`               | Separate manual paper ledger                                                             |
| GET / POST | `/orders`                       | Paper fill history / execute paper order                                                 |
| POST       | `/orders/preview`               | Paper reference quote, fee, estimated debit/credit                                       |
| GET        | `/exchange-orders`              | Exchange intents and submission snapshots                                                |
| POST       | `/exchange-orders/preview`      | Validate and create a 60-second exchange intent                                          |
| POST       | `/exchange-orders/{id}/confirm` | Submit once with typed confirmation                                                      |
| GET        | `/strategies`                   | Algorithm catalog                                                                        |
| POST       | `/strategies/backtest`          | Historical simulation and persisted result                                               |
| GET / POST | `/strategies/jobs`              | List / start isolated paper jobs                                                         |
| POST       | `/strategies/jobs/{id}/pause`   | Stop evaluating a paper job                                                              |
| POST       | `/strategies/jobs/{id}/resume`  | Resume evaluation                                                                        |
| GET        | `/forecast`                     | `symbol`, `horizon` 1–30                                                                 |
| GET        | `/news`                         | Filtered retained publisher excerpts / samples, pagination, VADER aggregates             |
| GET        | `/news/sources`                 | Publisher collection health, no network refresh                                          |
| POST       | `/news/refresh`                 | Public feed collection with a 60-second per-source cooldown                              |
| GET        | `/news/{article_id}`            | Retained story lookup independent of paging; optional mode                               |
| GET        | `/knowledge`                    | Glossary; optional `q` keyword query                                                     |
| GET        | `/research/crypto`              | Curated 20-asset catalog                                                                 |
| GET        | `/research/crypto/{asset_id}`   | Fetched metadata, history, market snapshot, and source status                            |
| GET        | `/blocks`                       | Recent Bitcoin blocks, count 1–100                                                       |
| GET        | `/stocks/{symbol}`              | Quote, adjusted history, statistics, profile                                             |
| GET        | `/agents`                       | Agent catalog and tool/provider metadata                                                 |
| POST       | `/agents/ask`                   | Run module tool and optional inference                                                   |
| GET        | `/runs`                         | Latest persisted runs; optional `kind=agent` or `backtest`                               |

## Strategy monitor routes

| Method | Path                               | Purpose                                                                                                      |
| ------ | ---------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| GET    | `/strategies/jobs/{id}`            | Coherent run snapshot, observed samples, execution/skipped markers, earlier retained fills; `limit` 10–2,000 |
| GET    | `/strategies/jobs/{id}/events`     | Newest-first events; `limit` 1–500, optional `before` event ID, and `action` filter                          |
| GET    | `/strategies/jobs/{id}/events.csv` | Stream complete chronological matching history with a fixed high-water event ID                              |
| POST   | `/strategies/jobs/{id}/stop`       | Permanently stop evaluation while retaining the virtual position and history                                 |

Event filters accept `all`, `fills`, `HOLD`, `SKIP_BUY`, `SKIP_SELL`, `ERROR`, `START`, `PAUSE`, `RESUME`, `STOP`, `BUY`, `SELL`, and `RECOVERED`. `fills` includes BUY and SELL. CSV text fields are protected against spreadsheet formula interpretation. Reads never perform a worker tick. Stop is terminal; pause/resume semantics are described in the [monitor guide](../guides/strategy-monitor.md).

## Examples

```bash
curl http://127.0.0.1:8000/api/v1/portfolio
```

```bash
curl -X POST http://127.0.0.1:8000/api/v1/agents/ask \
  -H 'Content-Type: application/json' \
  -d '{"module":"analyst","message":"Explain the selected indicators.","context":{"symbol":"ETH/USDT"}}'
```

```json
{
  "strategy": "ema",
  "symbol": "BTC/USDT",
  "capital": 10000,
  "candles": 180,
  "fee_bps": 10,
  "slippage_bps": 5,
  "window": 20,
  "timeframe": "4h",
  "fast_period": 9,
  "slow_period": 21,
  "rsi_period": 14,
  "band_std": 2,
  "volume_multiplier": 1.5,
  "stop_loss_pct": 5,
  "take_profit_pct": 15,
  "max_trades": 10
}
```

Post the object above to `/strategies/backtest` or `/strategies/jobs`.

A paper order request uses a client-generated, reusable-on-retry key:

```json
{
  "symbol": "BTC/USDT",
  "side": "buy",
  "quantity": 0.001,
  "idempotency_key": "unique-client-request-id"
}
```

Exchange previews add `connection_id`. Confirmation accepts only `{"confirmation":"BUY BTC"}` against the intent ID. No client-supplied quote can override the server-side intent.

## Errors

`400` means a business rule failed; `401` requires a token; `403` is an origin/local-access restriction; `404` means an unknown record; `422` means invalid input; `502` means a provider/agent failed; `504` means model inference exceeded the HTTP wait limit. Validation responses intentionally omit raw submitted values.

Read routes do not expose credentials. Exchange errors are sanitized rather than returning provider request objects. The API is single-user and does not paginate the full database: orders return the latest 200, exchange intents the latest 100, and run history the latest 50 matching records.

## Agent page context

`POST /agents/ask` accepts `module`, `message`, optional `session_id`, and optional `context`. Supported context fields are `job_id` (select one persisted paper run for Broker), `timeframe` (chart interval), `limit` (60–720), `symbol` (canonical base/quote), `equity_symbol` (bounded ticker), `horizon` (1–30 days), `parameters` (the backtest parameter object above), `query` (up to 200 characters), and `article_id` (up to 100 characters). Fields are optional and module-specific; unknown fields are rejected. Responses include the validated context, factual initial evidence, module/tool identity, and provider mode. Context does not grant any execution capability.

## Correlation request

`GET /markets/correlation?symbols=BTC/USDT,ETH/USDT&timeframe=4h&limit=180&method=spearman&transform=log_returns`

`method` accepts `pearson` or `spearman`; `transform` accepts `log_returns`, `prices`, or `changes`. Limit is 30–720, and 2–8 distinct canonical markets are required. The response reports aligned observations and the method/transformation used.

All backtest parameters, bounds, risk timing, and metric definitions are described in [Strategy studio](../guides/strategies.md). The OpenAPI schema rejects unknown parameters and non-finite values.

## Crypto research

`GET /research/crypto` returns the fixed 20-asset catalog without making 20 provider requests. `GET /research/crypto/{asset_id}` accepts only catalog IDs and returns normalized `profile`, `history`, and `market` sections, each independently nullable, together with source URLs, timestamps, cached/stale flags, and safe errors. Status is `ready`, `partial`, or `unavailable`. Unknown IDs return 404. No arbitrary provider URLs are accepted.

The profile service fetches CoinPaprika metadata/tickers and MediaWiki extracts with bounded time, response size, and concurrency. Read-through caches persist only normalized public data. Source errors are negatively cached for one minute; expired successful observations can be served with an explicit stale flag. These routes use the normal workspace access controls and fetch public data independently of the demo trading setting. Agent context accepts `crypto_id` for the Wiki module.

## Model configuration

`POST /settings/llm` accepts `provider`, `model`, `base_url`, and an optional `api_key`. Omit the key or send null to preserve its saved value. Credentials are never echoed. Only local/server adapters expose an endpoint field. URLs must use HTTP(S) and cannot embed credentials, a query, or a fragment. Embedded llama.cpp requires an existing GGUF path as its model. All model routes use the workspace token/origin controls. Metadata includes `has_api_key`, `key_source` (`saved`, `environment`, or `none`), installed dependency status, preset IDs, and provider guide URLs. Saves do not perform model inference or verify credentials.

## News queries

See [News ingestion and sentiment](news.md#query-contracts) for `mode`, publisher/asset/polarity/keyword/date filters, summaries, pagination and aggregate scope. Public news mode is independent of exchange mode.

## Data source settings and market mood

`GET` / `POST /settings/news` manages enabled news collectors and a write-only encrypted NewsAPI credential. `GET` / `POST /settings/market` discovers and activates reference feeds immediately; `DELETE /settings/market/{provider}/key` removes a stored API credential. Markets endpoints accept an optional `source` override. See [Market data contracts](market-data.md). `GET /news/fear-greed?mode=live` returns attributed cached Alternative.me index observations; `mode=demo` returns explicitly illustrative values. See [News ingestion](news.md#saved-collectors-api-access-and-web-collection).

Personal watchlist membership and order use `GET /markets/watchlist`, `POST` / `DELETE /markets/watchlist/items`, and `POST /markets/watchlist/order`, all with an optional `source` query. See [watchlist contracts](market-data.md#persisted-watchlists).

## Portfolio pricing evidence

`GET /portfolio` and `GET /portfolio/accounts` use the same held-asset conversion engine. They expose pricing coverage, direct/inverse/bridge paths, quote timestamps and explicit exclusions, independently of watchlists. Account failures use a null account total. See [portfolio valuation](portfolio-valuation.md) for the contracts, source boundaries and budgets.

## Account activation and views

`GET /accounts` describes saved/active accounts and view scopes without provider reads. `POST /accounts/demo` explicitly enables the virtual preview. `POST /connections/{id}/activation` accepts `{"active":true}` or `false`. Saving a new connection activates it. Portfolio endpoints accept `scope=all`, `exchange:<provider>`, or `account:<id>`. See [account selection](accounts.md) for invariants and execution gates.

## Retained account performance

`GET /account-ledger/performance` computes exact-market FIFO across the selected retained history. Optional `account_id`, `symbol`, and `environment` filters keep account/market scope explicit; `mark=true` requests current balance-checked reference marks. Ordinary reads and the Accountant's performance tool do not make those private reads.

`POST /connections/{id}/opening-inventory` takes `symbol`, positive `quantity`, nullable nonnegative `total_cost` in the pair's quote, and a past timezone-aware `as_of` preceding the first retained fill. `DELETE` on that route with `?symbol=...` removes the assertion; `GET /connections/{id}/opening-inventory/audit?symbol=...` returns the latest 50 changes. `GET /account-ledger/performance/example` computes an isolated example without persistent side effects.

These responses use `Cache-Control: no-store`. Reports expose native fee totals, unknown quantities, nullable final net/unrealized values and explicit coverage issues. See [performance contracts](account-performance.md).

## Funding history

`GET /funding-sync` reads supported streams and saved progress. `POST /connections/{id}/funding-sync` queues explicit `streams`, `start` and `end` for an active account; aware past ranges must be shorter than 90 days. `POST /connections/{id}/funding-sync/pause?stream=deposit` pauses one stream; omit the query to pause all.

`GET /account-ledger/funding` filters retained observations by `account_id`, `asset`, `kind`, `status`, `environment`, `limit` and `offset`. Completed summaries cover the full selection while records are paged. `GET /account-ledger/funding/example` returns an isolated fixture. No endpoint initiates a money movement. See [funding contracts](funding-history.md).

## Transfer review and cost carryover

`GET /account-ledger/transfers` reads saved links and suggestions with account/asset/environment filters; `include_removed` includes reversible removals. `/events` searches retained candidate records. `/example` and `/example/preview` operate on isolated fixtures.

`POST /account-ledger/transfers/preview` reviews a native withdrawal/deposit pair; `POST /account-ledger/transfers` confirms the displayed source-version evidence. `GET /account-ledger/transfers/{id}` reads detail/audit evidence; `POST /account-ledger/transfers/{id}/review` reconfirms or restores it. `DELETE` removes the link reversibly without changing native funding rows. Stale-source confirmation returns `409`. See [transfer contracts](transfer-reconciliation.md).

Performance consumes eligible confirmed transfers without creating fills. `GET /account-ledger/performance/example?transfers=true` demonstrates zero-fee carryover; `fees=true` demonstrates explicit fee allocation. Per-market results include carried original lot costs/dates, separate fee-unit inventory cost and unapplied-link reasons. Unsupported fee valuation and coverage remain provisional. See [cost carryover](transfer-cost-basis.md) and [fee allocation](transfer-fees.md).

## Managed spot orders

The existing exchange order preview accepts `order_type` (`market` by default, or `limit`) and requires a positive `limit_price` exactly for limits. Native limits are GTC. Demo uses the same managed-limit workflow with its virtual wallet; its existing market route stays separate.

`POST /exchange-orders/{id}/cancel/preview` reads native state and creates a 60-second review. Confirm through `POST /exchange-orders/{id}/cancel` with `cancel_id` and the displayed `confirmation`. `POST /exchange-orders/{id}/tracking` persists an `enabled` boolean. `GET /exchange-orders/example` is read-only illustrative data. `/paper/balances` reports available `balances`, `total` and `used` reservations. See [complete contracts and failure semantics](order-management.md).

`GET /exchange-orders/{id}/reconciliation` returns retained order/fill evidence without provider calls. `POST /exchange-orders/{id}/reconcile` checks native state and imports one exact-order execution page; the existing `/refresh` now does the same bounded import. `POST /exchange-orders/{id}/reconcile/tracking` changes the execution-read preference with `{enabled: boolean}`, including terminal follow-ups. `GET /exchange-orders/example/{id}/reconciliation` is an isolated fixture. See [evidence fields, pagination and error semantics](order-reconciliation.md).

## Local alerts and implementation inventory

`GET /alerts` reads persisted one-shot price rules. `POST /alerts` arms an exact `source` + `symbol`, `condition` (`above`/`below`) and positive `threshold`, with optional `label`. `POST /alerts/{id}/action` accepts `pause`, `arm`, `archive` or `restore`; `POST /alerts/{id}/check` respects the stored cooldown/backoff. `/alerts/example` is an isolated fixture.

`GET /notifications` pages retained local evidence with `limit` (1–100) and `offset`, plus unread totals. `POST /notifications/{id}/read` or `/notifications/read-all` acknowledges without deleting. Delivery is in-app only, never a trade or external send. See [complete alert contracts](alerts.md).

`GET /roadmap` returns the human-audited capability inventory, including deferred multi-user scope; it performs no provider calls. The Coming soon page consumes it directly.

## Retained market history

The `/market-history` routes expose local coverage, resumable reviewed imports, retention and immutable datasets. `/strategies/backtest/dataset` runs saved inputs offline. Current-feed backtests also save their exact input. See the [complete endpoint contracts and limits](candle-history.md#api).

## Observed source diagnostics

`GET /providers/health` returns sanitized current-process read health, independent quote freshness, shared queues/cooldowns and persistent import counts. Optional `source` filters one source. It never probes providers. Deferred reads return HTTP 503 with a safe Retry-After header. See [provider control](provider-control.md).
