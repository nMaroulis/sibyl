---
title: Alert delivery contracts
description: Future-only Telegram opt-in, transactional inbox cursors and send authorization.
---

# Alert delivery contracts

`alerts/delivery/` separates external notification selection from the four alert evaluators. Its typed settings, plain-text formatting and `AlertDelivery` coordinator use the existing shared inbox and `messaging/outbound.py` queue. No model, new Telegram library or provider refresh is involved. Trigger evaluators still commit only local evidence.

## Admission

`alert_delivery_policies` stores one optional policy per saved rule: kind, enabled flag, revision, exact bot/user binding, minimum interval, expiry window, inbox row cursor and last queued time. The table map is fixed to price/risk/strategy/connection rules. API writes compare both the reviewed policy revision and rule revision. Enabling requires an explicit `TelegramTarget` matching the checked profile; saves never call Telegram.

Every save baselines the cursor at the current global inbox tail. Enabling or resuming cannot send existing notices. A one-second worker admits up to twenty new notices from one policy with pending rows, using a thread so SQLite contention does not block the API event loop. Shutdown drains an admitted transaction before closing messaging. Within one `BEGIN IMMEDIATE` transaction it verifies the current rule revision/state, observation/receipt freshness and cooldown, inserts an idempotent `alert:<notification_id>` outbox record and advances the policy cursor. Rollback leaves neither an orphan send nor a consumed notice. Concurrent consumers cannot insert duplicates; deployment still requires one API worker.

Freshness uses the older of aware `observed_at` and `created_at`; missing, naive or more than sixty seconds future timestamps are rejected. Expiry defaults to ten minutes, configurable 60–3,600 seconds. Cooldown defaults to five minutes, configurable 60–86,400 seconds, measured from queue admission rather than successful HTTP delivery. Suppressed notices receive skipped receipts, not deferred sends. Failed or uncertain attempts cannot generate a later cooldown bypass.

In-app unread state is independent. Policy pause withdraws old queued messages; later enabling starts at a fresh tail. Rule edits/lifecycle actions invalidate older queued event revisions. A one-time price rule in `triggered` state remains eligible for its current notice. Delivery selection continues for future edited rule revisions; the UI discloses that scope.

## Shared transport

`NotificationOutbox.enqueue_message` accepts domain metadata, reviewed binding, expiry and optional caller transaction. The briefing `enqueue` entry point remains a small adapter. Domain authorizers are registered under `briefing` or `alert`; legacy records without a kind retain briefing semantics. Unknown domains fail closed. Conversation replies keep their original separate queue. Queued chat replies and accepted questions take priority, and a zero-wait incoming poll follows every four app-notification steps so an outbound burst cannot starve incoming messages.

Every part rechecks current policy revision, event availability, rule revision/state, bot/user binding, connection revision/control and expiry before send admission. Policy changes withdraw the preceding policy revision’s unsent messages, preserving a concurrently admitted new revision. In-flight HTTP cannot be undone; confirmed parts are retained. The shared queue permits twenty pending app deliveries and uses Telegram’s existing cooldown. Only explicit 429 rejections retry, up to five attempts; ambiguous writes are never replayed. See [briefing transport contracts](briefings.md#app-origin-telegram-outbox).

Messages use retained trigger facts with source, original dates and Demo/test/paper attribution, and a navigation path rather than an invented phone-accessible localhost URL. Account-value drawdowns retain their cash-movement limitation. No message implies execution or a verified position close. The sender uses protected plain text and bounded UTF-16 parts.

Known-terminal receipts retain about 200 per rule; unresolved uncertain receipts are preserved. Queue bodies are local plaintext, while credentials stay in the vault. Read APIs return bounded previews and part outcomes, not full bodies or tokens. Chat replies, briefings and alerts have separate counters.

## HTTP API

Paths use `/api/v1`, normal workspace authentication/origin checks and `Cache-Control: no-store`.

| Method | Path | Contract |
| --- | --- | --- |
| GET | `/alert-delivery/policies` | Up to 200 active opt-in indicators; no private recipient IDs |
| GET | `/alert-delivery/history` | Safe receipts, optional `rule_id`, limit 1–50, bounded offset |
| GET | `/alert-delivery/{kind}/{id}` | Policy, live rule revision/status and latest twenty receipts |
| POST | `/alert-delivery/{kind}/{id}` | Reviewed `revision`, `rule_revision`, `enabled`, optional checked `telegram_target`, cooldown and expiry seconds |

Kinds: `price`, `risk`, `strategy`, `connection`. Unknown kinds and invalid fields return 422, missing rules 404, stale editors/mismatched or unverified recipients 409. A paused Telegram connection may be selected; future admission while paused records skips. An archived rule cannot newly enable delivery. Native Technician page help explains the same controls without gaining mutation or messaging tools.

Tests use real Demo price/risk transitions, strategy journals and connection read incidents, with mocked Telegram HTTP. They exercise future-only baselines, concurrency, atomic rollback, cooldown, stale/future observations, pause/revision/recipient fences, uncertain sends, shared outbox compatibility and HTTP/privacy contracts. Live external delivery remains a deployment acceptance check.
