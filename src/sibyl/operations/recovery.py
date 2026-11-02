"""Quarantine automatic work in restored snapshots; never contact an exchange or messaging service."""

import json
from datetime import UTC, datetime


def prepare_recovery(store, backup_id):
    """Keep historical evidence but require explicit review before future automatic activity.

    A backup may predate real-world fills or message delivery. Its pending work
    cannot safely be replayed. Preserve native identifiers and unverified balances,
    pause strategy runs/calendars and quarantine pending sends as uncertain.
    """
    now = datetime.now(UTC).isoformat()
    with store.db() as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for row in db.execute("SELECT credentials FROM connections"):
            json.loads(store.cipher.decrypt(row[0]))
        db.execute("DELETE FROM active_accounts")
        if "strategy_jobs" in tables:
            for row in db.execute("SELECT id,payload FROM strategy_jobs").fetchall():
                job = json.loads(row[1])
                if job["status"] == "running":
                    job.update(
                        status="paused",
                        error="Restored snapshot: review actual exchange state before resuming.",
                        recovery_required=True,
                    )
                    db.execute("UPDATE strategy_jobs SET payload=? WHERE id=?", (json.dumps(job), row[0]))
        if "briefing_schedules" in tables:
            for row in db.execute(
                "SELECT id,payload FROM briefing_schedules WHERE status='armed'"
            ).fetchall():
                item = json.loads(row[1])
                item.update(status="paused", next_run_at=None, revision=item["revision"] + 1)
                db.execute(
                    "UPDATE briefing_schedules SET status='paused',next_at=NULL,payload=? WHERE id=?",
                    (json.dumps(item), row[0]),
                )
        if "briefing_occurrences" in tables:
            for row in db.execute(
                "SELECT id,payload FROM briefing_occurrences WHERE status IN ('waiting','running')"
            ).fetchall():
                item = json.loads(row[1])
                item.update(
                    status="interrupted",
                    finished_at=now,
                    error="Restored snapshot. No queued inference is replayed.",
                )
                db.execute(
                    "UPDATE briefing_occurrences SET status='interrupted',payload=? WHERE id=?",
                    (json.dumps(item), row[0]),
                )
        for table in ("telegram_outbox", "message_delivery_parts"):
            if table in tables:
                db.execute(
                    f"UPDATE {table} SET state='uncertain',error=? WHERE state IN ('pending','sending')",
                    ("Restored snapshot: check actual delivery before deciding to resend.",),
                )
        if "message_deliveries" in tables:
            for row in db.execute(
                "SELECT id,payload FROM message_deliveries WHERE state IN ('pending','sending','queued')"
            ).fetchall():
                item = json.loads(row[1])
                item.update(state="uncertain", error="Restored snapshot: actual delivery must be checked.")
                db.execute(
                    "UPDATE message_deliveries SET state='uncertain',payload=? WHERE id=?",
                    (json.dumps(item), row[0]),
                )
        if "telegram_updates" in tables:
            db.execute(
                "UPDATE telegram_updates SET state='interrupted' WHERE state IN ('pending','processing')"
            )
    profile = store.data_profile("messaging:telegram")
    if profile:
        store.save_data_profile(
            "messaging:telegram",
            {
                **profile,
                "enabled": False,
                "error": "Restored snapshot. Review and enable Telegram explicitly.",
            },
        )
    store.save_data_profile(
        "workspace-recovery", {"required": True, "restored_at": now, "source_backup": backup_id}
    )
