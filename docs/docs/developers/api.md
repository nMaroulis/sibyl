# API reference

The versioned base path is `/api/v1`. See the running service's `/docs` and `/openapi.json` for exact request schemas and validation rules. When a workspace token is configured, use `Authorization: Bearer YOUR_TOKEN` on versioned routes.

## Endpoints

| Method     | Path                            | Purpose                                                    |
| ---------- | ------------------------------- | ---------------------------------------------------------- |
| GET        | `/health` (unversioned)         | Process readiness and package version                      |
| GET        | `/system`                       | Safe workspace configuration                               |
| GET        | `/portfolio/accounts`           | Per-account free/reserved/total and conversion rates       |
| GET        | `/markets/symbols`              | Active spot catalog and available timeframes               |
| GET        | `/markets/orderbook`            | Public snapshot: symbol, depth 5–50                        |
| GET        | `/reports/trading`              | Combined records and matched paper FIFO P&L                |
| POST       | `/exchange-orders/{id}/refresh` | Read a known exchange order status; never resubmit         |
| GET        | `/portfolio`                    | Priced balances, allocation, history, warnings             |
| GET        | `/markets`                      | Watchlist and source labels                                |
| GET        | `/markets/analysis`             | `symbol`, `timeframe`, `limit` 60–720                      |
| GET        | `/markets/correlation`          | 2–8 symbols, timeframe, limit, method, transform           |
| GET / POST | `/connections`                  | List metadata / save encrypted credentials                 |
| DELETE     | `/connections/{id}`             | Remove a connection                                        |
| POST       | `/connections/{id}/check`       | Read-only credential verification                          |
| GET        | `/paper/balances`               | Separate manual paper ledger                               |
| GET / POST | `/orders`                       | Paper fill history / execute paper order                   |
| POST       | `/orders/preview`               | Paper reference quote, fee, estimated debit/credit         |
| GET        | `/exchange-orders`              | Exchange intents and submission snapshots                  |
| POST       | `/exchange-orders/preview`      | Validate and create a 60-second exchange intent            |
| POST       | `/exchange-orders/{id}/confirm` | Submit once with typed confirmation                        |
| GET        | `/strategies`                   | Algorithm catalog                                          |
| POST       | `/strategies/backtest`          | Historical simulation and persisted result                 |
| GET / POST | `/strategies/jobs`              | List / start isolated paper jobs                           |
| POST       | `/strategies/jobs/{id}/pause`   | Stop evaluating a paper job                                |
| POST       | `/strategies/jobs/{id}/resume`  | Resume evaluation                                          |
| GET        | `/forecast`                     | `symbol`, `horizon` 1–30                                   |
| GET        | `/news`                         | RSS/samples, summary=excerpt or extractive, VADER          |
| GET        | `/knowledge`                    | Glossary; optional `q` keyword query                       |
| GET        | `/blocks`                       | Recent Bitcoin blocks, count 1–100                         |
| GET        | `/stocks/{symbol}`              | Quote, adjusted history, statistics, profile               |
| GET        | `/agents`                       | Agent catalog and tool/provider metadata                   |
| POST       | `/agents/ask`                   | Run module tool and optional inference                     |
| GET        | `/runs`                         | Latest persisted runs; optional `kind=agent` or `backtest` |

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
