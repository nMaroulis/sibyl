# Alerts & inbox

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

The top-bar bell shows unread price and strategy notifications and retains the previous recent agent/backtest activity below them. The unread dot counts retained alert notifications, not general run activity. Opening the bell or inbox does not mark anything read.

Use **Alerts → Inbox** for retained notification pages, **Mark read** for one notification or **Mark all read** for the whole inbox. Acknowledgment persists across restarts and never deletes the observed price/source evidence. Demo alerts are labeled in the bell and inbox too.

Delivery is currently **inside Sibyl only**. There is no email, push permission request, webhook or messaging recipient, and alerts cannot place orders or start strategies.

## Keep the API running

A dedicated server worker checks at most one due rule per second. Rules are normally due every 30 seconds; a busy queue or shared provider transport can take longer. Prices may come from the existing short cache, but their provider timestamp is rechecked on every evaluation. Repeated or older quotes cannot create a crossing or reset an alert. More than five minutes between usable observations, or a failed read, starts crossing observation afresh. Failures back off from one minute to a maximum of 15 minutes and preserve the last observation.

Checks continue with the browser closed while the API remains running. A stopped/sleeping host cannot monitor prices. After restart, saved armed rules resume using current quotes; prices that crossed and recovered while offline are not reconstructed. This is a polling convenience, not a guaranteed real-time alarm service.

See [implementation and HTTP contracts](../developers/alerts.md) and the [complete remaining-work inventory](../developers/backend-roadmap.md).

## Strategy alerts

Open **Alerts → Strategy alerts**, or choose **Run alerts** in any saved strategy's monitor. Choose **New strategy alert**, select a paper or exchange run and choose one or both categories:

- **Pauses, errors & recovery:** recorded manual/safety pauses, evaluation errors and recovery observations.
- **Run lifecycle:** recorded resumes, stops, Stop & cancel requests and transitions to completed. A final sell can complete a paper run; its completion is recognized even though the journal action is `SELL`.

Watching is opt-in, with one non-archived rule per run and at most **50 non-archived strategy rules**, separate from the 50 price-rule budget. An account need not remain active to read already committed journal events. No model or provider read is needed by the notification worker.

**Watch strategy events** starts at the run's current journal tail. Existing pauses/errors and earlier lifecycle events do not produce immediate notifications. It watches that exact saved run, not future runs with the same algorithm. **View example** shows an isolated rule and notification; it creates no job, rule or connected account.

**Pause alert** stops notifications only; the strategy continues in its existing state. **Resume alert** starts at the current journal tail and skips everything recorded during the alert's pause. Editing saves the alert paused, preserves old notification evidence, and requires an explicit Resume. **Archive** is reversible; **Restore paused** does not resume observation. A stale editor/action cannot overwrite newer settings.

Armed rules keep their position across an API restart. Events committed after that position, including a startup safety pause of an exchange run, are processed once when the worker resumes. A dedicated local loop processes at most one rule and 100 journal events per second; rules normally become due again after five seconds. A backlog or many active rules can delay delivery. There is no new exchange polling and no reconstruction of events that were never recorded.

Notifications appear in the shared **Inbox** and top-bar bell with the exact run, source, Paper/Exchange mode, Demo/test attribution, original journal reason and event time. Receipt time and journal time are distinct. The bell's strategy entries and **Open strategy monitor** link lead back to that run; opening them does not acknowledge unread state. Use **Mark read** or **Mark all read** for acknowledgment.

Only recorded journal changes are monitored. An `ERROR` notice does not imply the run stopped, a manual pause is not necessarily a failure, and a Stop & cancel notice reports the request—not successful native cancellation. A completion notice does not prove an exchange position is flat. Inspect the monitor's orders, fills and holdings. Notifications cannot control execution, cancel orders or liquidate. Silent worker outages, every-fill/order policies, portfolio-risk and connection-failure alerts remain pending. Delivery stays in-app; Telegram chat does not automatically receive these notices.
