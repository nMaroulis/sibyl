"""Append-only observed source revisions, with bounded user-safe change summaries.

These are versions Sibyl observed, not an exchange's complete correction log.
Only material normalized provider facts enter the journal; account labels and
repeated unchanged polls do not create accounting revisions.
"""

import hashlib
import json
from uuid import uuid4

from sibyl.accounting.funding.rules import FACTS

FIELDS = tuple(key for key in FACTS if key not in {"id", "account_id", "exchange", "environment"}) + (
    "reference",
    "wallet_scope",
    "posted_ms",
)
NOTE = "Changes observed locally, not a complete provider revision history or independent settlement verification. Earlier unobserved versions may be unavailable."


def source_version(row):
    """Bind material source facts, including references used by transfer review."""
    fields = ("id", "native_id", "account_id", "exchange", "environment", *FIELDS)
    return hashlib.sha256(
        json.dumps({key: row.get(key) for key in fields}, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def record_version(db, row, previous, observed_at, origin):
    """Append a material change in the caller's source-update transaction."""
    if previous is not None and all(
        previous.get(key) == row.get(key)
        for key in ("id", "native_id", "account_id", "exchange", "environment", *FIELDS)
    ):
        return
    db.execute(
        "INSERT INTO funding_versions VALUES(?,?,?,?,?,?,?)",
        (
            uuid4().hex,
            row["id"],
            observed_at,
            origin,
            json.dumps(previous, allow_nan=False) if previous is not None else None,
            json.dumps(row, allow_nan=False),
            source_version(row),
        ),
    )


def public_version(row):
    """Expose changes to normalized facts, omitting credentials, metadata and local user notes."""
    before, after = (
        json.loads(row["before_payload"]) if row["before_payload"] else {},
        json.loads(row["after_payload"]),
    )
    return {
        "id": row["id"],
        "observed_at": row["observed_at"],
        "origin": row["origin"],
        "first_observation": row["before_payload"] is None,
        "before_asset": before.get("asset"),
        "after_asset": after.get("asset"),
        "changes": [
            {"field": key, "before": before.get(key), "after": after.get(key)}
            for key in FIELDS
            if before.get(key) != after.get(key)
        ],
    }


class FundingVersions:
    """Read twenty observed revisions for one retained funding record, without native requests."""

    def __init__(self, store):
        self.store = store

    @staticmethod
    def enrich(db, events):
        if not events:
            return events
        ids = [event["id"] for event in events]
        placeholders = ",".join("?" for _ in ids)
        latest = {
            row["event_id"]: row
            for row in db.execute(
                f"SELECT * FROM funding_versions WHERE rowid IN (SELECT MAX(rowid) FROM funding_versions WHERE event_id IN ({placeholders}) GROUP BY event_id)",
                ids,
            )
        }
        counts = {
            row[0]: row[1]
            for row in db.execute(
                f"SELECT event_id,COUNT(*) FROM funding_versions WHERE event_id IN ({placeholders}) GROUP BY event_id",
                ids,
            )
        }
        return [
            {
                **event,
                "observed_version_count": counts.get(event["id"], 0),
                "last_observed_change": public_version(latest[event["id"]])
                if event["id"] in latest
                else None,
            }
            for event in events
        ]

    def history(self, event_id):
        with self.store.db() as db:
            db.execute("BEGIN")
            source = db.execute("SELECT payload FROM funding_events WHERE id=?", (event_id,)).fetchone()
            if not source:
                raise LookupError("Funding record not found.")
            event = json.loads(source[0])
            rows = db.execute(
                "SELECT * FROM funding_versions WHERE event_id=? ORDER BY rowid DESC LIMIT 20", (event_id,)
            ).fetchall()
            total = db.execute(
                "SELECT COUNT(*) FROM funding_versions WHERE event_id=?", (event_id,)
            ).fetchone()[0]
        return {
            "event_id": event_id,
            "account": event["account"],
            "asset": event["asset"],
            "environment": event["environment"],
            "entries": [public_version(row) for row in rows],
            "total": total,
            "limit": 20,
            "note": NOTE,
        }
