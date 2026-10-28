# Transfer fee allocations

**Funding → Reconcile transfers → Review pair** now supports a reviewed amount/fee allocation. This extends [original-lot carryover](transfer-cost-basis.md) beyond equal-amount, explicitly zero-fee pairs. It does not initiate a transfer, rewrite a provider observation or submit an order.

## Review workflow

1. Open a suggested/manual pair or an existing saved review.
2. Select **Review amount & fee allocation**.
3. Choose what each source's reported amount means. No convention is selected automatically.
4. Inspect reported fees. If fee data is missing, explicitly enter the verified fee quantity in the transferred asset; entering zero is a user assertion, not a provider fact.
5. If both fees are nonzero, explicitly confirm they are **distinct charges**, not the same fee displayed twice.
6. Choose **Check allocation**. Python validates the balance against the exact source fingerprints shown in the dialog.
7. Explain the amount conventions and distinct charges in the required review note, then confirm/reconfirm the link.

The checked preview displays source debit, destination credit and each fee's reported/asserted origin. Changing an input invalidates the check. A source correction returns HTTP 409 and requires reloading/reviewing the source records. Saved allocations remain in the audit history; changed-source reviews clear the UI draft so conventions must be reviewed again. Turning allocation off and reconfirming removes it from the current review while retaining history.

The normal zero-fee rule still works without an allocation. A classification can be saved without an applicable allocation; Performance then shows why it remains unapplied.

## Amount conventions

| Source   | Convention      | Meaning                                                                      |
| -------- | --------------- | ---------------------------------------------------------------------------- |
| Outgoing | `total_debit`   | Reported amount is the total account debit, including its outgoing fee       |
| Outgoing | `principal`     | Reported amount is the sent principal; its outgoing fee is debited on top    |
| Incoming | `net_credit`    | Reported amount is the actual account credit after its incoming fee          |
| Incoming | `gross_receipt` | Reported amount is the gross arrival; its incoming fee is deducted afterward |

For nonnegative same-asset fees:

```text
source debit = outgoing amount + outgoing fee (only for principal mode)
dispatched principal = source debit - outgoing fee
destination credit = incoming amount - incoming fee (only for gross_receipt mode)
source debit = destination credit + outgoing fee + incoming fee
```

Dispatch and destination credit must remain positive. The last equation must balance exactly using the recorded decimals. An amount difference is never assigned automatically to a fee. Native third-currency fees, transfer rebates, split/merged pairs and residual differences remain unsupported.

Known reported fees cannot be overridden. A partially reported fee amount also cannot be contradicted. Missing quantities/currencies may be completed only with an explicit transferred-asset assertion; a reported nonzero/unknown fee in another currency cannot be asserted away. Small fee values are displayed without rounding them to zero.

Allocations use the existing 50-digit arithmetic budget, with at most 30 fractional places and sufficient headroom for exact addition/subtraction. Values outside that precision range are rejected rather than rounding a fee out of the balance equation. Source normalization still uses recorded JSON numbers; original provider decimal-string precision cannot be recovered.

## Lot and fee policy

The current policy is `separate_inventory_cost`. It is a computational convention, not a statement of tax treatment:

- At dispatch, source FIFO removes the **total debit**. Principal slices are allocated first and outgoing fee slices last.
- At receipt, net credited slices are allocated first; incoming fee units come from the tail of that arriving bundle. Existing destination lots are not used to pay the incoming fee.
- Credited slices retain their original acquisition dates, origin IDs and proportional quote cost. Fee slices are excluded from received lots.
- Fee units' known historical inventory cost and unknown-cost quantity are disclosed separately. They are not capitalized into received lots, treated as sales, or subtracted as zero-proceeds trading P&L.
- Later transfers can carry the remaining known lots. Fee units cannot be transferred a second time.

Quantity and known cost are conserved across source remainder, credited lots and both fee allocations. A source shortfall remains explicit unknown cost/date, including any fee units in that shortfall. A numeric zero **known portion** does not establish a zero total cost when unknown units exist.

Performance includes `transfer_fee_quantity`, `transfer_fee_known_inventory_cost` and `transfer_fee_unknown_quantity` per account/market. Each applied link has `movement`, `outgoing_fee_evidence` and `incoming_fee_evidence`, including bounded original fee-lot slices. CSV summaries include these quantities/costs.

**Historical fee market valuation is not implemented.** Nonzero transfer fees therefore keep final net matched results and current marks provisional under the existing coverage guard. Trading-only `realized_before_other_fees`, received inventory and known acquisition cost remain inspectable. Historical inventory cost is not the fee's market value, a complete expense figure, a tax result or a funding-adjusted account return.

## API and persistence

Existing authenticated/origin-protected routes accept optional `allocation`:

- `POST /api/v1/account-ledger/transfers/preview` checks frozen source versions and an optional allocation without writes.
- `POST /api/v1/account-ledger/transfers` saves a version-checked confirmation.
- `POST /api/v1/account-ledger/transfers/{id}/review` changes/removes allocation, re-reviews sources or restores a soft-removed link.

Example allocation body within a preview/confirmation:

```json
{
  "outgoing_id": "<64-character retained observation ID>",
  "incoming_id": "<64-character retained observation ID>",
  "outgoing_fingerprint": "<reviewed outgoing fingerprint>",
  "incoming_fingerprint": "<reviewed incoming fingerprint>",
  "allocation": {
    "outgoing_amount": "total_debit",
    "incoming_amount": "net_credit",
    "outgoing_fee_quantity": null,
    "incoming_fee_quantity": "0",
    "fee_policy": "separate_inventory_cost",
    "distinct_fees_confirmed": false
  },
  "note": "Verified the debit convention and that the destination charges no separate fee."
}
```

Omit `note` for preview. Supply a note of at least eight characters for every saved allocation. Both fingerprints are required for an allocation preview, and required for every confirmation. Derived debit/credit/cost values are server output, not accepted request fields.

The allocation request, computed balance and fee-origin labels are stored inside the existing reviewed payload. They commit atomically with source reservations and the audit entry. Idempotency includes the allocation; changing/removing it produces a new review action. No new calculated lots are persisted. Performance recomputes against current sources on every read; stale/removed links stop applying until reviewed/restored.

## Isolated examples and Accountant

Funding's **View example** lets you check allocation controls through `POST /api/v1/account-ledger/transfers/example/preview`. This endpoint reads only fixed example observations, validates fingerprints and never accesses saved account records or writes a link. The example's confirm action stays disabled.

In Performance, select **Transfer example → With a transfer fee**. The fixture debits 0.1 BTC, credits 0.099 BTC and removes 0.001 BTC with 40 USDT historical inventory cost. The later sale shows **2,481 USDT provisional trading P&L** and **6,450 USDT remaining known acquisition cost** across the wallets. Final net is unavailable because historical fee valuation is absent. Use `GET /api/v1/account-ledger/performance/example?transfers=true&fees=true`.

The Accountant's fixed read-only ProtoLink snapshot reads the same evidence. `performance_fee_example=true` accompanies the existing performance/transfer example context flags. Fee-lot evidence has the same five-slice agent cap as received-lot evidence. Inference cannot change source facts, assert fees, confirm allocations or fetch private balances through this report tool.

`tests/test_transfer_allocation.py` covers all four amount-convention combinations, distinct-charge acknowledgment, missing/known/foreign fee rules, precision limits, version checks, atomic audit rollback, allocation edits, fee/received-lot conservation, unknown fee-unit cost, chained transfers, isolated examples and ProtoLink agreement.

Remaining work includes historical fee/flow valuation, other fee currencies and rebates, split/merged allocations, cross-market basis, reviewed external-funding classification and cash-flow-adjusted account returns.
