# Persistent local alerts

`PriceAlerts` owns source-pinned one-shot rules and a local inbox. It uses the existing `Market` reference-data boundary and workspace SQLite database. It never invokes a trading, account-activation, agent or external-delivery tool.

## Persistence and evaluation

`price_alerts` stores rule ID, status, next-check time and JSON payload. Payloads include immutable source/pair/condition/threshold, source label/environment, lifecycle revision, cycle, observed price/provider time, failures and check/error evidence. `alert_notifications` stores immutable trigger evidence plus mutable read state, with a unique `(rule_id, cycle)` constraint.

Creation freezes the selected source and validates its exact spot catalog. It does not fetch a ticker. List/inbox/example reads never evaluate rules or make provider calls. The dedicated lifespan worker calls `tick()` once per second; one due rule is selected by next-check time/row order. It resumes persisted schedules after restart. Normal checks are due 30 seconds after evaluation. Failures back off exponentially from 60 seconds to a 900-second cap. A manual check shares the worker lock and honors cooldown/backoff; it is not a rate-limit bypass.

The quote read uses `Market.snapshot(rule.source)` and `valuation_ticker(rule.symbol)`, requesting no charts, private balances, orders or candles. Every evaluation revalidates exact catalog membership and requires a positive finite price and provider timestamp. Quotes older than five minutes, more than one minute in the future, undated or unavailable cannot trigger. Receipt time is never substituted. Provider errors are sanitized, and live failures never fall back to Demo.

The Demo client generates a synthetic snapshot timestamp at evaluation/cache load time; its fixed sample price still derives from the last closed fixture candle. Its historical OHLCV timestamps are unchanged. Demo remains explicitly attributed and must pass the same freshness checks as other rules. CoinGecko's Demo **API plan** remains a live API source and is not Sibyl's offline Demo.

A provider read happens outside the database transaction. The commit uses `BEGIN IMMEDIATE`, reloads the rule and checks armed status and revision. Pausing, archiving or rearming during an in-flight read invalidates that observation. When a condition matches (`>=` or `<=`), the triggered state and one inbox row commit together. A crash before commit leaves no notification; after commit the rule is terminal for that cycle. There is no external send to retry or transactional outbox claim.

Lifecycle actions advance revision. Arming an already armed rule is idempotent; resuming or rearming a paused/triggered rule starts a fresh cycle. Archive is reversible; restore leaves the rule paused. Notifications survive archive. Mark-read operations are idempotent and do not delete evidence. Unread/total counts cover all retained notifications independently of page size.

The service waits for an in-flight check during shutdown before closing shared market adapters. It assumes **one API worker**, matching the rest of this local workspace; distributed scheduling/claims remain deferred. Reads share existing transport/cache locks and can be delayed by other work. Creating/arming a rule does not wake or recreate missed historical prices.

## HTTP contract

Paths are relative to `/api/v1` and use existing workspace access controls. Mutable/private responses use `Cache-Control: no-store`.

| Method | Path                                      | Contract                                                                                                                |
| ------ | ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| GET    | `/alerts?include_archived=false&offset=0` | Rule pages of 50, total, offset and non-archived budget; no provider calls                                              |
| POST   | `/alerts`                                 | `source`, canonical `symbol`, `condition: above/below`, positive `threshold`, optional single-line `label`; returns 201 |
| POST   | `/alerts/{id}/action`                     | `action: pause/arm/archive/restore`                                                                                     |
| POST   | `/alerts/{id}/check`                      | Evaluate only if armed and due; otherwise return retained state                                                         |
| GET    | `/alerts/example`                         | Isolated illustrative rules and inbox; never persisted                                                                  |
| GET    | `/notifications?limit=20&offset=0`        | Paginated history (limit 1–100), total and unread counts                                                                |
| POST   | `/notifications/{id}/read`                | Mark one read, preserving original first-read time                                                                      |
| POST   | `/notifications/read-all`                 | Acknowledge current unread rows, without removing history                                                               |
| GET    | `/roadmap`                                | Audited implementation scope from `services/roadmap.py`; multi-user explicitly deferred                                 |

The API accepts no arbitrary destination, webhook, credential or trade field. Credentials stay in the existing encrypted source profiles. The rule payload and trigger evidence contain source identity and environment, never provider keys or raw transport errors.

## Current limits

Rules are immutable apart from lifecycle; changing pair/feed/level requires archive + new rule. Current rules are one-shot price thresholds, not recurring crossing, portfolio-risk, strategy or connection-health rules. Delivery is in-app only. Notification history is retained locally and paginated, without managed retention/export yet. No general-purpose durable job queue, external delivery retries, guarantee of timely delivery or multiple-worker coordination is claimed.

Tests use disposable stores, exact controlled feeds and API examples. They cover threshold equality, timestamp validation, cached-data aging, failures/backoff, source pinning, concurrency and delayed-response races, restart persistence, unread acknowledgment, pagination, archive/restore, capacity and absence of trading effects. See the [user guide](../guides/alerts.md).
