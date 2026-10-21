"""Persistent one-shot price rules and a local notification inbox.

Rules pin an exact market and source. The worker performs one due quote read per
turn; an atomic rule transition and unique cycle key prevent duplicate notices.
No alert can execute an order, contact a recipient or change account selection.
"""

import json
import threading
import time
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import Field, field_validator

from sibyl.exchanges.base import number
from sibyl.market_data.control import ProviderDeferred
from sibyl.models import OrderRequest, Request


class PriceAlertCreate(Request):
    """Create one exact-pair threshold rule on an explicitly selected source."""

    source: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9:-]+$")
    symbol: str
    condition: Literal["above", "below"]
    threshold: float = Field(gt=0, le=1e15)
    label: str = Field(default="", max_length=80)

    @field_validator("symbol")
    @classmethod
    def canonical_symbol(cls, value):
        """Reuse the spot-order symbol grammar without granting order capabilities."""
        return OrderRequest.valid_symbol(value)

    @field_validator("label")
    @classmethod
    def plain_label(cls, value):
        """Store a short single-line user label, without control characters."""
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise ValueError("Use a single-line alert name.")
        return value.strip()


class PriceAlertAction(Request):
    """Pause, explicitly start a fresh cycle, or archive/restore a saved rule."""

    action: Literal["pause", "arm", "archive", "restore"]


def stamp() -> str:
    """Return an aware UTC observation time."""
    return datetime.now(UTC).isoformat()


def fresh_quote(ticker: dict, now: float) -> tuple[float, str]:
    """Require positive finite last-price evidence with a recent provider timestamp.

    Receipt time cannot substitute for the provider timestamp. The same freshness
    check runs after cache hits; future-dated quotes cannot satisfy an alert.
    """
    price = None if isinstance(ticker.get("price"), bool) else number(ticker.get("price"))
    timestamp = None if isinstance(ticker.get("timestamp"), bool) else number(ticker.get("timestamp"))
    if price is None or price <= 0:
        raise ValueError("No valid price is available from the selected feed.")
    if timestamp is None:
        raise ValueError("This quote has no provider timestamp; the alert remains armed.")
    age = now - timestamp / 1000
    if age > 300 or age < -60:
        raise ValueError("This quote is stale or future-dated; the alert remains armed.")
    return price, datetime.fromtimestamp(timestamp / 1000, UTC).isoformat()


class PriceAlerts:
    """Own local rules, bounded quote evaluation and durable unread notification state.

    This service assumes one API process. In-flight reads commit only if the rule
    revision is still current, so pausing, archiving or rearming cannot be undone
    by a delayed provider response. Triggered rules require explicit rearming.
    """

    limit = 50

    def __init__(self, market, store):
        self.market, self.store = market, store
        self._worker = threading.Lock()
        self._closed = False
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS price_alerts (
                    id TEXT PRIMARY KEY, status TEXT NOT NULL,
                    next_check REAL NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS price_alerts_due ON price_alerts(status,next_check);
                CREATE TABLE IF NOT EXISTS alert_notifications (
                    id TEXT PRIMARY KEY, rule_id TEXT NOT NULL, cycle INTEGER NOT NULL,
                    created_at TEXT NOT NULL, read_at TEXT, payload TEXT NOT NULL,
                    UNIQUE(rule_id,cycle)
                );
            """)

    @staticmethod
    def _read(db, identity):
        row = db.execute("SELECT payload FROM price_alerts WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise LookupError("Price alert not found.")
        return json.loads(row[0])

    @staticmethod
    def _write(db, rule):
        db.execute(
            "UPDATE price_alerts SET status=?,next_check=?,payload=? WHERE id=?",
            (rule["status"], rule["next_check"], json.dumps(rule, allow_nan=False), rule["id"]),
        )

    def rules(self, include_archived: bool = False, offset: int = 0) -> dict:
        """Page local rules without provider reads; archived history stays reachable."""
        if not 0 <= offset <= 1_000_000:
            raise ValueError("Choose a valid alert page.")
        with self.store.db() as db:
            db.execute("BEGIN")
            rows = db.execute(
                "SELECT payload FROM price_alerts WHERE ? OR status!='archived' ORDER BY rowid DESC LIMIT 50 OFFSET ?",
                (include_archived, offset),
            ).fetchall()
            count = db.execute("SELECT COUNT(*) FROM price_alerts WHERE status!='archived'").fetchone()[0]
            total = db.execute(
                "SELECT COUNT(*) FROM price_alerts WHERE ? OR status!='archived'", (include_archived,)
            ).fetchone()[0]
        return {
            "items": [json.loads(row[0]) for row in rows],
            "limit": self.limit,
            "count": count,
            "total": total,
            "offset": offset,
            "page_size": 50,
            "delivery": "in_app",
            "requires_running_server": True,
        }

    def create(self, request: PriceAlertCreate) -> dict:
        """Validate exact source support before arming; do not evaluate or fetch a quote."""
        with self.market.snapshot(request.source):
            metadata = self.market.metadata()
            if request.symbol not in {row["symbol"] for row in self.market.symbols()["items"]}:
                raise ValueError("This exact spot pair is unavailable on the selected feed.")
        rule = {
            "id": uuid4().hex,
            **request.model_dump(),
            "source_label": metadata["source_label"],
            "environment": metadata["environment"],
            "status": "armed",
            "cycle": 1,
            "revision": 1,
            "created_at": stamp(),
            "updated_at": stamp(),
            "next_check": 0,
            "last_checked_at": None,
            "last_price": None,
            "observed_at": None,
            "triggered_at": None,
            "error": None,
            "failures": 0,
        }
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if (
                db.execute("SELECT COUNT(*) FROM price_alerts WHERE status!='archived'").fetchone()[0]
                >= self.limit
            ):
                raise ValueError(
                    f"Keep at most {self.limit} non-archived price rules. Archive an old rule first."
                )
            db.execute(
                "INSERT INTO price_alerts VALUES(?,?,?,?)", (rule["id"], rule["status"], 0, json.dumps(rule))
            )
        return rule

    def change(self, identity: str, action: str) -> dict:
        """Persist explicit lifecycle changes; restoring always leaves a rule paused."""
        if action not in {"pause", "arm", "archive", "restore"}:
            raise ValueError("Unknown price alert action.")
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            rule = self._read(db, identity)
            if action == "restore":
                if rule["status"] != "archived":
                    return rule
                if (
                    db.execute("SELECT COUNT(*) FROM price_alerts WHERE status!='archived'").fetchone()[0]
                    >= self.limit
                ):
                    raise ValueError("Archive another rule before restoring this one.")
                rule["status"] = "paused"
            elif action == "archive":
                if rule["status"] == "archived":
                    return rule
                rule["status"] = "archived"
            elif rule["status"] == "archived":
                raise ValueError("Restore this rule before arming or pausing it.")
            elif action == "pause":
                if rule["status"] != "armed":
                    return rule
                rule["status"] = "paused"
            else:
                if rule["status"] == "armed":
                    return rule
                rule.update(
                    status="armed",
                    cycle=rule["cycle"] + 1,
                    triggered_at=None,
                    last_price=None,
                    observed_at=None,
                    last_checked_at=None,
                )
            rule.update(
                revision=rule["revision"] + 1, updated_at=stamp(), next_check=0, failures=0, error=None
            )
            self._write(db, rule)
        return rule

    def _observe(self, rule):
        """Read one source-pinned exact pair without requesting candles or private balances."""
        with self.market.snapshot(rule["source"]):
            if rule["symbol"] not in {row["symbol"] for row in self.market.symbols()["items"]}:
                raise ValueError("This exact market is no longer available from its selected feed.")
            return fresh_quote(self.market.valuation_ticker(rule["symbol"]), time.time())

    def _evaluate(self, identity: str) -> dict:
        with self.store.db() as db:
            rule = self._read(db, identity)
        if rule["status"] != "armed":
            return rule
        deferred = None
        try:
            price, observed_at = self._observe(rule)
            error = None
        except ProviderDeferred as exc:
            deferred = exc
            error = "Feed reads are queued or cooling down. The alert remains armed."
        except ValueError as exc:
            # Only our freshness messages are persisted; source/provider errors are sanitized below.
            safe = {
                "No valid price is available from the selected feed.",
                "This quote has no provider timestamp; the alert remains armed.",
                "This quote is stale or future-dated; the alert remains armed.",
                "This exact market is no longer available from its selected feed.",
            }
            error = (
                str(exc)
                if str(exc) in safe
                else "Selected feed unavailable. Check its source, credentials and account activation."
            )
        except Exception:
            error = "Selected feed unavailable. Check its source, credentials and account activation."
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self._read(db, identity)
            if current["status"] != "armed" or current["revision"] != rule["revision"]:
                return current
            current.update(last_checked_at=stamp(), error=error)
            if error:
                failures = min(10, current["failures"] + int(deferred is None))
                current.update(
                    failures=failures,
                    next_check=time.time()
                    + (deferred.retry_after if deferred else min(900, 30 * 2**failures)),
                )
            else:
                current.update(
                    last_price=price, observed_at=observed_at, failures=0, next_check=time.time() + 30
                )
                matched = (
                    price >= current["threshold"]
                    if current["condition"] == "above"
                    else price <= current["threshold"]
                )
                if matched:
                    current.update(status="triggered", triggered_at=stamp())
                    payload = {
                        "rule_id": identity,
                        "label": current["label"],
                        "symbol": current["symbol"],
                        "condition": current["condition"],
                        "threshold": current["threshold"],
                        "price": price,
                        "source": current["source"],
                        "source_label": current["source_label"],
                        "environment": current["environment"],
                        "observed_at": observed_at,
                        "cycle": current["cycle"],
                    }
                    db.execute(
                        "INSERT INTO alert_notifications VALUES(?,?,?,?,NULL,?)",
                        (
                            uuid4().hex,
                            identity,
                            current["cycle"],
                            current["triggered_at"],
                            json.dumps(payload, allow_nan=False),
                        ),
                    )
            self._write(db, current)
        return current

    def check(self, identity: str) -> dict:
        """Request a bounded manual check; respect persisted scheduling/backoff too."""
        with self._worker:
            with self.store.db() as db:
                rule = self._read(db, identity)
            if rule["status"] != "armed" or rule["next_check"] > time.time():
                return rule
            return self._evaluate(identity)

    def tick(self) -> None:
        """Evaluate at most one due rule fairly; retained rows resume after restart."""
        with self._worker:
            if self._closed:
                return
            with self.store.db() as db:
                row = db.execute(
                    "SELECT id FROM price_alerts WHERE status='armed' AND next_check<=? ORDER BY next_check,rowid LIMIT 1",
                    (time.time(),),
                ).fetchone()
            if row:
                self._evaluate(row[0])

    def close(self) -> None:
        """Wait for an in-flight read before the shared market adapters close."""
        with self._worker:
            self._closed = True

    def inbox(self, limit: int = 20, offset: int = 0) -> dict:
        """Page retained notifications, with unread totals independent of pagination."""
        if not 1 <= limit <= 100 or not 0 <= offset <= 1_000_000:
            raise ValueError("Choose a valid notification page.")
        with self.store.db() as db:
            db.execute("BEGIN")
            rows = db.execute(
                "SELECT * FROM alert_notifications ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            total, unread = db.execute(
                "SELECT COUNT(*),COALESCE(SUM(read_at IS NULL),0) FROM alert_notifications"
            ).fetchone()
        return {
            "items": [
                {
                    "id": row["id"],
                    "created_at": row["created_at"],
                    "read_at": row["read_at"],
                    **json.loads(row["payload"]),
                }
                for row in rows
            ],
            "total": total,
            "unread": unread,
            "limit": limit,
            "offset": offset,
            "delivery": "in_app",
        }

    def mark_read(self, identity: str | None = None) -> dict:
        """Persist read state idempotently; history remains available after acknowledging."""
        with self.store.db() as db:
            if identity is not None:
                if not db.execute("SELECT 1 FROM alert_notifications WHERE id=?", (identity,)).fetchone():
                    raise LookupError("Notification not found.")
                db.execute(
                    "UPDATE alert_notifications SET read_at=COALESCE(read_at,?) WHERE id=?",
                    (stamp(), identity),
                )
            else:
                db.execute("UPDATE alert_notifications SET read_at=? WHERE read_at IS NULL", (stamp(),))
        return self.inbox()


def alert_example() -> dict:
    """Return isolated illustrative rules/inbox data; never write to a workspace."""
    time_string = "2026-10-21T08:00:00+00:00"
    shared = {
        "source": "demo",
        "source_label": "Sibyl Demo",
        "environment": "demo",
        "cycle": 1,
        "created_at": time_string,
        "last_checked_at": time_string,
        "observed_at": time_string,
        "next_check": 0,
        "failures": 0,
        "error": None,
    }
    rules = [
        {
            **shared,
            "id": "example-btc",
            "label": "Bitcoin milestone",
            "symbol": "BTC/USDT",
            "condition": "above",
            "threshold": 100000,
            "last_price": 102400,
            "status": "triggered",
            "triggered_at": time_string,
        },
        {
            **shared,
            "id": "example-eth",
            "label": "Ether on my radar",
            "symbol": "ETH/USDT",
            "condition": "below",
            "threshold": 2800,
            "last_price": 3200,
            "status": "armed",
            "triggered_at": None,
        },
    ]
    notification = {
        key: rules[0][key]
        for key in (
            "label",
            "symbol",
            "condition",
            "threshold",
            "source",
            "source_label",
            "environment",
            "observed_at",
            "cycle",
        )
    }
    notification.update(
        id="example-notification", rule_id="example-btc", price=102400, created_at=time_string, read_at=None
    )
    return {
        "illustrative": True,
        "rules": {"items": rules, "count": 2, "limit": 50, "total": 2, "offset": 0, "page_size": 50},
        "inbox": {
            "items": [notification],
            "total": 1,
            "unread": 1,
            "limit": 20,
            "offset": 0,
            "delivery": "in_app",
        },
    }
