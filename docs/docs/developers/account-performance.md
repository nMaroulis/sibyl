# Account performance and opening inventory

**Trade → Account history → Performance** computes market-level FIFO from the retained normalized fill ledger. The calculation is Python code, works without an LLM, and never creates orders, queues imports or rewrites imported fills. [Account synchronization](account-sync.md) supplies the execution facts.

## Scope and coverage

Each calculation uses **one account and one exact spot pair**. All retained buys and sells contribute, in timestamp order. Account, market and environment filters apply; fill-table direction and pagination filters do not. There is no date-range filter that could accidentally drop earlier acquisition lots. Reports reject selections above 20,000 fills rather than silently truncating history.

Totals retain their **environment and quote currency**. USD, USDT and BTC amounts are never added together or treated as equal. Demo and test results never enter production totals. Different accounts retain independent FIFO lots.

This is matched market P&L, not full account returns, cross-market accounting, a tax report or evidence that provider history is complete. Deposits, withdrawals, transfers and history outside the provider's retained range remain missing. A zero result may mean no known-cost sales were matched; inspect matched and unknown quantities.

## FIFO rules

`services/performance.py` exposes a pure `fifo(fills, opening)` function. It uses `Decimal` arithmetic at 50-digit precision over the normalized ledger's recorded numeric values. Normalization currently uses JSON numbers; original exchange decimal-string precision is not recovered. Display values are finite floats or null; overflow never becomes JSON Infinity/NaN.

- Buy fees in the pair's quote increase acquisition cost. Sell quote fees reduce proceeds.
- Buy fees in the base reduce acquired quantity. Sell base fees increase inventory consumed. This allocates the cost of base-denominated sale fees to the disposal.
- Negative fees are rebates and retain their sign.
- Third-currency fees/rebates stay in native units. Historical conversions are absent, so final net matched P&L is unavailable whenever a nonzero third-currency fee occurs.
- Missing fee records are unknown, not zero. A buy with unknown fees produces an unknown-cost lot; missing fees suppress final net results.
- Missing reported execution totals use price × quantity for a provisional match, with final net suppressed.
- Unknown-cost opening units are consumed before subsequent acquisitions. For a partially matched sale, only the known portion's proportional proceeds and cost contribute to matched P&L.
- A sale before any recorded acquisition remains unmatched. A later purchase never supplies retroactive basis.
- Equal execution timestamps have no established native ordering. Deterministic ID ordering permits inspection, but final net remains unavailable.
- Inconsistent net quantities or negative net costs/proceeds stop subsequent matching, rather than creating invalid lots.

A base asset appearing in another retained market on the same account, including as that market's quote, flags cross-market ambiguity and suppresses final net/unrealized figures. This detection still applies when the report filters to one pair. It cannot detect activity absent from retained history.

The response distinguishes `realized_before_other_fees` from `net_matched_realized`. The latter is null for unresolved fee coverage, estimated notionals, execution ordering, cross-market ambiguity, invalid opening dates or blocked matching. **Unknown-cost sold quantities are excluded even when net matched P&L is available**; it is never a complete-account result. Per-market issues remain visible, and CSV exports include those issues.

## Opening inventory

Users may enter an opening quantity, optional **total cost in this pair's quote currency**, and a date strictly before the first retained fill. This is a user assertion, not a fetched exchange balance. It represents holdings immediately before the imported history starts; the date alone cannot establish coverage.

A blank cost means unknown. An explicit zero is a known zero cost. Positive quantity and nonnegative finite cost have bounded validation; the timestamp must be in the past and include a timezone. The browser displays local time and submits UTC.

The `opening_inventory` table has one current assertion per account/pair, with quantity and cost stored as decimal text. Save/remove operations and a before/after audit row commit atomically in SQLite. Imported fills remain separate. Assertions can be edited for inactive saved accounts. Disconnecting retains both ledger facts and the audit history.

If a later import discovers a fill preceding the asserted date, the opening lot is ignored and the report flags it for review. The original assertion stays available for correction; the service does not silently shift its date or alter its quantity.

## Current marks

**Refresh current marks** is an explicit, read-only action. Ordinary calculations, opening edits and the Accountant's performance tool do not fetch account balances or market quotes.

A current unrealized figure is available only when:

1. The saved account is active.
2. Its current native base balance matches the exact-market FIFO inventory within relative tolerance `1e-8` / absolute tolerance `1e-10`.
3. Open lots have known cost and the report has no blocking fee/order/cross-market coverage issues.
4. The selected reference feed supplies usable base and quote conversions.

The calculation uses one frozen [valuation source](portfolio-valuation.md), computing base/USDT divided by quote/USDT. No stablecoin/fiat parity is assumed. It returns source metadata and conversion legs, rates and provider timestamps. Stale/invalid rates are excluded; undated usable rates are labeled. Demo prices cannot mark production/test exchange inventory. Closed, balance-matched inventory needs no price lookup.

The action shares cached balance reads per account, checks at most 20 market groups, and stops starting more work after the valuation service's 12-second budget. An already-running provider request still uses its transport timeout. Partial or unavailable marks explain their reason; there is no fallback to sample prices. A matching current balance is only an inventory check, not proof of complete historical transfers. Reference marks exclude future disposal fees.

## HTTP API

All endpoints live under `/api/v1`, use the existing workspace access controls and return `Cache-Control: no-store`.

| Method | Route                                                       | Behavior                                                                       |
| ------ | ----------------------------------------------------------- | ------------------------------------------------------------------------------ |
| GET    | `/account-ledger/performance`                               | Optional `account_id`, exact `symbol`, `environment`, and `mark=false` filters |
| POST   | `/connections/{id}/opening-inventory`                       | Save a validated assertion for a saved account                                 |
| DELETE | `/connections/{id}/opening-inventory?symbol=BTC/USDT`       | Remove the current assertion while retaining its audit trail                   |
| GET    | `/connections/{id}/opening-inventory/audit?symbol=BTC/USDT` | Latest 50 assertion changes, newest first                                      |
| GET    | `/account-ledger/performance/example`                       | Compute an isolated four-fill educational fixture; no persistence or orders    |

`GET /account-ledger/performance/markets` lists filter choices from both retained fills and opening-only assertions without provider reads.

Example opening request:

```json
{
  "symbol": "BTC/USDT",
  "quantity": "0.25",
  "total_cost": "10000",
  "as_of": "2023-01-01T00:00:00Z"
}
```

Reports include group summaries, per-currency fee totals, known/unknown sold and open quantities, the latest 100 disposal calculations and latest 500 cumulative matched-result points per market. Cumulative values include earlier matches even when earlier points are omitted. **Export summary** exports group-level results and scope notes, not every underlying disposal; use the fill ledger for original execution records.

## ProtoLink and testing

The Accountant's `accountant_snapshot` native tool reads the same backend calculation with `performance_view=true` and validated account/market/environment context. `performance_example` selects the isolated fixture. It includes at most 20 market groups and ten recent disposals per group, with explicit evidence limits. It never requests marks or changes basis. Without an LLM, the agent formats the supplied totals and coverage note; with an LLM, its prompt requires the same boundaries.

`tests/test_account_performance.py` covers fee currencies/signs, partial lots, unknown basis, timestamp ambiguity, invalid/overlapping assertions, audit persistence, cross-market detection through filters, account/environment separation, safe numeric overflow, opt-in marks, source/balance failures, inactive accounts, report budgets, fixture isolation and the native ProtoLink tool. Authenticated exchange acceptance testing remains separate.
