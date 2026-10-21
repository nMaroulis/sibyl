# Price alerts & inbox

Open **More → Alerts**, or choose **Price alerts** on Markets. Alerts use public market data independently of your portfolio accounts, execution permission and AI model. No account or LLM is required for a public feed. A connected-account feed still needs that account active; API feeds need their saved key.

## Set a level

Choose **New price alert**, select a market feed, search its exact spot pair, and enter a quote-currency threshold. Choose **At or above** or **At or below**, and optionally name the rule. Saving arms it for its first check. It can trigger immediately if the first usable quote already meets the condition; it does not wait for a crossing from the other side.

Each rule pins its feed and exact pair. Changing the workspace's default feed later does not move existing alerts. USD and USDT are distinct pairs/currencies. Rule cards show the source, Demo/test/live environment, last price, provider time, check time and any error. Missing, undated, stale or invalid quotes leave the rule armed with an explanation.

Demo is an explicit offline market feed and its notifications carry a **Demo** badge. Selecting it does not activate the Demo portfolio wallet or disable an exchange account. **View example** shows illustrative rules and a notification without changing any settings, records or accounts; its action controls are disabled.

## One notification per cycle

An armed rule creates one retained in-app notification when it meets its level, then becomes **triggered**. The alert's current state and notification commit together. Restarting Sibyl or reopening a browser cannot duplicate that cycle's notification.

- **Pause** stops future checks. An in-flight response cannot override the pause.
- **Resume / Rearm** explicitly starts a new cycle. If the condition is still true, another notification can arrive on the next check.
- **Archive** removes a rule from the default list and stops checks. Its notifications remain.
- Enable **Include archived**, page through older rules if needed, then **Restore paused** to bring a rule back without reactivating it.
- **Check** evaluates a due rule while respecting the same scheduling and error backoff as the worker.

The workspace permits 50 non-archived rules, including paused and triggered ones. To change a rule's pair, feed or threshold, archive it and create a new one. Editing and recurring/crossing rules remain future work.

## Where notifications appear

The top-bar bell shows unread price notifications and retains the previous recent agent/backtest activity below them. The unread dot counts price notifications, not run activity. Opening the bell or inbox does not mark anything read.

Use **Alerts → Inbox** for retained notification pages, **Mark read** for one notification or **Mark all read** for the whole inbox. Acknowledgment persists across restarts and never deletes the observed price/source evidence. Demo alerts are labeled in the bell and inbox too.

Delivery is currently **inside Sibyl only**. There is no email, push permission request, webhook or messaging recipient, and alerts cannot place orders or start strategies.

## Keep the API running

A dedicated server worker checks at most one due rule per second. Rules are normally due every 30 seconds; a busy queue or shared provider transport can take longer. Prices may come from the existing short cache, but their provider timestamp is rechecked on every evaluation. Failures back off from one minute to a maximum of 15 minutes and preserve the last observation.

Checks continue with the browser closed while the API remains running. A stopped/sleeping host cannot monitor prices. After restart, saved armed rules resume using current quotes; prices that crossed and recovered while offline are not reconstructed. This is a polling convenience, not a guaranteed real-time alarm service.

See [implementation and HTTP contracts](../developers/alerts.md) and the [complete remaining-work inventory](../developers/backend-roadmap.md).
