"""Reviewed cancellation and bounded, read-only reconciliation of local order intents.

Provider writes are never retried. Status reads merge into the current intent,
preserve cumulative fills, and cannot turn a terminal order back into an open one.
SQLite persists commands before writes; per-intent locks serialize this process.
"""

import json
import threading
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import ccxt

from sibyl.exchanges.base import number
from sibyl.market_data.control import ProviderDeferred

TERMINAL = {"closed", "canceled", "expired", "rejected"}
OPEN = {"open", "submitted", "pending", "unknown", "submitting"}


def now() -> str:
    """Use aware timestamps for review expiry and human-readable observation times."""
    return datetime.now(UTC).isoformat()


class OrderLifecycle:
    """Track only workspace-submitted orders; never submit replacements or infer fills."""

    def __init__(self, trading):
        self.trading, self.store, self.market = trading, trading.store, trading.market
        self._locks = defaultdict(threading.RLock)
        self._worker = threading.Lock()
        self._closed = False
        with self.store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS order_cancellations (id TEXT PRIMARY KEY, intent_id TEXT NOT NULL, payload TEXT NOT NULL)"
            )

    def lock(self, identity: str):
        """Serialize refresh, cancellation and execution for one intent in this worker."""
        return self._locks[identity]

    @staticmethod
    def read(db, identity: str) -> dict:
        """Read the current intent inside the caller's transaction."""
        row = db.execute("SELECT payload FROM exchange_orders WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise LookupError("Exchange order intent not found.")
        return json.loads(row[0])

    @staticmethod
    def write(db, intent: dict) -> None:
        """Persist a sanitized intent, never raw provider exceptions or responses."""
        db.execute(
            "UPDATE exchange_orders SET payload=? WHERE id=?",
            (json.dumps(intent, allow_nan=False), intent["id"]),
        )

    def observe(self, identity: str, result: dict) -> dict:
        """Merge a native observation; partial-fill quantities are not invented executions."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            intent = self.read(db, identity)
            request = intent["request"]
            for key, expected in (
                ("symbol", request["symbol"]),
                ("side", request["side"]),
                ("id", intent.get("exchange_order_id")),
            ):
                if expected is not None and result.get(key) is not None and str(result[key]) != str(expected):
                    raise ValueError("Provider order identity does not match the reviewed intent.")
            filled = number(result.get("filled"))
            if filled is not None:
                if filled < 0 or filled > request["quantity"] + max(1e-10, request["quantity"] * 1e-8):
                    raise ValueError("Provider returned an invalid filled quantity.")
                if intent.get("filled") is not None and filled < intent["filled"]:
                    raise ValueError(
                        "Provider returned an older cumulative fill observation; retained status was preserved."
                    )
                intent["filled"] = filled
            remaining = number(result.get("remaining"))
            if remaining is not None and (
                remaining < 0 or remaining > request["quantity"] + max(1e-10, request["quantity"] * 1e-8)
            ):
                raise ValueError("Provider returned an invalid remaining quantity.")
            status = result.get("status") or intent["status"]
            status = "canceled" if status == "cancelled" else status
            if status not in OPEN | TERMINAL:
                status = "unknown"
            if intent["status"] in TERMINAL and status not in TERMINAL:
                status = intent["status"]
            if intent["status"] == "closed":
                status = "closed"
            intent["status"] = status
            if intent.get("cancel_state"):
                if status == "canceled":
                    intent.update(
                        cancel_state="confirmed",
                        cancel_message="Native status confirms cancellation. Any cumulative fills remain recorded.",
                    )
                elif status == "closed":
                    intent.update(
                        cancel_state="filled",
                        cancel_message="Native status reports a closed order. Inspect cumulative fills; cancellation cannot undo executions.",
                    )
                elif intent["cancel_state"] == "submitting":
                    intent.update(
                        cancel_state="unknown",
                        cancel_message="No final cancellation acknowledgment was retained. Check native status before a fresh review; no write is retried.",
                    )
            for key in ("remaining", "average", "cost"):
                value = number(result.get(key))
                if value is not None and value >= 0:
                    intent[key] = value
            intent.update(refreshed_at=now(), sync_failures=0, sync_error=None, next_check=time.time() + 20)
            if status in TERMINAL:
                intent["tracking"] = False
            intent["message"] = (
                "Native order status observed. Filled quantity is cumulative; import account fills for execution IDs and final fees."
            )
            self.write(db, intent)
        return intent

    def refresh(self, identity: str) -> dict:
        """Read a known native ID; only Demo can recover a lost ID from its local client key."""
        with self.lock(identity):
            with self.store.db() as db:
                intent = self.read(db, identity)
            connection = self.trading._connection(intent["request"]["connection_id"], allow_demo=True)
            if (
                not intent.get("exchange_order_id")
                and connection.exchange == "demo"
                and intent["status"] in {"submitting", "unknown"}
            ):
                with self.store.db() as db:
                    found = db.execute(
                        "SELECT payload FROM paper_limits WHERE request_key=?", (intent["client_order_id"],)
                    ).fetchone()
                    if found:
                        recovered = json.loads(found[0])
                        if (
                            recovered["symbol"] == intent["request"]["symbol"]
                            and recovered["side"] == intent["request"]["side"]
                            and recovered["amount"] == intent["request"]["quantity"]
                            and recovered["price"] == intent["request"].get("limit_price")
                        ):
                            intent["exchange_order_id"] = recovered["id"]
                            self.write(db, intent)
            if not intent.get("exchange_order_id"):
                raise ValueError(
                    "No exchange order ID is recorded. Check the exchange using the client order ID; do not resubmit an uncertain order."
                )
            with self.market.adapter(connection) as client:
                if connection.exchange == "demo":
                    client.match_order(intent["exchange_order_id"], intent["request"]["symbol"])
                result = client.fetch_order(intent["exchange_order_id"], intent["request"]["symbol"])
            return self.observe(identity, result)

    def preview_cancel(self, identity: str) -> dict:
        """Observe the native order before creating a short-lived cancellation review."""
        with self.lock(identity):
            intent = self.refresh(identity)
            if intent["status"] in TERMINAL or intent["status"] not in {"open", "pending", "submitted"}:
                raise ValueError("Only an observed open order can be reviewed for cancellation.")
            command = {
                "id": uuid4().hex,
                "intent_id": identity,
                "status": "preview",
                "exchange_order_id": intent["exchange_order_id"],
                "symbol": intent["request"]["symbol"],
                "account": intent["account"],
                "environment": intent.get("environment", "test" if intent["sandbox"] else "production"),
                "filled": intent.get("filled"),
                "remaining": intent.get("remaining"),
                "confirmation": "CANCEL " + intent["request"]["symbol"],
                "created_at": now(),
                "expires_at": (datetime.now(UTC) + timedelta(seconds=60)).isoformat(),
            }
            with self.store.db() as db:
                db.execute(
                    "INSERT INTO order_cancellations VALUES(?,?,?)",
                    (command["id"], identity, json.dumps(command)),
                )
            return command

    def cancel(self, identity: str, cancel_id: str, confirmation: str) -> dict:
        """Persist one cancellation attempt before its write; an acknowledgment is not a fill."""
        with self.lock(identity):
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT payload FROM order_cancellations WHERE id=? AND intent_id=?",
                    (cancel_id, identity),
                ).fetchone()
                if not row:
                    raise LookupError("Cancellation review not found.")
                command, intent = json.loads(row[0]), self.read(db, identity)
                if confirmation != command["confirmation"]:
                    raise ValueError("Type " + command["confirmation"] + " to confirm cancellation.")
                if command["status"] != "preview":
                    return intent
                if datetime.now(UTC) > datetime.fromisoformat(command["expires_at"]):
                    raise ValueError("Cancellation review expired; check the order again.")
                if intent["status"] in TERMINAL:
                    return intent
                if intent.get("exchange_order_id") != command["exchange_order_id"]:
                    raise ValueError("Order identity changed; review cancellation again.")
                if intent.get("cancel_requested_at") and (
                    intent.get("refreshed_at", "") <= intent["cancel_requested_at"]
                    or command["created_at"] <= intent["cancel_requested_at"]
                ):
                    raise ValueError(
                        "Check the native order after the previous cancellation attempt before reviewing another."
                    )
                command.update(status="submitting", attempted_at=now())
                intent.update(cancel_state="submitting", cancel_requested_at=command["attempted_at"])
                db.execute(
                    "UPDATE order_cancellations SET payload=? WHERE id=?", (json.dumps(command), cancel_id)
                )
                self.write(db, intent)
            try:
                connection = self.trading._connection(intent["request"]["connection_id"], allow_demo=True)
                with self.market.adapter(connection, write=True) as client:
                    result = client.cancel_order(command["exchange_order_id"], command["symbol"])
                command.update(
                    status="requested",
                    message="Cancellation requested. A fill can race cancellation; check native status for the outcome.",
                )
                # Only a native explicit terminal state may close the local order.
                if result.get("status") in TERMINAL:
                    self.observe(identity, result)
            except (ccxt.NetworkError, TimeoutError):
                command.update(
                    status="unknown",
                    message="Cancellation outcome is unknown. Check native status; this command will not be retried.",
                )
            except Exception:
                command.update(
                    status="unknown",
                    message="Cancellation was not confirmed. Check native status before a new review; no automatic retry occurs.",
                )
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                intent = self.read(db, identity)
                if intent["status"] not in TERMINAL:
                    intent.update(cancel_state=command["status"], cancel_message=command["message"])
                intent["next_check"] = 0
                db.execute(
                    "UPDATE order_cancellations SET payload=? WHERE id=?", (json.dumps(command), cancel_id)
                )
                self.write(db, intent)
            return intent

    def track(self, identity: str, enabled: bool) -> dict:
        """Persist tracking preference; enabling performs no order writes."""
        with self.lock(identity), self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            intent = self.read(db, identity)
            if intent["status"] == "preview" or intent["status"] in TERMINAL:
                raise ValueError("Tracking applies to nonterminal submitted orders only.")
            intent.update(tracking=enabled, next_check=0)
            self.write(db, intent)
            return intent

    def tick(self) -> None:
        """Check at most one due active-account order, with durable bounded backoff."""
        with self._worker:
            if self._closed:
                return
            with self.store.db() as db:
                row = db.execute(
                    "SELECT payload FROM exchange_orders WHERE json_extract(payload,'$.tracking')=1 AND COALESCE(json_extract(payload,'$.next_check'),0)<=? AND json_extract(payload,'$.status') NOT IN ('preview','closed','canceled','expired','rejected') ORDER BY COALESCE(json_extract(payload,'$.next_check'),0),rowid LIMIT 1",
                    (time.time(),),
                ).fetchone()
            if not row:
                return
            intent = json.loads(row[0])
            try:
                connection = self.trading._connection(intent["request"]["connection_id"], allow_demo=True)
                if not connection.active:
                    raise ValueError("Account is inactive; automatic status checks are paused.")
                self.refresh(intent["id"])
            except Exception as error:
                with self.lock(intent["id"]), self.store.db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    current = self.read(db, intent["id"])
                    deferred = isinstance(error, ProviderDeferred)
                    count = min(10, current.get("sync_failures", 0) + int(not deferred))
                    current.update(
                        sync_failures=count,
                        next_check=time.time() + (error.retry_after if deferred else min(900, 20 * 2**count)),
                        sync_error="Status unavailable or account inactive/disconnected. The last observation is retained; no write was retried.",
                    )
                    self.write(db, current)

    def close(self) -> None:
        """Wait for an in-flight status read before its shared adapter closes."""
        with self._worker:
            self._closed = True
