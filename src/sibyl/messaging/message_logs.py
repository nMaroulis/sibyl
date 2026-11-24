"""Clearable diagnostics kept separate from delivery, deduplication and chat records."""

import json
import re
import time

from protolink import ContextLimitError, RunAdmissionError

from sibyl.agents.utils.network import ModelRequired

_CONTEXT = re.compile(
    r"protected model input needs about (\d{1,12}) tokens; prompt allowance is (\d{1,12})", re.I
)


def initialize_message_logs(db, *, telegram):
    """Index retained messages once without recreating logs after a clear or restart."""
    source = "telegram" if telegram else "private"
    db.execute("BEGIN IMMEDIATE")
    db.execute("""
        CREATE TABLE IF NOT EXISTS messaging_message_logs (
            channel TEXT NOT NULL, revision TEXT NOT NULL, sequence INTEGER NOT NULL,
            payload TEXT NOT NULL, PRIMARY KEY(channel,revision,sequence)
        ) WITHOUT ROWID
    """)
    db.execute("CREATE TABLE IF NOT EXISTS messaging_log_imports (source TEXT PRIMARY KEY)")
    if db.execute("INSERT OR IGNORE INTO messaging_log_imports VALUES (?)", (source,)).rowcount:
        messages = (
            "SELECT 'telegram' AS channel,revision,rowid AS sequence,payload FROM telegram_updates WHERE state!='ignored'"
            if telegram
            else "SELECT channel,revision,rowid AS sequence,payload FROM channel_messages"
        )
        db.execute(f"""
            INSERT OR IGNORE INTO messaging_message_logs
            SELECT channel,revision,sequence,json_object('received_at',json_extract(payload,'$.received_at'))
            FROM ({messages})
            WHERE json_type(payload,'$.received_at') IN ('integer','real')
        """)


def add_message_log(db, channel, revision, sequence, received_at):
    """Attach a diagnostic to a newly admitted message in its ingestion transaction."""
    db.execute(
        "INSERT INTO messaging_message_logs VALUES (?,?,?,?)",
        (channel, revision, sequence, json.dumps({"received_at": received_at})),
    )


def update_message_log(db, channel, revision, sequence, **values):
    """Record a lifecycle change without resurrecting a cleared log."""
    db.execute(
        "UPDATE messaging_message_logs SET payload=json_patch(payload,?) WHERE channel=? AND revision=? AND sequence=?",
        (json.dumps(values), channel, revision, sequence),
    )


def message_error(error):
    """Classify known execution failures without persisting exception messages."""
    if isinstance(error, ContextLimitError):
        return "context_limit"
    if isinstance(error, ModelRequired):
        return "model_not_ready"
    if isinstance(error, RunAdmissionError):
        return error.code if error.code in {"queue_full", "queue_timeout"} else "processing_failed"
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, LookupError):
        return "conversation_missing"
    return "processing_failed"


def failure_detail(code, provider, report):
    """Convert native evidence into an allowlisted explanation and optional token counts."""
    metadata = ((report.final_task or {}).get("metadata") or {}) if report else {}
    error = metadata.get("error")
    if isinstance(error, dict):
        error = error.get("message")
    detail = {"code": code or "reason_unavailable"}
    if provider:
        detail["provider"] = provider
    if not isinstance(error, str):
        return detail
    if limit := _CONTEXT.search(error):
        return {
            **detail,
            "code": "context_limit",
            "estimated_tokens": int(limit[1]),
            "prompt_tokens": int(limit[2]),
        }
    if code and code != "processing_failed":
        return detail
    text = error.lower()
    if any(
        marker in text
        for marker in ("all connection attempts failed", "connection refused", "failed to connect")
    ):
        detail["code"] = "provider_unreachable"
    elif "failed to parse llm output" in text:
        detail["code"] = "invalid_model_output"
    elif "contextlimiterror" in text or "maximum context length" in text:
        detail["code"] = "context_limit"
    elif "timed out" in text:
        detail["code"] = "timeout"
    return detail


def log_storage(db, channel, revision):
    """Count retained log entries and UTF-8 payload bytes within the displayed connection."""
    count, size = db.execute(
        "SELECT COUNT(*),COALESCE(SUM(length(CAST(payload AS BLOB))),0) FROM messaging_message_logs WHERE channel=? AND revision=?",
        (channel, revision),
    ).fetchone()
    return {"entries": count, "bytes": size, "revision": revision}


def clear_message_logs(db, channel, revision):
    """Delete diagnostics for settled messages while protecting work with an open queue."""
    if channel == "telegram":
        protected = """
            SELECT 1 FROM telegram_updates m
            WHERE m.revision=log.revision AND m.rowid=log.sequence
            AND (m.state IN ('queued','processing') OR EXISTS (
                SELECT 1 FROM telegram_outbox p WHERE p.revision=m.revision
                AND p.update_id=m.update_id AND p.state IN ('pending','sending')
            ))
        """
    else:
        protected = """
            SELECT 1 FROM channel_messages m
            WHERE m.channel=log.channel AND m.revision=log.revision AND m.rowid=log.sequence
            AND (m.state IN ('queued','processing') OR EXISTS (
                SELECT 1 FROM channel_outbox p WHERE p.channel=m.channel AND p.revision=m.revision
                AND p.native_id=m.native_id AND p.state IN ('pending','sending')
            ))
        """
    cleared = db.execute(
        f"DELETE FROM messaging_message_logs AS log WHERE channel=? AND revision=? AND NOT EXISTS ({protected})",
        (channel, revision),
    ).rowcount
    return {"cleared": cleared, **log_storage(db, channel, revision)}


def message_finished(db, channel, revision, sequence, error=None):
    """Stamp the observed processing outcome without saving private diagnostic text."""
    values = {"finished_at": time.time()}
    if error is not None:
        values["failure_code"] = message_error(error)
    update_message_log(db, channel, revision, sequence, **values)
