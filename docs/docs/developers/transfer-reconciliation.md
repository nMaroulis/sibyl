# Transfer matching and review

**Trade → Account history → Funding → Reconcile transfers** matches retained movements between accounts the user identifies as their own. Suggestions are read-only heuristics. Confirmation saves a local, reversible assertion with source snapshots and an audit trail.

Confirmation classifies pairs. The separate [Performance calculation](transfer-cost-basis.md) can replay eligible pairs with original lots. It does **not** initiate transfers, infer ownership or settlement, rewrite funding facts, or calculate cash-flow-adjusted returns. Unlinked observations are **unreviewed**, not established external deposits/withdrawals.

## Review workflow

1. Import both sides through [Funding history](funding-history.md).
2. Open **Reconcile transfers** and filter by account, asset or environment. An account filter matches **either side** of a pair.
3. Open **Review pair** to inspect each account, venue, native ID, date, reported amount and reported fee. Confirm that the accounts are yours and the observations represent the same movement.
4. Explain differing reported amounts or timing outside the suggestion window in a review note. These cases require at least eight characters of explanation.
5. Choose **Confirm own-account transfer**. Confirmation stores the exact source versions displayed in the dialog.

**Match records** searches retained native IDs, app record IDs, account labels, asset codes and native references, with independent paging. It can find older observations outside the suggestion scan. Outgoing search initially respects the selected account, with an explicit option to search all accounts; incoming search spans counterpart accounts. Completed records already reserved by a link cannot be reused until that link is removed.

**View example** contains competing BTC suggestions, an equal-amount ETH pair and a saved USDT classification. It never writes sample funding records or links. Example dialogs cannot save confirmations.

## Suggestion boundaries

`services/transfer_reconciliation.py` reads at most the latest **1,000 eligible observations** for the selected asset/environment across accounts. It returns at most **40 suggestions**. The response and UI disclose truncation, scanned/eligible counts and the scan's scope. Narrow the asset filter or use manual search when the scan is limited. No suggestion is automatically confirmed.

A suggestion requires:

- A positive **completed** withdrawal/transfer out and deposit/transfer in.
- Different account IDs, the same asset and the same environment. Demo, test and production never mix.
- An incoming timestamp from five minutes before the outgoing timestamp through 72 hours after it. The small earlier window accommodates source clock differences without assuming settlement ordering.
- Reported amounts within 1%, or an amount difference exactly equal to a reported outgoing fee in that asset.

Ranking prefers a shared native reference **at the same venue**, then equal amounts or a fee-compatible difference, then shorter time gaps. Cross-venue references and native IDs are not treated as globally unique transaction proofs. The UI exposes competing suggestions when a record has multiple plausible counterparts.

Equal quantities, venue-internal markers, similar timing and a shared reference are evidence to inspect, not proof of an own-account transfer. Split/merged transfers are not reconstructed; each active link reserves exactly one outgoing and one incoming observation.

Manual review may select larger amount differences or older/different timing, with an explanation. A reported outgoing-minus-incoming difference is not assigned to fees, profit or loss. Provider amount/fee conventions remain separate and unknown fee data stays unknown. Comparisons use decimal arithmetic over the normalized ledger's recorded numbers; original exchange decimal-string precision is not recovered.

## Durable assertions and source changes

Three SQLite tables separate user decisions from imported facts:

| Table              | Responsibility                                                                           |
| ------------------ | ---------------------------------------------------------------------------------------- |
| `transfer_links`   | Pair IDs, confirmed/removed state, reviewed source snapshots, review note and timestamps |
| `transfer_members` | Unique event reservation: one active link per source observation                         |
| `transfer_audit`   | Confirm, reconfirm, remove and restore actions, with before/after evidence               |

Every confirmation uses a `BEGIN IMMEDIATE` transaction. The server rereads both facts, validates account/asset/environment/direction/status, checks both expected fingerprints, reserves both observations and appends the audit action atomically. Concurrent reviewers cannot claim one event twice. A failed audit write rolls back the link and reservations. An exact repeated confirmation is idempotent and creates no extra audit action.

Fingerprints cover native identity/reference, account, venue/environment, asset, kind/direction, timestamp, amount, status, fee/fee coverage, internal marker and amount convention. Display-label changes or local observation timestamps alone do not invalidate a review.

A later source correction does not silently alter the reviewed snapshots. Each read compares current source facts to the saved fingerprints. A changed or missing source produces **Needs review**, while reservations remain in place. Review current facts, inspect saved evidence/history and explicitly reconfirm; pending/failed/wrong-asset records cannot be reconfirmed as a valid completed pair. A stale submitted review receives HTTP **409** and must reload its source records.

**Remove link** is a soft removal: it releases both reservations and retains the pair, source snapshots and audit trail. Enable **Include removed links**, open a removed link, review current source versions and choose **Restore link**. Restoration cannot take an event now reserved by another link. An existing link's pair cannot be silently swapped; remove it before choosing another counterpart.

Read-only detail responses include the latest **50 explicit audit actions**, newest first; all actions remain stored. Automatic source changes are detected dynamically and do not create user-confirmation audit entries. Source imports still use their own observation timestamps and update counts.

## Funding, performance and agents

Funding rows expose the linked classification and counterpart account. Open a **User-confirmed transfer** or **Transfer link needs review** indicator to inspect it. Original amounts and completed native-quantity summaries remain unchanged, including any linked own-account movements. They are reported activity totals, not external cash-flow totals.

[FIFO performance](account-performance.md) reads current source versions and can carry original acquisition lots for zero-fee pairs or explicit balanced same-asset fee allocations, with unambiguous exact-market history. Applied pairs clear their two funding coverage gaps. Other links remain unapplied with a visible reason. Confirmation itself does not persist calculated lots: `cost_basis_applied=false` in the classification response describes that lack of a write; the Performance response supplies the current derived status. See [transfer cost basis and limits](transfer-cost-basis.md).

**Ask about transfers** opens Accountant in place. Its ProtoLink tool reads the selected local links and suggestions, with at most ten links and six suggestions in the initial evidence. Inference receives a fixed read-only snapshot tool, so it cannot change the selection, fetch private balances, confirm links or alter records. Tool-only mode formats the supplied evidence without an LLM. The prompt explicitly distinguishes user assertions, heuristic candidates, unreviewed funding and missing cost basis.

Inactive or disconnected accounts' retained records remain reviewable through these local APIs. No provider client or credentials are required for matching/review. The trading workspace's existing no-active-account onboarding still applies in the UI.

## HTTP contracts

All routes are under `/api/v1/account-ledger/transfers`, use the existing workspace token/origin controls and return `Cache-Control: no-store`.

| Method | Suffix              | Behavior                                                                                                                          |
| ------ | ------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| GET    | `/`                 | Saved links plus bounded suggestions; filters: `account_id`, `asset`, `environment`, `include_removed`, `limit` (1–100), `offset` |
| GET    | `/example`          | Isolated read-only fixture                                                                                                        |
| GET    | `/events`           | Manual record search: required `direction=in\|out`; optional account/asset/environment/`q`, `limit` (1–50), `offset`              |
| POST   | `/preview`          | Compare `outgoing_id` and `incoming_id`; no persistence                                                                           |
| POST   | `/`                 | Confirm reviewed source versions and a note                                                                                       |
| GET    | `/{link_id}`        | Current/saved evidence and recent explicit review history                                                                         |
| POST   | `/{link_id}/review` | Reconfirm or restore the original pair after reviewing current sources                                                            |
| DELETE | `/{link_id}`        | Soft-remove classification and release reservations                                                                               |

Source IDs and fingerprints are 64-character lowercase SHA-256 strings returned by the backend; link IDs are server-generated. Preview returns `valid`, issues, warnings, reported difference, note requirements and current fingerprints. Confirmation accepts only source IDs, expected fingerprints and a review note, not caller-supplied amounts, accounts or fees.

```json
{
  "outgoing_id": "<outgoing app record ID>",
  "incoming_id": "<incoming app record ID>",
  "outgoing_fingerprint": "<fingerprint from the review>",
  "incoming_fingerprint": "<fingerprint from the review>",
  "note": "Reviewed both source records and the reported amount difference."
}
```

Invalid pair facts return 400, missing records/links 404, stale facts or reservation conflicts 409, and invalid request fields 422. No write changes `funding_events`, `account_fills`, wallet balances, opening basis or exchange orders.

## Verification and remaining work

`tests/test_transfer_reconciliation.py` covers source-version checks, concurrent reservation, fee/difference handling, ambiguous/time-bounded suggestions, environment/account separation, manual search outside scan limits, source correction/missing facts, soft removal/restoration, audit rollback, unchanged source/wallet state, API validation and scoped ProtoLink inference.

Remaining work includes many-to-one transfer allocation, historical fee valuation, other fee currencies/rebates and cross-market basis, verified chain/settlement evidence where appropriate, reviewed external-funding classifications, historical flow conversion and complete account returns. A confirmed link alone is not a tax or accounting conclusion.

**Review amount & fee allocation** now checks source-version-frozen amount conventions, distinct same-asset fee charges and explicit assertions for missing fee data. It saves inside the existing audited review payload. See [transfer fee allocations](transfer-fees.md).
