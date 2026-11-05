---
title: Investment performance
description: Measure account gains separately from contributions and withdrawals, with explicit coverage review.
---

# Investment performance

Open **Account → Investment performance**. This measures a fixed set of accounts in USDT, independently of current value, daily market moves and the exact-market FIFO results in Trade.

## Measure a period

1. Choose a combined, exchange or individual account view at the top of Account.
2. Expand **Investment performance**, select **Start period** and capture a fresh opening valuation. Every balance and price must be available and sufficiently fresh; missing assets cannot become a zero starting value.
3. Later, **Capture closing valuation**. The account set, source and environment stay pinned. Changed connection/feed configuration requires a new period. Opening and closing observations are frozen, with dates and account labels.
4. Import the period's funding records in **Trade → Account history → Funding**. Resolve wallet scope and own-account transfer links there.
5. Review each funding observation's treatment, actual wallet movement time and historical **principal value in USDT, excluding fees**. Values and times entered here are your assertions; Sibyl does not fetch historical conversion prices or assume stablecoin parity.
6. Add missing external flows manually when native funding coverage is incomplete. Manual entries are clearly labeled USDT value assertions and do not change the funding ledger or balances. Avoid duplicating imported records; remove a manual entry if its native record arrives later.
7. **Review coverage** only after checking every selected wallet and funding stream, including fiat, unsupported streams, rewards and duplicates. A completed import is not proof of complete history. Without this exact-evidence assertion and current flow reviews, the return stays unavailable.

Returns cannot be reconstructed from old Account chart points. Begin measuring now. Demo uses the same workflow over its explicitly active virtual account; simulated results remain marked Demo.

## Read the result

The panel shows the opening/closing values, net external contributions or withdrawals, investment gain and a **Modified Dietz estimate**. Gain equals closing value minus opening value minus signed external flows. Positive flows enter the measured scope; withdrawals are negative. The return divides that gain by opening capital plus time-weighted external flows. Zero/negative weighted capital leaves the percentage unavailable.

The method approximates period performance using elapsed timestamps. It is not exact time-weighted return, an IRR, complete exchange accounting or tax P&L. Large flows and volatile prices can make the approximation less representative. Income and fees remain in investment performance rather than being treated as outside contributions.

A current confirmed own-account transfer cancels from **combined** external flows only when both reviewed legs fall wholly inside the measured account set and period. The same legs count as cash moving in/out for the individual accounts. In-transit transfers at a valuation boundary remain unresolved; accounts are not revalued as if the missing funds were already received.

Late imported records, changed native funding, altered transfer links or changed funding reviews invalidate the coverage assertion. Recheck the evidence before confirming again. New source facts never silently preserve an old return. Native funding records and review audit history remain separate.

**Ask Accountant** reads the selected saved period, source evidence and blockers through native ProtoLink tools. It cannot capture valuations or edit reviews. **Export evidence** downloads the frozen valuations, current funding/review evidence, calculations and recent audit history. There are at most 100 retained periods, 2,000 native funding observations and 200 manual flows per period; account sets are limited to ten, with bounded complete valuation reads.

**Remove period** deletes its saved valuations and local review history after confirmation; native funding, fills and accounts are untouched. Export first if you need a lasting copy.
