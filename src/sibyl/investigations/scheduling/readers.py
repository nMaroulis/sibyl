"""Small read-only schedule projections for the native Sibyl evidence tool."""

import json

from sibyl.investigations.scheduling.contracts import delivery_binding, delivery_channel
from sibyl.investigations.scheduling.repository import BriefingConflict, BriefingRepository


def briefing_snapshot(repository: BriefingRepository, investigation_id="", schedule_id=""):
    """Read real saved calendars and bounded delivery outcomes, excluding private user IDs."""
    store = repository.store
    schedules = (
        [repository.get(schedule_id)] if schedule_id else repository.list(investigation_id or None)[:20]
    )
    if investigation_id and any(item["investigation_id"] != investigation_id for item in schedules):
        raise BriefingConflict("This schedule belongs to a different investigation.")
    items = []
    for schedule in schedules:
        binding = delivery_binding(schedule)
        item = {
            key: value
            for key, value in schedule.items()
            if key not in {"telegram_binding", "delivery_binding", "private_target", "telegram_target"}
        }
        item["delivery_channel"] = delivery_channel(schedule)
        item["delivery_connection"] = (
            binding.get("bot_username")
            if delivery_channel(schedule) == "telegram"
            else delivery_channel(schedule)
        )
        item["telegram_bot"] = (
            binding.get("bot_username") if delivery_channel(schedule) == "telegram" else None
        )
        if schedule_id:
            item["recent_occurrences"] = []
            for occurrence in repository.history(schedule_id)[:5]:
                row = {
                    key: value
                    for key, value in occurrence.items()
                    if key not in {"deadline", "delivery_snapshot"}
                }
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
                            "channel": delivery.get("channel", "telegram"),
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
                "Optionally check a Telegram, Discord, Slack, Signal, WhatsApp or email connection in Settings → Messaging and select its private destination. Telegram additionally supports text documents.",
                "Pause or edit future automation in the schedule controls. Stop an already running report in Investigations.",
            ],
            "behavior": "The Python backend must be running. Missed times are recorded without catch-up inference. Private delivery is explicit, recipient-bound and frozen to the connection controls at acceptance. Paused/replaced connections leave affected reports local; WhatsApp also needs an active private reply window. No orders or other agent mutation actions are scheduled.",
        },
    }
