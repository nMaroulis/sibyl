# Transfer cost basis

**Trade → Account history → Performance** now carries original acquisition lots between account books for an explicit subset of [user-confirmed transfers](transfer-reconciliation.md). Confirmation records ownership/classification; Performance derives current lot allocations from retained facts on each calculation. Neither action moves money or submits orders.

## Which links apply

A pair qualifies only when all of these checks pass:

- The saved link is active, both current source records exist, and their material fingerprints still match the reviewed versions.
- The observations remain valid completed, positive, same-asset, same-environment movements between different accounts.
- Without an explicit allocation, reported outgoing/incoming quantities must be **exactly equal** and both fees explicitly zero.
- [Reviewed same-asset fee allocations](transfer-fees.md) can apply unequal reported amounts or missing fee assertions when the debit, credit and distinct fee charges balance exactly. Conventions are never inferred. Other-currency fees, rebates and split/merged allocations remain unsupported.
- Receipt follows dispatch. Equal/reversed timestamps, a fill at a movement timestamp, or multiple relevant funding records at that account timestamp leave ordering unresolved.
- The connected asset accounts have one unambiguous retained exact market and quote denomination. A base asset also used in another pair, including as a quote, blocks that connected component. No USD/USDT parity or historical conversion is assumed.
- The pair lies strictly after each applicable opening assertion. A previous transfer is not added on top of a user-entered opening balance.
- The source book has no earlier unresolved funding, incomplete fees, estimated notionals, ambiguous ordering, invalid opening assertion or blocked matching. Later unmatched funding on the source does not retroactively block a previously valid dispatch. Cross-market and timestamp ambiguity checks use the retained market history conservatively.

The UI shows **Lots carried** or **Unapplied**, with a reason for each reviewed link. An unapplied link keeps its funding/coverage gap; it does not silently create zero-cost inventory or pretend an amount difference is a fee. Other assets on the same account are not affected by an unrelated unapplied link.

## Calculation

The same `services/fifo.py` book handles ordinary fills and transfer-aware calculations. A single chronological replay processes each account's fills, outgoing dispatch and incoming receipt. At dispatch, FIFO slices leave the source book; at receipt, those exact slices enter the destination book. There are no disposal proceeds and no realized P&L for the move.

Each slice retains its original acquisition time, origin fill/opening record, originating account, quantity and cost in the exact market's quote. Partial slices divide cost proportionally with `Decimal` precision 50. Transfer receipt dates do **not** reset acquisition age: older transferred units precede newer local purchases. A subsequent eligible transfer carries those same origins through intermediate accounts or back to the original account.

Known zero cost remains known zero. Unknown-cost opening units retain their unknown cost and user-provided date. If a dispatch exceeds retained source inventory, the shortfall is explicit unknown-cost inventory with an **unknown acquisition date**. For provisional inspection, undated units precede dated lots; final net/marks remain unavailable. Distinct origins sharing an acquisition timestamp also flag ordering ambiguity.

Quote/base trading fees and rebates retain the ordinary FIFO rules. Third-currency fees are not converted. Nonzero same-asset transfer fees require an explicit [reviewed allocation](transfer-fees.md). Their inventory cost stays separate from received lots and trading P&L; final net results remain provisional without historical fee valuation.

## Dependency and scope rules

Selecting a receiving account first loads and replays its connected donor and intermediate account history. Only then are output account/market/environment filters applied. Otherwise a destination could incorrectly show zero acquisition cost simply because its donor was hidden.

The report includes `dependency_fill_count` and `dependency_account_count`; its `fill_count` describes the displayed rows. Receiving-only accounts can appear with zero local fills and transferred inventory. Disconnected/inactive accounts retain their historical facts and may supply donor lots. Current marks still require an active destination, a matching native balance, known open cost and complete applicable coverage.

Reads use one SQLite snapshot for fills, opening assertions, funding records and link versions. Derived lots are **not persisted** into source tables. Changing a source fill, re-reviewing a changed funding record, removing/restoring a link or editing opening inventory changes the next replay. A missing/corrected reviewed record remains a gap even if the source row itself disappeared.

Budgets reject rather than truncate:

| Input                | Limit and scope                                                                                             |
| -------------------- | ----------------------------------------------------------------------------------------------------------- |
| Fills                | 20,000 including dependency accounts, after exact-market/environment selection                              |
| Current links        | 2,000 after asset/environment selection, checked before account-component filtering                         |
| Funding observations | 20,000 across dependency accounts and the selected asset/environment, including relevant base-currency fees |
| Link evidence        | First 50 report links and first 50 related links per market; all budgeted links still calculate             |
| Lot evidence         | First 100 carried slices per link; `lot_count` discloses the full number                                    |

Filtered reports never import another environment's lots. If retained fills for the same account/market mix environments, an unfiltered calculation rejects the selection and asks for an environment filter rather than combining amounts.

## Performance and coverage

`transfer_summary` reports applied/unapplied counts. `transfer_evidence` contains status/reason, source/destination IDs and labels, dispatch/receipt times, known/unknown quantities, carried cost and bounded original lot slices. Each market includes `transfer_in_count`, `transfer_out_count`, `funding_event_count` and `unresolved_funding_count`.

Applied pairs clear their two funding gaps. Nonzero transfer fees still suppress final net/marks because historical fee valuation is missing. Other non-failed/non-cancelled observations continue to suppress final net/marks. Without a valid opening assertion, deposits **before the first retained fill** still count as missing coverage. Observations before an explicit opening boundary are covered by that assertion and not reapplied.

Unknown-cost sales stay excluded from matched P&L. A matching current balance is only an inventory check. This feature does not establish complete provider history, external cash flows, funding-adjusted account returns, historical currency conversions or tax treatment.

**Export summary** includes applied incoming/outgoing transfer counts and unresolved funding observations alongside the existing P&L/coverage columns. Inspect the on-screen evidence and original ledgers for individual lot records.

## Example and Accountant

**Transfer example** uses the same replay without a database or exchange client. A long-term wallet buys 0.2 BTC at 40,000 USDT; a trading wallet later buys 0.1 BTC at 50,000. A zero-fee 0.1 BTC transfer moves the older lot to the trading wallet. Selling 0.15 BTC at 60,000, with a 9 USDT trading fee, matches 6,500 USDT of cost and 8,991 USDT of proceeds: **2,491 USDT matched realized P&L**. Remaining known cost is 6,500 USDT across both wallets. This fixture does not create accounts, fills, funding rows, links or orders.

Select **With a transfer fee** to inspect the fee-aware variant, or use `GET /api/v1/account-ledger/performance/example?transfers=true&fees=true`. See [fee allocation and its example](transfer-fees.md).

Use `GET /api/v1/account-ledger/performance/example?transfers=true` for the original zero-fee variant. The existing example endpoint without that flag retains the four-fill/opening-inventory fixture.

The in-page Accountant reads the same calculation through ProtoLink. `performance_view`, `performance_example` and `performance_transfer_example` preserve the page context. Its fixed read-only evidence tool cannot alter filters, edit lots/links or fetch private balances. Evidence limits are explicit: 20 market groups, ten recent disposals per group, six report links, three links per market and five slices per link. Those are response caps, not calculation truncation.

## Verification and remaining work

`tests/test_transfer_basis.py` exercises cost/quantity conservation, partial slices, source fees, original-age FIFO, chains/round trips, unknown/zero basis, source corrections, missing facts, removal/restoration, dependency filters, environment/quote separation, opening overlap, time ambiguity, earlier funding, read budgets, opt-in balance marks, fixture isolation and ProtoLink evidence.

Remaining work includes historical transfer-fee valuation, other fee currencies/rebates, split/merged movements, cross-market acquisition basis, historical fee/flow conversion, reviewed external-funding classification and cash-flow-adjusted account returns. A user-confirmed link is not independent evidence of settlement or ownership.
