---
title: Telegram alert delivery
description: Select future alerts for private Telegram delivery and inspect actual outcomes.
---

# Telegram alert delivery

Keep alerts in Sibyl’s local inbox, and optionally receive them through your private Telegram bot chat. This works for price rules, account-risk watches, strategy events and connection read failures. It needs no AI model or trading permission.

## Select a rule

1. [Set up Telegram](telegram.md) in **Settings → Messaging**, **Check bot**, then enable it. Open your bot’s private chat and press Start.
2. Open **More → Alerts** and choose **Delivery** on the rule you want to receive.
3. Select **Telegram**, reviewing the displayed bot and private numeric user ID.
4. Set a **Minimum interval** and **Delivery window**, then **Save delivery**.

In-app notifications always stay on. Delivery starts with events recorded after saving; existing inbox entries are never sent. Saving again or resuming delivery also starts from future events. The rule’s Telegram selection applies to its future edits, so review delivery when changing private account selections.

**Telegram selected** on a card means opt-in is saved. The rule and the Telegram connection must also be running. A triggered one-time price rule can deliver its current notice; rearming it begins another alert cycle. Demo/test environments and paper runs are identified in the message.

## Control noise and freshness

| Setting | Meaning |
| --- | --- |
| Minimum interval | At least 1–1,440 minutes between queued Telegram notifications for this rule; default 5 |
| Delivery window | At most 1–60 minutes from the original observation; default 10 |

The delivery interval is separate from price/risk rule reset conditions and their cooldowns. It suppresses extra Telegram messages rather than saving them to send later. Every suppressed notification still remains in the local inbox.

The delivery window checks both the observation and inbox receipt time. A strategy event discovered after a long shutdown can appear locally while being too old for Telegram. Pending sends are checked again before transmission. Reconnection does not create a stale-message backlog.

The Python backend must be running. Closing the browser is fine; a sleeping or stopped computer cannot deliver notifications. This is a polling convenience, not a guaranteed real-time alarm service.

## Pause and change recipients

**Pause Telegram delivery** inside a rule’s Delivery editor withdraws its unsent messages while leaving local alert monitoring active. Pause the alert rule itself to stop its monitoring. Editing, pausing, rearming or archiving a rule invalidates queued messages from its older revision.

**Pause Telegram** in Messaging stops future polls and all bot sends. Events admitted while Telegram is paused stay local, and resuming does not resend those events. A send already in flight can finish; confirmed parts stay visible.

A changed bot or private user never redirects old notifications. Open the rule’s Delivery editor and explicitly select/save the checked recipient again. Rotating a token for the same bot/user preserves future opt-in, but invalidates messages queued under the old connection.

## Inspect outcomes

**Alerts → Delivery** shows retained message receipts, including events suppressed by cooldown, stale observations and paused connections. A rule’s editor also has its own filtered history. Expand **Message & delivery details** to inspect the preview, part states, attempts and confirmed Telegram message IDs. Messaging shows alert counts separately from chat replies and research briefings.

- **Queued** is not a delivery confirmation.
- **Delivered** means Telegram confirmed every message part; it does not prove you read it.
- **Not sent** explains suppression, expiry or changed authorization.
- **Failed** records a definite rejection.
- **Unconfirmed** means the network outcome is ambiguous. Check your chat before requesting another notification; Sibyl never automatically repeats that part.

Only explicit rate-limit rejections retry, with bounded attempts inside the delivery window. Later parts stay blocked after an unconfirmed part. Marking an inbox entry read does not cancel, send or retry a message. There is no automatic resend control.

:::info[Private research]

Account labels, valuations and selected trigger evidence can pass through Telegram when you opt in. Message bodies are stored locally as SQLite text; bot credentials remain encrypted. Full queued bodies and tokens are not returned by the delivery API. Agents can explain setup but cannot change rules or authorize recipients.

:::

Known-terminal receipts retain approximately 200 recent deliveries per rule; unresolved uncertain receipts remain inspectable. The local inbox retains the original trigger evidence independently. Other messaging clients, webhooks and native push delivery remain pending.
