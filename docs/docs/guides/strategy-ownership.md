# Strategy position ownership

An exchange strategy owns the units acquired by its linked native fills. **Position ownership** adds an explicit way to compare those units with the exchange and review existing holdings or residuals. Paper runs remain separate.

## Check actual balances

Open a run’s monitor and select **Check exchange balance**. This reads the exact account’s base-asset total/free balance, current book and native amount/notional minimums. The result compares every strategy owner of that base asset, including runs on other quote pairs.

- **Unassigned units** exceed the current strategy-owned total. They may be manual holdings, transfers or another system’s funds; their origin is not inferred.
- A **shortfall** means observed account units cannot back all recorded owners. Inspect account activity before attributing anything.
- **Dust** uses the exact pair’s amount precision, current bid and reported minimums. Being above an observed minimum does not guarantee an order can execute.

Checks are on demand. The panel shows when a check was made and whether local ownership evidence changed. Native balances are point-in-time observations, not fund reservations. Recent imported fills outside strategy orders can help explain changes, but import coverage may be incomplete.

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

Lifetime percentage returns, curve risk statistics and complete lifetime accounting are unavailable after attribution. Native acquired/disposed cost basis still follows the actual fill and receipt replay; the ownership panel exposes carried or asserted basis separately.

Fresh observed backing is required when attributed runs resume, evaluate or submit; separately reviewed exits also check backing. External trades can still race a read: this is not a native reservation or complete wallet reconciliation.

Later corrections to orders/fills preceding a receipt invalidate that receipt and descendants of a handoff. Uncertain evidence blocks further orders; it is not silently reassigned or rewritten. A reviewed correction/reversal workflow across already executed descendants, third-currency fee valuation, complete settlement/bust handling and validated cash-flow-adjusted lifetime statistics remain pending. Inspect the source in Trade and keep affected runs paused; do not bypass the block by creating duplicate ownership.
