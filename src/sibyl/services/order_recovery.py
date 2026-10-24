"""Recover missing native order IDs using bounded, durable, read-only evidence."""

import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import ccxt

from sibyl.exchanges.base import number
from sibyl.exchanges.order_lookup import RECOVERY_PROVIDERS, OrderLookupPage
from sibyl.market_data.control import ProviderDeferred

ELIGIBLE = {"unknown", "submitting"}
MESSAGES = {
    "available": "Look up this submission using its saved client order ID. No order is submitted again.",
    "searching": "Lookup is continuing. No native order ID has been attached yet.",
    "found": "Exact client ID and reviewed order details matched. Native status and execution checks can continue.",
    "not_found": "No match was returned in this lookup. This does not prove the order was never placed. Inspect the venue before creating another order.",
    "ambiguous": "More than one native order matched this client ID. No ID was attached; inspect the venue.",
    "incomplete": "The lookup reached its page budget. No ID was attached; inspect the venue before creating another order.",
    "mismatch": "Returned order evidence does not match the reviewed submission. No ID was attached; inspect the venue.",
    "error": "Lookup is temporarily unavailable. Retained evidence is preserved; no order was resubmitted.",
    "unsupported": "Client-ID lookup is unavailable for this client. Inspect the venue using the saved client order ID.",
}


def window(intent: dict) -> tuple[int, int]:
    """Bound order creation around the persisted review/submission, allowing modest clock skew."""
    created = datetime.fromisoformat(intent["created_at"])
    submitted = datetime.fromisoformat(intent.get("submitted_at") or intent["expires_at"])
    if created.tzinfo is None or submitted.tzinfo is None:
        raise ValueError("Submission timestamps require timezone information.")
    if not created <= submitted <= created + timedelta(minutes=2):
        raise ValueError("Submission timestamps are inconsistent with the reviewed window.")
    return int((created - timedelta(minutes=5)).timestamp() * 1000), int(
        (submitted + timedelta(minutes=15)).timestamp() * 1000
    )


def validate_candidate(intent: dict, order: dict) -> None:
    """Require an exact client ID and immutable reviewed details before accepting identity."""
    native_id = order.get("id")
    if (
        not isinstance(native_id, str)
        or not native_id
        or len(native_id) > 200
        or any(ord(char) < 32 for char in native_id)
    ):
        raise ValueError("Invalid native order identity.")
    request = intent["request"]
    for key, expected in (
        ("clientOrderId", intent["client_order_id"]),
        ("symbol", request["symbol"]),
        ("side", request["side"]),
        ("type", request.get("order_type", "market")),
    ):
        if order.get(key) != expected:
            raise ValueError("Recovery identity or order type differs.")
    amount = number(order.get("amount"))
    if amount is None or Decimal(str(amount)) != Decimal(str(request["quantity"])):
        raise ValueError("Recovery quantity differs.")
    if request.get("order_type", "market") == "limit":
        if order.get("timeInForce") not in {None, "GTC"}:
            raise ValueError("Recovery time in force differs.")
        price = number(order.get("price"))
        if price is None or Decimal(str(price)) != Decimal(str(request["limit_price"])):
            raise ValueError("Recovery limit price differs.")
    start, end = window(intent)
    timestamp = number(order.get("timestamp"))
    if timestamp is None or not start <= timestamp < end:
        raise ValueError("Recovery order creation time differs or is unavailable.")


class OrderRecovery:
    """Persist private lookup cursors/candidates, committing adopted IDs with native observations.

    One check reads one provider page. Automatic checks make at most three
    complete no-match passes, or five consecutive failed reads, then pause.
    History scans stop after ten pages. A lookup miss never authorizes resubmission.
    """

    def __init__(self, trading):
        self.trading, self.store = trading, trading.store
        with self.store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS order_recovery (intent_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )

    @staticmethod
    def read(db, identity: str) -> dict | None:
        row = db.execute("SELECT payload FROM order_recovery WHERE intent_id=?", (identity,)).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def write(db, identity: str, job: dict) -> None:
        db.execute(
            "INSERT INTO order_recovery VALUES(?,?) ON CONFLICT(intent_id) DO UPDATE SET payload=excluded.payload",
            (identity, json.dumps(job, allow_nan=False)),
        )

    def summary(self, db, intent: dict) -> dict:
        """Expose safe progress only; GET never starts a lookup or returns native cursor tokens."""
        job = self.read(db, intent["id"]) or {}
        supported = intent["exchange"] in RECOVERY_PROVIDERS
        eligible = intent["status"] in ELIGIBLE and not intent.get("exchange_order_id")
        state = job.get(
            "state", "available" if eligible and supported else "unsupported" if eligible else "not_needed"
        )
        if intent.get("exchange_order_id") and state != "found":
            state = "not_needed"
        return {
            "supported": supported,
            "eligible": eligible,
            "state": state,
            "message": MESSAGES.get(
                state, "A native order ID is already recorded, or this intent was not submitted."
            ),
            **{key: job[key] for key in ("pages", "passes", "checked_at", "recovered_at") if key in job},
        }

    def resume(self, db, intent: dict) -> None:
        """An explicit tracking resume renews failed/no-match budgets without discarding unfinished pages."""
        job = self.read(db, intent["id"])
        if job and intent["status"] in ELIGIBLE and not intent.get("exchange_order_id"):
            job.update(passes=0, failures=0)
            if job["state"] != "searching":
                job.update(cursor={}, seen=[], candidates={}, pages=0, complete=False, state="available")
            self.write(db, intent["id"], job)

    def accept(self, db, intent: dict, order: dict) -> None:
        """Validate identity and reserve its local attribution in the observation transaction."""
        if intent.get("exchange_order_id") or intent["status"] not in ELIGIBLE:
            raise ValueError("This submission no longer needs identity recovery.")
        validate_candidate(intent, order)
        collision = db.execute(
            "SELECT 1 FROM exchange_orders WHERE id<>? AND json_extract(payload,'$.request.connection_id')=? "
            "AND json_extract(payload,'$.exchange_order_id')=? LIMIT 1",
            (intent["id"], intent["request"]["connection_id"], order["id"]),
        ).fetchone()
        if collision:
            raise ValueError("Native order already belongs to another local intent.")
        connection = self.trading._connection(intent["request"]["connection_id"], allow_demo=True)
        if connection.exchange != intent["exchange"] or connection.sandbox != intent["sandbox"]:
            raise ValueError("Account environment changed during recovery.")
        intent["exchange_order_id"] = order["id"]
        job = self.read(db, intent["id"]) or {}
        job.update(
            state="found",
            checked_at=datetime.now(UTC).isoformat(),
            recovered_at=datetime.now(UTC).isoformat(),
        )
        self.write(db, intent["id"], job)

    def check(self, identity: str, *, manual: bool = False) -> dict:
        """Read one lookup page, never retrying submission/cancellation or claiming absence."""
        with self.trading.lifecycle.lock(identity):
            with self.store.db() as db:
                intent = self.trading.lifecycle.read(db, identity)
                if intent.get("exchange_order_id"):
                    return intent
                if intent["status"] not in ELIGIBLE:
                    raise ValueError("Only uncertain submitted orders can be recovered.")
                job = self.read(db, identity) or {
                    "state": "available",
                    "cursor": {},
                    "seen": [],
                    "candidates": {},
                    "pages": 0,
                    "passes": 0,
                    "failures": 0,
                    "complete": False,
                }
            if manual and job["state"] not in {"searching", "error"}:
                job.update(cursor={}, seen=[], candidates={}, pages=0, complete=False)
            if manual:
                job["failures"] = 0
            try:
                if intent["exchange"] not in RECOVERY_PROVIDERS:
                    raise ccxt.NotSupported("Unreviewed recovery provider.")
                connection = self.trading._connection(intent["request"]["connection_id"], allow_demo=True)
                if connection.exchange != intent["exchange"] or connection.sandbox != intent["sandbox"]:
                    raise ValueError("Account environment differs.")
                if not manual and not connection.active:
                    raise ccxt.ExchangeNotAvailable("Account is inactive.")
                if job["complete"]:
                    job.update(cursor={}, seen=[], candidates={}, pages=0, complete=False)
                if job["pages"] >= 10:
                    job["state"] = "incomplete"
                else:
                    start, end = window(intent)
                    with self.trading.market.adapter(connection) as client:
                        if not hasattr(client, "fetch_order_lookup_page"):
                            raise ccxt.NotSupported("Client has no reviewed lookup.")
                        page = client.fetch_order_lookup_page(
                            intent["client_order_id"], intent["request"]["symbol"], job["cursor"], start, end
                        )
                    if (
                        not isinstance(page, OrderLookupPage)
                        or not isinstance(page.candidates, list)
                        or not isinstance(page.cursor, dict)
                        or not isinstance(page.complete, bool)
                        or len(page.candidates) > 100
                    ):
                        raise ValueError("Invalid lookup page.")
                    signature = hashlib.sha256(json.dumps(page.cursor, sort_keys=True).encode()).hexdigest()
                    if not page.complete and (page.cursor == job["cursor"] or signature in job["seen"]):
                        raise ValueError("Lookup cursor did not advance.")
                    candidate_job = {**job, "candidates": dict(job["candidates"])}
                    for order in page.candidates:
                        validate_candidate(intent, order)
                        candidate_job["candidates"][order["id"]] = order
                        if len(candidate_job["candidates"]) > 1:
                            break
                    candidate_job.update(
                        cursor=page.cursor,
                        seen=[*job["seen"], signature],
                        pages=job["pages"] + 1,
                        complete=page.complete,
                        failures=0,
                        state="searching",
                        checked_at=datetime.now(UTC).isoformat(),
                    )
                    if len(candidate_job["candidates"]) > 1:
                        candidate_job["state"] = "ambiguous"
                    elif page.complete:
                        candidate_job["passes"] += 1
                        candidate_job["state"] = "not_found" if not candidate_job["candidates"] else "found"
                    elif candidate_job["pages"] >= 10:
                        candidate_job["state"] = "incomplete"
                    with self.store.db() as db:
                        # "found" and the adopted ID become public in one observation transaction.
                        self.write(
                            db,
                            identity,
                            {**candidate_job, "state": "searching"}
                            if candidate_job["state"] == "found"
                            else candidate_job,
                        )
                    job = candidate_job
                    if job["state"] == "found":
                        return self.trading.lifecycle.observe(
                            identity, next(iter(job["candidates"].values())), recovered=True
                        )
            except Exception as error:
                deferred = isinstance(error, ProviderDeferred)
                job["failures"] += int(not deferred)
                job["state"] = (
                    "unsupported"
                    if isinstance(error, ccxt.NotSupported)
                    else "mismatch"
                    if isinstance(error, ValueError)
                    else "error"
                )
                delay = error.retry_after if deferred else min(900, 20 * 2 ** min(job["failures"], 6))
            else:
                delay = 1 if job["state"] == "searching" else 60 if job["passes"] == 1 else 300
            job["checked_at"] = datetime.now(UTC).isoformat()
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                current = self.trading.lifecycle.read(db, identity)
                if current.get("exchange_order_id"):
                    return current
                self.write(db, identity, job)
                current.update(
                    next_check=time.time() + delay,
                    message=MESSAGES[job["state"]],
                    sync_error=MESSAGES[job["state"]],
                )
                if (
                    job["state"] in {"ambiguous", "incomplete", "mismatch", "unsupported"}
                    or job["passes"] >= 3
                    or job["failures"] >= 5
                ):
                    current["tracking"] = False
                self.trading.lifecycle.write(db, current)
            return current
