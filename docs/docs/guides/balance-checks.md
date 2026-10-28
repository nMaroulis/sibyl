# Balance checks

Open **Account → Balance checks**, below Account balances. Choose one active account. Demo and test accounts keep their labels and are checked separately from production funds.

1. Select **Capture starting balances**. Sibyl reads the account's configured wallet and saves a local checkpoint alongside the history already imported at that time.
2. Import subsequent trades and available funding in **Trade → Account history**. Include the exact markets you used; a configured market does not cover every market on the exchange.
3. Select **Compare balances** to read current wallet quantities and save a comparison. Inspect its status and the affected assets.

Opening this panel, choosing an earlier report or asking Accountant about a saved check does not fetch exchange balances. Only the capture/compare buttons make a balance read. They never place orders, change exchange funds, import history or repair differences.

## Reading a check

The table shows opening quantities, known trade changes, known funding changes, expected quantities, observed quantities and differences. Amounts remain in each asset's native units; they are not added across assets or priced as investment returns. Trades across different imported markets share the same asset arithmetic, including base/quote fees, third-asset fees and rebates.

- **Observed match** means the quantities agree with the available imported facts within the stated numeric tolerance. It does not establish complete account history or settlement.
- **Differences to review** means a calculable expected quantity differs from the balance read. Missing trades, funding, wallet activity or provider scope can explain it; it is not automatically a trading loss.
- **Missing evidence** means an expected quantity cannot be established. The affected row explains the gap; a dash is unknown, not zero.

Unknown trade fees, unfinished imports, older history imported or corrected after the starting point, and activity near either balance observation can prevent a comparison. Native balances and history are not an atomic exchange snapshot. The comparison conservatively excludes activity overlapping either request window, with one second of additional boundary padding.

Funding uses documented provider rules, explicitly zero-fee records or your current local review of an ambiguous wallet/fee convention. In **Trade → Account history → Funding**, inspect **Wallet balance effect** and select **Review balance effect** when offered. Verify the wallet, amount convention and any missing fee against your exchange statement. Original amounts and fees stay unchanged. **Your review** labels distinguish your assertions from provider rules, and you can withdraw a decision.

Pending/restricted/unknown movements, missing posting times and unresolved fee/wallet conventions leave expected quantities incomplete. Kraken posted ledger entries subtract the same-asset fee from the signed amount. Other nonzero fee conventions are not guessed. Failed/cancelled observations contribute no completed movement. A funding balance review and a reviewed own-account transfer link are separate decisions; neither supplies cost basis automatically. See [funding rules and review limits](../developers/funding-effects.md).

## Starting again and keeping evidence

**New starting point** explicitly replaces the account's current checkpoint. Review unexplained changes before rebasing; a new checkpoint does not explain an earlier gap. Up to twenty comparison reports remain available in **Saved checks**. **Export check** exports the displayed report, including its account/environment, dates, tolerance and gap notes.

Changing saved credentials, provider environment, wallet configuration or the installed exchange SDK invalidates a checkpoint's scope. Capture a new starting point after reviewing the account. Saved reports remain historical observations, including after an account is deactivated or disconnected.

The current bounds are 10,000 retained fills, 10,000 funding observations and 2,000 reported assets per account. Oversized or invalid native observations fail without replacing saved evidence. Timing uses the actual read window: a provider's timestamp may describe its last account update rather than when you requested balances. Broad historical coverage, additional provider fee/wallet rules, earn/staking, subaccounts and full account reconciliation remain on the [implementation checklist](../developers/backend-roadmap.md).
