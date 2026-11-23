---
title: Alert delivery contracts
description: Six checked private routes, future-only policies, transactional cursors and conservative native outcomes.
---

# Alert delivery contracts

`alerts/delivery/` separates external selection from five rule evaluators: price, risk, strategy, connection and order/fill. Evaluators commit local evidence only. `AlertDelivery` admits explicitly selected future notices to the shared `messaging/outbound.py` queue. `messaging/delivery/` resolves the owning Telegram or private-channel native client without an LLM, send tool or new provider library.

## Consent and admission

One optional destination is stored per rule. Settings compare rule/policy revisions and the exact checked native identity. Telegram retains its typed bot/user target for existing clients. Other channels use `PrivateTarget`: channel, connection revision, bot/account ID, allowed recipient and checked native target ID. The server rejects arbitrary or stale destinations; it never probes a provider while saving a policy. A checked paused route can be selected, but notices admitted while paused are skipped.

Every save baselines the cursor at the current inbox tail. Enabling/resuming or changing destinations never forwards existing notices. A bounded one-second worker processes at most twenty notices from one policy. Vault access precedes SQLite write admission consistently with credential rotation, avoiding inverted lock ordering. An immediate SQLite transaction validates event/rule versions, original freshness and cooldown, inserts an idempotent `alert:<notification_id>` delivery and advances the policy cursor. Rollback consumes neither the notice nor its delivery identity. The application remains a single-worker local deployment.

Freshness uses the older aware observation/receipt time; missing, naive or over-60-second future dates are rejected. Expiry is 60–3,600 seconds (default 600). Cooldown is 60–86,400 seconds (default 300), measured from queue admission. Suppressed events retain skipped receipts rather than deferred messages. A triggered one-time price rule can deliver its own current event. Edits/lifecycle changes invalidate older event revisions; policy changes withdraw only the preceding policy’s unsent parts.

## Owned native routing

`NotificationOutbox` owns persistence, part ordering, expiry, uncertainty, history and review. `NotificationRoutes` owns checked identity projection, provider text limits and native client selection. The existing Telegram worker processes only Telegram rows; each private worker processes only its own rows under its existing client lock. A route cannot consume another route’s backlog. Conversation replies/accepted questions take priority, and a receive step follows at most four notification steps to prevent steady outbound traffic from starving inbound processing.

Before every part the sender rechecks domain authorization, channel, connection revision/control, bot/account, allowed recipient, target and expiry. Private asynchronous client setup has another identity/policy fence before the actual native send. Pause remains responsive; an already admitted request cannot be undone. After a confirmed part, changed consent withdraws the remainder.

Text uses the installed native clients’ limits, with code-point-safe UTF-16 chunking. Discord disables mentions; Slack disables markdown, link names and unfurls. Email uses one fixed SMTP recipient, `Sibyl notification` / `Auto-Submitted: auto-generated`, verified TLS and no incoming pairing phrase. WhatsApp requires the recipient’s authenticated private reply window at admission and send (24 hours minus 60 seconds); closed windows skip locally, without templates or delayed backfill. Documents remain Telegram-only, and scheduled research briefings use the same checked routes with acceptance-time control snapshots.

The queue is bounded to twenty pending app deliveries across routes. Only explicit nonambiguous 429/rate-limit rejections retry, at most five attempts, inside the original window. A private provider’s retry delay also holds its owning connection. Timeout, cancellation, unreadable/missing acceptance or interrupted send stays uncertain; later parts are blocked. Cancellation immediately retains uncertainty, and startup also reconciles interrupted sending rows without retrying them. None of these outcomes claims exactly-once provider delivery.

## Receipts and privacy

Messages contain retained trigger facts, actual source/date and Demo/test/paper labels, plus in-app navigation instructions rather than invented phone-accessible localhost URLs. Alert delivery does not imply an order/close happened and never changes financial permissions.

Telegram retains integer native message IDs. Other providers use a separate **TEXT `provider_id`** column, preserving Slack decimal timestamp IDs and email Message-IDs exactly rather than allowing SQLite numeric affinity to alter them. A new nullable column is added safely to existing part tables. Legacy deliveries without a `channel` remain Telegram. No queue bodies are rewritten.

History exposes channel, bounded preview and part outcomes. Explicit authenticated review exposes the queued text/target, unsent withdrawal and at most ten separate local-user acknowledgments. Review preserves native outcomes and never resends. Known-terminal receipts retain about 200 per rule; uncertain evidence remains protected. The local inbox and its unread/cursor retention guards remain independent. Credentials stay in encrypted profiles and never enter receipts, agent summaries or exported RunContext metadata. Native Technician evidence contains channel/outcome summaries, without private text or targets.

## HTTP API

All paths have the `/api/v1` prefix, normal workspace auth/origin controls and `Cache-Control: no-store`.

| Method | Path | Contract |
| --- | --- | --- |
| GET | `/alert-delivery/targets` | Checked private identity projections, paused state and WhatsApp window status; no probes |
| GET | `/alert-delivery/policies` | Enabled rule/channel indicators without recipient IDs |
| GET/POST | `/alert-delivery/{kind}/{rule_id}` | Current selection/history or revision-checked future-only consent |
| GET | `/alert-delivery/history` | Paged safe receipts, optionally one rule |
| GET | `/message-deliveries` | Paged alert/briefing outcomes across routes, or Telegram conversation replies |
| GET | `/message-deliveries/{id}` | Exact queued-text/target review and optimistic evidence token |
| POST | `/message-deliveries/{id}/review` | Withdraw/received/dismissed decisions, never resend |

Existing `/settings/messaging/telegram/deliveries/{id}` review paths remain compatible; new UI uses the provider-neutral route.

## Verification and remaining work

Offline checks exercise real native identity/send serializers for all five added routes, standard-library SMTP/TLS with controlled servers, exact IDs, future-only opt-in, channel switching, route isolation, stale/replaced recipients, WhatsApp window expiry, Unicode chunks, rate-limit rejection, pause/client-setup races, cancellation, uncertain restart/manual review, worker fairness and private HTTP APIs. Existing Telegram alert/briefing/review tests remain required. These are controlled provider fixtures, not live service acceptance.

Media beyond Telegram, generic outbound webhooks/native push and deployment-specific live delivery acceptance remain in the general checklist.
