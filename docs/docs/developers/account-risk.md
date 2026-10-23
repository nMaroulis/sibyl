# Account risk monitoring

`alerts/risk/` contains the complete opt-in workflow: validated contracts, a bounded spot-valuation reader, deterministic conditions, SQLite sample/rule persistence, worker/lifecycle service and an isolated example. `Portfolio.risk_alerts` owns the service; a dedicated background loop uses existing provider admission in the background lane. Other local journal alerts remain independent of these private network reads.

## Data and freshness boundaries

`RiskObservations` validates an exact sorted set of at most ten active account IDs and a single pricing source. It rejects mixed Demo/test/production funds and Demo/reference mismatches. It reads total spot balances through typed adapters, validating all quantities instead of silently dropping invalid entries. Empty valid spot maps are zero holdings. More than 100 positive combined assets is an explicit coverage error.

It reuses `Valuation` for exact direct/inverse/bridge conversions, observed stablecoin/fiat rates and existing 80-quote/12-second conversion budgets. No chart history, return calculation, account snapshot series or private write is requested. All positive holdings require `fresh` or USDT `identity` pricing. The reader rechecks original quote times at commit, rejecting ages over 300 seconds or more than 60 seconds ahead. Balance receipts and complete assembly must fit a 45-second quality window, with a 1 ms rounding tolerance. Existing individual transport timeouts remain in force; the assembly budget cannot preempt a running SDK read.

Safe samples contain account descriptors, funds/pricing environments, per-asset reference values/allocations/paths, oldest quote times, balance receipt times, assembly times and original metric/limit policy. Credentials, raw provider errors and private configuration guards never enter API/agent evidence. A successful provider response does not prove complete exchange wealth; scope remains each typed adapter's supported spot wallet.

## Configuration and commit races

Configuration is resolved outside write transactions. An in-memory guard captures encrypted market-profile and selected-account configuration snapshots plus activation metadata, including a connected pricing source if applicable. The guard never decrypts credentials or serializes them. At commit, SQLite compares those records directly under `BEGIN IMMEDIATE`; no Settings/Market Python lock or network read is acquired under the database writer. This avoids a Settings-save/database lock inversion and rejects account activation/removal, credential/profile or pricing configuration changes during a read. A default-feed save can conservatively invalidate one in-flight attempt, but cannot change the rule's pinned source.

Provider reads happen outside the transaction. Commit reloads the rule and verifies armed status, configuration revision and an optimistic check counter before accepting a sample. Lifecycle edits invalidate late responses. Concurrent consumers cannot overwrite a newer committed check or duplicate its notice. Original sample timestamps must advance. Values, peaks, incident/cooldown state, the new sample and any inbox row commit atomically; a failure before commit rolls everything back. This remains a single-process workspace, not distributed scheduling or a guaranteed alarm service.

## Conditions and state

- `value_floor`: inclusive total ≤ limit; recovery ≥ its higher reset value.
- `concentration`: selected asset / complete total × 100; inclusive weight ≥ limit, recovery ≤ lower reset value. Missing asset means zero; zero total means no percentage assessment.
- `drawdown`: `(observed_peak − total) / observed_peak × 100`, bounded to 0–100; inclusive ≥ limit, recovery ≤ lower reset value. First positive complete sample establishes the peak. It includes cash movements and is not investment return.

`conditions.py` owns peak and incident transitions without I/O. One breach notice is emitted per incident. A configurable 60–86,400-second cooldown applies between breach notices. A new incident during cooldown needs another fresh qualifying sample after expiry; its stored old value cannot notify. Recovery notices require that incident's breach notice to have been emitted. Turning recovery notices off still clears the incident. Incomplete/failed samples never update conditions or retained complete evidence. Resume resets the peak/window; process restart retains it.

A complete check schedules the next read 60 seconds later. Provider failures use bounded exponential backoff (60 to 900 seconds). Admission deferrals preserve the failure count and use their reported retry delay. A manual check cannot bypass scheduling. The dedicated worker retries transient SQLite storage failures without pretending a check was committed. At most one due fixed account set is evaluated per worker tick, with independent local inbox workers. Twenty-five non-archived risk rules are allowed; new connections never expand a saved set.

## Persistence and evidence

`risk_alerts` indexes status/next-check and stores a versioned configuration/state JSON document. `risk_samples` indexes rule/revision/ID and stores complete valuation snapshots. Each successful check prunes samples to 120 per rule, 14 days and a global suffix capped at 2,000 sample IDs. Startup also prunes aged samples. Local evidence reads exclude expired details without deleting records; physical pruning happens at startup/complete checks. Archived rules and their notifications are not deleted; the shared notification inbox keeps its existing retention policy. Sample history is observational, without backfill/interpolation or cash-flow adjustment.

Risk inbox payloads use `kind: risk`, action `breached/recovered`, rule revision/cycle, original metric/asset/limits, total/metric value/USDT denomination, account descriptors, funds/pricing environments, source attribution, observed peak/time and sample ID/time. Receipt time and unread acknowledgment use the shared repository. Unique `(rule_id,cycle)` and atomic state/inbox writes prevent duplicate notices. Opening a notification follows its exact retained sample. Evidence from an older revision uses that sample's original policy, not current rule labels/limits. Pruned details return `sample: null` while the notice retains its original summary.

Accountant has a native ProtoLink `risk_alerts(rule_id="")` evidence tool. Technician's alerts guide explains setup. Agents cannot create/check rules, change limits, activate accounts, read balances through the evidence tool or control execution.

## HTTP contracts

All paths have prefix `/api/v1`, workspace token/origin controls and `Cache-Control: no-store`.

| Method | Path | Contract |
| --- | --- | --- |
| GET | `/risk-alerts?include_archived=false&offset=0` | Local pages of 50, non-archived budget and scheduling metadata; no balance/quote reads |
| POST | `/risk-alerts` | Fixed `account_ids` (1–10 unique saved IDs), `source`, `metric: value_floor/concentration/drawdown`, positive finite `threshold`; optional `reset_threshold`, `asset`, `cooldown_seconds`, `notify_recovery`, `label`; returns 201 |
| POST | `/risk-alerts/{id}/edit` | Full create configuration + strict positive integer `revision`; preserves history, saves paused |
| POST | `/risk-alerts/{id}/action` | `action: pause/arm/archive/restore` + `revision`; stale editors return 409 |
| POST | `/risk-alerts/{id}/check` | Read only if armed and due; respect backoff/budgets |
| GET | `/risk-alerts/{id}/evidence?sample_id=123` | Local complete snapshots from that rule/revision; no provider calls |
| GET | `/risk-alerts/example` | Separate illustrative rule/inbox/evidence; no activation or persistence |

Thresholds/recovery values are strict JSON numbers, excluding booleans/non-finite values. Percentage limits are `(0,100]`. Value floors are `(0,10¹⁵]` USDT; recovery values must be higher. Concentration requires a canonical uppercase asset ID (max 24 characters); other metrics reject an asset. Percentage recovery is lower and nonnegative. Defaults: value floor × 1.01 or percentage limit minus one percentage point (minimum zero); cooldown 300 seconds; recovery notices enabled. Unknown fields are rejected (422); unavailable setup returns 400; missing rules 404; stale revisions 409. A same-account/source edit can save paused while access is unavailable, without claiming a new successful assessment.

`tests/test_risk_alerts.py` covers native-shaped valuation, source pinning, fixed groups/environments, stablecoin/inverse routes, quality gates, observed peaks/zero values, cooldown/recovery behavior, in-flight lifecycle/configuration/age races, rollback, duplicate consumers, local-only evidence, retention/revisions, HTTP validation, token access and native Accountant client tools. No actual exchange order or external message is sent.
