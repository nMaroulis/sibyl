---
title: Private alert delivery
description: Select a checked Telegram, Discord, Slack, Signal, WhatsApp or email destination for future alerts.
---

# Private alert delivery

Keep every alert in Sibyl’s local inbox, and optionally receive future events through **Telegram, Discord, Slack, Signal, WhatsApp or email**. Price, account-risk, strategy, connection-read and order/fill rules use the same delivery controls. No AI model or trading permission is needed to deliver a recorded alert.

## Choose a destination

1. In **Settings → Messaging**, save and check a private connection. The connection is bound to the single recipient you configured; group chats and arbitrary addresses are not destinations.
2. Open **More → Alerts** and choose **Delivery** on a rule.
3. Select its destination card and review the displayed connection and recipient. Unconfigured/unverified cards direct you to Messaging; checked paused connections can be selected in advance.
4. Set the **Minimum interval** and **Delivery window**, then **Save delivery**. Enable the connection in Messaging when you want sends to run.

The local inbox always stays on. Saving/enabling/resuming a delivery policy starts from **future events**; existing inbox entries never get forwarded. The selected destination applies to later edits of that rule, so review it when changing private account selections. **Local only** or **Pause external delivery** withdraws unsent parts while keeping local monitoring active.

A card marked **Discord selected**, for example, means opt-in is saved. The rule and the selected connection must also be running. Paused, stale or changed destinations can produce a local skipped receipt; selection does not prove a message was sent. A one-time price rule in `triggered` state can finish its current notice; rearm the rule to monitor another cycle.

## WhatsApp reply window

WhatsApp sends only free-form private text inside the configured recipient’s active 24-hour reply window, with a one-minute safety margin. Outside that window an alert remains local; Sibyl does not send message templates or defer it until a new window opens. Send a new authenticated private message to open a later window. Both queue admission and sending check the window again. Deployment still requires the signed public HTTPS webhook described in [private messaging](../developers/private-messaging.md).

## Noise and freshness

| Setting | Meaning |
| --- | --- |
| Minimum interval | 1–1,440 minutes between queued messages for this rule; default 5 |
| Delivery window | 1–60 minutes from the original observation; default 10 |

Cooldown suppresses extra messages rather than accumulating a later backlog. Freshness uses the older of the observation and local receipt times. Stale, invalid or expired observations remain in the inbox; queued sends are checked again before transmission. Source, dates and Demo/test/paper attribution are retained.

The backend and computer must be running. Closing the browser is fine; a sleeping/stopped host cannot deliver. This is a bounded notification convenience rather than a guaranteed real-time alarm service.

## Pause, replace or change recipients

Pausing the alert rule stops its monitoring. Pausing external delivery stops its outbound notices. Pausing a messaging connection invalidates its queued parts; resuming uses a new control generation. An already admitted native send can finish, and confirmed parts remain visible. Changing the selected channel or policy withdraws the preceding policy’s queued remainder.

Replacing a private connection or changing its identity/recipient requires reviewing its current checked destination again. Existing notifications cannot silently move to another recipient. Telegram’s existing same-bot/user token behavior remains compatible, while queued work is still bound to its connection revision/control.

## Inspect what happened

**Show delivery history** records the channel, queued/sending/sent/rate-limited/skipped/failed/unconfirmed state, confirmed part count and exact available provider IDs. **Sent** means provider acceptance, not human receipt or read status. Text is split to the selected provider’s bounded limit; email uses a dedicated `Sibyl notification` subject without your incoming pairing phrase.

Only explicit rate-limit rejection is retried, with bounded attempts inside the original delivery window. Timeout, interrupted send or missing acceptance stays **Unconfirmed** and is never automatically repeated. Later parts remain blocked. Marking the inbox read does not cancel, send or retry delivery.

**Settings → Messaging → Review message deliveries** centralizes app-origin receipts across channels (plus Telegram conversation replies). **Review delivery** shows actual queued text and the recorded private target, permits withdrawal of an unsent remainder, and records separate received/dismissed acknowledgments. User review never invents a native message ID, changes the provider outcome or resends a message. Skipped notices that never queued parts retain their bounded preview instead of a nonexistent full queued body.

:::info[Private content]

Opted-in alert evidence, account labels and valuations may pass through the selected provider. Message bodies remain local SQLite text; channel credentials remain encrypted. Normal history returns bounded previews and outcomes; the explicit private review endpoint can return the queued body. Agents can explain the feature and read safe outcome summaries, but cannot authorize destinations, send or review messages.

:::

Known-terminal receipts retain about 200 per rule; unresolved uncertain receipts remain inspectable. Generic outbound webhooks/native push and additional media remain separate pending work. Scheduled text briefings support all six checked routes. Real provider acceptance is a deployment check; offline tests use controlled HTTP/SMTP responses.
