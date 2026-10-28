"""Append-only, optimistic local decisions over immutable normalized funding facts."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import uuid4

from pydantic import Field

from sibyl.accounting.funding.rules import balance_effect, fingerprint, reviewed_change
from sibyl.models import Request


class FundingReviewConflict(ValueError):
    """The source observation or latest decision changed after the form was loaded."""


class ReviewVersion(Request):
    """Require the exact source and review revision displayed to the user."""

    source_version: str = Field(pattern=r"^[a-f0-9]{64}$")
    replace_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class ReviewFunding(ReviewVersion):
    """A user assertion about wallet scope and amount inclusion, never a native correction."""

    wallet_scope: Literal["configured", "outside"]
    amount_convention: Literal["total_debit", "principal", "net_credit", "gross_receipt"] | None = None
    fee_quantity: Decimal | None = Field(default=None, ge=0, le=Decimal("1e30"), allow_inf_nan=False)
    note: str = Field(min_length=1, max_length=1000)


class FundingReviews:
    """Keep a separate audit journal; saving or withdrawing a review never contacts an exchange."""

    def __init__(self, store):
        self.store = store
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS funding_reviews (
                    id TEXT PRIMARY KEY, event_id TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS funding_review_event ON funding_reviews(event_id);
            """)

    @staticmethod
    def latest(db, event_ids):
        """Load the latest revisions in batches inside the caller's consistent read transaction."""
        result = {}
        ids = list(event_ids)
        for offset in range(0, len(ids), 400):
            batch = ids[offset : offset + 400]
            placeholders = ",".join("?" for _ in batch)
            for row in db.execute(
                f"SELECT event_id,payload FROM funding_reviews WHERE rowid IN "
                f"(SELECT MAX(rowid) FROM funding_reviews WHERE event_id IN ({placeholders}) GROUP BY event_id)",
                batch,
            ):
                result[row[0]] = json.loads(row[1])
        return result

    @classmethod
    def enrich(cls, db, rows):
        """Attach derived effects without modifying stored provider observations."""
        reviews = cls.latest(db, [row["id"] for row in rows])
        return [{**row, "balance_effect": balance_effect(row, reviews.get(row["id"]))} for row in rows]

    @staticmethod
    def _event(db, event_id):
        row = db.execute("SELECT payload FROM funding_events WHERE id=?", (event_id,)).fetchone()
        if row is None:
            raise LookupError("Funding record not found.")
        return json.loads(row[0])

    def state(self, event_id):
        """Read the source, current effect and newest twenty audit decisions without native requests."""
        with self.store.db() as db:
            db.execute("BEGIN")
            event = self._event(db, event_id)
            history = [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT payload FROM funding_reviews WHERE event_id=? ORDER BY rowid DESC LIMIT 20",
                    (event_id,),
                )
            ]
            return {
                "event": event,
                "balance_effect": balance_effect(event, history[0] if history else None),
                "history": history,
                "history_limit": 20,
            }

    def save(self, event_id, body, *, withdraw=False):
        """Compare source and decision versions atomically, then append the explicit local choice."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            event = self._event(db, event_id)
            previous = self.latest(db, [event_id]).get(event_id)
            if (
                fingerprint(event) != body.source_version
                or (previous["id"] if previous else None) != body.replace_id
            ):
                raise FundingReviewConflict("Funding facts or review changed. Reload before saving.")
            if withdraw:
                if not previous or previous["action"] == "withdraw":
                    raise ValueError("There is no active review to withdraw.")
                decision = None
            else:
                if not balance_effect(event)["reviewable"]:
                    raise ValueError("This record is not eligible for a manual funding balance review.")
                decision = body.model_dump(mode="json", exclude={"source_version", "replace_id", "note"})
                reviewed_change(event, decision)
                if not body.note.strip():
                    raise ValueError("Add a note describing the evidence you reviewed.")
            saved = {
                "id": uuid4().hex,
                "source_version": body.source_version,
                "action": "withdraw" if withdraw else "review",
                "decision": decision,
                "note": "" if withdraw else body.note.strip(),
                "created_at": datetime.now(UTC).isoformat(),
            }
            db.execute(
                "INSERT INTO funding_reviews VALUES(?,?,?)",
                (saved["id"], event_id, json.dumps(saved, allow_nan=False)),
            )
        return self.state(event_id)
