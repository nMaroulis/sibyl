"""Sanitized observed execution changes, committed with their source order or fill."""

import json
from datetime import UTC, datetime


def schema(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS execution_events (id INTEGER PRIMARY KEY, account_id TEXT NOT NULL, payload TEXT NOT NULL)"
    )
    db.execute("CREATE INDEX IF NOT EXISTS execution_events_account ON execution_events(account_id,id)")


def append(db, account_id, payload):
    """Retain factual changes only; credentials and raw exchange responses never enter events."""
    db.execute(
        "INSERT INTO execution_events(account_id,payload) VALUES(?,?)",
        (account_id, json.dumps({**payload, "observed_at": datetime.now(UTC).isoformat()}, allow_nan=False)),
    )

    last = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    if last % 1000 == 0:
        db.execute("DELETE FROM execution_events WHERE id<=?", (last - 100000,))


def order_changed(db, before, after):
    if after.get("status") == "preview":
        return
    keys = ("status", "filled", "cancel_state", "sync_error")
    if before and all(before.get(key) == after.get(key) for key in keys):
        return
    status = after.get("status", "unknown")
    previous_fill = (before or {}).get("filled")
    filled = after.get("filled")
    groups = []
    if filled is not None and filled > (previous_fill or 0):
        groups.append("fills")
    if status == "closed" and (before or {}).get("status") != status and "fills" not in groups:
        groups.append("fills")
    if status in {"canceled", "expired"} and (before or {}).get("status") != status:
        groups.append("cancellations")
    if (
        status in {"unknown", "rejected", "failed"}
        or after.get("sync_error")
        or after.get("cancel_state") in {"unknown", "failed"}
    ):
        groups.append("attention")
    if (before or {}).get("status") != status:
        groups.append("status")
    if not groups:
        return
    action = status
    if after.get("cancel_state") in {"unknown", "failed"}:
        action = "cancellation_uncertain"
    elif after.get("sync_error"):
        action = "synchronization_problem"
    elif status not in {"closed", "canceled", "expired", "rejected"} and "fills" in groups:
        action = "partial_fill"
    request = after["request"]
    append(
        db,
        request["connection_id"],
        dict(
            type="order",
            groups=groups,
            intent_id=after["id"],
            native_order_id=after.get("exchange_order_id"),
            symbol=request["symbol"],
            side=request["side"],
            status=status,
            previous_status=(before or {}).get("status"),
            filled=filled,
            previous_filled=previous_fill,
            origin=after.get("origin", "sibyl"),
            action=action,
            cancel_state=after.get("cancel_state"),
            exchange=after.get("exchange"),
        ),
    )


def fill_changed(db, before, after):
    material = (
        "account_id",
        "symbol",
        "order_id",
        "side",
        "quantity",
        "price",
        "notional",
        "timestamp_ms",
        "fees",
        "fees_known",
    )
    if before and all(before.get(key) == after.get(key) for key in material):
        return
    append(
        db,
        after["account_id"],
        dict(
            type="fill",
            groups=["fills"],
            intent_id=None,
            native_order_id=after.get("order_id"),
            fill_id=after["id"],
            symbol=after["symbol"],
            side=after["side"],
            action="fill_corrected" if before else "fill_imported",
            quantity=after["quantity"],
            price=after["price"],
            fees=after["fees"],
            fees_known=after["fees_known"],
            exchange=after["exchange"],
            execution_at=after["timestamp_ms"],
        ),
    )
