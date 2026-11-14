# Durable local jobs

Settings → Workspace → Local jobs saves explicitly registered domain tasks. New jobs are paused by default. Run once accepts one immediate request without arming a schedule; Enable schedule opts into future work. Pause affects future scheduling. Cancel targets one exact run; Archive also cancels outstanding local interest. None can kill a Python thread or undo work already committed by a domain service.

## Implemented handlers

| Type | Inputs | Restart contract |
| --- | --- | --- |
| Workspace health | No arguments; bounded SQLite check and content-free process evidence | Safe interrupted read can retry |
| Retained account accounting | Account/environment, reporting unit and retained price source | Safe interrupted local calculation can retry |
| Pinned forecast training | Existing immutable daily dataset and a validated ridge/neural recipe | Explicit one-off only; interrupted fitting is not replayed |

A pinned training job fits its saved dataset. It does not fetch fresh prices, recalibrate an active forecast or replace a model automatically. A model committed before cancellation remains in the registry. Task results disclose the model ID. Accounting task results retain at most 100 asset rows per environment with full counts; the calculation uses the entire checked dependency set. General jobs never submit exchange orders or send messages.

## Scheduling and persistence

`operations/jobs` separates typed controls, private domain handlers and lifecycle. A handler declares its argument model, restart safety and repeatability. There are no Python import paths, shell commands, arbitrary URLs or credential fields in a job request. The registry is assembled in the app lifespan; adding an HTTP type cannot execute an unregistered function.

One local worker claims a FIFO run with a short `BEGIN IMMEDIATE`, executes outside SQLite, then conditionally saves only while that exact run is still running. Concurrent cancellation wins over a late success. Shutdown drains the owned thread through WorkerHealth. Unexpected process loss requeues declared safe reads from their frozen arguments; other runs become interrupted with an explicit review requirement. This is not distributed worker coordination.

Recurring jobs use fixed elapsed-second intervals (not civil daily/weekly calendars). Missed policy Skip advances to the first future interval; Once admits at most one catch-up, without a burst. A one-off more than 60 seconds late is skipped unless Once was selected. Exhausted means that its one-off schedule has no future occurrence, not that its run succeeded. A paused job can still be run once explicitly.

The workspace accepts at most 100 non-archived definitions, one active run per definition, arguments up to 16 KiB and results up to 256 KiB. The latest twenty run receipts per definition are retained. Separate submission tombstones preserve deduplication after receipt pruning: retrying an expired identity reports that it was already accepted and never starts it again. Native outcomes and sanitized exception type codes are saved; raw provider exceptions are not exposed. Restore quarantines queued/running work and pauses active schedules.

## HTTP and agent integration

- `GET/POST /api/v1/workspace/jobs`: inventory or validated definition creation.
- `POST /{id}/action`: revision-bound pause, resume or archive.
- `GET/POST /{id}/runs`: retained receipts or idempotent explicit admission.
- `GET /{id}/runs/{run_id}`: passive JSON inspection/export.
- `POST /{id}/runs/{run_id}/cancel`: cancellation of one exact run.

All routes use existing workspace authentication/origin checks and `Cache-Control: no-store`. Technician reads bounded schedule/run summaries through native `workspace_operations` and explains the controls through `settings_guide`; agents cannot create or cancel jobs. These domain jobs do not replace ProtoLink's native durable inference primitives.

Tests cover persistence, missed schedules, duplicate identities beyond receipt retention, revision races, cancellation while a handler is blocked, restart safety, sanitized errors, source-only task routing, read-only health results and restore quarantine.
