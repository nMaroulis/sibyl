"""Read recent activity and message logs without exposing private content."""

from datetime import datetime
from sqlite3 import Error as DatabaseError
from time import time
from typing import Literal

from sibyl.messaging.message_logs import failure_detail, log_storage

ACTIVITY_LIMIT = 8
TimelineWindow = Literal["1h", "1d", "1w", "30d", "all"]
WINDOW_SECONDS = {"1h": 3600, "1d": 86400, "1w": 604800, "30d": 2592000}
TIMELINE_BINS = 36

_TELEGRAM_MESSAGES = """
    SELECT log.sequence, m.update_id AS identity, m.state,
        json_extract(log.payload, '$.received_at') AS received_at
    FROM messaging_message_logs log JOIN telegram_updates m
        ON m.rowid=log.sequence AND m.revision=log.revision
    WHERE log.channel='telegram' AND log.revision=:revision
"""
_PRIVATE_MESSAGES = """
    SELECT log.sequence, m.native_id AS identity, m.state,
        json_extract(log.payload, '$.received_at') AS received_at
    FROM messaging_message_logs log JOIN channel_messages m
        ON m.rowid=log.sequence AND m.channel=log.channel AND m.revision=log.revision
    WHERE log.channel=:channel AND log.revision=:revision
"""
_NOTIFICATION_ROWS = """
    SELECT rowid AS sequence, state, COALESCE(json_extract(payload,'$.kind'),'briefing') AS kind,
        COALESCE(json_extract(payload,'$.updated_at'),created_at) AS updated_at
    FROM message_deliveries
    WHERE json_extract(payload,'$.connection_revision')=:revision
        AND COALESCE(json_extract(payload,'$.channel'),'telegram')=:channel
        AND kind IN ('briefing','alert')
"""
_NOTIFICATION_TIME = "(julianday(updated_at)-2440587.5)*86400"


def _reply_state(inbound_state, parts):
    if not parts:
        return inbound_state
    sent = parts.get("sent", 0)
    if sent == sum(parts.values()):
        return "sent"
    if parts.get("uncertain"):
        return "uncertain"
    if parts.get("failed") or parts.get("blocked"):
        return "partial" if sent else "failed"
    if parts.get("sending"):
        return "sending"
    if parts.get("pending"):
        return "pending"
    if sent:
        return "partial"
    return "withdrawn" if parts.get("withdrawn") else "skipped"


def _messages(db, channel, revision, limit=ACTIVITY_LIMIT, offset=0, *, start=None, end=None):
    """Summarize each accepted inbound message using the current states of its reply parts."""
    telegram = channel == "telegram"
    scope = (revision,) if telegram else (channel, revision)
    count_parts = (
        "SELECT state,COUNT(*) FROM telegram_outbox WHERE revision=? AND update_id=? GROUP BY state"
        if telegram
        else "SELECT state,COUNT(*) FROM channel_outbox WHERE channel=? AND revision=? AND native_id=? GROUP BY state"
    )
    source = _TELEGRAM_MESSAGES if telegram else _PRIVATE_MESSAGES
    bounds = "WHERE received_at BETWEEN :start AND :end" if start is not None else ""
    order = "received_at DESC, sequence DESC" if bounds else "sequence DESC"
    rows = db.execute(
        f"SELECT * FROM ({source}) {bounds} ORDER BY {order} LIMIT :limit OFFSET :offset",
        dict(channel=channel, revision=revision, start=start, end=end, limit=limit, offset=offset),
    )
    for sequence, identity, state, received_at in rows:
        parts = dict(db.execute(count_parts, (*scope, identity)).fetchall())
        yield {
            "id": f"message-{sequence}",
            "kind": "message",
            "at": received_at,
            "state": _reply_state(state, parts),
            "accepted_parts": parts.get("sent", 0),
            "total_parts": sum(parts.values()),
        }


def _notifications(db, channel, revision, *, start=None, end=None):
    """Return alert and briefing outcomes without loading their previews or destinations."""
    bounds = f"WHERE ({_NOTIFICATION_TIME}) BETWEEN :start AND :end" if start is not None else ""
    rows = db.execute(
        f"SELECT * FROM ({_NOTIFICATION_ROWS}) {bounds} ORDER BY updated_at DESC, sequence DESC LIMIT :limit",
        dict(channel=channel, revision=revision, start=start, end=end, limit=ACTIVITY_LIMIT),
    )
    for sequence, state, kind, updated_at in rows:
        yield {
            "id": f"delivery-{sequence}",
            "kind": kind,
            "at": datetime.fromisoformat(updated_at).timestamp(),
            "state": state,
        }


def recent_activity(db, channel, profile, *, include_notifications=True, start=None, end=None):
    """Return a bounded, content-free view scoped to the saved connection revision."""
    if not (revision := profile.get("revision")):
        return []
    items = list(_messages(db, channel, revision, start=start, end=end))
    if include_notifications:
        items.extend(_notifications(db, channel, revision, start=start, end=end))
    checked_at = profile.get("last_checked_at")
    if checked_at and (start is None or start <= checked_at <= end):
        items.append({"id": "connection-check", "kind": "check", "at": checked_at, "state": "verified"})
    return sorted(items, key=lambda event: event["at"], reverse=True)[:ACTIVITY_LIMIT]


def activity_timeline(db, channel, profile, window: TimelineWindow, *, now=None):
    """Aggregate every retained event into bounded buckets and return the latest rows in the range."""
    end = time() if now is None else now
    checked_at = profile.get("last_checked_at")
    revision = profile.get("revision")
    span = WINDOW_SECONDS.get(window)
    start = end - span if span else None
    if channel == "telegram":
        source = _TELEGRAM_MESSAGES
        replies = "telegram_outbox p WHERE p.revision=:revision AND p.update_id=m.identity"
    else:
        source = _PRIVATE_MESSAGES
        replies = (
            "channel_outbox p WHERE p.channel=:channel AND p.revision=:revision AND p.native_id=m.identity"
        )
    rows = db.execute(
        f"""
        WITH points(at, attention) AS (
            SELECT m.received_at, m.state IN ('failed','interrupted') OR EXISTS (
                SELECT 1 FROM {replies} AND p.state IN ('failed','uncertain','blocked')
            )
            FROM ({source}) m
            UNION ALL
            SELECT {_NOTIFICATION_TIME}, state IN ('failed','uncertain','partial','blocked','retrying')
            FROM ({_NOTIFICATION_ROWS})
            UNION ALL SELECT :checked_at, 0 WHERE :checked_at IS NOT NULL
        ), bounds AS (
            SELECT COALESCE(:start, MIN(:end-60, MIN(at)), :end-3600) AS start
            FROM points WHERE at <= :end
        )
        SELECT bounds.start, MIN(:bins-1, CAST((points.at-bounds.start)*:bins/(:end-bounds.start) AS INTEGER)) AS bin,
               COUNT(points.at), COALESCE(MAX(points.attention),0)
        FROM bounds LEFT JOIN points ON points.at BETWEEN bounds.start AND :end
        GROUP BY bin
        """,
        dict(
            channel=channel,
            revision=revision,
            checked_at=checked_at,
            start=start,
            end=end,
            bins=TIMELINE_BINS,
        ),
    ).fetchall()
    start = rows[0][0]
    bins = [{"count": 0, "attention": False} for _ in range(TIMELINE_BINS)]
    for _, index, count, attention in rows:
        if index is not None:
            bins[index] = {"count": count, "attention": bool(attention)}
    return {
        "window": window,
        "start": start,
        "end": end,
        "bins": bins,
        "events": recent_activity(db, channel, profile, start=start, end=end),
    }


def list_message_logs(db, channel, revision, limit, offset):
    """Page through the current connection’s stored diagnostics."""
    return {
        **log_storage(db, channel, revision),
        "items": list(_messages(db, channel, revision, limit, offset)),
    }


def message_log(db, channel, revision, sequence, *, run_store=None):
    """Describe one accepted message and its ordered reply parts for the current binding."""
    log = db.execute(
        """SELECT json_extract(payload,'$.received_at'),json_extract(payload,'$.started_at'),
               json_extract(payload,'$.finished_at'),json_extract(payload,'$.failure_code')
        FROM messaging_message_logs WHERE channel=? AND revision=? AND sequence=?""",
        (channel, revision, sequence),
    ).fetchone()
    if not log:
        raise LookupError("Message log is unavailable for this connection.")
    received_at, started_at, finished_at, failure_code = log
    if channel == "telegram":
        message = db.execute(
            """SELECT update_id,state,json_extract(payload,'$.request_id') AS request_id
            FROM telegram_updates WHERE rowid=? AND revision=? AND state!='ignored'""",
            (sequence, revision),
        ).fetchone()
        parts_query = """SELECT part,state,attempts,next_attempt,error,format FROM telegram_outbox
            WHERE revision=? AND update_id=? ORDER BY part"""
        scope = (revision,)
    else:
        message = db.execute(
            """SELECT native_id,state,json_extract(payload,'$.request_id') AS request_id
            FROM channel_messages WHERE rowid=? AND channel=? AND revision=?""",
            (sequence, channel, revision),
        ).fetchone()
        parts_query = """SELECT part,state,attempts,next_attempt,error FROM channel_outbox
            WHERE channel=? AND revision=? AND native_id=? ORDER BY part"""
        scope = (channel, revision)
    if not message:
        raise LookupError("Message activity is unavailable for this connection.")
    result = {
        "received_at": received_at,
        "started_at": started_at,
        "finished_at": finished_at,
        "state": message["state"],
        "parts": [dict(part) for part in db.execute(parts_query, (*scope, message[0]))],
    }
    request = (
        db.execute(
            """SELECT json_extract(payload,'$.provider'),json_extract(payload,'$.model'),
                      json_extract(payload,'$.run_id'),json_extract(payload,'$.started_at'),
                      json_extract(payload,'$.finished_at')
               FROM sibyl_requests WHERE id=?""",
            (message["request_id"],),
        ).fetchone()
        if message["request_id"]
        else None
    )
    provider, model, run_id, run_start, run_finish = request or (None, None, None, None, None)
    if provider and model:
        result["selected_model"] = {"provider": provider, "id": model}
    if not started_at and run_start:
        result["started_at"] = datetime.fromisoformat(run_start).timestamp()
    if not finished_at and run_finish:
        result["finished_at"] = datetime.fromisoformat(run_finish).timestamp()
    if result["state"] == "failed":
        report = None
        if run_id and run_store is not None:
            try:
                report = run_store.get_report(run_id)
            except (DatabaseError, ValueError):
                pass
        result["failure"] = failure_detail(failure_code, provider, report)
    return result
