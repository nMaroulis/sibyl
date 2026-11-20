# Split and merged transfers

Transfer groups carry original acquisition lots through one-to-many, many-to-one or many-to-many movements in **Performance → Across pairs**. They are explicit local accounting assertions over imported funding records. They do not move funds or independently prove wallet ownership, settlement, external cash flow or complete history.

## Review a group

1. Import the completed withdrawals/transfers out and deposits/transfers in under Trade → Account history → Funding.
2. Open Reconcile transfers → **Split & merged transfers → Create group**. Select 3–16 records, at most eight on either side. For two records use the existing pair review.
3. Choose each reported amount's convention: total debit/principal at the source; net credit/gross receipt at the destination. Known reported fees cannot be overridden. Enter a verified same-asset fee, including zero, when the source did not report it.
4. Enter the **principal allocation matrix**, in transferred-asset units. Row sums must exactly equal dispatched principal; column sums must exactly equal arrivals before receipt fees. Blank/zero cells mean no movement. Confirm that multiple nonzero fees represent distinct charges.
5. Preview the source debit, destination credit and total fees. Add an evidence note, confirm own-account ownership and configured-wallet scope, then confirm the group.

No group is suggested or confirmed automatically. Search is paged over retained records; no exchange is contacted. A record reserved by any pair or group cannot be used twice. Removing a group releases its records while preserving its review history. Re-review or restore keeps the same members and requires the latest revision and source versions.

## Accounting contract

All records must be positive and completed, in the same native asset and Demo/test/production environment. Source and destination account sets must be disjoint. Every dispatch must precede or share the first receipt's effective posting timestamp; interleaved batches need separate reviews. A documented or separately reviewed funding wallet effect must agree with the allocation. Outside-wallet facts cannot be overridden. If wallet/amount effects are unresolved, the group explicitly asserts them for its own replay; it does not silently resolve independent balance checks.

At dispatch, source FIFO inventory is consumed once for the total debit. Principal is sliced in the listed matrix edge order (the dialog uses receipt-column order), with source fee units taken from the tail. At each receipt, arriving slices merge by their **original acquisition age**, then receipt fee units are removed from the tail. Known cost, source account and origin IDs survive; unknown cost and missing acquisition ages stay unknown. Equal acquisition or dispatch timestamps remain qualified as ambiguous; deterministic record/origin IDs are only a reproducible fallback.

The exact conservation rule is `source debits = destination credits + all distinct fees`. Decimal arithmetic uses 50 digits with bounded input precision and at most 30 fractional places. There is no tolerance or rounding plug. Nonnegative transferred-asset fees are supported; foreign fee assets, rebates and policies capitalizing funding fees need separate work. The existing cross-pair engine can report historical fee values only when its retained dated conversion rules can establish them; missing values remain unresolved.

A corrected source, posting time, wallet scope or separate funding-review revision invalidates the **whole** group. Overlapping opening inventory likewise blocks the entire group in that accounting report. A valid-looking subset is never carried on its own. Across pairs loads all source dependencies before filtering to a destination account and rejects oversized inputs instead of truncating them. The additional budget is 1,000 groups; transfer receipt/lot evidence is bounded independently and reports disclose limits.

The older **By market** FIFO remains deliberately narrower and does not carry group allocations. Unpaired funding remains provisional there. Measured-period returns and balance comparisons continue to require their own source-bound reviews and coverage; group confirmation does not establish external-flow classification.

## HTTP and native agent access

All responses use `Cache-Control: no-store`:

- `GET /api/v1/account-ledger/transfers/events`: paged records include `group_fingerprint`, bound to native facts and the current separate funding review.
- `GET /api/v1/account-ledger/transfer-groups`: account (either side), asset, environment, removed, offset and limit filters.
- `POST .../transfer-groups/preview`: typed legs and ordered edges; returns exact conservation and the review fingerprint, without saving.
- `POST .../transfer-groups`: exact preview fingerprint, explicit ownership/wallet assertions and an evidence note. One immediate SQLite transaction checks every version and reserves every member.
- `GET .../transfer-groups/{id}`: saved/current evidence and the latest 50 audit actions.
- `POST .../transfer-groups/{id}/review`: same members, current source fingerprints and the displayed group revision. Supports re-review and restoration.
- `DELETE .../transfer-groups/{id}?revision=N`: withdraw that version and release reservations.

Exact repeated confirmations return the same receipt, including retries after a missed response. Stale source/review revisions or reservation conflicts return 409. Provider funding facts are never edited. The native Accountant's `accountant_snapshot` reports bounded group summaries in the transfer view; `group_id` reads an observed group's detailed allocation. `page_help(topic="transfers")` explains the workflow. Agents have no confirmation/removal tool.

## Verification

Offline acceptance covers split/merged and many-to-many cost conservation, source and receipt fee slices, unknown shortfalls, retained origins, exact matrix sums, incompatible environments/wallets, source corrections, funding-review invalidation, opening overlaps, pair/group exclusivity, concurrent confirmations, idempotency, removal/restoration, HTTP pagination/privacy and native read-only Accountant access. These checks do not establish authenticated funding coverage or accounting/tax policy suitability.
