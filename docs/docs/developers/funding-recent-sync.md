# Recent funding sync and observed changes

**Trade → Account history → Funding → Recent history sync** can discover new funding and revisit completed records inside a selected rolling window. It is **off by default**, separate from pending updates and independent of manual import ranges.

## Controls and actual support

Choose a stream, a lookback of **24 hours, 7 days or 30 days**, and a scan interval of **15 minutes, 1 hour or 6 hours**. **Enable recent sync** queues the first window. **Scan now** requests a fresh pass; **Turn off** stops future reads and invalidates an in-flight old reply. Changing controls also abandons the old pass safely, retaining validated source observations.

Implemented sources are Binance production crypto deposits/withdrawals, Kraken posted deposit/withdrawal/transfer ledgers, and Bybit master-UID on-chain withdrawals. Other clients, Demo and test environments do not advertise this feature. The adapter restrictions in [funding history](funding-history.md) still apply; no transfer, withdrawal or order is submitted.

Scans end one minute behind now and use **creation/ledger time**, not completion time, to select records. A transaction arriving later than its creation timestamp can be discovered when that timestamp remains inside the lookback. Older arrivals and corrections outside the window still need manual imports. Kraken's source is posted ledger entries, not pending funding requests. Bybit's existing adapter splits long requests into native windows shorter than thirty days; see [Bybit history](https://bybit-exchange.github.io/docs/v5/asset/withdraw/withdraw-record) and [Kraken ledgers](https://docs.kraken.com/api-reference/account-data/get-ledgers-info).

Pausing a manual funding import, deactivating or disconnecting an account turns off both automatic modes for the affected streams. Account/credential configuration changes invalidate old work and require explicit re-enabling. Controls remain available without an LLM.

## Bounded runtime

`services/funding/scans.py` defines the worker and controls. `scan_journal.py` owns frozen windows, source guards and pass reports. Both automatic workers share `worker.py` and the ordinary `ImportWorker` retry/lifecycle implementation. `state.py` holds their small common SQLite job contract.

Each pass freezes its start/end, run ID and versions of up to **10,000** retained records in the selected account/stream/window. It reads at most **200 pages**, with at most **50 observations per page**. Oversized inputs/pages stop with an explicit error; choose a shorter lookback or use manual imports. Validated earlier pages remain retained if a later page fails. A restart resumes the frozen native cursor, rather than moving the window during pagination.

Pending and recent-history reads share a persisted **ten-second read-slot floor**. Due jobs compete fairly across both workers. Provider admission, cooldowns, client leases and the existing bounded transient retry budget still apply. Delays can make a scan finish later than its selected interval. This is a local single-worker runtime, not distributed coordination.

## Corrections, concurrent changes and missing records

Updates match exact account/stream/native identities. Existing source versions are frozen at pass start. A source inserted, corrected or removed by another local import during the pass is preserved rather than overwritten or resurrected. Duplicate observations across pages, repeated cursors/pages and invalid records fail visibly. Native facts, audit entries and the page cursor commit in one transaction.

An exhausted window records new/changed counts, concurrent changes and retained records not returned by the source. Missing records are **kept unchanged**. A preview identifies at most ten; absence is not cancellation, a bust or proof of settlement. Source retention and changing native pagination can limit evidence even after a pass finishes.

If downtime or a narrower lookback leaves an interval between completed fetched windows, that interval stays in `funding_coverage_gaps`. Later passes do not silently hide it. Completing a manual import or a rolling window subtracts the fetched range, including splitting partially covered intervals. This tracks **available-page read coverage**, not complete native transaction history. The UI shows up to ten outstanding intervals and their total count.

The newest **twenty completed scan reports** are retained per account/stream. Routine status reads return only current controls/progress and the latest report. Expanded history is fetched lazily. Every report keeps `complete_history: false` and `settlement_final: false`.

## Observed source versions

`accounting/funding/versions.py` records append-only changes to material normalized native facts. Manual imports, pending updates and recent sync all use the same transaction helper. Initial observations and actual changes are recorded; unchanged polls and account-label changes do not create revisions. Native references, fees, quantities, status, wallet scope and posting times are tracked.

Open **Source record → Observed versions** to compare the previously observed and newly observed values. Twenty entries are displayed at a time; all audit entries remain stored. For records predating this feature, the first later correction preserves the prior retained facts, but unobserved earlier versions cannot be reconstructed. This is Sibyl's observation history, not an exchange-provided correction log.

Original provider observations, transfer-review assertions and funding-balance reviews remain separate. Material fee/wallet/amount corrections invalidate affected reviews through their existing source fingerprints. A new historical import/correction can make a saved Balance check incomplete and require a reviewed new checkpoint. Existing saved reports remain historical evidence.

No credentials, raw native metadata, addresses or user review notes enter the public change summaries. Accountant's ordinary ProtoLink tools receive the selected ledger's latest observed changes and up to ten scoped, read-only recent-sync policies. There are no agent mutation tools for these controls.

## API

Routes use the existing workspace/local-origin protections and `Cache-Control: no-store`:

| Method | Path relative to `/api/v1` | Purpose |
| --- | --- | --- |
| POST | `/connections/{account_id}/funding-scans/{stream}` | Save opt-in controls or queue a fresh pass |
| GET | `/connections/{account_id}/funding-scans/{stream}/reports` | Twenty retained pass reports, including after disconnect |
| GET | `/account-ledger/funding/{event_id}/versions` | Twenty observed source revisions and total count |
| GET | `/funding-sync` | Adds actual `recent_sync_streams` support and bounded `recent_sync` progress |

Control bodies contain `enabled`, `lookback_days`, `interval_minutes`, `replace_revision` (null initially) and optional `check_now`. Stale revisions return HTTP 409. Saving queues work; it does not perform a synchronous native read. Public status excludes native cursors, frozen source hashes and encrypted-account fingerprints.

## Validation and remaining work

Offline tests cover late arrivals, completed corrections, missing records, concurrency, account/control invalidation, restart, budgets, rate sharing, persistent gap tracking, version retention, API privacy and native AgentClient evidence. A single authenticated Binance deposit-history pass over a 24-hour window was exhausted successfully with a GET-only allowlisted transport on October 28, 2026. No native writes occurred; the main workspace's automatic controls remained off. The acceptance does not establish live correction behavior or authenticated Kraken/Bybit coverage; see [exchange acceptance](exchange-acceptance.md).

Broader funding adapters, records outside chosen lookbacks, native removal/bust semantics, full account reconciliation and fill/order revision histories remain on the [implementation checklist](backend-roadmap.md).
