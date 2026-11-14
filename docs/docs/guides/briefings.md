---
title: Scheduled briefings
description: Revisit saved research daily or weekly, with optional checked private delivery through six messaging channels.
---

# Scheduled briefings

Turn a [saved investigation](investigations.md) into a regular research briefing. Sibyl consults the same native ProtoLink team, saves a new report version and optionally delivers it to one checked Telegram, Discord, Slack, Signal, WhatsApp or email connection.

:::tip[Start with a useful question]

Save “Summarize the selected market’s trend, volatility and recent news. Explain conflicting signals and missing evidence.” Run it once, review its sources, then choose **Schedule**.

:::

## Choose a calendar

Open **Sibyl → Investigations**, select a saved question and choose **Schedule**. Select **Daily** or **Weekly**, a local time and an IANA time zone such as `Europe/Zurich`. Weekly schedules also select a weekday. The editor starts with your browser’s time zone.

**Create schedule** authorizes future model calls at the displayed times. **Save paused** stores the calendar without enabling it. Neither action runs an investigation immediately. You can configure a schedule before connecting a model; attempts without a configured model are recorded as **Blocked**, with a settings link.

The Python backend must remain running. Closing the browser is fine. A stopped backend cannot wake your computer or deliver a briefing. Startup records overdue times as missed and advances to the next future time without spending model calls on a backlog.

| Situation | Behavior |
| --- | --- |
| Daylight-saving time skips your chosen local time | That date is skipped |
| The clock repeats your chosen local time | The first occurrence runs once |
| A report slot is occupied | Wait up to fifteen minutes from the due time, then record **Missed** |
| A model or source fails | Record the actual outcome; do not publish a successful report |
| The backend stops during research | Record interruption; do not replay inference on restart |

Each accepted briefing freezes the entire team’s model choices, including time spent waiting for capacity. New occurrences use the model settings then configured. Saved starting context selects feeds; workspace defaults resolve again for each new report. A new version uses evidence available at that time, not an exact replay of earlier observations.

## Optional private delivery {#optional-telegram-delivery}

Save and check a connection in **Settings → Messaging**. In the schedule editor choose its destination card and review the displayed connection/recipient. **Local only** keeps all reports in Sibyl. Choose **Summary & uncertainty** or **Full briefing** for selected message content. Saving a calendar never probes the messaging service or runs a model.

Delivery is opt-in per schedule. All six channels support bounded text messages; Telegram additionally supports one UTF-8 text document up to 64 KiB. The document option is shown only for Telegram. Other destinations reset to text and reject document requests rather than silently changing transport.

Each accepted briefing freezes the connection revision and pause-control generation alongside its private accepted model choices. A paused or unverified connection, closed WhatsApp window, recipient replacement or later pause/resume keeps that accepted briefing local. Enabling a connection before the report finishes cannot turn an earlier local-only/paused acceptance into a send. A changed private identity requires editing the schedule and selecting the checked target again. These controls do not create new inference or redirect a report to another recipient.

For WhatsApp, the recipient’s authenticated 24-hour reply window (minus a one-minute safety margin) must be open at acceptance and sending. Closed windows stay local without templates or waiting for a new window. See [private messaging](../developers/private-messaging.md) for setup.

Reports are saved regardless of delivery success. Queued delivery expires one hour after the report’s completion; text follows the selected provider’s message limits. Long text is bounded/shortened with a notice, while the full report and its source evidence remain in Investigations. Telegram documents preserve the complete selected content and reject oversized output explicitly.

:::info[Private research]

Selected findings, account labels and uncertainty can pass through your chosen messaging provider and AI providers. Queue bodies are local SQLite text; credentials stay encrypted. Agent schedule tools omit recipient bindings and connection-control details. Agents have no general message-send or schedule-editing tool.

:::

## Control and inspect

The schedule strip shows its next time, time zone, research state, chosen channel and actual message delivery outcome.

- **Run now / Run & deliver** requests one extra briefing with the selected delivery policy. It does not move the regular calendar time.
- **Pause / Resume** controls future research and withdraws unsent briefing messages. Pause the connection separately in Messaging to stop its future receive/send work.
- **Edit** changes the calendar or delivery selection and discards waiting work from the previous revision.
- **History** shows missed, blocked, completed and interrupted attempts, available report links, delivery errors and native provider IDs and confirmed message-part counts. **Review delivery** inspects the queued text and recorded target without resending it. The Messaging settings review list includes briefings from all six channels.
- **Archive** retires the calendar while retaining history. Archive it before deleting its investigation. A new schedule can then be created.

Pausing or archiving does not cancel an already admitted research run. Stop that run in Investigations. A native send already admitted can still finish; remaining unsent parts are withdrawn.

Only explicit provider rate-limit rejections retry within the delivery window. A timeout or interrupted send can leave **Uncertain** delivery: check the chat before requesting another briefing. Sibyl never automatically repeats an unconfirmed message, and later parts remain blocked. “Sent” means the provider accepted every part, not that the recipient read it.

## Keep report history manageable

Expand **Report retention** to keep 5–40 scheduled report versions per calendar, with a default of 20. Before a new scheduled run, older terminal versions from that same calendar are removed to make room. Manually started reports, other calendars and active work are preserved. Untouched conversations created only for removed scheduled reports are also cleaned up; conversations you continued are retained.

An investigation still has a total retained-run limit of 50. If manual reports fill that allowance, a scheduled attempt can miss its admission window. Export anything you need to retain separately. History keeps up to 200 recent occurrences per calendar and displays the latest 30; links indicate when a report was removed by retention. Completed delivery receipts have a separate bounded history, while unresolved uncertain sends remain inspectable.

These are read-only research schedules. Exchange execution, general background jobs and resumable multi-stage investigations are separate workflows.
