---
title: Order and fill notifications
description: Follow retained execution changes per account through Sibyl's inbox and optional Telegram delivery.
---

# Order and fill notifications

Open **More → Alerts → Orders & fills**, select **New execution alert** and choose a saved account. Choose fills/corrections, cancellations/expiry, execution problems and optionally other status changes. One non-archived rule is allowed per account, within a workspace budget of 50.

Subscriptions start after the current observation journal. Editing saves paused; resuming starts a new future-only baseline. Pausing or archiving changes only the subscription, never an order, account, strategy, provider tracking or exchange permissions. Existing notifications stay in the shared inbox.

## What triggers a notification

- An observed cumulative fill increase, including a partial fill on an open order.
- A retained cancellation/expiry or selected status transition.
- A recorded unknown/rejected/failed execution state or changed synchronization error.
- A newly imported individual fill or a material correction to its quantities, price or reported fees.

These are **observations Sibyl already obtains** from order tracking, discovery and history imports. Creating a rule does not start new exchange polling. Imported fills can describe old executions; the message distinguishes imported evidence from cumulative order status. A cumulative total and its individual fills may produce separate, related notifications.

The **Inbox** and top-bar bell show the same dated evidence, account/environment and destination. Use **Delivery** on a saved rule to opt into Telegram for future events through the existing reviewed bot/private recipient. Cooldowns, expiry, delivery receipts, paused policies and uncertain-send handling are shared with other alert types. Saving a Telegram policy does not replay existing inbox entries.

Demo accounts use the same observation subscription for simulated orders and retained Demo fills; notifications show Demo. No demonstration subscription is created silently. Archived rules can be restored paused.

The journal retains approximately the latest 100,000 changes. If downtime passes a rule's retained cursor, the rule pauses with a gap message instead of pretending coverage. Review and resume from a new baseline. Broker can read subscriptions and recent evidence through native ProtoLink tools, but cannot create rules, change orders or send messages.
