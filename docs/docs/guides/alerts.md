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

The top-bar bell shows unread price, account-risk, strategy and connection notifications and retains the previous recent agent/backtest activity below them. The unread dot counts retained alert notifications, not general run activity. Opening the bell or inbox does not mark anything read.

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

## Connection read-failure alerts

Open **Alerts → Connections → New connection alert**, or expand a source under **Settings → Market data → Source health** and choose **Watch read failures**. Choose a public exchange, data API or saved/previously observed account source. API keys and active accounts are not needed to save a watch; reads still require the source's normal setup. Saving an alert never connects, activates or polls it. Offline Demo has no connection to monitor; **View example** is an isolated illustration instead.

The default rule notifies after **three consecutive failed HTTP reads of the same operation**. It can notify again when **two successful reads of that operation** follow. You can choose 1–10 failures, 1–5 successes, a short name and whether to send the recovery notice. Successful quotes cannot resolve a balance-read incident. Unsupported market/request errors break counts without establishing failure or recovery. Rate limits, network failures and rejected authentication can establish a failure incident. A brief native read retry counts as another actual transport attempt.

The inbox says **Read failures observed** or **Successful reads resumed**, with the operation, original observation time, source/environment, sanitized reason and recorded read ID. These are transport outcomes: a successful HTTP response may still fail the module's data validation. Recovery does not verify current credentials, fresh prices, complete account readiness or continuous uptime. No reads means no current assessment; quiet/disconnected sources and silent worker outages do not trigger these rules.

Counters restart after a session/profile change, missing/out-of-order evidence or more than five minutes between reads. Retired profiles' late reads are ignored. Cache hits, admission deferrals, Demo and order submission/cancellation/preflight reads supply no evidence. Read evidence is retained for up to 14 days and globally bounded to 50,000 observations; recording or retention gaps may prevent a notice and are disclosed. An unresolved recorded incident remains historical evidence until enough confirming reads of the same operation arrive.

Each source permits one non-archived rule, with a separate budget of 50 connection rules. **Edit** saves paused; **Resume** starts from the current read-history tail and forgets old incident/count state. **Pause** and **Archive** stop processing only. **Restore paused** preserves past notifications without rearming. Armed cursors survive API restarts and catch up on retained evidence, so a notice can arrive after its observation time. Delivery stays in-app and requires the API running; no LLM or external messaging is involved.

## Account risk watches

**Alerts → Account risk** adds opt-in fixed-account value floors, asset concentration and observed-value drawdown limits. Complete fresh spot valuation is required; notices do not control orders or strategies. See [setup, formulas and limits](account-risk.md).
