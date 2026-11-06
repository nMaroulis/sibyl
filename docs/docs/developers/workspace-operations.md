---
title: Workspace operations
description: Supervised workers, fault diagnostics, authenticated archives and non-destructive recovery.
---

# Workspace operations

`operations/health.py` owns actual periodic task supervision. `archives.py` owns encrypted snapshots and validation; `recovery.py` quarantines automatic work in a recovered copy. Domain services retain ownership of trading, messaging, provider reads and reconciliation.

## Worker lifecycle

The application registers its real background actions with `WorkerHealth`. Sync actions run in bounded application threads; async actions are awaited directly. Start/finish times and counts reflect actual iterations. A monotonic clock derives stalled/overdue states; it does not manufacture progress or cancel an overdue operation. The existing account/funding sequence and order lifecycle → reconciliation → discovery sequence remain intact.

Unexpected exceptions stop that worker and expose a sanitized exception type. Only selected workers retain an explicit SQLite-retry policy. Fault/recovery transitions persist in a bounded 200-event SQLite history; successful ticks stay in memory to avoid constant diagnostic writes. Shutdown cancels supervised tasks and drains tracked sync work before closing domain services.

`GET /api/v1/workspace/health` returns the current process's observations and recent transitions. Browser polling includes a separate stale-receipt indication. Technician's native read-only `workspace_operations` tool exposes the same evidence and setup guidance. Process liveness, successful iterations, provider readiness and confirmed native actions remain separate facts. This is not external uptime monitoring.

## Archive format and boundaries

The versioned binary format is `SIBYLBK1\n`, a random 16-byte salt, and authenticated Fernet ciphertext. Scrypt derives the archive key from the supplied passphrase with `n=2**15`, `r=8`, `p=1` and 32 output bytes. It is separate from the vault key; neither passphrase nor derived key is persisted. The encrypted payload contains ZIP members plus a format/version/date/file-size/SHA-256 manifest.

SQLite files are copied with SQLite's online backup API and closed explicitly for Windows portability. Filesystem symlinks and transient SQLite journals are excluded/rejected. Separate databases are individually consistent, without a global transaction. For an exact cross-database idle snapshot, stop the app and copy the workspace manually.

Authentication precedes ZIP parsing. Validation rejects excessive sizes/file counts, duplicate/noncanonical/absolute/traversal/device paths, symlinks, mismatched hashes, missing database/vault members and newer Sibyl versions. Restore validates SQLite integrity and copied vault credentials, then creates a unique directory under `.sibyl-managed/recovered`. Its failure removes only that incomplete output. The active workspace cannot be overwritten.

Archives are stored in a private `.sibyl-managed/backups` directory in the workspace volume, with owner-only files on POSIX. Windows uses the account/directory ACLs. Both the vault key and encrypted credentials are inside the passphrase-protected archive; losing the passphrase makes that archive unrecoverable. Environment files outside the workspace and external model installations are not captured.

## Recovery admission

Restored accounts are inactive. Running strategies and armed calendars are paused, pending inference is interrupted, Telegram is disabled and pending message delivery becomes uncertain. Native IDs and historical observations remain retained; they are not evidence of current venue state.

A copied encrypted `workspace-recovery` profile requires review. On startup, recovery mode disables both exchange-execution flags and registers workers as paused without starting them. Explicit review clears the saved requirement but does not start tasks in that process; restart is required. Module-specific account, strategy/calendar and Telegram controls remain explicit. This avoids treating old queued work as permission to replay side effects.

## HTTP controls

Under `/api/v1/workspace`: `GET /health`; `GET/POST /backups`; `POST /backups/upload`; `POST /backups/{id}/inspect`; `GET /backups/{id}/download`; `POST /backups/{id}/restore`; `DELETE /backups/{id}`; and `POST /recovery/complete`.

Passphrases use private request bodies and are never exposed to native agent tools. Uploads are bounded even without trustworthy Content-Length. Restore/recovery review require exact confirmation strings. All responses use `Cache-Control: no-store` and existing origin/bearer controls.

`tests/test_workspace_operations.py` verifies fault visibility without raw error leakage, actual-work deadlines, cancellation/draining, explicit retry history, archive authentication, unsafe path rejection, copied vault recovery, inactive accounts and paused startup. No test submits an exchange order or sends a message.

Managed backup/recovery directories include a local Git ignore rule. The source checkout also ignores default backup/recovery folders, encrypted archive files and vault keys. Keep runtime data out of source control; forced Git additions and copies outside these directories still need deliberate care.

The managed subtree is excluded from archive creation, including existing archives and recovered workspaces. Keeping it inside the writable data volume supports the non-root Docker image and preserves files across container replacement.

## Lightweight process resources

Workspace settings and `GET /workspace/health` include current Python API process CPU, RSS memory, thread count, database plus WAL bytes, free workspace-volume bytes and process uptime. `operations/resources.py` uses [psutil](https://psutil.readthedocs.io/) process counters, with a five-second snapshot cache and no separate sampler/history. CPU is the change in process user+system seconds divided by monotonic elapsed wall time; one busy CPU is 100%, so a multithreaded process can exceed 100%. The first observation has no CPU percentage.

The scope excludes Ollama, browsers, other processes and machine/external uptime. Unsupported/denied counters are explicitly unavailable; diagnostics never inspect command lines, environments or credentials. These observations do not establish provider readiness or order completion. Native Technician `workspace_operations` returns the same scoped evidence.
