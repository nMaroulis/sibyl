# Provider request coordination and health

`market_data/control.py` coordinates reads made by **Market-owned exchange and market API clients**. It adds shared admission, bounded HTTP concurrency, conservative transport spacing, sanitized cooldowns and observed health. News, crypto profiles, equities and other research integrations retain their existing independent policies.

## Read path

`Market` binds typed clients in place; their classes and native exchange contracts remain intact. Public and private clients for the same provider/environment share an admission lane and cooldown. Production and test environments remain separate. Native CCXT weighted rate limiting stays enabled.

Explicit read methods acquire their provider lane **before** entering adapter locks. Queued dashboard work precedes queued background work, both at provider admission and at the global HTTP gate. In-flight operations and deliberate multi-step account sequences are not preempted. A new public read can proceed while an unrelated provider is slow; the workspace mutex now protects pool/cache bookkeeping rather than network calls.

The transport gate records actual SDK HTTP reads through `exchange.fetch` and aggregator reads through their bounded `_get`. Cached catalogs or batched cached API prices do not establish new transport success. Private read endpoints that use POST are classified by the explicit read method contract, not by HTTP method alone.

| Policy                           | Local bound                                                                        |
| -------------------------------- | ---------------------------------------------------------------------------------- |
| Concurrent external HTTP reads   | 4                                                                                  |
| Waiting operations               | 64 per provider, 256 total                                                         |
| Admission wait                   | Up to 5 seconds                                                                    |
| Background transport-budget wait | Up to 2 seconds                                                                    |
| Minimum transport spacing        | 250 ms per provider/environment; 1 second for CryptoCompare and CoinGecko Demo API |
| Direct foreground read attempts  | At most 2                                                                          |
| Recent error evidence            | 5 sanitized events per observed source                                             |
| Observed source records          | 512 per process                                                                    |

These are conservative application budgets, **not claims about a provider's purchased quota or exact endpoint weights**. The SDK's native limiter, account plan, IP limits and provider restrictions still apply. Continually busy feeds can defer background imports; their checkpoints remain saved.

## Retry and mutation boundaries

One foreground read may be retried after a short initial transient failure. The entire explicit read method is called again so signed requests receive fresh native parameters. Transport hooks never replay a signed URL. Longer cooldowns, rate limits and worker reads return to their caller's scheduling path. Multi-step account sequences do not automatically replay.

Network failures use shared exponential cooldowns starting at 0.5 seconds and bounded to 60 seconds. Rate-limit failures impose at least two seconds. Valid numeric or HTTP-date `Retry-After` hints can extend that cooldown, bounded to one day. Authentication failures affect the observed source's diagnostics without cooling down unrelated public access to the same exchange.

`ProviderDeferred` means **no new network attempt** took place. The API returns HTTP 503 with a safe `Retry-After` header and `retry_after` field. Candle, fill and funding workers preserve their failure budget and saved cursor when deferred. Alerts stay armed and automatic order-status checks preserve their last observation. Actual failed requests still consume each domain worker's existing bounded retry budget.

Order submission and cancellation, including their preflight reads, bypass this new read retry/admission policy and retain their existing single-attempt handling. `Market.adapter(write=True)` preserves the private adapter lock and lease without entering a read lane. No new permission, order type or automated execution is enabled by the request coordinator.

References: [CCXT rate limiting](https://docs.ccxt.com/docs/manual), [CoinGecko errors and rate limits](https://docs.coingecko.com/docs/errors-and-rate-limits), [HTTP Retry-After semantics](https://httpwg.org/specs/rfc9110.html#field.retry-after). Provider quotas can change independently of Sibyl's conservative local budgets.

## Cache and client lifecycle

Identical market cache misses share one in-flight future. Different keys and providers remain independent. Cache/source identities retain the exact source, environment and credential fingerprint. A global cache epoch prevents an invalidated in-flight result from repopulating a cleared cache.

Frozen reference reads lease the client for their complete operation. Credential replacement retires existing adapters immediately for new callers, while active leases finish before their transports close. Late old-key snapshots create transient leased clients rather than reentering the current pool. New credentials start with unchecked health; late retired reads update only retired evidence.

Client construction and settings reads remain protected by short local locks. Each adapter retains its own transport lock, and account sequences acquire admission before that lock to avoid a lock/queue inversion. The local deployment remains **one API process**. Distributed budgets, cross-process single-flight and worker leases are not implemented.

## Observed health API

`GET /api/v1/providers/health` returns public source identities, process-local read metrics, quote evidence, shared queue/cooldown state and persisted active import counts. Optional `source` selects one configured or observed source. The endpoint applies workspace access controls and returns `Cache-Control: no-store`. It never probes a provider or validates a key just because the panel is opened.

Connectivity status is separate from quote quality:

- `not_checked`: no successful external read has been observed in this process/current credential profile.
- `healthy`: an actual provider read succeeded recently.
- `stale`: no successful external read has been observed in five minutes.
- `retrying`: the shared provider/environment lane is cooling down.
- `degraded`: a sanitized authentication, transport or validation error needs attention.
- `unavailable`: the configured source is unavailable, inactive or missing access configuration.
- `demo`: explicitly offline synthetic data; it makes no external connectivity claim.

`data_status` describes **one latest quote sample** as fresh, stale, undated, invalid, not observed or synthetic. It uses the original provider timestamp, never cache-access time. A healthy HTTP response can therefore accompany an old quote. Existing valuation, alerts and trading reference-price checks continue enforcing their own data requirements.

Metrics include actual request/success/failure counts, the last transport latency, last completed successful read, foreground retries, deferrals and market-cache hits. Recent errors contain only a fixed category, fixed message and timestamp. URLs, keys, headers, request arguments, raw provider messages, balances and order payloads are excluded. Live session metrics reset on API restart; retained read history and imports persist separately. An unavailable source can keep previously observed evidence until it is retired or the API restarts.

The dashboard shows a compact status line on Markets and populated Portfolio views, plus **Settings → Market data → Source health**. Expanding a source reveals its observed evidence. Refreshing diagnostics reads local state only. Hidden Settings sections stop their diagnostics polling.

## Tests and remaining work

`tests/test_provider_control.py` covers provider and global priority, concurrency bounds, spacing, sanitized failures, header handling, environment isolation, bounded retry, quote quality, cache coalescing, credential rotation, mutation non-retry, offline diagnostics and worker deferrals. Other account/order/alert tests retain their existing execution invariants.

Remaining work includes live authenticated provider acceptance, exact endpoint-weight budgeting across credentials/IPs, streaming subscriptions, more detailed rolling latency/availability metrics, application-wide operational history and distributed coordination. This feature is local request control and observed diagnostics, not an external availability monitor.

## Retained read history

`market_data/health_history.py` records completed HTTP reads from the existing transport gate into the workspace SQLite database. It stores source ID, kind, provider/environment, a random profile generation, hourly counts/timings and fixed error categories. Source labels, credentials, request arguments, URLs, headers, prices, balances, raw errors and response bodies are excluded. Generation IDs are random and are not credential fingerprints.

`GET /api/v1/providers/health/history?source=binance&window=24h` returns hourly observations; `window=7d` returns 168 buckets. The current hour is partial, so these are bucket windows rather than exact trailing intervals. Totals include observed reads, successes/failures, success percentage, weighted mean/maximum response time and first/last retained read. Up to 20 sanitized recent errors accompany the chart. Reads require the workspace token, return `Cache-Control: no-store`, and never probe a provider. Unknown source IDs return 400; invalid windows return 422. Current configured sources and retained formerly observed identities are inspectable.

The live health report adds `history_available` per source and a `history_recording` status. A previously observed disconnected account is unavailable; restart or credential replacement starts current connectivity unchecked. The saved history explicitly includes earlier sessions/profiles and is never used to restore current health, cooldowns, queues, retries or quote freshness. A retained account identity does not restore credentials or access.

Only completed HTTP read outcomes count. Cache hits, admission deferrals, Demo, submission/cancellation and their preflight reads do not create history. Each short native retry contributes its own actual transport attempt. A successful HTTP call followed by adapter validation failure remains an HTTP success; current logical error diagnostics and domain validation still report the problem. An HTTP success is not evidence of correct/fresh data. Gaps are unobserved traffic, not downtime; the percentage is not provider uptime. News and other research services remain outside this market-client recorder.

Hourly aggregates are retained for up to 14 days, bounded globally to 50,000 profile/hour rows; error samples are bounded to 2,000 rows. Pruning runs at startup and when a new bucket or error is saved. Early evidence can be evicted under the row caps. There is no backfill of observations from before this feature, and no background availability sampler. The chart uses a small SVG with hover and arrow-key inspection, with no added chart dependency.

Each completed transport read attempts an immediate local commit outside the request-coordinator lock. SQLite lock waits are bounded to 50 ms. Busy/unavailable storage does not replace the provider result or trigger a provider retry; recording counts dropped observations and the UI discloses partial history. Those loss counters are process-local, while successful history commits survive restart. No buffer is replayed, and the history is observational diagnostics rather than an execution audit.

`tests/test_provider_history.py` covers persistence, weighted totals, source/environment boundaries, sparse windows, caps/retention, Demo/cache/deferral/mutation exclusions, storage contention, retired profiles, restart readiness, read-only access and workspace authorization.
