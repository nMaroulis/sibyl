# Observed balance comparisons

`accounting/balance_checks/` owns account-level quantity checks separately from exchange adapters, FIFO cost basis and trading controls. `service.py` coordinates explicit reads, `journal.py` retains checkpoints/reports, `movements.py` performs Decimal arithmetic and `contracts.py` defines revision controls and limits.

## Evidence and timing

A checkpoint freezes normalized total balances, a local observation window and the then-retained fills/funding records. A comparison reads a fresh strict balance snapshot, then reads the ledgers in one SQLite snapshot. The comparison applies newly imported records dated strictly after the starting window plus one second and before the current window minus one second. It does not replay pre-checkpoint history into opening balances. Corrections/removals, pre-checkpoint backfills and overlapping activity leave affected quantities unresolved. Both old and new fee assets stay affected when a historical correction changes the fee currency.

Buy fills credit base and debit reported quote notional; sells do the reverse. Signed native fees are subtracted in their actual asset, including rebates and third assets. Arithmetic uses a fifty-digit Decimal context. Comparison tolerance per asset is `max(1e-12, max(abs(expected), abs(observed)) * 1e-10)` over the already normalized JSON quantities. This does not recover precision lost in an upstream float.

Funding applies resolved configured-wallet effects: documented Kraken ledger arithmetic, explicit zero fees, or a current local wallet/amount review. Provider rules and user assertions keep distinct provenance. See [funding effects](funding-effects.md). Posting time, rather than creation time, controls the interval; missing posting times stay unresolved. Pending and uncertain movements remain unresolved. Missing imports and unknown fee assets can make all expected quantities unknown. Every report sets `coverage_complete: false` and `settlement_final: false`, even for an observed arithmetic match.

`ExchangeClient.fetch_balance_snapshot()` is an explicit read. The CCXT implementation preserves unknown amounts for rejection instead of dropping them, strips raw metadata and uses the configured provider wallet. It shares read admission, retry/cooldown handling, client leases and sanitized provider health. The comparison bypasses the account display cache, performs no pricing requests and rejects invalid, negative, oversized or excessively slow observations.

A provider timestamp is only an update-time hint: for example, CCXT maps Binance's `updateTime` into its balance timestamp, which can predate a fresh read. Old update hints do not make a current request stale. Invalid/future hints are rejected; comparison boundaries use the local request window. This is not independent verification of the venue's internal data age.

## Local lifecycle

One checkpoint and twenty reports are retained per account. History lists contain summaries; a separate endpoint loads one report. Saved GETs make no provider call. State does not expose the checkpoint's ledger snapshot or its private fingerprint. The fingerprint binds encrypted credentials, provider/environment, wallet parameters, SDK version and comparison format; no credential is decrypted for fingerprinting or returned in agent evidence.

Capture requires the viewed `replace_id` when replacing a checkpoint. Compare requires its `checkpoint_id`. Per-account locks serialize operations in this process, and final SQLite write transactions recheck the checkpoint, active account and scope. Failed observations or stale controls preserve existing evidence. Reports are immutable observations; imports arriving later do not retroactively change an earlier saved result. No background worker rebases or repairs an account.

| Method | `/api/v1` path | Effect |
| --- | --- | --- |
| GET | `/account/balance-checks?scope=all` | Active accounts in the page's production/test/Demo scope; no provider call |
| GET | `/account/balance-checks/{account_id}` | Current checkpoint metadata, latest report and twenty history summaries |
| POST | `/account/balance-checks/{account_id}/checkpoint` | `{replace_id: null or viewed id}`; fresh read and local checkpoint replacement |
| POST | `/account/balance-checks/{account_id}/compare` | `{checkpoint_id: viewed id}`; fresh read and immutable comparison |
| GET | `/account/balance-checks/{account_id}/reports/{report_id}` | One retained report scoped to its account; no provider call |

Inputs are bounded to 10,000 records per ledger and 2,000 assets. Account history, spot-wallet scope and provider retention remain incomplete. This is a single-worker local workflow, not a distributed reconciliation engine.

## ProtoLink

Accountant declares the ordinary native `balance_check_report` tool. It reads saved evidence only, returns up to forty asset rows and preserves source limitations. `page_help(topic="balance_checks")` explains the workflow without reading funds. Agents cannot capture checkpoints, fetch current balances through this tool, repair differences or mutate exchange funds.

Tests cover cross-market arithmetic, native fees/rebates, pending/ambiguous funding, boundary records, backfills/corrections, disappearing assets, incomplete imports, invalid balances, scope changes, concurrent checkpoint controls, report retention/privacy and native AgentClient reads without provider access.
