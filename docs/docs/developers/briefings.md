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

Create/edit inputs: `frequency` (`daily`/`weekly`), `local_time` (`HH:MM`), `timezone`, `weekday` (Monday 0 through Sunday 6), `telegram`, `delivery_format` (`summary`/`full`) and `keep_reports` (5–40). Create accepts `enabled`; edit requires `revision`.

Telegram selection requires `telegram_target: {bot_id, user_id}`, matching the currently checked profile. The server captures that exact stable identity as the schedule binding. This prevents a settings change while the editor is open from silently authorizing a different recipient. A token rotation for the same checked bot/user is compatible with future occurrences. Legacy profiles need one **Check bot** to populate the stable bot ID.

Run-now requires a 32-character hexadecimal `request_id` and `revision`. Retained identical IDs return their previous occurrence without creating work, including after a pause. An ID belonging to another schedule conflicts. Input failures use 422, stale/missing setup or capacity constraints 409, unknown records 404. A valid schedule can be saved without an LLM; a due attempt records **blocked** if its accepted model configuration is unready.

Schedule detail returns the latest thirty occurrences, report availability and safe delivery metadata/part outcomes. Tokens and full queued message bodies are excluded. The native Sibyl `briefing_schedules` tool reads the same bounded calendars and receipts, excludes private recipient IDs, and provides setup instructions without mutation tools.

## App-origin Telegram outbox

`messaging/outbound.py` contains `NotificationOutbox`, separate from conversational replies. The existing direct-HTTP `TelegramClient` supplies transport. Queue insertion is idempotent by occurrence ID. A report is formatted from its saved structured answer without another model request.

`message_deliveries` records policy revision, bot/user binding, connection revision/control identity, report/version, a bounded preview and expiry. `message_delivery_parts` records plain text, order, attempts, next attempt, outcome and confirmed Telegram message ID. Private research text is local SQLite data, not encrypted message storage. Credentials remain in the existing vault.

Before claiming a part, the sender checks the armed policy revision, completed report availability, checked bot/user, enabled connection controls and one-hour expiry from the report's actual completion time. Parts use at most 4,000 UTF-16 units and preserve code points. Earlier unconfirmed parts block later parts.

- Telegram confirmation records the native message ID; only all-confirmed deliveries become **sent**.
- Explicit rate-limit rejections honor provider delay and allow at most five attempts within expiry.
- Unconfirmed writes, timeouts, 5xx failures and interrupted sends become **uncertain**, without automatic retry. Restart preserves confirmed earlier parts and blocks remaining parts.
- Authorization changes withdraw pending parts; already confirmed parts remain visible as a partial delivery.
- A paused/unverified or changed recipient at report completion produces a skipped receipt, not a backlog.

The existing messaging worker sends at most one outbound part per tick, after pending conversation replies, and observes its shared Telegram cooldown. Briefing counts are reported separately from conversational reply counts. This is at-most-once admission after an ambiguous outcome, not an exactly-once network-delivery guarantee.

## Bounds and retention

Workspace bounds: 50 non-archived calendars, one pending occurrence per calendar, the existing four pending investigations and two native outer AI requests, plus at most twenty pending app deliveries. Terminal calendar history retains about 200 recent records per schedule. Known-terminal delivery history retains 200 per schedule; unresolved uncertain receipts remain available.

Scheduled report retention removes only that calendar's oldest terminal report versions before reserving another. Manual reports and active work remain untouched. Version numbers remain monotonic after pruning. Generated conversations are removed only when they have exactly one request and one turn and are not active; any user continuation, including an unsuccessful attempt, preserves the conversation. Deletion removes the associated native history through the existing conversation owner. Total retained investigation runs remain capped at fifty.

Focused tests cover calendar/DST rules, concurrent claims, frozen queued models, capacity expiry, restart/missed behavior, recipient changes, retention, native specialist evidence, mock HTTP delivery, rate limits, uncertain writes and pause/shutdown boundaries. No test contacts a real bot or spends paid model calls.
