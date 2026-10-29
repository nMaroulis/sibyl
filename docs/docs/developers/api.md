# API reference

The versioned base path is `/api/v1`. See the running service's `/docs` and `/openapi.json` for exact request schemas and validation rules. When a workspace token is configured, use `Authorization: Bearer YOUR_TOKEN` on versioned routes.

## Endpoints

| Method     | Path                                                | Purpose                                                                                    |
| ---------- | --------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| GET        | `/health` (unversioned)                             | Process readiness and package version                                                      |
| GET        | `/system`                                           | Safe workspace configuration                                                               |
| GET        | `/settings/llm`                                     | Provider catalog, workspace default, effective agent models/revision; keys are write-only  |
| POST       | `/settings/llm`                                     | Save encrypted profile; `activate=false` preserves the workspace default                   |
| POST       | `/settings/llm/agents/{agent}`                      | Revision-checked provider/model override; null provider restores inheritance               |
| DELETE     | `/settings/llm/{provider}/key`                      | Remove stored key; fall back to tool mode if active required key is unavailable            |
| GET        | `/account/accounts`                                 | Per-account free/reserved/total and conversion rates                                       |
| GET        | `/markets/symbols`                                  | Active spot catalog and available timeframes                                               |
| GET        | `/markets/orderbook`                                | Public snapshot: symbol, depth 5–50                                                        |
| GET        | `/reports/trading`                                  | Combined records and matched paper FIFO P&L                                                |
| POST       | `/exchange-orders/{id}/refresh`                     | Read a known exchange order status; never resubmit                                         |
| GET        | `/account`                                          | Priced balances, allocation, history, warnings                                             |
| GET        | `/markets`                                          | Saved watchlist quotes, order and source labels                                            |
| GET        | `/markets/analysis`                                 | `symbol`, `timeframe`, `limit` 60–720                                                      |
| GET        | `/markets/correlation`                              | 2–8 symbols, timeframe, limit, method, transform                                           |
| GET        | `/exchanges`                                        | Provider catalog, credential fields, capabilities, execution policy and unconfigured IDs   |
| GET        | `/connections/{id}/balances`                        | One account's normalized balances                                                          |
| GET        | `/connections/{id}/open-orders`                     | One exact market's open orders (`symbol`)                                                  |
| GET        | `/connections/{id}/trades`                          | Bounded fill page (`symbol`, `since` milliseconds, `limit` 1–500)                          |
| GET        | `/connections/{id}/markets`                         | Saved account's exact spot symbols and environment                                         |
| GET        | `/account-sync`                                     | Import support/progress without provider calls                                             |
| POST       | `/connections/{id}/sync`                            | Queue/resume fill imports (`symbols`, 1–12); returns 202                                   |
| POST       | `/connections/{id}/sync/pause`                      | Pause one `symbol`, or all account imports                                                 |
| GET        | `/account-ledger/fills`                             | Retained normalized fills, native-currency fees, filters and bounded pagination            |
| GET / POST | `/connections`                                      | List metadata / save encrypted credentials                                                 |
| DELETE     | `/connections/{id}`                                 | Remove a connection                                                                        |
| POST       | `/connections/{id}/check`                           | Read-only credential verification                                                          |
| GET        | `/paper/balances`                                   | Separate manual paper ledger                                                               |
| GET / POST | `/orders`                                           | Paper fill history / execute paper order                                                   |
| POST       | `/orders/preview`                                   | Paper reference quote, fee, estimated debit/credit                                         |
| GET        | `/exchange-orders`                                  | Exchange intents and submission snapshots                                                  |
| POST       | `/exchange-orders/preview`                          | Validate and create a 60-second exchange intent                                            |
| POST       | `/exchange-orders/{id}/confirm`                     | Submit once with typed confirmation                                                        |
| GET        | `/strategies`                                       | Algorithm catalog                                                                          |
| POST       | `/strategies/backtest`                              | Historical simulation and persisted result                                                 |
| GET / POST | `/strategies/jobs`                                  | List paper/exchange runs / start isolated paper jobs                                       |
| GET        | `/strategies/exchange/options`                      | Actual automation support, account activation and execution flags                          |
| GET / POST | `/strategies/exchange/controls`                     | Passive global halt/history or revision-bound Halt / typed Release; resumes no runs        |
| GET        | `/strategies/exchange/markets/{id}`                 | Exact account-exchange pairs/timeframes                                                    |
| POST       | `/strategies/exchange/preview`                      | Read-only account/budget review                                                            |
| POST       | `/strategies/exchange/reviews/{id}/start`           | Approve a fixed scope; wait for the next closed candle                                     |
| POST       | `/strategies/exchange/jobs/{id}/stop-cancel-review` | Read local fixed-run cancellation scope; no native call or mutation                        |
| POST       | `/strategies/exchange/stop-reviews/{id}/confirm`    | Typed approval; stop submissions and queue owned-order cancellation                        |
| GET        | `/strategies/exchange/jobs/{id}/close-position`     | Local closing eligibility, reason, owned units and retained exit state                     |
| POST       | `/strategies/exchange/jobs/{id}/close-preview`      | Fresh native book/funds and fixed 60-second sell review; no native write                   |
| POST       | `/strategies/exchange/close-reviews/{id}/confirm`   | Typed one-order exit approval; repeated confirmations only return progress                 |
| POST       | `/strategies/jobs/{id}/pause`                       | Stop evaluating a paper job                                                                |
| POST       | `/strategies/jobs/{id}/resume`                      | Resume evaluation                                                                          |
| GET        | `/forecast`                                         | `symbol`, `horizon` 1–30                                                                   |
| GET        | `/news`                                             | Filtered retained publisher excerpts / samples, pagination, VADER aggregates               |
| GET        | `/news/sources`                                     | Publisher collection health, no network refresh                                            |
| POST       | `/news/refresh`                                     | Public feed collection with a 60-second per-source cooldown                                |
| GET        | `/news/{article_id}`                                | Retained story lookup independent of paging; optional mode                                 |
| GET        | `/knowledge`                                        | Glossary; optional `q` keyword query                                                       |
| GET        | `/research/crypto`                                  | Curated 20-asset catalog                                                                   |
| GET        | `/research/crypto/{asset_id}`                       | Fetched metadata, history, market snapshot, and source status                              |
| GET        | `/blocks`                                           | Recent Bitcoin blocks, count 1–100                                                         |
| GET        | `/bitcoin`                                          | Mainnet lookup scope and explicit Demo references, without network access                    |
| POST       | `/bitcoin/inspect`                                  | Exact transaction/address inspection, with optional paged transaction inputs/outputs          |
| POST       | `/bitcoin/history`                                  | One confirmed cursor page or bounded pending address activity                                |
| GET        | `/stocks/{symbol}`                                  | Quote, adjusted history, statistics, profile                                               |
| GET        | `/agents`                                           | Agent catalog and tool/provider metadata                                                   |
| GET        | `/agents/runs/{run_id}/summary`                     | Safe native tool outcomes/timing and available per-call metrics; no raw prompts or results |
| POST       | `/agents/ask/stream`                                | Same module operation as `/agents/ask`, with safe native activity as NDJSON                |
| GET        | `/agents/runs/{run_id}`                             | Persisted native ProtoLink report; no model call, missing report returns 404               |
| POST       | `/agents/ask`                                       | Run module tool and optional inference                                                     |
| GET        | `/runs`                                             | Latest persisted runs; optional `kind=agent` or `backtest`                                 |

## Agent streaming and run summaries

The two Ask stream routes accept exactly the same bodies and workspace authentication as their JSON counterparts. They run the same operation once, with `Content-Type: application/x-ndjson`, `Cache-Control: no-store` and proxy buffering disabled. Each line is one JSON object:

- `{"type":"status","status":"queued"}` while accepting the request.
- `{"type":"activity",...}` with native action ID, run/task ID, agent, `kind` (`tool` or `consultation`), label and lifecycle status. No prompts, raw model chunks, tool arguments/results or provider exception text.
- `{"type":"reply","reply":{...}}` with the original committed result, or `{"type":"error","status":502,"message":"..."}` with a sanitized failure. These are terminal frames.

Authentication and body validation use normal HTTP errors before streaming. Failures after streaming starts use an error frame; clients must inspect that frame rather than treating HTTP 200 as success. Disconnect cancels/drains the producer and its native handle. Running synchronous work may finish after cancellation; its late return is discarded. Clients do not automatically replay an interrupted model request. Sibyl's existing chat activity/history reads remain available for reopening a request.

`GET /agents/runs/{run_id}/summary` is an authenticated, no-store read of the persisted native report (404 when missing). `tools` contains names, outcomes and durations; `calls` contains provider/model, latency, native token usage and optional per-call cost/currency. Missing values stay null, estimates retain labels, and `tokens.known_calls` discloses aggregate coverage. Costs are never summed across currencies. Owned-agent usage is currently unavailable because of the [verified ProtoLink 0.8.3 gap](protolink-metrics.md).

## Strategy monitor routes

Chronological validation has separate retained-study endpoints: `GET /strategies/validation/options`, `POST /strategies/validations`, `GET /strategies/validations` (optional `demo=true/false`), `GET /strategies/validations/{id}`, and `POST /strategies/validations/{id}/rerun`. These use immutable local inputs and never create orders or strategy jobs. See [validation contracts](strategy-research.md#chronological-parameter-validation) and the [user guide](../guides/strategy-validation.md).

| Method | Path                               | Purpose                                                                                                      |
| ------ | ---------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| GET    | `/strategies/jobs/{id}`            | Coherent run snapshot, observed samples, execution/skipped markers, earlier retained fills; `limit` 10–2,000 |
| GET    | `/strategies/jobs/{id}/events`     | Newest-first events; `limit` 1–500, optional `before` event ID, and `action` filter                          |
| GET    | `/strategies/jobs/{id}/events.csv` | Stream complete chronological matching history with a fixed high-water event ID                              |
| POST   | `/strategies/jobs/{id}/stop`       | Permanently stop evaluation while retaining the virtual position and history                                 |

Event filters accept `all`, `fills`, `HOLD`, `SKIP_BUY`, `SKIP_SELL`, `ERROR`, `START`, `PAUSE`, `RESUME`, `STOP`, `BUY`, `SELL`, `RECOVERED`, `FILL_CORRECTION`, `ORDER_PLANNED`, `ORDER_SUBMITTED`, `STOP_CANCEL`, `CANCEL_QUEUED`, `CANCEL_BLOCKED`, `CANCEL_REQUESTED`, `CANCEL_UNKNOWN`, `CANCEL_RECONCILING` and `CANCEL_RECONCILED`. `fills` includes BUY and SELL. CSV text fields are protected against spreadsheet formula interpretation. Cancellation events include `order_id`, `cancel_state`, shared `cancellation_id` when available, and `expires_at`. Reads never perform a worker tick. Stop is terminal; pause/resume semantics are described in the [monitor guide](../guides/strategy-monitor.md).

Exchange reviews accept nullable `risk.order_lifetime_seconds`: an integer 60–86,400 or `null` (default, including older jobs). Submitted strategy intents retain `strategy_expires_at`; monitor order rows include `strategy_cancellation` state/message, outcome, check time and terminal follow-up count, plus shared `cancel_state`. That count advances only for matching native observations against unchanged fill evidence; native changes and later fill/fee imports reopen it. Running strategies can report `execution_state: "waiting_cancellation"`; both new signals and separately reviewed exits wait for those checks. This is rechecked inside the submission transaction. The Stop & cancel confirmation body is `{ "confirmation": "<displayed phrase>" }`. Repeated confirmation returns the same stopped run; it never repeats a native write. Stop persists before the worker attempts cancellation and may return while access is blocked. See [lifetime, permissions and restart semantics](../guides/strategy-execution.md#order-lifetime-and-cancellation).

Closing readiness reads no native endpoints. `close-preview` accepts `price_limit_bps` (default 25, >0–200), `max_spread_bps` (default 50, >0–500), `fee_reserve_bps` (default 100, 10–500) and nullable `order_lifetime_seconds` (default 300, 60–86,400). It requires stopped/completed status, current matched native fill/fee evidence, no pending order and completed cancellation follow-ups. The result fixes account/environment/pair, owned/sell units, limit floor, gross floor proceeds, illustrative quote-fee allowance, base reserve and residual estimate. The confirmation body contains only the displayed `confirmation`; quantities/prices cannot be edited there. Evidence and expiry are checked again inside the shared submitting transaction. No AI agent can approve the operation.

The run's `close_position` contains `review_id`, `intent_id`, state/message, check time, native status, requested/filled units and remaining owned units. Order rows include `strategy_action: close` and `strategy_close_review_id`. Event/CSV filters additionally accept `CLOSE_APPROVED`, `CLOSE_SUBMITTED`, `CLOSE_UNKNOWN`, `CLOSE_RECONCILING`, `CLOSE_RECONCILED`, `CLOSE_INTERRUPTED` and `CLOSE_REJECTED`, carrying `close_review_id` and `order_id`. No close request is replayed after restart. See [exit scope and residuals](../guides/strategy-execution.md#close-a-retained-position).

Global controls are documented in the [submission-halt contract](strategy-controls.md). `options.enabled` includes the halt; `options.server_enabled` reports the two server flags separately. Global pause journal/CSV records carry `control_revision`.

## Examples

```bash
curl http://127.0.0.1:8000/api/v1/account
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

`POST /agents/ask` accepts `module`, `message`, optional `session_id`, and optional `context`. Supported context fields are `job_id` (select one persisted paper run for Broker), `timeframe` (chart interval), `limit` (60–720), `symbol` (canonical base/quote), `equity_symbol` (bounded ticker), `horizon` (1–30 days), `parameters` (the backtest parameter object above), `query` (up to 200 characters), and `article_id` (up to 100 characters). Fields are optional and module-specific; unknown fields are rejected. Responses include the validated context, actual completed tool observations, module/tool identity, provider mode and native `run_id`. Evidence is read on demand rather than preloaded for inference; no-model mode returns the selected factual snapshot. Context does not grant any execution capability.

## Correlation request

`GET /markets/correlation?symbols=BTC/USDT,ETH/USDT&timeframe=4h&limit=180&method=spearman&transform=log_returns`

`method` accepts `pearson` or `spearman`; `transform` accepts `log_returns`, `prices`, or `changes`. Limit is 30–720, and 2–8 distinct canonical markets are required. The response reports aligned observations and the method/transformation used.

All backtest parameters, bounds, risk timing, and metric definitions are described in [Strategy studio](../guides/strategies.md). The OpenAPI schema rejects unknown parameters and non-finite values.

## Crypto research

`GET /research/crypto` returns the fixed 20-asset catalog without making 20 provider requests. `GET /research/crypto/{asset_id}` accepts only catalog IDs and returns normalized `profile`, `history`, and `market` sections, each independently nullable, together with source URLs, timestamps, cached/stale flags, and safe errors. Status is `ready`, `partial`, or `unavailable`. Unknown IDs return 404. No arbitrary provider URLs are accepted.

The profile service fetches CoinPaprika metadata/tickers and MediaWiki extracts with bounded time, response size, and concurrency. Read-through caches persist only normalized public data. Source errors are negatively cached for one minute; expired successful observations can be served with an explicit stale flag. These routes use the normal workspace access controls and fetch public data independently of the demo trading setting. Agent context accepts `crypto_id` for the Wiki module.

## Model configuration

`POST /settings/llm` accepts `provider`, `model`, `base_url`, and an optional `api_key`. Ollama also accepts `context_window`, a strict integer from 4,096 to 131,072; omitted/null preserves a saved value or defaults to 32,768. Other providers reject that field. See [context contracts](agent-models.md#ollama-context-and-tool-protocol). Omit the key or send null to preserve its saved value. Credentials are never echoed. Only local/server adapters expose an endpoint field. URLs must use HTTP(S) and cannot embed credentials, a query, or a fragment. Embedded llama.cpp requires an existing GGUF path as its model. All model routes use the workspace token/origin controls. Metadata includes `has_api_key`, `key_source` (`saved`, `environment`, or `none`), installed dependency status, preset IDs, and provider guide URLs. Saves do not perform model inference or verify credentials.

## News queries

See [News ingestion and sentiment](news.md#query-contracts) for `mode`, publisher/asset/polarity/keyword/date filters, summaries, pagination and aggregate scope. Public news mode is independent of exchange mode.

## Data source settings and market mood

`GET` / `POST /settings/news` manages enabled news collectors and a write-only encrypted NewsAPI credential. `GET` / `POST /settings/market` discovers and activates reference feeds immediately; `DELETE /settings/market/{provider}/key` removes a stored API credential. Markets endpoints accept an optional `source` override. See [Market data contracts](market-data.md). `GET /news/fear-greed?mode=live` returns attributed cached Alternative.me index observations; `mode=demo` returns explicitly illustrative values. See [News ingestion](news.md#saved-collectors-api-access-and-web-collection).

Personal watchlist membership and order use `GET /markets/watchlist`, `POST` / `DELETE /markets/watchlist/items`, and `POST /markets/watchlist/order`, all with an optional `source` query. See [watchlist contracts](market-data.md#persisted-watchlists).

## Portfolio pricing evidence

`GET /account` and `GET /account/accounts` use the same held-asset conversion engine. They expose pricing coverage, direct/inverse/bridge paths, quote timestamps and explicit exclusions, independently of watchlists. Account failures use a null account total. See [portfolio valuation](portfolio-valuation.md) for the contracts, source boundaries and budgets.

## Account activation and views

`GET /accounts` describes saved/active accounts and view scopes without provider reads. `POST /accounts/demo` explicitly enables the virtual preview. `POST /connections/{id}/activation` accepts `{"active":true}` or `false`. Saving a new connection activates it. Account endpoints accept `scope=all`, `exchange:<provider>`, or `account:<id>`. See [account selection](accounts.md) for invariants and execution gates.

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

`POST /exchange-orders/{id}/recover` reads one bounded saved-client-ID lookup page for an uncertain submitted intent. A verified ID joins status/fill checks; missing/ambiguous evidence retains uncertainty without resubmission. Managed orders include safe `recovery` state, support/eligibility, progress and messages. GET does not start lookups. See [provider contracts, exact-detail validation and retry limits](order-recovery.md).

## Local alerts and implementation inventory

`GET /alerts` reads persisted one-shot price rules. `POST /alerts` arms an exact `source` + `symbol`, `condition` (`above`/`below`) and positive `threshold`, with optional `label`. `POST /alerts/{id}/action` accepts `pause`, `arm`, `archive` or `restore`; `POST /alerts/{id}/check` respects the stored cooldown/backoff. `/alerts/example` is an isolated fixture.

`GET /notifications` pages retained local evidence with `limit` (1–100) and `offset`, plus unread totals. `POST /notifications/{id}/read` or `/notifications/read-all` acknowledges without deleting. Delivery is in-app only, never a trade or external send. See [complete alert contracts](alerts.md).

`GET /roadmap` returns the human-audited capability inventory, including deferred multi-user scope; it performs no provider calls. The Coming soon page consumes it directly.

## Retained market history

The `/market-history` routes expose local coverage, resumable reviewed imports, retention and immutable datasets. `/strategies/backtest/dataset` runs saved inputs offline. Current-feed backtests also save their exact input. See the [complete endpoint contracts and limits](candle-history.md#api).

## Observed source diagnostics

`GET /providers/health` returns sanitized current-process read health, independent quote freshness, shared queues/cooldowns and persistent import counts. Optional `source` filters one source. It never probes providers. Deferred reads return HTTP 503 with a safe Retry-After header. See [provider control](provider-control.md).

## Combined exchange order monitor

`GET /exchange-orders/monitor` pages local submissions and read-only imported orders, filtering by account, exchange, origin and active/terminal status before the limit. `GET /exchange-orders/discovery` reads local progress; `POST` to that path starts/resumes bounded discovery with `account_id`, `symbols` and `days`. `POST /exchange-orders/discovery/{account_id}/pause` preserves the checkpoint and stops future pages. Imported rows cannot be submitted or canceled. See [coverage, response fields and durable scheduling](order-discovery.md).

Price alerts also accept `condition: crosses_above/crosses_below`, `repeat: once/after_reset` and integer `cooldown_seconds` (60–86400). `POST /alerts/{id}/edit` takes complete rule settings and `revision`, saves paused and returns `409` for a stale editor. Recurring reset/cooldown state persists; past notifications retain the original rule evidence. See [alert state and edit contracts](alerts.md).

## Sibyl and messaging setup

All paths below use the `/api/v1` prefix and existing workspace access controls.

| Method     | Path                                                      | Purpose                                                                                                                       |
| ---------- | --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| GET        | `/sibyl`                                                  | Runtime and model configuration readiness; safe setup reason and settings link                                                |
| POST       | `/sibyl/ask/stream`                                       | Same Sibyl request, streamed native activity and one terminal reply/error as NDJSON                                           |
| POST       | `/sibyl/ask`                                              | `message` (1–4,000 nonblank characters), optional `session_id` and unique `request_id`; model-driven specialist collaboration |
| GET / POST | `/sibyl/conversations`                                    | Latest 100 local chats / create an empty chat                                                                                 |
| GET        | `/sibyl/conversations/{session_id}`                       | Latest 100 completed turns and actual consultation evidence                                                                   |
| DELETE     | `/sibyl/conversations/{session_id}`                       | Permanently remove this chat; returns 204, or 409 while pending                                                               |
| GET        | `/sibyl/conversations/{session_id}/activity`              | Latest request stage and consultation summaries without full evidence; null before the first attempt                          |
| GET        | `/sibyl/conversations/{session_id}/requests`              | Latest 20 request summaries including stopped/failed/interrupted attempts                                                     |
| GET        | `/sibyl/conversations/{session_id}/requests/{request_id}` | Exact request and retained consultation evidence within its owning chat                                                       |
| POST       | `/sibyl/conversations/{session_id}/cancel`                | Required `request_id`; accepts exact queued/running request, returns 202                                                      |
| GET        | `/settings/messaging`                                     | Channel capabilities, connection status, setup fields and official setup links                                                |

Successful Ask results include `request_id` and `status: completed`. If stopped, the original Ask returns 200 with `{status: cancelled, session_id, request_id}`, without saving a chat answer. Cancellation is idempotent for an already stopped request; completed/non-running requests return 409 and unknown/foreign request IDs return 404. Session and request IDs are 32 lowercase hexadecimal characters; repeated request IDs return 409 without another model call. Startup marks unfinished requests interrupted without replaying them. History retains completed consultation evidence; frequent activity reads omit answer/evidence payloads. These request reads use `Cache-Control: no-store`.

Channels: `whatsapp`, `telegram`, `discord`, `slack`, `signal`, `email`. Telegram is implemented with explicit connection controls; the remaining channels are unavailable previews with disabled fields. See the [Telegram guide](../guides/telegram.md) for setup and delivery limits. Sibyl setup/duplicate-turn failures return 409, unknown chat IDs 404, provider failures a sanitized 502, and outer timeouts 504. The backend limits one pending turn per chat and two outer requests globally; native ProtoLink run budgets bound delegation/model/tool work. See [agent contracts](./agents.md).

`GET/POST /connection-alerts`, `POST /connection-alerts/{id}/edit` and `/action` manage passive read-failure/recovery subscriptions. Strict thresholds, revisions and lifecycle controls operate only on local evidence. `GET /connection-alerts/example` is isolated. The shared inbox accepts `kind: connection` alongside price and strategy notices. See [connection read contracts](alerts.md#connection-read-subscriptions).

`GET/POST /risk-alerts`, `POST /risk-alerts/{id}/edit`, `/action` and `/check` manage opt-in fixed-account risk watches. `/evidence` reads retained complete snapshots without provider calls; `/example` is isolated. Risk notices share the inbox with `kind: risk`. See [account-risk contracts](account-risk.md).

Agent-model assignment bodies accept `revision`, `provider` and `model` only. `/system` reports the workspace default; `/sibyl` reports the coordinator’s actual selection. The agents catalog and model-backed replies/consultations include provider/model attribution. See [per-agent model contracts](agent-models.md).


## Observed balance checks

`GET /account/balance-checks?scope=all` lists active accounts in the page scope. `GET /account/balance-checks/{id}` reads checkpoint metadata, the latest saved comparison and twenty report summaries. `POST /account/balance-checks/{id}/checkpoint` accepts `{replace_id: null or the viewed checkpoint ID}` and explicitly reads starting balances. `POST /account/balance-checks/{id}/compare` requires `{checkpoint_id: the viewed ID}` and saves a new comparison. `GET /account/balance-checks/{id}/reports/{report_id}` reads one retained report scoped to its account. All responses use `Cache-Control: no-store`. Saved reads never contact a provider; capture/compare never write to the exchange. See [balance-check contracts and numeric limits](balance-checks.md).

Funding balance conventions have local GET/POST review and POST withdrawal endpoints at `/api/v1/account-ledger/funding/{event_id}/review` (withdrawal appends `/withdraw`). Both writes require source/review revisions; no native exchange call is made. See [request fields and limits](funding-effects.md).

Pending status controls: `POST /connections/{account_id}/funding-refresh/{stream}` saves version-checked opt-in settings or queues a check of retained unfinished records. `GET /funding-sync` includes actual support and public pending-update progress. See [request fields, support and budgets](funding-pending-updates.md).

Recent funding sync: version-checked opt-in controls at `POST /connections/{account_id}/funding-scans/{stream}`, lazy pass history at `GET /connections/{account_id}/funding-scans/{stream}/reports`, and observed source history at `GET /account-ledger/funding/{event_id}/versions`. See [controls, budgets and coverage semantics](funding-recent-sync.md).
