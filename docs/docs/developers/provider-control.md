# Provider request coordination and health

`market_data/control.py` coordinates reads made by **Market-owned exchange and market API clients**. It adds shared admission, bounded HTTP concurrency, conservative transport spacing, sanitized cooldowns and observed health. News, crypto profiles, equities and other research integrations retain their existing independent policies.

## Read path

`Market` binds typed clients in place; their classes and native exchange contracts remain intact. Public and private clients for the same provider/environment share an admission lane and cooldown. Production and test environments remain separate. Native CCXT weighted rate limiting stays enabled.

Explicit read methods acquire their provider lane **before** entering adapter locks. Queued dashboard work precedes queued background work, both at provider admission and at the global HTTP gate. In-flight operations and deliberate multi-step account sequences are not preempted. A new public read can proceed while an unrelated provider is slow; the workspace mutex now protects pool/cache bookkeeping rather than network calls.

A small SDK `fetch2` hook reduces unsigned request metadata to fixed labels/costs and waits for read allowance before signing. The transport gate rechecks quota after native throttling and defers a race without sending the signed URL. It records actual SDK HTTP reads through `exchange.fetch` and aggregator reads through their bounded `_get`. Cached catalogs or batched cached API prices do not establish new transport success. Private read endpoints that use POST are classified by the explicit read method contract, not by HTTP method alone.

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

These base budgets are supplemented by the [reviewed quota policies](#reviewed-quota-policies). Application allowances remain separate from reported provider limits and account tiers. The SDK's native limiter, account plan, IP limits and provider restrictions still apply. Continually busy feeds can defer background imports; their checkpoints remain saved.

## Retry and mutation boundaries

One foreground read may be retried after a short initial transient failure. The entire explicit read method is called again so signed requests receive fresh native parameters. Transport hooks never replay a signed URL. Longer cooldowns, rate limits and worker reads return to their caller's scheduling path. Multi-step account sequences do not automatically replay.

Network failures use shared exponential cooldowns starting at 0.5 seconds and bounded to 60 seconds. Rate-limit failures impose at least two seconds. Valid numeric or HTTP-date `Retry-After` hints can extend that cooldown, bounded to one day. Authentication failures affect the observed source's diagnostics without cooling down unrelated public access to the same exchange.

`ProviderDeferred` means **no new network attempt** took place. The API returns HTTP 503 with a safe `Retry-After` header and `retry_after` field. Candle, fill and funding workers preserve their failure budget and saved cursor when deferred. Alerts stay armed and automatic order-status checks preserve their last observation. Actual failed requests still consume each domain worker's existing bounded retry budget.

Order submission and cancellation, including their preflight reads, bypass this new read retry/admission policy and retain their existing single-attempt handling. `Market.adapter(write=True)` preserves the private adapter lock and lease without entering a read lane. Quota telemetry observes bypassed attempts and allowlisted numeric provider headers separately from read-success history. A rate-limit hint on a bypassed native request may cool future reads, but never retries that mutation or turns it into a failed-read event. A quota-observer failure cannot change a native result. No new permission, order type or automated execution is enabled by the request coordinator.

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

The dashboard shows a compact status line on Markets and populated Account views, plus **Settings → Market data → Source health**. Expanding a source reveals its observed evidence. Refreshing diagnostics reads local state only. Hidden Settings sections stop their diagnostics polling.

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

### Read-event journal and connection alerts

Alongside hourly aggregates, each recorded transport completion now appends a bounded event for **Alerts → Connections**. The event includes an allowlisted operation, random session/profile generation, sequence and retired-profile flag. It shares the telemetry commit and its 50 ms lock budget; storage loss cannot trigger retries or mask the provider result. No cache hit, deferral, Demo or mutation/preflight read is added. An offline/quiet source is unobserved, not failed.

The journal keeps a contiguous ID suffix up to 14 days/50,000 events and a durable pruning watermark. Per-stream sequences expose missing/reordered observations; restarts and credential changes reset streak continuity. Connection alerts use this evidence for consecutive failure/recovery notices, without restoring current health or probing credentials. See [connection read subscriptions](alerts.md#connection-read-subscriptions) for contracts and limitations.

## Response-time distributions

Retained hourly reads now include fixed latency counters with upper bounds at 10, 25, 50, 100, 250, 500, 1,000, 2,500, 5,000, 10,000 and 30,000 ms, plus an explicit overflow bucket. `latency_distribution` on saved health history reports samples, coverage, histogram counts and p50/p95 bucket upper bounds, not exact quantiles. A null upper bound can mean no usable samples, invalid evidence or a quantile in the >30-second tail; inspect status and overflow counts.

The schema adds histogram JSON without rewriting old means into invented samples. Legacy observations remain in overall traffic/success/mean metrics but are excluded from percentile samples, so coverage can be partial. Counts use the same atomic observation transaction and retention bounds as existing saved history. Cache hits, queued/deferred work, Demo and mutations are not extra network-read samples. Settings’ saved history exposes the distribution without probing a provider.

## Reviewed quota policies

`market_data/quotas/` contains explicit policies, unsigned SDK metadata reduction and bounded budget/evidence projection. The existing coordinator owns admission, locks, worker priority and read retries. Native CCXT throttling stays enabled; its internal fractional cost units are **not** used as published exchange weights.

| Provider                                           | Implemented app allowance and evidence                                                                                                                                                                                                                                                                                                                                                              |
| -------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Binance / Binance.US / Binance Testnet             | Reviewed Spot v3 GET weights, including book-size tiers, single/multi-symbol ticker cases, account/order/history reads. App ceilings: 600 weight and 120 GET requests per UTC minute. A valid observed `exchangeInfo` one-minute `REQUEST_WEIGHT` limit adds a separate 80% read ceiling. Allowlisted `X-MBX-USED-WEIGHT-1M` observations raise its estimate; local/in-flight charges are retained. |
| Kraken                                             | Public reads share a one-token/second local allowance. Reviewed private POST reads use a key-scoped local counter: capacity 12, refill 0.30/sec, basic cost 1 and history cost 4. Identical keys share a bucket across aliases. This is a conservative estimate, not discovered verification tier or live provider counter.                                                                         |
| Coinbase Exchange Sandbox                          | Public token capacity/refill 10/8 per second; private 12/10; fills additionally 8/8. Public and private/fills scopes are distinct. All local private profiles conservatively share the allowances because real profile identity is not inferred.                                                                                                                                                    |
| Coinbase Advanced, other exchanges and market APIs | Existing shared spacing, native throttling and cooldowns. Endpoint-specific quota policy remains unreviewed; Exchange Sandbox limits are not applied to Advanced Trade.                                                                                                                                                                                                                             |

Kraken’s developer guide lists history cost 2 while its support guide lists 4. Sibyl deliberately uses the higher application estimate and a rate below the documented Starter decay; it does not claim to know the key’s actual tier. Current reviewed policy date: **9 November 2026**. Definitions and provider links live in `policies.py`.

Only one-minute Binance IP windows are enforced from declarations in this slice. Wallet/SAPI endpoint weights, other interval families and exact exchange-tier/profile policies remain gaps. Reported order counters and their declared limits are dated observations only: they do not authorize, queue or limit submission through this read layer. Unknown request costs remain visible; no weight or headroom is invented.

Local window counters and token debt include actual attempts, including failures and reviewed preflight reads that bypass read admission. Missing responses do not refund an attempt. Same-minute reported IP counters can only raise the estimate; outstanding reservations are included. Old replies cannot overwrite a new minute, and backward wall time does not reset a window. Provider `Date` is used only to place a valid counter in a nearby observation window; this is not a clock-synchronization service. Limit declarations retain their observed time. Their availability can change independently of the application.

Quota waits happen before SDK signing and remain bounded by the existing five-second foreground/two-second background budget. A request that cannot fit returns `ProviderDeferred`; workers preserve cursors and retry budgets, while the HTTP boundary returns safe 503/Retry-After. Global transport/spacing admission remains independent. An external write during native throttling can exhaust allowance; the final gate then defers before HTTP rather than reusing a signed request.

Budget state is local to the retained process and resets on restart; provider usage does not reset. Identical credential groups are internal only. Diagnostics expose neither hashes nor raw keys, paths, signed URLs, request parameters, account IDs from responses, headers or response bodies. Numeric headers/declared fields are bounded and allowlisted. Source generations isolate replaced credentials; shared IP capacity is not refunded by resetting a source. There is no coordination with other processes, programs, devices, external IP traffic or WebSocket clients.

## UI and native agent evidence

Expand **Settings → Market data → Source health**. **Read allowances & quota evidence** separates app allowance, observed provider ceiling, usage estimates, reset/refill behavior, unreviewed/bypassed attempts and dated order counters. A read-budget deferral is distinct from transport health and quote freshness. Refresh does not probe an exchange. Retained HTTP history remains separate; quota estimates are session-local.

Technician’s ordinary typed `source_health` tool reads up to twelve default/observed sources or one selected source through native ProtoLink. It provides context for setup and deferrals without refreshing a provider or granting execution permission.

Acceptance uses actual installed native SDK request generation, signing and controlled `requests` responses for Binance, Kraken and Coinbase Exchange Sandbox. It covers shared/isolated budgets, metadata privacy, pre-sign deferral, raw header mappings, delayed/out-of-order responses, malformed declarations, observed order counts, uncertain writes and native Technician evidence. No real account order or live provider quota exhaustion is performed.

References: [Binance Spot limits](https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#limits), [Binance.US limits](https://docs.binance.us/), [Kraken REST guide](https://docs.kraken.com/exchange/guides/rest/ratelimits), [Kraken support rate limits](https://support.kraken.com/articles/206548367-what-are-the-api-rate-limits-), [Coinbase Exchange rate limits](https://docs.cdp.coinbase.com/exchange/rest-api/rate-limits).
