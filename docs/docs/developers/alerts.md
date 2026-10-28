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

Editable level/crossing rules and reset-based repetition are implemented. Strategy journal subscriptions are also implemented below. Portfolio-risk, connection-health and silent-worker outage conditions remain pending. Delivery is in-app only. Notification history is retained locally and paginated, without managed retention/export yet. No general-purpose durable job queue, external delivery retries, guarantee of timely delivery or multiple-worker coordination is claimed.

Tests use disposable stores, exact controlled feeds and API examples. They cover threshold equality, crossing direction/baselines, cooldown reset sequences, ordered timestamps/gaps, cached-data aging, failures/backoff, edit conflicts, source pinning, concurrency and delayed-response races, atomic rollback and restart persistence, unread acknowledgment, pagination, archive/restore, capacity and absence of trading effects. See the [user guide](../guides/alerts.md).

## Strategy journal subscriptions

`alerts/strategies.py` owns `StrategyAlerts`, attached to the strategy domain at startup. `alerts/contracts.py` declares strict create/update/action schemas. `alerts/inbox.py` owns the shared notification table and read acknowledgments; the existing price service delegates its inbox methods to this repository. Prior price notifications default to `kind: price`; new strategy payloads have `kind: strategy`. No legacy row rewrite is needed.

`strategy_alerts` stores one JSON rule with indexed `job_id`, status and next-check time. A partial unique index permits one non-archived rule per run. A separate 50-rule non-archived budget applies. JSON includes categories, run/source/mode/environment snapshot, revision, current global journal ID cursor, last observed job status, check/event/notification times and cumulative notification count.

Creating a rule captures the job, metadata and its maximum event ID inside `BEGIN IMMEDIATE`. This defines the subscription boundary atomically with concurrent journal writes. No existing events are delivered. Pausing/archive does not advance the cursor, but explicit Resume creates a new boundary at the then-current tail and skips the paused interval. Editing validates revision, saves paused and preserves all original notification evidence. Restore checks budget and duplicate-run constraints and leaves the rule paused. Lifecycle/configuration actions advance revision; worker progress does not.

The dedicated lifespan task is independent of the provider-backed price loop. Each tick serializes a local write transaction and reads at most 100 ascending event IDs for one due armed rule. Ignored decisions also advance the cursor. Each matched event inserts an inbox record with unique `(rule_id, event_id)` using the shared `cycle` column. Cursor/status progress and notices commit together. A crash rolls both back; concurrent consumers serialize and cannot duplicate a committed notice. Full pages remain due for catch-up, otherwise checks are scheduled five seconds later. Selection by next-check/row order bounds work across rules. Shutdown waits for the bounded local transaction.

`Strategies._event` now records `job_status` beside the existing action/reason at journal time. Attention matches `PAUSE`, `ERROR`, `RECOVERED`; lifecycle matches `RESUME`, `STOP`, `STOP_CANCEL`, plus the first transition to `completed`, even if its journal action is `SELL` or `SKIP_BUY`. Later events in the same completed state do not duplicate completion. Ordinary HOLD/BUY/SELL/order observations do not notify by themselves. Existing journal error suppression remains authoritative; this is event delivery, not a new error-detection engine.

Strategy payloads retain rule revision/name, job ID, algorithm/pair/interval, source/mode/environment/account label, classification and original journal action, status, reason, event ID/time and receipt time. Credentials, balances and complete job/order payloads are not copied. UI helpers render the mixed inbox and route strategy entries to their exact monitor. Read acknowledgments cover both kinds without deleting history. Broker has a native read-only `strategy_alerts` evidence tool; Technician's `settings_guide(section="alerts")` explains setup. Neither can create rules or change runs.

| Method | Path | Contract |
| --- | --- | --- |
| GET | `/strategy-alerts?include_archived=false&offset=0&job_id=...` | Optional exact-run filter; 50-row pages, global non-archived budget and category descriptions; local reads only |
| POST | `/strategy-alerts` | Exact saved `job_id`, `events: [attention/lifecycle]`, optional single-line label; returns 201, watching future events |
| POST | `/strategy-alerts/{id}/edit` | Full create configuration plus positive integer `revision`; saves paused, conflict 409 |
| POST | `/strategy-alerts/{id}/action` | `action: pause/arm/archive/restore`, reviewed `revision`; never a strategy control |
| GET | `/strategy-alerts/example` | Isolated sample rule/notification, no persistence |

Paths use `/api/v1`, existing workspace access controls and `Cache-Control: no-store`. Schemas reject unknown execution/delivery fields. This remains one local API worker, in-app delivery and retained journal catch-up, not a distributed scheduler, worker liveness alarm, order settlement guarantee or external notification system.

## Connection read subscriptions

`alerts/connections.py` owns the local watcher; `connection_conditions.py` contains deterministic per-operation streak/incident transitions. `Market.connection_alerts` shares the existing `ProviderHistory` recorder, without adding network probes. Its dedicated worker is independent of provider-backed price checks, and inspects at most 100 retained read events for one due rule per tick. Completed pages are due five seconds later; full pages are immediately eligible for catch-up. Lifecycle and worker writes serialize under `BEGIN IMMEDIATE`, atomically committing the cursor, incident state and inbox rows. Unique `(rule_id,cycle)` uses the global read-event ID. Two local consumers cannot duplicate a notification. This is still a one-process workspace, not distributed scheduling.

`market_data/read_events.py` appends a credential-free event in the **same bounded transaction** as hourly telemetry: source ID, provider/environment/kind, random process session/profile generation, whitelisted operation, per-stream sequence, observation time, safe error category and retired-profile flag. No URLs, keys, labels, request/response bodies or raw exceptions enter this journal. Sequence is assigned before commit, so contention loss/reordering is detectable. Streams are capped at 1,024 process-local counters; a random stream suffix on the session token changes after eviction, so the consumer restarts counts without waiting for an old sequence to catch up. Retention is a contiguous journal-ID suffix, up to 14 days/50,000 rows, with a durable pruning watermark. Best-effort 50 ms storage waits never replace provider results or cause retries.

Each rule pins a source, snapshots its safe display metadata and keeps per-operation counters/incident state, stream identity/sequence/time, continuity note, cursor, check/notification times and revision. Counters reset on stream/profile changes, sequence gaps/reordering, backward time, untrusted future timestamps or gaps over 300 seconds. Late retired completions are ignored. `request` errors break streaks without establishing or resolving incidents. Successful transports followed by logical adapter validation errors remain successful transports; domain validation remains separate. Existing incidents survive continuity resets, but recovery needs fresh successes of the same operation. Turning recovery notices off still clears an incident once confirmed so a later failure can notify.

Creation/resume establishes a fresh global journal-tail baseline and clears incidents/counts. Editing preserves ID/notifications, checks revision and saves paused. Pausing/archiving never changes a source/account, and restore leaves the rule paused. There is one non-archived rule per source and a separate 50-rule budget. A retained removed source can be watched, but no alert itself produces traffic. Idle sources, dropped observations and silent worker outages cannot be inferred as healthy or failed. Notification payloads use `kind: connection`, operation, action `failing/recovered`, source/environment, safe reason/category, thresholds/counts, original event ID/time and receipt time. Source settings links replace strategy-monitor links for this kind. Technician has a native read-only `connection_alerts` tool; it cannot save/evaluate watches.

| Method | Path | Contract |
| --- | --- | --- |
| GET | `/connection-alerts?include_archived=false&offset=0` | Local pages of 50, budgets, safe source choices and recording status; no provider calls |
| POST | `/connection-alerts` | `source`, optional strict `failures_required` (1–10, default 3), `successes_required` (1–5, default 2), `notify_recovery` (boolean, default true), `label` (single-line, max 80); returns 201 |
| POST | `/connection-alerts/{id}/edit` | Full create settings + positive integer `revision`; saves paused |
| POST | `/connection-alerts/{id}/action` | `action: pause/arm/archive/restore` + `revision`; stale editors return 409 |
| GET | `/connection-alerts/example` | Isolated illustrative rule/inbox; no writes or probes |

All paths use the `/api/v1` prefix, workspace authorization and `Cache-Control: no-store`. Unknown/Demo source IDs return 400; strict invalid/unknown body fields return 422. Shared notification acknowledgment/pagination supports all three kinds without deleting evidence.

`tests/test_connection_alerts.py` covers real local journal writes, operation isolation, thresholds and recurrence, request-error exclusions, credential/session/timing/recording continuity, retired profiles, partial telemetry, pruning, lifecycle/revision/budgets, restart recovery, atomic rollback, duplicate consumers, bounded backlog, HTTP contracts and the native Technician client tool. No private exchange or external delivery is used.

## Account risk subscriptions

`Portfolio.risk_alerts` evaluates fixed active-account sets with source-pinned complete fresh valuation. Value floors, concentration and observed-value drawdown, recovery/cooldown, revision-checked controls and bounded snapshots share the inbox with `kind: risk`. These are notification policies, separate from execution protection. See [contracts and concurrency boundaries](account-risk.md).
