# Global strategy submission halt

`strategies/execution/controls.py` owns a durable, single-workspace halt for **new automatic signal orders**. It is independent of provider availability and does not change backend environment flags. This remains a local, single-worker application; cross-worker coordination is pending.

## State and transactions

`strategy_execution_control` stores one row with `halted`, monotonic `revision`, `changed_at` and an optional note. The initial latch is released; both server flags still default to disabled. `strategy_control_events` retains the newest 200 actual transitions; the passive state response includes the latest 20 and current exchange-run counts. Same-state requests at the current revision make no event or revision change. A stale revision returns HTTP 409.

Halt acquires the existing strategy lifecycle lock and uses one SQLite write transaction to:

1. Increment the control generation and set the persistent latch.
2. Pause every currently running exchange job, across production/test accounts, recording a normal `PAUSE` journal event with `control_revision` and a retained `halt_revision` on the job.
3. Mark prepared, unsubmitted automatic signal intents abandoned, without granting new cancellation authority.
4. Commit the control audit, including the exact paused job IDs/count.

Database failure rolls back the whole transition. The halt makes no provider request itself, but obtaining the lifecycle lock can wait for an existing provider operation. An already admitted native submission can finish before the halt returns. A queued or timed-out browser request is **not** confirmation that the halt committed; read current control state.

## Admission checks

Preview, Start, Resume and worker evaluation check the latch before provider-backed work. Start reviews retain the current `control_revision`; a halt/release cycle invalidates unused reviews, including pre-feature reviews at generation zero. Existing Start confirmations remain idempotent reads of an already created job and cannot restart it.

The worker also pins its observation generation. It checks that generation after the unlocked market read, and attaches it to the prepared signal intent as `strategy_control_revision`. Inside the shared order pipeline's `BEGIN IMMEDIATE` submission transaction, automatic signal intents recheck the latch/generation, server strategy permission, current job status and abandoned-plan marker before entering `submitting`. Thus a caller with an internal strategy owner ID cannot bypass the latch. The normal runner serializes this boundary with halt using the lifecycle lock. Native writes already admitted at that boundary are not recalled or retried.

Release requires the displayed revision and exact `RELEASE STRATEGY HALT` confirmation. It increments the generation, retains an audit event and resumes **no** jobs. Individual Resume still performs the usual access, native accounting, pending-order, loss-latch and fresh-candle checks. Release cannot override disabled server flags or revive an old intent/review.

## Scope

| Operation | While halted |
| --- | --- |
| Automatic strategy entries and signal-based exits, new Start reviews, Start and Resume | Blocked |
| Existing native orders and late fill/fee imports | Remain live / continue tracking |
| Previously approved local order expiry | Continues with its existing account and two-flag requirements |
| Separately approved Stop & cancel and manual cancellation | Available with existing permissions |
| Separately reviewed Close position sell | Available with its existing ownership/evidence checks and live-order flag |
| Manual Trade orders | Existing per-order approval and permissions apply |
| Paper jobs and historical research | Unaffected |

The halt is neither an exchange-wide order-writing ban nor liquidation. Separate [portfolio strategy limits](portfolio-limits.md) now implement shared capital/exposure and observed UTC daily-loss policies for each funds environment. Automatic multi-order liquidation and broader authenticated venue acceptance remain pending. Ordinary account-risk alerts are notifications and never activate the halt.

## HTTP and agent contracts

`GET /api/v1/strategies/exchange/controls` is local-only and provider-free. `POST` at the same path accepts `{ "action": "halt" | "release", "revision": 0, "reason": "optional note", "confirmation": "required phrase for release" }`. Revision is a strict nonnegative integer, notes are limited to 240 characters, and unknown fields are rejected. Success/conflict responses use `Cache-Control: no-store`; the existing workspace token/origin checks apply.

`GET /strategies/exchange/options` distinguishes `server_enabled` (both flags) from `enabled` (flags plus released latch), and includes the control state. Broker's native ProtoLink `execution_controls` tool reads state/history without mutating it or probing providers. No agent has a halt/release tool.

Tests in `tests/test_strategy_controls.py` exercise rollback, revision conflicts, invalidated reviews, restart, a halt during provider work, the native-write race, retained partial fills, expiry/Stop & cancel/Close position, manual/paper isolation, HTTP access controls, audit retention and native ProtoLink tool access.
