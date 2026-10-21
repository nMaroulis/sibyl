# Persistent local alerts

`PriceAlerts` owns source-pinned level/crossing rules with one-shot or reset-based repetition and a local inbox. It uses the existing `Market` reference-data boundary and workspace SQLite database. It never invokes a trading, account-activation, agent or external-delivery tool.

## Persistence and evaluation

`price_alerts` stores rule ID, status, next-check time and JSON payload. Payloads include selected source/pair/condition/threshold, repeat mode and cooldown, source label/environment, lifecycle/configuration revision, cycle, observed price/provider time, crossing baseline, reset state, failures and check/error evidence. `alert_notifications` stores immutable trigger evidence plus mutable read state, with a unique `(rule_id, cycle)` constraint.

Creation freezes the selected source and validates its exact spot catalog. It does not fetch a ticker. List/inbox/example reads never evaluate rules or make provider calls. The dedicated lifespan worker calls `tick()` once per second; one due rule is selected by next-check time/row order. It resumes persisted schedules after restart. Normal checks are due 30 seconds after evaluation. Failures back off exponentially from 60 seconds to a 900-second cap. A manual check shares the worker lock and honors cooldown/backoff; it is not a rate-limit bypass.

The quote read uses `Market.snapshot(rule.source)` and `valuation_ticker(rule.symbol)`, requesting no charts, private balances, orders or candles. Every evaluation revalidates exact catalog membership and requires a positive finite price and provider timestamp. Quotes older than five minutes, more than one minute in the future, undated or unavailable cannot trigger. Receipt time is never substituted. Provider errors are sanitized, and live failures never fall back to Demo.

The Demo client generates a synthetic snapshot timestamp at evaluation/cache load time; its fixed sample price still derives from the last closed fixture candle. Its historical OHLCV timestamps are unchanged. Demo remains explicitly attributed and must pass the same freshness checks as other rules. CoinGecko's Demo **API plan** remains a live API source and is not Sibyl's offline Demo.

A provider read happens outside the database transaction. The commit uses `BEGIN IMMEDIATE`, reloads the rule and checks armed status and revision. Pausing, editing, archiving or rearming during an in-flight read invalidates that observation. When a condition qualifies, its lifecycle/reset/cooldown state and one inbox row commit together. A crash before commit leaves no notification; after commit the cycle cannot notify twice. Notifications retain the original label, pair, source, condition, threshold, repetition settings and rule revision, even after edits. There is no external send to retry or transactional outbox claim.

Lifecycle actions advance revision. Arming an already armed rule is idempotent; resuming or rearming a paused/triggered rule starts a fresh cycle. Archive is reversible; restore leaves the rule paused. Notifications survive archive. Mark-read operations are idempotent and do not delete evidence. Unread/total counts cover all retained notifications independently of page size.

The service waits for an in-flight check during shutdown before closing shared market adapters. It assumes **one API worker**, matching the rest of this local workspace; distributed scheduling/claims remain deferred. Reads share existing transport/cache locks and can be delayed by other work. Creating/arming a rule does not wake or recreate missed historical prices.

## Conditions and repetition

`services/alert_conditions.py` contains deterministic state transitions, separate from provider reads and SQLite commits.

- `above` and `below` use inclusive `>=` / `<=`; a one-time rule can notify on its first fresh quote.
- `crosses_above` requires a previous quote strictly below the threshold, then one at or above it. `crosses_below` is symmetric. A first quote only establishes a baseline; starting on the qualifying side does not trigger.
- Provider timestamps must strictly advance. Repeated or older quotes cannot replace retained evidence, reset an alert, or create a crossing. The rule shows a waiting note and keeps its normal check schedule.
- Crossings require consecutive usable observations no more than 300 seconds apart. A larger gap starts a new baseline. Read/freshness errors, including provider admission deferrals, clear crossing evidence while retaining the last displayed quote. Missed crossings are never reconstructed from offline time.
- `repeat: once` is the default and becomes `triggered` after its notification. Older saved rules retain this behavior.
- `repeat: after_reset` remains `armed` after notifying, with `waiting_reset: true` and a persisted `cooldown_until`. It must observe the strict opposite side before a new qualifying entry can notify. Subsequent entries use the same ordered, bounded-gap crossing requirements. A level rule can still notify on its first quote of a freshly armed cycle; a crossing rule always needs a baseline.
- `cooldown_seconds` is an integer from 60 to 86,400 (default 300). A move into the qualifying side during cooldown is consumed and waits for another reset; it is not delivered later when cooldown expires. A reset observed during cooldown may precede a new entry after cooldown.

`cycle` identifies a notification opportunity, not a count of successful deliveries. A repeated notification advances the cycle atomically before insertion; explicit resume/rearm also advances it and starts fresh observation. Duplicate checks and process restarts preserve reset/cooldown state. Explicit rearming starts a fresh cycle and can notify immediately for level rules, regardless of the previous cycle's cooldown.

## Editing

`POST /alerts/{id}/edit` takes the full create configuration plus the editor's positive integer `revision`. Saving preserves the rule ID and notification history, increments revision, clears current observation/reset/cooldown state and leaves the rule **paused**. The user explicitly resumes it when ready. Archived rules must first be restored.

Only source/pair changes need catalog validation. An unchanged-feed label/threshold edit can repair a rule while the provider is unavailable. Revisions are checked before and after any catalog read, with the second check inside the write transaction. A stale editor returns `409` and cannot overwrite a newer edit or lifecycle change. Evaluation does not advance the configuration revision; its current cycle is retained when the edit commits.

## HTTP contract

Paths are relative to `/api/v1` and use existing workspace access controls. Mutable/private responses use `Cache-Control: no-store`.

| Method | Path                                      | Contract                                                                                                                                                              |
| ------ | ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GET    | `/alerts?include_archived=false&offset=0` | Rule pages of 50, total, offset and non-archived budget; no provider calls                                                                                            |
| POST   | `/alerts`                                 | `source`, canonical `symbol`, `condition: above/below/crosses_above/crosses_below`, positive `threshold`, optional `label`, `repeat`, `cooldown_seconds`; returns 201 |
| POST   | `/alerts/{id}/edit`                       | Full rule configuration + `revision`; saves paused; stale revision returns 409                                                                                        |
| POST   | `/alerts/{id}/action`                     | `action: pause/arm/archive/restore`                                                                                                                                   |
| POST   | `/alerts/{id}/check`                      | Evaluate only if armed and due; otherwise return retained state                                                                                                       |
| GET    | `/alerts/example`                         | Isolated illustrative rules and inbox; never persisted                                                                                                                |
| GET    | `/notifications?limit=20&offset=0`        | Paginated history (limit 1–100), total and unread counts                                                                                                              |
| POST   | `/notifications/{id}/read`                | Mark one read, preserving original first-read time                                                                                                                    |
| POST   | `/notifications/read-all`                 | Acknowledge current unread rows, without removing history                                                                                                             |
| GET    | `/roadmap`                                | Audited implementation scope from `services/roadmap.py`; multi-user explicitly deferred                                                                               |

The API accepts no arbitrary destination, webhook, credential or trade field. Credentials stay in the existing encrypted source profiles. The rule payload and trigger evidence contain source identity and environment, never provider keys or raw transport errors.

## Current limits

Editable level/crossing rules and reset-based repetition are implemented. Portfolio-risk, strategy and connection-health conditions remain pending. Delivery is in-app only. Notification history is retained locally and paginated, without managed retention/export yet. No general-purpose durable job queue, external delivery retries, guarantee of timely delivery or multiple-worker coordination is claimed.

Tests use disposable stores, exact controlled feeds and API examples. They cover threshold equality, crossing direction/baselines, cooldown reset sequences, ordered timestamps/gaps, cached-data aging, failures/backoff, edit conflicts, source pinning, concurrency and delayed-response races, atomic rollback and restart persistence, unread acknowledgment, pagination, archive/restore, capacity and absence of trading effects. See the [user guide](../guides/alerts.md).
