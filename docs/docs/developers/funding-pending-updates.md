# Pending funding updates

Pending updates revisit unfinished records already in the funding ledger. They are **off by default** and configured independently for an account and stream in **Trade → Account history → Funding**.

## User controls

Select a connected account, then choose **Enable updates** for deposits or withdrawals. Available intervals are 5 minutes, 15 minutes and 1 hour. These are minimum recheck intervals; pagination, other accounts, cooldowns and failures can delay the next opportunity. Opening a page or asking Accountant never enables reads.

**Check now** queues a bounded pass and explicitly retries records previously marked for review. It still respects provider admission and the global read floor. **Turn off** invalidates an in-flight response and stops future reads. Pausing a manual funding import also turns off pending updates for that stream. Deactivation/disconnect disables all account streams; reactivation requires another explicit enable. Changing encrypted account configuration stops old work and requires review/re-enabling.

The panel shows unfinished counts, source updates, last exhausted check, upcoming opportunities, sanitized failures and records needing review. Up to ten missing records are shown with links that filter the funding table. These are source observations, not bank/chain settlement confirmations.

## Actual support

| Client | Pending streams | Limits |
| --- | --- | --- |
| Binance production | Deposits, withdrawals | Existing crypto capital-history endpoints; original creation-time windows and native pagination |
| Bybit production | Withdrawals | Existing master-UID on-chain source; no off-chain, sub-UID or additional-tax support |
| Kraken | Unavailable | Its current source contains posted ledger entries, not pending requests |
| Demo, test environments, other clients | Unavailable | No pending-source adapter advertised |

The worker reuses the reviewed [Binance history endpoints](https://developers.binance.com/en/docs/catalog/core-trading-wallet/api/rest-api/capital) and [Bybit withdrawal history](https://bybit-exchange.github.io/docs/v5/asset/withdraw/withdraw-record). It adds no exchange write method and does not create deposits, withdrawals, transfers or orders.

## Bounded scheduling and persistence

Implementation lives in `services/funding/`: `contracts.py` defines opt-in controls/budgets, `journal.py` owns SQLite state and `refresh.py` uses the shared `ImportWorker` lifecycle. Manual imports keep their original independent checkpoints in `funding_sync`.

`funding_refresh` saves controls and an in-progress source window/cursor. `funding_rechecks` saves each record's latest exhausted outcome, last check, last match and consecutive missing checks. No credentials, addresses or raw provider payloads enter public progress.

A due pass freezes at most 1,000 existing `pending`, `restricted` or `unknown` records within a creation-time window of at most 62 seconds. One native page of at most 50 observations is read per slot, with a maximum of 20 pages per pass and a shared ten-second floor between attempts across policies. The regular background read admission, provider cooldowns, client leases and bounded transient retry logic also apply. Provider deferral does not consume the transient retry budget.

An exhausted window updates per-record outcomes. Five consecutive exhausted windows without a target mark it **needs review** and stop automatic retries for that record. The source status and quantities remain intact. **Check now** explicitly resets these missing counters. Other due records can continue.

A process restart resumes the saved page cursor; an interrupted `running` page is queued again. Work is serialized within the supported single API worker. Shutdown drains finite in-flight reads before closing transports. This is not a distributed scheduler.

## Evidence and concurrency

Only frozen retained IDs can update, even if the native window returns other records. A source-version comparison prevents an older refresh from overwriting a concurrent manual correction. Native identities, first observation time, existing transfer links and local review audit remain intact. Fee/status/posting-time corrections invalidate affected local reviews through the existing material-source fingerprint.

Whole-page validation precedes writes. Source updates, refresh cursor and outcomes commit together. Duplicate identities, repeated cursors/pages, overlapping target observations and page-budget exhaustion stop the pass with an explicit error. Missing entries are never deleted, completed or cancelled by inference. Previously validated pages remain retained if a later page fails.

A control revision prevents stale saves and old in-flight results/failures from changing newer controls. An encrypted-account fingerprint binds each pass without decrypting credentials for scheduler controls or public status. No fingerprint or cursor is returned to the browser or agents.

## API and ProtoLink

`POST /api/v1/connections/{account_id}/funding-refresh/{stream}` accepts:

```json
{
  "enabled": true,
  "interval_minutes": 5,
  "replace_revision": null,
  "check_now": false
}
```

Use the currently displayed revision for later saves; stale controls return HTTP 409. The existing `GET /api/v1/funding-sync` now includes per-account `pending_update_streams` and public `pending_updates`. Reads and control saves use existing workspace authentication/local-origin protections and `Cache-Control: no-store`. Saving only queues work; native reads run later.

Accountant's native ProtoLink tools can explain up to ten relevant stream policies, keeping selected account, stream and environment restrictions. They receive read-only status, not mutation tools, cursors or control revisions. `page_help(topic="funding")` explains enabling, stopping and reviewing updates.

## Remaining work

Optional [recent history sync](funding-recent-sync.md) discovers new arrivals and completed corrections inside a chosen window. Funding outside that window, full account discovery and terminal execution bust/removal handling still require explicit imports or future infrastructure. A pending update does not supply missing wallet/fee conventions, completion timestamps, cost basis or investment returns. An exhausted pass is not complete history or final settlement proof.

Offline tests cover pagination/restart, rate limiting, bounded retries, missing targets, source/control races, credential changes, unsupported venues, batch limits, API privacy and native AgentClient evidence. No authenticated Binance/Bybit pending-transition acceptance was performed for this batch.
