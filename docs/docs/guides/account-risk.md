# Account risk alerts

Open **More → Alerts → Account risk**, or choose **Risk alerts** on Account. Create a watch for one account or a fixed group of up to ten active accounts. Choose a reference pricing feed and your own limit. Expanding **Recovery & notification controls** reveals the recovery level, breach cooldown and optional recovery notices.

Starting a watch authorizes background **read-only spot balance and price requests**. No LLM or trading permission is required. It never submits orders, closes positions, pauses a strategy or enforces an execution risk policy. Notifications appear in Sibyl's bell and shared Inbox; external alert delivery is not implemented.

## Choose a limit

| Watch | Calculation | Alert condition | Recovery |
| --- | --- | --- | --- |
| Account value floor | Complete selected holdings valued in USDT | Value at or below your floor | At or above a higher recovery value |
| Asset concentration | Selected asset value / complete account-set value × 100 | Weight at or above your percentage | At or below a lower recovery percentage |
| Observed-value drawdown | (Observed peak − current value) / observed peak × 100 | Decline at or above your percentage | At or below a lower recovery percentage |

A value floor or allocation limit can notify on its first complete check. Drawdown first needs a positive observed value to establish its peak. Peaks grow only from complete fresh checks while the rule is armed; there is no historical backfill. An unheld asset has 0% allocation; a zero-value wallet has no allocation percentage. A zero-value wallet after a positive peak is a 100% observed-value drawdown.

**Drawdown measures account value, not investment return.** Deposits, withdrawals, fees, trades and currency rates can all change it. It is not adjusted for cash flows, and missed offline peaks are not reconstructed. Portfolio-wide strategy exposure controls, cash-flow-aware returns and automatic loss protection remain separate pending work.

USD, fiat and stablecoins require observed conversion rates. Only USDT itself needs no conversion. Reference valuations are indicative and are not executable liquidation quotes.

## Fixed accounts and explicit environments

Rules retain the exact account IDs you reviewed. Adding an exchange later does not expand an existing watch. Production, test and Demo accounts cannot mix in one rule. Production/test funds require a live reference feed; Demo funds require the offline Demo feed. A public production pricing feed can value test accounts, with the funds and pricing environments labeled separately.

A pinned account becoming inactive or disconnected stops assessment. It is never treated as a zero balance or silently excluded. Restore its activation or edit the rule's account set. Changing the default market feed does not repin saved rules. Changes during a read invalidate that attempt; the next check uses current configuration.

No account is activated by creating a rule. Use Settings to connect/activate accounts. **View example** is a separate, read-only illustration and requires no setup or Demo activation.

## Complete fresh evidence

Every selected spot balance must be readable and valid, and every positive holding must have a supported, fresh, dated conversion path. Unknown assets, invalid quantities, missing account reads, undated/stale/future quotes and exceeded read budgets prevent the entire assessment. Earlier valid values remain labeled with their original time; an error does not generate a breach or recovery, change a peak, or clear an incident.

Each check is bounded to ten accounts, 100 positive assets, existing conversion-read budgets and a 45-second assembly quality window. Individual reads retain their provider transport timeouts. Every non-USDT conversion quote must be no older than five minutes or more than one minute ahead. Balance receipt times record completion of reads, not a universal provider balance timestamp. A combined check is not an atomic cross-exchange snapshot and covers only the adapters' supported spot wallet, not all wealth or derivatives liabilities.

## Recovery, repetition and lifecycle

A recovery level supplies a clear band around the limit. Defaults are 1% above a value floor or one percentage point below a percentage limit; you can set your own. One breach notice is sent per incident. Remaining beyond a limit does not repeatedly notify.

The default breach cooldown is five minutes (configurable from one minute to one day). A new breach during cooldown needs another fresh qualifying check after cooldown. It is not delivered from an old sample. Recovery notices are optional; incidents still clear at the recovery level when those notices are disabled. An incident that never sent a breach notice does not send an orphaned recovery notice.

- **Pause** stops future risk reads. An old in-flight response cannot overwrite it.
- **Edit** saves paused, preserving prior notification/snapshot revisions.
- **Resume** starts a new window, clearing the observed peak and incident state.
- **Archive** stops reads and removes the rule from the default list. Notifications remain.
- **Restore paused** restores the rule without starting reads.
- **Check** requests a due check and respects the same schedule/backoff.

The workspace permits 25 non-archived risk rules, separate from other alert budgets. Complete checks are normally scheduled about a minute apart; provider queues and slow reads can delay them. Failures back off up to 15 minutes. Checks continue with the browser closed while the backend runs. A stopped/sleeping host cannot monitor, and missed limit changes are not reconstructed. Armed state, observed peaks and incident/cooldown state survive restart.

## Inspect saved evidence

Choose **View evidence** on a rule or **View valuation evidence** in its Inbox notice. The dialog reads local snapshots only. It shows original rule revision/limits, exact accounts and pricing source, total, per-asset values/weights/conversion paths, oldest provider times and individual balance receipt times. A small chart and check selector inspect retained values from the selected revision. The chart joins observations; it does not establish what happened between them.

Up to 120 complete samples per rule are retained within a 14-day, 2,000-sample workspace budget. Sample details may expire sooner under the caps. Notifications retain their original metric, value, limits, account/source attribution, peak, observation/receipt times and sample ID even after sample expiry or edits. Marking a notice read never deletes it.

See [backend contracts](../developers/account-risk.md) and the [remaining-work checklist](../developers/backend-roadmap.md).
