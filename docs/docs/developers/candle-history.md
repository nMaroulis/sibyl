# Candle archive and reproducible research

`market_data/archive.py` owns timestamp validation, provenance, coverage, immutable snapshots and retention. `market_data/backfills.py` owns one local worker's resumable import state. `market_data/research.py` connects immutable inputs to the existing pure backtest engine.

## Storage contract

`candle_series` uses a hash of source ID, environment, canonical ASCII spot pair and timeframe. It records public identity metadata and a revision. `candle_rows` is keyed by series and opening UTC millisecond; equal observations are idempotent and corrected values update the mutable archive. Revision advances once per changed page. Credentials and raw native payloads are never persisted here.

Validation rejects malformed/non-finite prices, invalid OHLC bounds, negative volume, conflicting duplicate timestamps and off-grid intervals. Incomplete candles are omitted. Week boundaries use Monday UTC. No price interpolation, volume synthesis or quote substitution occurs.

A successful `Market.candles()` cache load retains its closed page. Cache hits do not repeat writes. Archive-budget and validation failures are surfaced rather than silently losing research history. Coverage compares expected timestamps, independently of pagination completion. Queries cover at most 50,000 intervals and serialize at most 2,000 preview bars. Series discovery is limited to the latest 1,000 entries, with explicit truncation metadata.

`candle_imports` retains a frozen range, cursor, source/environment, revision, status, page observations and retry time. One current job exists per series. `candle_datasets` stores copied candle arrays and metadata, separately from mutable observations. Dataset IDs are SHA-256 over canonical JSON `[identity, candles]`, where identity contains source/environment/pair/timeframe/schema. Reads verify the fingerprint and count. Content equality deduplicates snapshots; labels are outside the content hash.

## Worker and provider contracts

`ExchangeClient.candle_history` is false by default. Reviewed implementations expose `fetch_candle_page(symbol, timeframe, start, end)` with an exclusive end and `candle_page_size(timeframe)`. The native read must be bounded, validate exact pairs and avoid SDK auto-pagination.

Reviewed CCXT adapters use `since` and, where supported, `until=end-1`, with at most 200 requested observations. Kraken has an explicit recent-history restriction and no claimed old-history pagination. CryptoCompare uses native `toTs`, disables synthesized pair conversion and reduces page size under its 2,000 underlying-interval aggregation budget. Its weekly aggregation is deliberately excluded until calendar alignment is reviewed. Demo pages the same 730 synthetic bars as its current-data interface.

The worker fetches outside SQLite, then checks the saved job revision/status. An immediate transaction commits validated observations, cursor and progress together. Pausing or replacing a range invalidates a delayed response. Unexpected/outside timestamps fail rather than advancing the cursor. Empty valid pages advance the inspected range but leave missing coverage. Quota errors roll back the page and checkpoint together.

One page runs per worker tick; a committed page has a one-second next-attempt delay. Network/rate-limit failures have sanitized exponential backoff and up to five retries. Terminal invalid/access failures keep their checkpoint for explicit resume. Rescan restarts the same frozen range; it does not delete observations or saved datasets. Startup requeues interrupted `running` jobs from their last committed cursor. The API must run as a **single worker**; multi-worker leases are not implemented. Market-owned clients now share local read admission, transport budgets and cooldowns; deferrals preserve the import retry budget. See [provider control](provider-control.md).

Primary provider references: [CCXT pagination](https://docs.ccxt.com/docs/manual), [Binance klines](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market), [Coinbase public candles](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/get-public-product-candles), [Kraken OHLC limits](https://docs.kraken.com/api-reference/market-data/get-ohlc-data), [CoinDesk/CryptoCompare historical contract](https://developers.coindesk.com/documentation/legacy/Historical/dataHistominute). Mocked contract tests do not establish authenticated provider acceptance.

## Research execution

`POST /strategies/backtest` validates the exact provider pair and freezes the contiguous current sample before computing. `POST /strategies/backtest/dataset` validates requested pair/frame/count against the immutable metadata, verifies its fingerprint and runs without provider reads. The dataset route accepts 60–20,000 bars; the current-feed request remains bounded to 60–720.

Results retain the input metadata/fingerprint, strategy parameters and package engine version. They are repeatable under the same code and settings. This is neither a model artifact registry nor archival execution of older engine versions. Paper-running jobs do not consume saved datasets and remain separate from exchange execution.

## API

All paths below are relative to `/api/v1`, use workspace authentication/origin checks and return `Cache-Control: no-store`.

| Method | Path                                     | Contract                                                                                                                                                                      |
| ------ | ---------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GET    | `/market-history`                        | Required `source`, exact `symbol`, `timeframe`; optional aware `start` and `end` together. Coverage, retained preview, job state and provider limitations; no provider reads. |
| GET    | `/market-history/series`                 | Retained public identities/extents/counts, including disconnected sources.                                                                                                    |
| POST   | `/market-history/imports`                | Source/pair/frame and aware start/end dates; validates adapter and queues a frozen range; HTTP 202.                                                                           |
| POST   | `/market-history/imports/{id}/action`    | `action`: `pause`, `resume`, `rescan`.                                                                                                                                        |
| POST   | `/market-history/retention`              | Source/pair/frame, aware `before`, exact `confirmation: "PRUNE BTC/USDT"`; active import must be paused.                                                                      |
| GET    | `/market-history/datasets`               | Metadata only, 50 rows per page, `offset`.                                                                                                                                    |
| POST   | `/market-history/datasets`               | Source/pair/frame/start/end and optional label; complete 60–20,000 intervals required; HTTP 201.                                                                              |
| GET    | `/market-history/datasets/{id}`          | Verified immutable metadata and all copied candles, for JSON export.                                                                                                          |
| GET    | `/market-history/datasets/{id}/metadata` | Verified metadata for a research form without sending the bar array.                                                                                                          |
| POST   | `/strategies/backtest/dataset`           | Existing strategy parameters plus `dataset_id`; pair/frame/count must exactly match.                                                                                          |

Metadata/status reads use settings and stored identities, including disconnected sources; they do not construct provider market catalogs. Retention deletes only mutable observations. A snapshot remains usable after disconnect or prune.

`tests/test_candle_history.py` covers identity separation, corrections, validation, quotas/rollback, atomic checkpoints, delayed-page pause, restart recovery, retry sanitization, gaps, immutable retention, integrity verification, offline replay and native paging contracts.
