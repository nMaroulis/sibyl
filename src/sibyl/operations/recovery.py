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
    workflow_snapshots = []
    with store.db() as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "private_order_streams" in tables:
            from uuid import uuid4

            for record in db.execute("SELECT account_id,payload FROM private_order_streams").fetchall():
                stream = json.loads(record["payload"])
                stream.update(
                    enabled=False,
                    state="paused",
                    generation=uuid4().hex,
                    revision=uuid4().hex,
                    wake_pending=True,
                    targets=[],
                )
                db.execute(
                    "UPDATE private_order_streams SET payload=? WHERE account_id=?",
                    (json.dumps(stream), record["account_id"]),
                )
        for row in db.execute("SELECT credentials FROM connections"):
            json.loads(store.cipher.decrypt(row[0]))
        db.execute("DELETE FROM active_accounts")
        if "investigation_runs" in tables:
            for record in db.execute(
                "SELECT payload FROM investigation_runs WHERE COALESCE(json_extract(payload,'$.durable'),0)=1 AND status IN ('queued','running','cancelling','input_required')"
            ).fetchall():
                run = json.loads(record[0])
                run.update(
                    status="interrupted",
                    finished_at=now,
                    error="Restored snapshot: native workflow continuation is quarantined. Start a new explicitly reviewed version.",
                )
                db.execute(
                    "UPDATE investigation_runs SET status='interrupted',payload=? WHERE id=?",
                    (json.dumps(run), run["id"]),
                )
                workflow_snapshots.append(run["id"])
        if "local_jobs" in tables:
            for record in db.execute("SELECT payload FROM local_jobs WHERE state='active'").fetchall():
                job = json.loads(record[0])
                job.update(state="paused", revision=job["revision"] + 1)
                db.execute(
                    "UPDATE local_jobs SET state='paused',revision=?,payload=? WHERE id=?",
                    (job["revision"], json.dumps(job), job["id"]),
                )
        if "local_job_runs" in tables:
            for record in db.execute(
                "SELECT payload FROM local_job_runs WHERE state IN ('queued','running')"
            ).fetchall():
                run = json.loads(record[0])
                run.update(
                    state="interrupted",
                    finished_at=now,
                    error="Restored snapshot: queued work was not replayed.",
                )
                db.execute(
                    "UPDATE local_job_runs SET state='interrupted',payload=? WHERE id=?",
                    (json.dumps(run), run["id"]),
                )
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
        for table in ("order_alerts", "forecast_tracking"):
            if table in tables:
                for record in db.execute(f"SELECT id,payload FROM {table}").fetchall():
                    item = json.loads(record[1])
                    if item["status"] in {"armed", "active"}:
                        item.update(status="paused", revision=item["revision"] + 1)
                        if table == "order_alerts":
                            db.execute(
                                "UPDATE order_alerts SET status='paused',payload=? WHERE id=?",
                                (json.dumps(item), record[0]),
                            )
                        else:
                            db.execute(
                                "UPDATE forecast_tracking SET payload=? WHERE id=?",
                                (json.dumps(item), record[0]),
                            )
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
    for run_id in workflow_snapshots:
        store.save_data_profile("workflow-models:" + run_id, {})
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

    media = store.data_profile("messaging:telegram-media")
    if media:
        from uuid import uuid4

        store.save_data_profile(
            "messaging:telegram-media",
            {
                **media,
                "documents": False,
                "photos": False,
                "audio": False,
                "revision": uuid4().hex,
            },
        )
    # Newly implemented channels use the same encrypted profile vault. Restored
    # native events/outcomes are evidence, never authorization to replay work.
    for channel in ("discord", "slack", "signal", "whatsapp", "email"):
        profile = store.data_profile("messaging:" + channel)
        if profile:
            store.save_data_profile(
                "messaging:" + channel,
                {
                    **profile,
                    "enabled": False,
                    "verified": False,
                    "error": "Restored snapshot: check native history and the private recipient before enabling.",
                },
            )
    with store.db() as db:
        if "channel_outbox" in tables:
            db.execute(
                "UPDATE channel_outbox SET state='uncertain',error='Restored snapshot: check actual recipient history.' WHERE state IN ('pending','sending')"
            )
        if "channel_messages" in tables:
            db.execute(
                "UPDATE channel_messages SET state='interrupted' WHERE state IN ('queued','processing')"
            )
