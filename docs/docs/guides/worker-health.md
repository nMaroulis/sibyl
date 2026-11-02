---
title: Background activity
description: See actual worker progress, failures and overdue work in Workspace settings.
---

# Background activity

Open **Settings → Workspace → Background activity** to inspect the workers behind strategies, imports, order maintenance, alerts, candle history, scheduled investigations, Telegram and research indexing.

Each worker shows its last start/finish, duration, completed iteration count and current state. Expand **Inspect supervised workers** for details. An app-wide notice links here when a worker needs attention, status cannot be refreshed, or a restored workspace is paused for review.

| State | Meaning |
| --- | --- |
| Starting / waiting | Registered work is starting or waiting for its next iteration. |
| Running | An actual iteration is in progress. |
| Retrying | A worker with an explicit storage-retry policy encountered a database error. |
| Failed | Unexpected failure stopped this worker. Review the relevant module before restarting Sibyl. |
| Stalled | An iteration exceeded its observation deadline. Its thread or provider operation may still be running. |
| Overdue | The next iteration has not started within its allowed delay. |
| Paused | A restored workspace has not completed recovery review. |
| Stopped | The supervised task ended or was cancelled. |

Fault and recovery transitions are retained across restart; counters and current progress belong to the current backend process. Error details show exception types, without credentials or raw provider responses.

These are observations of local work, not availability guarantees. A completed iteration may have found no due work, or the domain service may have recorded a provider error. Check the module's own evidence for provider access, native fills or confirmed Telegram delivery. An unresponsive backend cannot report its own health; the browser separately indicates unavailable or stale status.

Monitoring never cancels an overdue exchange operation, restarts a failed worker or repeats an uncertain write. Inspect **Trade**, strategy monitors and provider status before restarting. Existing domain reconciliation and idempotency controls still own execution recovery.
