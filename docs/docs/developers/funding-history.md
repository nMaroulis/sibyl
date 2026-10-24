# Funding history

**Trade → Account history → Funding** imports reported deposits, withdrawals and internal transfers into a ledger separate from trade fills, wallet balances and opening cost basis. It does not initiate money movements, change balances or calculate investment returns.

## Reviewed clients

| Client                                                                    | Imported streams                                | Limits                                                                                                                                           |
| ------------------------------------------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| Binance production                                                        | Crypto deposits and withdrawals                 | Explicit time window, native offsets; fiat purchases/bank funding, universal transfers, earn and subaccounts remain outside this importer        |
| Kraken production                                                         | Deposit, withdrawal and transfer ledger entries | Default wallet and posted ledger entries; pending funding requests, earn/staking and other ledger categories are not imported                    |
| Bybit production                                                          | On-chain withdrawals                            | Master-UID keys only; native cursor inside 29-day slices. Deposits, off-chain transfers, sub-UID reads and additional tax charges remain pending |
| Demo                                                                      | Empty funding history                           | Virtual seed inventory is not a fabricated deposit; the isolated example demonstrates the UI without account mutations                           |
| Binance.US, Coinbase Advanced Trade, Coinbase Sandbox and other providers | Coming soon                                     | No generic timestamp-pagination fallback or unreviewed endpoint substitution                                                                     |
| Binance Spot Test Network                                                 | Unavailable in this importer                    | Production wallet capital endpoints are never used for a sandbox                                                                                 |

The adapters follow the official [Binance capital API](https://developers.binance.com/en/docs/catalog/core-trading-wallet/api/rest-api/capital), [Kraken ledger API](https://docs.kraken.com/api-reference/account-data/get-ledgers-info) and [Bybit withdrawal records](https://bybit-exchange.github.io/docs/v5/asset/withdraw/withdraw-record). Binance uses offset pages inside a window shorter than 90 days. Kraken uses `with_cursor`, native `cursor.next`, and fixed time bounds. The adapter handles Kraken's exclusive lower timestamp bound and normalizes currency aliases through the installed SDK. Bybit uses `withdrawId` identities, `nextPageCursor` and contiguous 29-day slices inside the selected range; `BlockchainConfirmed` remains pending until native `success`. Unknown states remain unknown. Extra tax charges reject the page. A missing cursor that could conceal additional entries is an error. These adapters do not rely on SDK auto-pagination.

These native contracts have offline tests. Authenticated account acceptance testing remains outstanding. Do not grant withdrawal permissions for history reads. Kraken requires access to query ledger entries.

## Importing a range

1. Activate a supported saved account, then select it in Funding.
2. Select the offered streams and a past start/end range shorter than 90 days. The UI shows local time and submits timezone-aware UTC timestamps.
3. Choose **Import range**. The background worker reads one page at a time, without blocking the HTTP request.
4. Use **Pause** and **Resume** to retain progress. Pause the active stream before selecting a different range.
5. After **Range fetched**, **Rescan range** starts that range again and upserts corrections by account, stream and native ID. Import older or newer ranges separately.

There is one current checkpoint per account/stream. Changing a completed/paused range replaces its checkpoint; observations from previous ranges remain retained. Restart recovery resumes an interrupted page from the last committed checkpoint. A range revision prevents an old in-flight response or failure from overwriting a newly selected range.

The shared `ImportWorker` supplies scheduling, a per-service work lock, sanitized errors and at most five transient retries with exponential backoff. Fill and funding imports use the same account transport locks. Each page and its checkpoint commit atomically. Pausing/deactivating/disconnecting stops subsequent reads while an already-started valid page may checkpoint. An inactive account cannot enqueue imports. Shutdown waits for finite in-flight reads before closing transports.

Funding pages contain at most 50 records. A 2,000-page budget stops an overly large import with an explicit error; choose a smaller date range. Repeated cursors and repeated record pages fail instead of looping. A rejected page cannot advance the cursor or partially insert records.

**Range fetched** only means the selected provider pagination ended. Late records, old pending statuses and provider retention can leave gaps. A new date range does not refresh pending records created in an older range; rescan that older range. No automatic periodic account scan is enabled.

## Observation contract

`funding_event()` validates the native ID, selected kind, time window, asset, direction, status, finite amount and fee before writing anything. The ledger stores:

- Account, venue and environment, keeping Demo/test/production distinct.
- Native identity and an optional native reference, scoped to account and stream.
- Provider execution/ledger timestamp, first local observation and last local observation.
- Kind (`deposit`, `withdrawal`, `transfer`), reported direction and nonnegative native quantity.
- Status (`pending`, `completed`, `restricted`, `failed`, `cancelled`, `unknown`).
- A nullable fee currency/amount; negative fees remain rebates.
- Whether the venue explicitly identifies internal activity and whether the amount comes from a funding record or a posted ledger entry.

Raw provider payloads, wallet addresses, address tags, transaction keys and blockchain IDs are not retained or sent to the UI/agent. An unknown fee is not silently zero. Native amounts remain separate from fees: this importer does not infer whether the provider's amount includes a fee. Binance credited-but-locked deposits remain **restricted**. Kraken **completed** means a posted ledger observation, not an independent bank/chain settlement check.

An internal-at-venue marker or shared reference does not prove that two connected accounts belong to the same owner, or establish a unique transfer pair. Explicit [cross-account transfer review](transfer-reconciliation.md) is available; [Performance](transfer-cost-basis.md) can carry original lots for eligible confirmed pairs. Negative ledger amounts become outgoing quantities; positive amounts become incoming quantities, even for reversals associated with a withdrawal category.

As with the fill ledger, normalized display quantities use finite JSON numbers; this is not a lossless native decimal archive. Values above the reviewed numeric bounds reject the page.

## Filtering and summaries

Filter retained records by account, environment, asset, kind and status. Original facts remain readable after deactivation or disconnect. With no active accounts, the trading workspace still shows its connection/Demo onboarding; the read-only ledger API remains available for retained history.

Summaries cover the **entire filtered selection**, not just the current table page, and include only completed observations. They retain account, environment, asset, kind and direction. Different assets are never added into a single number. Completed fee/rebate totals keep their native currencies and remain separate from movement amounts. A pending-only filter has no completed summary.

**Export this page** exports the displayed records, source identities and coverage note. It does not export all historical pages. **View example** shows an isolated four-record fixture, including a pending deposit excluded from completed totals; no sample records enter the account ledger or wallet.

## Performance and ProtoLink

The [FIFO report](account-performance.md) reads funding coverage in the same database snapshot as fills and opening assertions. Unapplied non-failed/non-cancelled funding observations affecting the base asset, or a nonzero fee in that asset, suppress final net/unrealized figures. Eligible current confirmed transfers carry original lots and clear their two funding gaps. Pending observations also make coverage provisional. Funding before an asserted opening boundary is not reapplied. Without an explicit opening assertion, observations before the first retained fill also contribute to coverage. The provisional matched calculation stays inspectable without inventing acquisition costs.

**Ask about funding** opens Accountant in place. Its ProtoLink native tool reads the selected local ledger, completed summaries and sanitized import progress. It never fetches private balances, queues jobs, pairs transfers or changes records. It includes at most ten records from real history (the isolated example has four), and labels the evidence limit. Without an LLM, it formats the supplied evidence directly. With an LLM, the module prompt preserves the same amount/fee/coverage limits.

## API and storage

All routes use the existing workspace token/origin protections. Ledger/status/example reads and enqueue responses use `Cache-Control: no-store`.

| Method | `/api/v1` route                        | Contract                                                                          |
| ------ | -------------------------------------- | --------------------------------------------------------------------------------- |
| GET    | `/funding-sync`                        | Saved account support and public range progress, without cursors                  |
| POST   | `/connections/{id}/funding-sync`       | Queue selected `streams`, aware `start` and `end`                                 |
| POST   | `/connections/{id}/funding-sync/pause` | Optional `stream` query parameter; omit to pause all account funding streams      |
| GET    | `/account-ledger/funding`              | `account_id`, `asset`, `kind`, `status`, `environment`, `limit` (1–100), `offset` |
| GET    | `/account-ledger/funding/example`      | Read-only isolated fixture                                                        |

Example request:

```json
{
  "streams": ["deposit", "withdrawal"],
  "start": "2026-09-01T00:00:00Z",
  "end": "2026-10-01T00:00:00Z"
}
```

`funding_events` stores normalized observations with unique `(account_id, stream, native_id)` identities. `funding_sync` stores each stream's range, scheduling fields, private cursor, progress and revision. Neither table changes the paper wallet or `account_fills`. Native corrections update the retained observation; first/last observation times and progress update counts remain visible, but this is not a version archive of every provider response.

Tests in `tests/test_funding_history.py` cover native cursor/offset requests, terminal pages, restricted statuses, corrections, atomic rollback, stale in-flight revisions, pause/restart/deactivation, repeated pages, unsupported/test clients, filtering/currency separation, example isolation, ProtoLink evidence and FIFO coverage flags.

Remaining work: additional reviewed provider adapters; fiat/earn/subaccount coverage; reconciliation of pending and late events; fee-aware/unequal cost-basis carryover and split/merged transfer allocation; historical flow valuation and cash-flow-adjusted returns.

## Transfer annotations

**Reconcile transfers** opens reviewed matching in the same Funding workspace. Funding rows expose linked/needs-review annotations and their detail shortcut. Source amounts, statuses and completed activity totals remain unchanged. Unlinked records remain unreviewed; confirmation alone does not supply acquisition facts or external cash-flow returns; Performance separately checks whether original lots can carry over. See [transfer assertions, source versions and restoration](transfer-reconciliation.md).

Performance can now clear funding coverage gaps for eligible confirmed transfer pairs by replaying their original acquisition lots. Other observations remain unresolved; see [transfer cost basis](transfer-cost-basis.md) for exact fee, amount, ordering and denomination requirements.
