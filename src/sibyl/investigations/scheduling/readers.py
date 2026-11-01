"""Small read-only schedule projections for the native Sibyl evidence tool."""

import json

from sibyl.investigations.scheduling.repository import BriefingRepository


def briefing_snapshot(repository: BriefingRepository, investigation_id="", schedule_id=""):
    """Read real saved calendars and bounded delivery outcomes, excluding private user IDs."""
    store = repository.store
    schedules = (
        [repository.get(schedule_id)] if schedule_id else repository.list(investigation_id or None)[:20]
    )
    items = []
    for schedule in schedules:
        binding = schedule.get("telegram_binding") or {}
        item = {key: value for key, value in schedule.items() if key != "telegram_binding"}
        item["telegram_bot"] = binding.get("bot_username")
        if schedule_id:
            item["recent_occurrences"] = []
            for occurrence in repository.history(schedule_id)[:5]:
                row = {key: value for key, value in occurrence.items() if key != "deadline"}
                if occurrence.get("delivery_id"):
                    with store.db() as db:
                        saved = db.execute(
                            "SELECT payload FROM message_deliveries WHERE id=?", (occurrence["delivery_id"],)
                        ).fetchone()
                        counts = db.execute(
                            "SELECT COUNT(*),COALESCE(SUM(state='sent'),0) FROM message_delivery_parts WHERE delivery_id=?",
                            (occurrence["delivery_id"],),
                        ).fetchone()
                    if saved:
                        delivery = json.loads(saved[0])
                        row["delivery"] = {
                            "status": delivery["status"],
                            "error": delivery.get("error"),
                            "sent_parts": counts[1],
                            "total_parts": counts[0],
                        }
                item["recent_occurrences"].append(row)
        items.append(item)
    url = "/sibyl?tab=investigations"
    if investigation_id or (schedules and schedule_id):
        url += "&investigation=" + (investigation_id or schedules[0]["investigation_id"])
    return {
        "schedules": items,
        "url": url,
        "help": {
            "steps": [
                "Open a saved investigation in Sibyl → Investigations.",
                "Choose Schedule, select daily/weekly time and an IANA time zone, then save.",
                "Optionally check your Telegram bot in Settings → Messaging and select private-chat delivery.",
                "Pause or edit future automation in the schedule controls. Stop an already running report in Investigations.",
            ],
            "behavior": "The Python backend must be running. Missed times are recorded without catch-up inference. Telegram delivery is explicit and bound to the checked bot and private user. No orders or other agent mutation actions are scheduled.",
        },
    }
