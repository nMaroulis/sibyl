# Price alerts & inbox

Open **More → Alerts**, or choose **Price alerts** on Markets. Alerts use public market data independently of your portfolio accounts, execution permission and AI model. No account or LLM is required for a public feed. A connected-account feed still needs that account active; API feeds need their saved key.

## Set a level

Choose **New price alert**, select a market feed, search its exact spot pair, and enter a quote-currency threshold. Choose **At or above**, **At or below**, **Crosses to or above**, or **Crosses to or below**, and optionally name the rule. Level conditions can notify immediately if the first fresh quote qualifies. Crossing conditions first establish a starting point, then wait for a later move from the strict opposite side to or through the level. A touch counts, but starting exactly on the level is not an opposite-side observation.

Each rule pins its feed and exact pair. Changing the workspace's default feed later does not move existing alerts. USD and USDT are distinct pairs/currencies. Rule cards show the source, Demo/test/live environment, last price, provider time, check time and any error. Missing, undated, stale or invalid quotes leave the rule armed with an explanation.

Demo is an explicit offline market feed and its notifications carry a **Demo** badge. Selecting it does not activate the Demo portfolio wallet or disable an exchange account. **View example** shows illustrative rules and a notification without changing any settings, records or accounts; its action controls are disabled.

## One time or repeat after reset

Choose **One time** to stop after one notification. Choose **Repeat after price resets** to keep watching. Repeated alerts must observe the price return to the other side of the threshold, then make a new qualifying move after the selected minimum interval (one minute to one day). They do not notify repeatedly while the price stays above/below the level.

Moves during cooldown are skipped, rather than delivered late. If a move crosses during cooldown, the price must reset again before another notification. A reset during cooldown can precede a new move after cooldown. Cards show **Watching**, **Waiting for reset**, or **Cooling down**, with the last notification and quote evidence.

The rule's current state and notification commit together. Restarting Sibyl preserves reset/cooldown progress and cannot duplicate that cycle's notification. Each notification keeps the settings that produced it, including after a rule is edited.

- **Pause** stops future checks. An in-flight response cannot override the pause.
- **Resume / Rearm** explicitly starts a new cycle. If the condition is still true, another notification can arrive on the next check.
- **Archive** removes a rule from the default list and stops checks. Its notifications remain.
- Enable **Include archived**, page through older rules if needed, then **Restore paused** to bring a rule back without reactivating it.
- **Check** evaluates a due rule while respecting the same scheduling and error backoff as the worker.

The workspace permits 50 non-archived rules, including paused and triggered ones.

## Edit a rule

Choose the pencil on a non-archived rule to change its feed, pair, level, condition, frequency or name. **Save paused** preserves its ID and previous notifications, and leaves it paused. Review the new settings, then choose **Resume**. This starts observation afresh; a level condition can notify immediately, while a crossing condition needs a new starting quote.

If another edit or lifecycle action changed the rule while the editor was open, Sibyl asks you to reopen it. A level/name edit on the same pair/feed remains possible when that feed is temporarily unavailable. Restore an archived rule before editing it.

## Where notifications appear

The top-bar bell shows unread price notifications and retains the previous recent agent/backtest activity below them. The unread dot counts price notifications, not run activity. Opening the bell or inbox does not mark anything read.

Use **Alerts → Inbox** for retained notification pages, **Mark read** for one notification or **Mark all read** for the whole inbox. Acknowledgment persists across restarts and never deletes the observed price/source evidence. Demo alerts are labeled in the bell and inbox too.

Delivery is currently **inside Sibyl only**. There is no email, push permission request, webhook or messaging recipient, and alerts cannot place orders or start strategies.

## Keep the API running

A dedicated server worker checks at most one due rule per second. Rules are normally due every 30 seconds; a busy queue or shared provider transport can take longer. Prices may come from the existing short cache, but their provider timestamp is rechecked on every evaluation. Repeated or older quotes cannot create a crossing or reset an alert. More than five minutes between usable observations, or a failed read, starts crossing observation afresh. Failures back off from one minute to a maximum of 15 minutes and preserve the last observation.

Checks continue with the browser closed while the API remains running. A stopped/sleeping host cannot monitor prices. After restart, saved armed rules resume using current quotes; prices that crossed and recovered while offline are not reconstructed. This is a polling convenience, not a guaranteed real-time alarm service.

See [implementation and HTTP contracts](../developers/alerts.md) and the [complete remaining-work inventory](../developers/backend-roadmap.md).
