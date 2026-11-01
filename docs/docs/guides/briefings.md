---
title: Scheduled briefings
description: Revisit saved research daily or weekly, with optional private Telegram delivery.
---

# Scheduled briefings

Turn a [saved investigation](investigations.md) into a regular research briefing. Sibyl consults the same native ProtoLink team, saves a new report version and optionally delivers it to your checked Telegram bot chat.

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

## Optional Telegram delivery

Set up and **Check bot** in [Settings → Messaging](telegram.md), then enable Telegram. In the schedule editor select **Deliver to Telegram** and review the displayed bot and private user. Choose a short summary or a fuller report with findings and source references.

Delivery is opt-in for each schedule and bound to that checked bot and private user. Changing the bot or user requires editing the schedule and selecting the current recipient again. Rotating a token for the same bot/user preserves the schedule binding, but withdraws messages queued under the previous connection.

The report is saved locally even if Telegram is paused, unavailable or delivery fails. Reports completed while the connection is paused are not saved for later sending. Queued deliveries expire one hour after report completion. Long briefings are split into plain-text message parts; the full report and evidence remain in Investigations.

:::info[Research leaves your workspace when delivery is selected]

Briefings may contain private account research. Selected content passes through Telegram and the AI providers chosen for the investigation. The local message queue contains plain text; bot/model credentials remain encrypted. Agents have no general send-message or schedule-editing tool.

:::

## Control and inspect

The schedule strip shows its next time, time zone, research state and Telegram delivery outcome.

- **Run now / Run & deliver** requests one extra briefing with the selected delivery policy. It does not move the regular calendar time.
- **Pause / Resume** controls future research and withdraws unsent briefing messages. Pause Telegram separately to stop all future bot sends and polling.
- **Edit** changes the calendar or delivery selection and discards waiting work from the previous revision.
- **History** shows missed, blocked, completed and interrupted attempts, available report links, delivery errors and confirmed message-part counts.
- **Archive** retires the calendar while retaining history. Archive it before deleting its investigation. A new schedule can then be created.

Pausing or archiving does not cancel an already admitted research run. Stop that run in Investigations. A Telegram HTTP request already in flight can still finish; remaining unsent parts are withdrawn.

Explicit Telegram rate limits retry within the delivery window. A timeout or interrupted send can leave **Uncertain** delivery: check the chat before requesting another briefing. Sibyl never automatically repeats an unconfirmed message, and later parts remain blocked. “Sent” means Telegram confirmed every part, not that you read it.

## Keep report history manageable

Expand **Report retention** to keep 5–40 scheduled report versions per calendar, with a default of 20. Before a new scheduled run, older terminal versions from that same calendar are removed to make room. Manually started reports, other calendars and active work are preserved. Untouched conversations created only for removed scheduled reports are also cleaned up; conversations you continued are retained.

An investigation still has a total retained-run limit of 50. If manual reports fill that allowance, a scheduled attempt can miss its admission window. Export anything you need to retain separately. History keeps up to 200 recent occurrences per calendar and displays the latest 30; links indicate when a report was removed by retention. Completed delivery receipts have a separate bounded history, while unresolved uncertain sends remain inspectable.

These are read-only research schedules. Exchange execution, general background jobs and resumable multi-stage investigations are separate workflows.
