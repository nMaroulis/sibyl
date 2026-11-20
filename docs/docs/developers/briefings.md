---
title: Briefing schedules and delivery
description: Calendar admission, private model snapshots, retention and conservative Telegram outcomes.
---

# Briefing schedules and delivery

`investigations/scheduling/` owns daily/weekly calendars, occurrence admission and the explicit Telegram handoff. It reuses `Investigations.start` and the existing native ProtoLink `AgentGroup` run, request-local factories, registry delegation, evidence and session persistence. It introduces no parallel agent runtime or inference replay engine.

## Boundaries and lifecycle

`calendar.py` uses `zoneinfo`, with packaged `tzdata` available on Windows/minimal systems. It computes the next strictly future UTC occurrence from an IANA zone. Nonexistent wall times are skipped; ambiguous times use the first fold only.

`BriefingRepository` persists `briefing_schedules` and `briefing_occurrences`. Short `BEGIN IMMEDIATE` transactions serialize calendar edits and claims. Unique indexes enforce one non-archived schedule per investigation, one pending occurrence per schedule and one calendar occurrence per `(schedule_id, scheduled_for)`. Revisions fence stale controls. The local deployment still requires one API worker; the database checks do not turn it into a distributed scheduler.

The app checks calendars every two seconds. A due occurrence is admitted only within fifteen minutes. Report-capacity conflicts retry admission every five seconds inside that window. Late dates are summarized as missed and the calendar advances into the future. Startup skips overdue dates, reconnects occurrences to already persisted report IDs and interrupts unaccepted work. It never reconstructs private configuration to replay inference.

When an occurrence enters the waiting queue, `BriefingScheduler` freezes the entire team's model configuration in a private in-memory mapping. It forwards that same configuration through the existing native request context when a report slot becomes available. Credentials are not serialized in calendar payloads, report metadata or tool results. Saving calendars is lazy and never contacts a model or Telegram.

Pause/edit/archive cancels waiting occurrences and withdraws unsent notifications. Report admission is the boundary after which the existing investigation owns cancellation. Connection and schedule authorization are checked again for every Telegram send admission; a write already in flight may finish.

## API

All paths use `/api/v1`, the normal workspace authentication/origin controls and `Cache-Control: no-store`.

| Method | Path | Purpose |
| --- | --- | --- |
| GET, POST | `/investigations/{id}/schedules` | Read calendars or create one; GET accepts `archived=true` |
| GET | `/briefing-schedules/status` | Last local tick and explicit timing/history bounds |
| GET, POST | `/briefing-schedules/{id}` | Read schedule/history or edit a checked revision |
| POST | `/briefing-schedules/{id}/actions` | `pause`, `resume` or `archive` with `revision` |
| POST | `/briefing-schedules/{id}/run-now` | Extra occurrence, HTTP 202; regular next time unchanged |

Create/edit inputs: `frequency` (`daily`/`weekly`), `local_time` (`HH:MM`), `timezone`, `weekday` (Monday 0 through Sunday 6), nullable `channel`, `message_format` (`text`/`document`), `delivery_format` (`summary`/`full`) and `keep_reports` (5–40). Create accepts `enabled`; edit requires `revision`. `GET /api/v1/message-deliveries/targets` reads checked destination projections without probing providers. Non-Telegram consent supplies its exact `private_target` (channel, revision, bot/account, recipient and native target IDs); Telegram supplies `telegram_target`. Documents are Telegram-only. Existing `telegram`/`telegram_format` inputs and stored calendars normalize at the boundary; contradictory selections/formats are rejected, never silently reinterpreted.

Telegram selection requires `telegram_target: {bot_id, user_id}`, matching the currently checked profile. The server captures that exact stable identity as the schedule binding. This prevents a settings change while the editor is open from silently authorizing a different recipient. A token rotation for the same checked bot/user is compatible with future occurrences. Legacy profiles need one **Check bot** to populate the stable bot ID.

Run-now requires a 32-character hexadecimal `request_id` and `revision`. Retained identical IDs return their previous occurrence without creating work, including after a pause. An ID belonging to another schedule conflicts. Input failures use 422, stale/missing setup or capacity constraints 409, unknown records 404. A valid schedule can be saved without an LLM; a due attempt records **blocked** if its accepted model configuration is unready.

Schedule detail returns canonical fields and the latest thirty occurrences, report availability and safe delivery metadata/part outcomes. Tokens, full queued message bodies and acceptance-time control snapshots are excluded. Native agent projections additionally omit every recipient binding and private target. The native Sibyl `briefing_schedules` tool reads the same bounded calendars and receipts, excludes private recipient IDs, and provides setup instructions without mutation tools.

## App-origin private outbox {#app-origin-telegram-outbox}

`messaging/outbound.py` contains `NotificationOutbox`, separate from conversational replies. The shared `NotificationRoutes` adapter reuses the owned Telegram/Discord/Slack/Signal/WhatsApp/email clients under their existing worker locks. Queue insertion is idempotent by occurrence ID. A report is formatted from its saved structured answer without another model request.

`message_deliveries` records policy revision, bot/user binding, connection revision/control identity, report/version, a bounded preview and expiry. `message_delivery_parts` records plain text, order, attempts, next attempt, outcome and confirmed Telegram integer IDs or exact private-provider TEXT IDs (including Slack timestamps and SMTP Message-IDs). Private research text is local SQLite data, not encrypted message storage. Credentials remain in the existing vault.

Before claiming a part, the sender checks the armed policy revision, completed report availability, checked bot/user, enabled connection controls and one-hour expiry from the report's actual completion time. Parts use the selected native client’s UTF-16 unit limit and preserve code points. Text messages are supported across six channels; document output remains Telegram-only. Earlier unconfirmed parts block later parts.

- Provider confirmation records the native acceptance ID; only all-confirmed deliveries become **sent**.
- Explicit rate-limit rejections honor provider delay and allow at most five attempts within expiry.
- Unconfirmed writes, timeouts, 5xx failures and interrupted sends become **uncertain**, without automatic retry. Restart preserves confirmed earlier parts and blocks remaining parts.
- Authorization changes withdraw pending parts; already confirmed parts remain visible as a partial delivery.
- A paused/unverified route or closed WhatsApp window at acceptance produces a skipped receipt, not a backlog. Connection revision/control changes after acceptance also skip the report, even after a later resume. WhatsApp windows are checked again before sending.

The existing messaging worker sends at most one outbound part per tick, after pending conversation replies, and observes its shared Telegram cooldown. Briefing counts are reported separately from conversational reply counts. This is at-most-once admission after an ambiguous outcome, not an exactly-once network-delivery guarantee.

## Bounds and retention

Workspace bounds: 50 non-archived calendars, one pending occurrence per calendar, the existing four pending investigations and two native outer AI requests, plus at most twenty pending app deliveries. Terminal calendar history retains about 200 recent records per schedule. Known-terminal delivery history retains 200 per schedule; unresolved uncertain receipts remain available.

Scheduled report retention removes only that calendar's oldest terminal report versions before reserving another. Manual reports and active work remain untouched. Version numbers remain monotonic after pruning. Generated conversations are removed only when they have exactly one request and one turn and are not active; any user continuation, including an unsuccessful attempt, preserves the conversation. Deletion removes the associated native history through the existing conversation owner. Total retained investigation runs remain capped at fifty.

Focused tests cover calendar/DST rules, concurrent claims, frozen queued models, capacity expiry, restart/missed behavior, recipient changes, retention, native specialist evidence, mock HTTP delivery, rate limits, uncertain writes and pause/shutdown boundaries. No test contacts a real bot or spends paid model calls.

## Telegram document output

`telegram_format: text|document` is independent of existing `delivery_format: summary|full`; defaults preserve ordinary messages. Document rendering bypasses text-message shortening and queues one complete protected `.txt` upload, bounded to 65,536 UTF-8 bytes. Oversized content produces a local skipped receipt, with no truncated attachment. `messaging/documents.py` validates backend-generated basenames and upgrades both outboxes with `format`/`filename` columns, leaving legacy parts as text.

`TelegramClient.send_document` uses [Telegram's native sendDocument](https://core.telegram.org/bots/api#senddocument) with HTTPX multipart bytes, never local paths or model-supplied URLs. It shares sanitized response classification with ordinary messages. Bot/private-target/revision/policy/expiry checks, at-most-once admission, explicit-429-only retries, restart uncertainty and manual unsent withdrawal remain unchanged. Conversation replies snapshot the opt-in document flag at acceptance and use the same reply receipt contract. No Telegram SDK or incoming-media client is introduced.

## Acceptance-time route consent

A queued occurrence stores only an opaque route snapshot: selected channel, connection revision/control IDs and whether it was eligible then. Credentials stay in encrypted profiles and the team’s accepted model configuration stays in the private scheduler cache/native request context. This snapshot is not passed to model-facing tools or serialized RunContext metadata. The native investigation execution path is unchanged.

The sender requires the accepted controls to remain current at report completion and checks current domain/connection authorization before each part. Current profile state cannot retroactively authorize an older paused/unverified acceptance. A legacy running occurrence without a recorded acceptance snapshot remains local rather than inventing consent. Existing Telegram calendars are read with canonical defaults; no bulk history rewrite occurs.

Schedule edits/actions withdraw only older schedule revisions and drop only their waiting model snapshots. A new-revision occurrence admitted between the calendar commit and withdrawal retains its consent/cache. Source/report availability and policy revisions still fence every native write. Vault access precedes SQLite write admission on credential-reading save paths.

The enqueue/occurrence-update boundary is crash-safe through the existing occurrence-derived idempotency key: restart reconnects the saved native report and observes the existing delivery without replaying a model run or native send. Missed periods, model snapshot privacy and report-retention rules stay separate from delivery.

## Verification

Offline native end-to-end cases generate actual ProtoLink investigation reports and deliver through all five added clients using controlled HTTP/TLS SMTP responses. They cover exact provider IDs, missing/stale/conflicting consent, paused/replaced and in-progress connection generations, WhatsApp windows, schedule revision withdrawal races, post-commit handoff recovery and agent/API privacy. Existing Telegram calendar, document and model-snapshot tests remain required. These fixtures do not establish live external-service acceptance.
