"""Persistent opt-in private order observers with coalesced REST wake-up recovery.

One process owns a bounded set of native async clients. Restart/reconnect leaves
pending read wakeups before subscribing. Existing REST trackers/discovery retain
all financial validation, pagination, backoff and explicit user pause semantics.
No stream message can place/cancel/replace an order or infer a fill.
"""

import asyncio
import hashlib
import json
import math
import re
import threading
import time
from datetime import UTC, datetime
from uuid import uuid4

import ccxt
from pydantic import Field

from sibyl.exchanges.streams.clients import PROVIDERS, create_stream
from sibyl.exchanges.streams.wakeups import OrderWakeups
from sibyl.models import Request


class StreamAction(Request):
    enabled: bool = Field(strict=True)
    revision: str = Field(pattern=r"^[a-f0-9]{32}$")


def stamp():
    return datetime.now(UTC).isoformat()


class PrivateAccountStreams:
    """Own at most eight opt-in connection streams; expose actual signals, not fake liveness."""

    def __init__(self, store, trading, *, factory=create_stream):
        self.store, self.trading, self.factory = store, trading, factory
        self.wakeups = OrderWakeups(trading)
        self.lock = threading.RLock()
        self.tasks = {}
        self.closed = False
        with store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS private_order_streams(account_id TEXT PRIMARY KEY,payload TEXT NOT NULL)"
            )
            for record in db.execute("SELECT account_id,payload FROM private_order_streams").fetchall():
                row = json.loads(record["payload"])
                row.update(
                    state="queued" if row["enabled"] else "paused",
                    wake_pending=bool(row["enabled"]),
                    full_sweep=True,
                    targets=[],
                    next_attempt=0,
                )
                self._write(db, record["account_id"], row)

    @staticmethod
    def _key_version(db, account_id):
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='connection_key_changes'"
        ).fetchone():
            return 0
        return db.execute(
            "SELECT COALESCE(MAX(id),0) FROM connection_key_changes WHERE account_id=?", (account_id,)
        ).fetchone()[0]

    @staticmethod
    def _read(db, identity):
        record = db.execute(
            "SELECT payload FROM private_order_streams WHERE account_id=?", (identity,)
        ).fetchone()
        return json.loads(record[0]) if record else None

    @staticmethod
    def _write(db, identity, row):
        db.execute(
            "INSERT INTO private_order_streams VALUES(?,?) ON CONFLICT(account_id) DO UPDATE SET payload=excluded.payload",
            (identity, json.dumps(row, allow_nan=False)),
        )

    def snapshot(self):
        """Read actual connection/state counters without authenticating or opening a socket."""
        with self.store.db() as db:
            rows = {
                record[0]: json.loads(record[1])
                for record in db.execute("SELECT * FROM private_order_streams")
            }
        accounts = []
        for connection in self.store.connections():
            if connection.exchange == "demo":
                continue
            supported = connection.exchange in PROVIDERS and (
                not connection.sandbox or connection.exchange == "binance-testnet"
            )
            row = rows.get(connection.id, {})
            public = {
                key: value
                for key, value in row.items()
                if key not in {"seen", "targets", "key_version", "generation"}
            }
            if public.get("enabled") and not connection.active:
                public["state"] = "inactive"
            accounts.append(
                {
                    "account_id": connection.id,
                    "account": connection.label,
                    "exchange": connection.exchange,
                    "active": connection.active,
                    "sandbox": connection.sandbox,
                    "supported": supported,
                    "revision": "0" * 32,
                    "state": "off",
                    "enabled": False,
                    **public,
                }
            )
        return {
            "accounts": accounts,
            "limit": 8,
            "scope": "Opt-in order signals, not a complete account stream or uptime guarantee. Native adapters may reconnect internally. Restart, observed failures and 60-second backstops wake enabled healthy REST status/fill/discovery readers. Paused readers stay paused; the last scheduling time is not proof of REST completion. No stream event changes financial evidence or executes an order.",
        }

    def configure(self, identity, body):
        """Explicitly enable/pause one displayed connection revision without contacting its provider."""
        with self.lock, self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            connection = db.execute(
                "SELECT exchange,sandbox,EXISTS(SELECT 1 FROM active_accounts WHERE account_id=connections.id) AS active FROM connections WHERE id=?",
                (identity,),
            ).fetchone()
            if connection is None:
                raise LookupError("Connection not found.")
            row = self._read(db, identity)
            if body.revision != (row["revision"] if row else "0" * 32):
                raise ValueError("Stream settings changed. Refresh the connection before saving.")
            if body.enabled:
                if connection["exchange"] not in PROVIDERS or (
                    connection["sandbox"] and connection["exchange"] not in {"binance", "binance-testnet"}
                ):
                    raise ValueError("This exchange/environment has no implemented private order stream.")
                if not connection["active"]:
                    raise ValueError("Activate this account before enabling its private order stream.")
                count = db.execute(
                    "SELECT COUNT(*) FROM private_order_streams s JOIN connections c ON c.id=s.account_id WHERE s.account_id!=? AND json_extract(s.payload,'$.enabled')=1",
                    (identity,),
                ).fetchone()[0]
                if count >= 8:
                    raise ValueError("Keep at most eight enabled private order streams.")
            row = {
                "signals": 0,
                "connections": 0,
                "wakeups": 0,
                "seen": [],
                **(row or {}),
                "enabled": body.enabled,
                "revision": uuid4().hex,
                "generation": uuid4().hex,
                "key_version": self._key_version(db, identity),
                "state": "queued" if body.enabled else "paused",
                "error": None,
                "blocked": False,
                "failures": 0,
                "next_attempt": 0,
                "wake_pending": body.enabled,
                "targets": [],
                "full_sweep": True,
                "next_sweep": 0,
            }
            self._write(db, identity, row)
        return self.snapshot()

    def _current(self, db, identity, generation):
        row = self._read(db, identity)
        active = db.execute(
            "SELECT 1 FROM connections JOIN active_accounts ON account_id=connections.id WHERE connections.id=?",
            (identity,),
        ).fetchone()
        return (
            row
            if row
            and row["enabled"]
            and row["generation"] == generation
            and active
            and row["key_version"] == self._key_version(db, identity)
            else None
        )

    def _change(self, identity, generation, **patch):
        with self.lock, self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._current(db, identity, generation)
            if row is None:
                return False
            row.update(patch)
            self._write(db, identity, row)
            return True

    def signal(self, identity, generation, updates):
        """Coalesce bounded native identities; no statuses or quantities enter the order ledger."""
        signals = []
        for update in updates:
            symbol, native = update.get("symbol"), update.get("id")
            if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9]{1,12}/[A-Z0-9]{1,12}", symbol):
                continue
            if (
                not isinstance(native, str)
                or not 0 < len(native) <= 128
                or any(ord(char) < 33 for char in native)
            ):
                continue
            values = [native, symbol]
            for key in ("status", "filled", "cost", "lastTradeTimestamp"):
                value = update.get(key)
                if isinstance(value, str):
                    value = value[:32]
                elif type(value) not in {int, float} or not math.isfinite(value):
                    value = None
                values.append(value)
            signals.append((symbol, native, hashlib.sha256(json.dumps(values).encode()).hexdigest()))
        with self.lock, self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._current(db, identity, generation)
            if row is None:
                return
            fresh = list({item[2]: item for item in signals if item[2] not in row["seen"]}.values())
            if signals:
                row.update(state="observed", last_signal_at=stamp(), failures=0, error=None, next_attempt=0)
            if fresh:
                targets = {tuple(item) for item in row["targets"]} | {(item[0], item[1]) for item in fresh}
                row.update(
                    signals=row["signals"] + len(fresh),
                    wake_pending=True,
                    targets=[] if len(targets) > 1000 else sorted(targets),
                    full_sweep=row.get("full_sweep", False) or len(targets) > 1000,
                    seen=(row["seen"] + [item[2] for item in fresh])[-300:],
                )
            self._write(db, identity, row)

    async def _run(self, connection, generation):
        client = None
        try:
            client = self.factory(connection, self.store.credentials(connection.id))
            with self.store.db() as db:
                row = self._read(db, connection.id)
            if not self._change(
                connection.id,
                generation,
                state="subscribing",
                connections=row["connections"] + 1,
                last_started_at=stamp(),
                wake_pending=True,
                full_sweep=True,
                targets=[],
            ):
                return
            while not self.closed:
                updates = await client.receive()
                self.signal(connection.id, generation, updates)
                await asyncio.sleep(0)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            with self.store.db() as db:
                row = self._read(db, connection.id)
            if row:
                failures = min(row.get("failures", 0) + 1, 20)
                denied = isinstance(
                    error, (ccxt.AuthenticationError, ccxt.PermissionDenied, ccxt.NotSupported)
                )
                self._change(
                    connection.id,
                    generation,
                    state="attention" if denied else "retrying",
                    failures=failures,
                    error="Private stream access was denied. Review this account and pause/re-enable after checking it."
                    if denied
                    else "Private order signals were interrupted. Existing REST readers remain authoritative.",
                    next_attempt=time.time() + min(300, 2 ** min(failures, 8)),
                    blocked=denied,
                    wake_pending=True,
                    full_sweep=True,
                    targets=[],
                )
        finally:
            if client is not None:
                await client.close()

    async def tick(self):
        """Own socket tasks and atomically acknowledge pending read scheduling, not financial sync."""
        connections = {row.id: row for row in self.store.connections()}
        with self.lock, self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            enabled = []
            db.execute(
                "DELETE FROM private_order_streams WHERE account_id NOT IN (SELECT id FROM connections)"
            )
            for record in db.execute("SELECT * FROM private_order_streams").fetchall():
                identity, row = record[0], json.loads(record[1])
                connection = connections.get(identity)
                if row["enabled"] and connection and row["key_version"] != self._key_version(db, identity):
                    row.update(
                        enabled=False,
                        state="credentials_changed",
                        revision=uuid4().hex,
                        error="Credentials changed. Check access and explicitly re-enable order signals.",
                    )
                    self._write(db, identity, row)
                if not row["enabled"] or not connection or not connection.active:
                    continue
                if row.get("wake_pending") or row.get("next_sweep", 0) <= time.time():
                    counts = self.wakeups.apply(
                        db,
                        identity,
                        row.get("targets", [])
                        if not row.get("full_sweep") and row.get("next_sweep", 0) > time.time()
                        else [],
                    )
                    row.update(
                        wake_pending=False,
                        full_sweep=False,
                        targets=[],
                        next_sweep=time.time() + 60,
                        last_wakeup_at=stamp(),
                        wakeups=row["wakeups"] + 1,
                        last_wakeup=counts,
                    )
                    self._write(db, identity, row)
                enabled.append((connection, row))
        keep = {connection.id: row["generation"] for connection, row in enabled}
        for identity, (generation, task) in list(self.tasks.items()):
            if keep.get(identity) != generation or task.done():
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                self.tasks.pop(identity, None)
        for connection, row in enabled:
            if (
                self.closed
                or connection.id in self.tasks
                or row.get("blocked")
                or row.get("next_attempt", 0) > time.time()
            ):
                continue
            task = asyncio.create_task(
                self._run(connection, row["generation"]), name="sibyl-private-orders-" + connection.id
            )
            self.tasks[connection.id] = (row["generation"], task)

    async def close(self):
        """Cancel/drain every owned native stream before exchange domain services close."""
        self.closed = True
        for _, task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*(task for _, task in self.tasks.values()), return_exceptions=True)
        self.tasks.clear()
