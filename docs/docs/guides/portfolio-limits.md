# Portfolio strategy limits

Open **Strategies → Portfolio limits**, beside the exchange automation controls. This policy combines **all exchange strategies across accounts**, with separate limits for **Production** and **Exchange test funds**. It does not include unrelated account holdings, manual Trade activity or paper runs. Shared limits start **off**; existing per-run limits and both backend execution flags still apply.

## Set a policy

1. Choose the funds environment and enable its shared policy.
2. Choose an observed production reference feed. Test funds also use real reference prices; Demo prices cannot enforce an exchange policy. Configure any required market API key in Settings first.
3. Enter three positive caps in **reference USDT**:
   - **Allocated capital:** total original budgets of active/paused runs and terminal runs that still retain holdings or unresolved orders. Reviews reserve nothing; Start checks again. These are local approvals, not exchange wallet reservations.
   - **Gross exposure:** marked strategy-owned units plus outstanding buy capacity. Pending sells never reduce this value before actual fills. A new buy must fit this cap; ordinary automatic sells retain their other checks.
   - **Daily loss:** the net decline in observed strategy P&L across the environment, including unrealized position changes and known native fees. Profits offset losses within the same period.
4. Type `SAVE STRATEGY LIMITS` and save. Changes pause affected running strategies, abandon unsent automatic signal intents and invalidate unused Start reviews. Existing orders and holdings remain at the exchange.
5. Select **Refresh assessment**, review contributions and prices, then Resume each eligible run deliberately. Saving, assessing or releasing never resumes a run.

No arbitrary monetary cap is chosen for you. Per-run budgets, loss guards, order caps and permissions continue to apply independently. Raising a shared limit cannot release a latched per-run loss guard.

## Understand the evidence

The panel shows capital, exposure and daily loss against their caps, with the source and assessment time. Expand **Contributions** for each retained run and **Reference prices & paths** for conversion evidence. Stablecoins and fiat require observed conversion rates; only the USDT denomination itself has identity value one. Rates can differ from the execution venue and are not guaranteed sale prices.

An open partially filled buy contributes its imported owned units plus its unfilled capacity. Remaining buy capacity uses the higher of limit-price notional and current reference value. Fully reconciled canceled/closed orders release their unfilled capacity. Stopped holdings, including dust, remain counted. New strategy allocations are not profits, and releasing a terminal run's unused allocation does not erase its period P&L.

The first complete assessment establishes the initial daily baseline. Later UTC days carry the last observed P&L into the next period, so a price gap while the backend is down is not silently rebased away. This is an **observed UTC daily P&L change**, not an exact midnight valuation, cash-flow-adjusted investment return or whole-account exchange P&L. Late imported fills and fee corrections affect the period when they become observable. Foreign-quote P&L is translated at current reference rates, so changes in those rates can affect observed P&L.

## A daily-loss lock

Reaching the daily-loss cap latches a durable lock and pauses every running exchange strategy in that funds environment. It blocks Start, Resume and new automatic signal orders. Production and test locks are independent; the manual global halt remains a separate control across both.

The lock survives backend restart and cannot be cleared on the breach's UTC day. Increasing the threshold does not clear it. On a later UTC day, type `RELEASE DAILY LOSS LOCK`; Sibyl performs a fresh complete assessment and refuses release if that new day's observed loss also reaches its cap. Runs remain paused. A locked policy cannot be disabled until released.

This requests **no cancellation or liquidation**. Already admitted orders can finish and existing orders can fill after a breach. Approved expiry/cancellation, manual Trade and separately reviewed **Close position** retain their own permissions. Limits cannot guarantee a maximum loss.

## Incomplete evidence

Missing fees, third-currency fees, uncertain submissions, mismatched native execution totals or incomplete terminal fill pages prevent a complete assessment. Missing, undated, stale or future-dated reference quotes also block automatic orders. A failed assessment preserves the last complete evidence/baseline and pauses affected runs; a later successful assessment does not resume them.

Reference assessments expire after 60 seconds, and the original conversion quotes must remain within their five-minute freshness window. The running strategy worker normally checks every 30 seconds; provider limits, slow requests and backend downtime can delay detection. The final native submission boundary rechecks freshness and rebuilds ownership in the same local database transaction that admits the order. Refreshing the browser is not itself an exchange check.

The implementation currently assesses at most 100 retained exchange runs per environment, with the existing 10,000-fill accounting limit per run. Coverage limits block orders rather than dropping old runs. This is a single-worker local control; hosted/distributed coordination remains pending. See the [developer contract](../developers/portfolio-limits.md).
