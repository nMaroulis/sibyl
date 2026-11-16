# Strategy position ownership

An exchange strategy owns the units acquired by its linked native fills. **Position ownership** adds an explicit way to compare those units with the exchange and review existing holdings or residuals. Paper runs remain separate.

## Check actual balances

Open a run’s monitor and select **Check exchange balance**. This reads the exact account’s base-asset total/free balance, current book and native amount/notional minimums. The result compares every strategy owner of that base asset, including runs on other quote pairs.

- **Unassigned units** exceed the current strategy-owned total. They may be manual holdings, transfers or another system’s funds; their origin is not inferred.
- A **shortfall** means observed account units cannot back all recorded owners. Inspect account activity before attributing anything.
- **Dust** uses the exact pair’s amount precision, current bid and reported minimums. Being above an observed minimum does not guarantee an order can execute.

Checks are on demand. The panel shows when a check was made and whether local ownership evidence changed. Native balances are point-in-time observations, not fund reservations. Recent imported fills outside strategy orders can help explain changes. A **Matched Sibyl manual order** label requires the same account, pair, side and native order ID on a single recorded manual order. Fills without this evidence show **Order origin unknown**. The label never assigns units or asserts the origin of orders placed outside Sibyl.

## Adopt existing units

Pause a nonterminal exchange run and resolve its orders, native fills, fees and cancellation follow-ups. Select **Adopt existing units**, enter the base quantity, its **total acquisition cost in the pair’s quote asset**, and a reason. Review fresh native facts and type the displayed confirmation.

Adoption is bounded by both free balance and units left after all same-base owners. Cost basis is explicitly your assertion, not verified exchange history. Cash stays unchanged and the run stays paused; Resume is separate. Shared limits can still refuse execution.

## Release or hand off leftovers

Stop a run and resolve all order evidence first.

- **Release to unmanaged** removes a reviewed quantity and its proportional recorded basis from that run. It does not sell, transfer, recover cash or infer proceeds from a manual sale.
- **Hand off to a new run** opens exchange setup. Select the exact stopped/completed source under **Existing strategy position**. New-run approval carries all remaining units and original recorded basis atomically; the source stays terminal. The new quote budget is **additional cash**, separate from the carried position. Only the exact account, environment and pair are eligible.

A partial release retains the rest. Repeated confirmation never duplicates a receipt. No ownership action itself places an exchange order.

## Profit, evidence and limits

Ownership receipts remain separate from native fills and appear in the journal/CSV as `OWNERSHIP`. Their dated reference value is a capital flow, not exchange cash or trading proceeds. Marked total P&L and shared loss observations exclude that flow. Shared allocated capital includes attributed inbound value; units remain part of gross exposure.

Native acquired/disposed cost basis follows fill and receipt replay. The panel shows the carried or asserted basis separately.

## Lifetime performance and archiving

The run monitor shows a **Modified Dietz estimate** from the initial quote budget, closing cash and owned units, and recorded reference-valued ownership flows. Adoption and inbound handoffs contribute capital. Release and outbound handoffs withdraw capital. Each signed flow is weighted by the fraction of the measurement period remaining after its timestamp.

- With inventory, the closing valuation uses the last retained exchange midpoint. **Refresh valuation mark** reads the exact venue's book without changing the run's trading or risk state.
- A terminal run with zero owned units uses its allocated quote cash adjusted for any other-asset fee expenses or rebates. The as-of time includes known fills and attributions after stop.
- For fees in a third currency, keep closed candles for a conversion route on the run's exact connected feed and environment. Sibyl values each charge or rebate at the latest eligible close at or before its execution, up to 24 hours old. The report shows conversion legs and omits returns when required values are missing. [Approved fee prices](strategy-execution.md#review-fees-charged-in-another-asset) are used in both this report and execution risk. Available estimates can appear here before approval.
- A stale ownership receipt, uncertain order, incomplete native costs or fees, or mark older than a fill or attribution withholds the lifetime return. Historical chart samples and risk statistics remain tied to their original observations.

Once a stopped or completed run is flat and its execution ledger is reconciled, select **Archive run**. Use **Run visibility → Archived** to inspect or restore it. Archiving only organizes the run list. Monitoring still retains the journal, order reconciliation, and applicable shared risk evidence.

## Corrected exchange evidence

Fresh observed backing is required when attributed runs resume, evaluate or submit; separately reviewed exits also check backing. External trades can still race a read: this is not a native reservation or complete wallet reconciliation.

Later corrections to orders/fills preceding a receipt invalidate that receipt and descendants of a handoff. The ownership panel links each affected source run and shows the number of affected receipts and pinned orders to inspect. Uncertain evidence blocks further orders; it is not silently reassigned or rewritten. Reviewed correction or reversal across already executed descendants and definitive venue settlement or bust handling remain pending. Inspect the source in Trade and keep affected runs paused; do not bypass the block by creating duplicate ownership.
