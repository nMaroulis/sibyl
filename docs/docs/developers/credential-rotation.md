# Credential and wrapping-key rotation

Two operations serve different purposes. Settings → Exchanges → Saved accounts → Update keys replaces API credentials for the **same** remote account. Settings → Workspace → Credential vault rotates the local Fernet wrapping key across saved encrypted records. Neither operation revokes a token at an exchange, AI provider or messaging platform.

## Same-account API replacement

Deactivate the connection, enter a complete replacement credential set, confirm that it belongs to the same exchange account/wallet/environment, and type the displayed replacement phrase. The backend checks inactivity and the opaque encrypted-record revision inside one SQLite writer transaction. The provider-specific credential requirements are identical to initial setup. Demo has no keys.

The connection ID, label, environment and creation date remain fixed; imported fills/funding and strategy/order references are retained. The audit saves change dates and opaque revisions, never old or new API values. Saving contacts no provider and leaves the account inactive. Imports/funding/discovery are paused, cached clients are forgotten, and the UI clears its previous access check. Check access explicitly before reactivating and reviewing automatic controls. Existing venue orders/holdings remain at the venue and must be reviewed separately.

A generic exchange API cannot prove that replacement keys identify the same principal. The owner assertion is explicit. For a different account or subaccount, add a new connection instead of replacing keys. Previously admitted requests may finish; replacing a key is not order cancellation.

## Local vault rotation

`credentials/vault.py` owns complete owner-readable key files and cryptography's native MultiFernet. `credentials/rotation.py` owns explicit revision-bound re-encryption and the SQLite audit. A rotation authenticates and rewraps connection credentials, provider configurations, `data:*` encrypted settings and the saved default model, preserving native Fernet token timestamps. Plain settings, financial facts and chat history are unchanged.

The operation takes the vault lock and a SQLite writer. It atomically/fsyncs a separate `vault.previous.key`, rewraps rows, then atomically publishes the new `vault.key` **before releasing the database writer**. The old key remains until the SQL commit succeeds. If the process stops before or after key publication, startup loads current and recovery keys and can authenticate either database state. Complete rotation rewraps to the published key (or generates a new key if publication had not happened), commits its audit and then removes the recovery file.

Credential writes acquire SQLite admission before selecting the current wrapping key. This prevents a waiting Store instance from inserting an old-key token after rotation. Already-open in-process read snapshots can retain old decryptors until shutdown. Missing primary keys fail closed rather than silently generating a replacement for an existing database. Invalid encrypted records roll back the re-encryption; no record is dropped to force success. Symlink key files are rejected.

Online archive creation shares the vault lock, so its SQLite snapshot and included key files agree. A recovery key retained by an interrupted rotation is included inside archive encryption if present. Restores remain separate workspaces with automation quarantined. Existing archives retain their original matching keys; rotation cannot revoke downloaded backups or securely erase filesystem/memory history.

Encrypted-record fingerprints change on rewrapping even though provider values are unchanged. Source-bound funding update/recent-sync controls pause on that change and need fresh review/re-enabling. Shared strategy reference assessments must refresh; daily loss baselines are not reset. The operation does not bypass existing source/version guards.

## Private API and agent boundary

- `GET /api/v1/connections/{id}/credentials/status`: revision and actual replacement dates, no secret prefixes.
- `PUT /api/v1/connections/{id}/credentials`: complete write-only credentials, exact revision and owner confirmation.
- `GET /api/v1/workspace/vault`: opaque key ID, recovery status, encrypted-record counts and newest twenty audit entries.
- `POST /api/v1/workspace/vault/rotate`: exact key ID and typed rotation phrase.

Routes use workspace authentication/origin controls and no-store responses. Secrets and wrapping keys are never returned by these APIs. Technician explains the controls through its native settings guide; agents cannot replace API keys, invoke rotation, read key files or receive decrypted credentials.

Tests authenticate every encrypted column after reopening, preserve Fernet timestamps, reject stale/active edits, preserve account history, simulate interruption both sides of key publication, roll back invalid records, exercise competing Store writers and restore a post-rotation encrypted archive. No actual provider token is changed by these checks.
