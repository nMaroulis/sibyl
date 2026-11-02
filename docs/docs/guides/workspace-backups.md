---
title: Workspace backup and recovery
description: Create authenticated encrypted archives and restore a separate workspace with automatic work paused.
---

# Workspace backup and recovery

Open **Settings → Workspace → Workspace backups** to create, download, import, inspect or restore local archives.

## Make a recoverable copy

1. Select **Create backup** and enter a new passphrase of at least twelve characters twice.
2. Wait for the snapshot and encryption to complete. The archive is saved under `.sibyl-managed/backups` inside the workspace volume.
3. Download an additional copy and keep it somewhere independent of this machine.
4. Use **Inspect / restore** to authenticate the archive with its passphrase. Inspection shows the Sibyl version, snapshot date, file count and unpacked size.

The archive contains the workspace's databases, research originals/text, local state and vault key **inside passphrase-protected encryption**. Keep the passphrase separately; Sibyl never stores it and cannot recover it. A downloaded archive alone does not expose the stored exchange credentials without its passphrase.

Environment files outside the data directory, installed Python/Node software and external model weights are not included. Each SQLite database is captured using its online backup API; separate databases can represent slightly different times. This is not a distributed transactional snapshot or a record of the exchange's state after that time.

## Restore without replacing the running workspace

1. Select a local archive, or use **Import an encrypted backup** for a downloaded copy.
2. Enter its passphrase and **Inspect archive**.
3. Type **RESTORE AS NEW WORKSPACE**, then restore.
4. Copy the recovered data-directory path shown in the result. Launch Sibyl with `--data-dir` pointing to that directory. Choose another `--port` if the current workspace remains open.

```bash
sibyl --data-dir "/path/to/recovered-directory" --port 8001 --open-browser
```

Restore creates a separate directory under `.sibyl-managed/recovered` and leaves the running workspace untouched. It authenticates the archive, verifies file hashes and SQLite integrity, rejects unsafe paths and newer-release archives, and checks the recovered credential vault. A failed restore removes its incomplete output.

## Review the recovered copy

The restored app starts in **recovery mode**:

- All automatic workers and exchange execution are paused.
- Exchange accounts start inactive.
- Running paper/exchange strategies and armed briefing calendars are paused.
- Telegram is disabled, queued inference is interrupted, and pending message sends are quarantined as uncertain.

Review actual orders and fills at their exchanges, retained strategy positions, calendars, message delivery and connection credentials. A backup cannot undo a trade or establish whether a message was delivered after the snapshot.

In the recovered app's Workspace settings, type **I REVIEWED THE RESTORED WORKSPACE** and complete the review. Restart Sibyl to start workers. Accounts, paused strategies/calendars and Telegram still require their own explicit activation/resume controls. Finishing review does not place orders, send messages or cancel existing exchange orders.

The local list retains at most twenty encrypted archives, with a 384 MiB archive/512 MiB unpacked limit and at most 1,000 files. Removing a local archive does not remove downloaded copies or recovered workspaces. For manual filesystem backups, stop Sibyl and copy the entire data directory, including all databases and `vault.key`.

Managed backup/recovery directories include a local Git ignore rule. The source checkout also ignores default backup/recovery folders, encrypted archive files and vault keys. Keep runtime data out of source control; forced Git additions and copies outside these directories still need deliberate care.

The managed subtree is excluded from archive creation, including existing archives and recovered workspaces. Keeping it inside the writable data volume supports the non-root Docker image and preserves files across container replacement.
