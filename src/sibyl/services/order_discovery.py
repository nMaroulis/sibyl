"""Durable read-only discovery of exchange orders, sharing the existing order/fill monitor."""

import hashlib
import json
import re
import threading
import time
from datetime import UTC, datetime
from uuid import uuid4

import ccxt
from pydantic import Field, field_validator

from sibyl.exchanges.base import number
from sibyl.exchanges.order_discovery import DAY_MS, DISCOVERY_PROVIDERS, OrderDiscoveryPage
from sibyl.market_data.control import ProviderDeferred
from sibyl.models import OrderRequest, Request
from sibyl.services.account_sync import environment
from sibyl.services.ledger import now_iso
from sibyl.services.order_lifecycle import TERMINAL


class OrderDiscoveryRequest(Request):
    """Choose one saved account or all active reviewed accounts, with bounded recent coverage."""

    account_id: str = Field(default="", max_length=100)
    symbols: list[str] = Field(default_factory=list, max_length=12)
    days: int = Field(default=1, ge=1, le=7)

    @field_validator("symbols")
    @classmethod
    def valid_symbols(cls, values):
        """Binance history uses explicit spot markets; other providers scan account-level pages."""
        return list(dict.fromkeys(OrderRequest.valid_symbol(value) for value in values))


def normalized_order(row: dict) -> dict:
    """Project native evidence without raw metadata; quote-sized quantities stay unknown."""
    identity, symbol, side = row.get("id"), row.get("symbol"), row.get("side")
    if (
        not isinstance(identity, str)
        or not identity
        or len(identity) > 200
        or any(ord(c) < 32 for c in identity)
    ):
        raise ValueError("Invalid native order identity.")
    if (
        not isinstance(symbol, str)
        or not re.fullmatch(r"[A-Z0-9]{1,12}/[A-Z0-9]{1,12}", symbol)
        or side not in {"buy", "sell"}
    ):
        raise ValueError("Invalid spot order market or side.")
    client_id = row.get("clientOrderId")
    if client_id is not None and (
        not isinstance(client_id, str) or len(client_id) > 200 or any(ord(c) < 32 for c in client_id)
    ):
        raise ValueError("Invalid client order identity.")
    result = {"id": identity, "symbol": symbol, "side": side, "clientOrderId": client_id}
    for key in ("amount", "filled", "remaining", "price", "average", "cost", "timestamp"):
        value = number(row.get(key))
        if row.get(key) is not None and (value is None or value < 0):
            raise ValueError("Invalid native order values.")
        result[key] = value if key not in {"amount", "price", "average", "timestamp"} or value else None
    if result["timestamp"] is not None and result["timestamp"] > time.time() * 1000 + 300_000:
        raise ValueError("Invalid native creation time.")
    amount, filled, remaining = (result[key] for key in ("amount", "filled", "remaining"))
    if amount is not None and any(
        value is not None and value > amount + max(1e-10, amount * 1e-8) for value in (filled, remaining)
    ):
        raise ValueError("Invalid cumulative order quantity.")
    status = "canceled" if row.get("status") == "cancelled" else row.get("status")
    result["status"] = status if status in TERMINAL | {"open", "pending"} else "unknown"
    kind = row.get("type")
    result["type"] = kind if isinstance(kind, str) and re.fullmatch(r"[a-z0-9_-]{1,40}", kind) else "unknown"
    tif = row.get("timeInForce")
    result["timeInForce"] = tif if isinstance(tif, str) and re.fullmatch(r"[A-Z0-9_-]{1,40}", tif) else None
    return result


class OrderDiscovery:
    """One page per tick, atomic order/checkpoint commits and explicitly enabled five-minute passes.

    Imported rows are observations, never executable intents. Exact native IDs link
    to local intents and shared fills. Uncertain matching client IDs remain on the
    existing reviewed recovery path rather than creating a duplicate order.
    """

    def __init__(self, trading):
        self.trading, self.store, self.market = trading, trading.store, trading.market
        self._worker = threading.Lock()
        self._closed = False
        with self.store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS order_discovery (account_id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS exchange_order_native ON exchange_orders(json_extract(payload,'$.request.connection_id'),json_extract(payload,'$.request.symbol'),json_extract(payload,'$.exchange_order_id'))"
            )
            for row in db.execute("SELECT account_id,payload FROM order_discovery").fetchall():
                job = json.loads(row[1])
                if job["state"] == "running":
                    job.update(state="queued", next_attempt=0)
                    self.write(db, job)

    @staticmethod
    def read(db, account_id):
        row = db.execute("SELECT payload FROM order_discovery WHERE account_id=?", (account_id,)).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def write(db, job):
        db.execute(
            "INSERT INTO order_discovery VALUES(?,?) ON CONFLICT(account_id) DO UPDATE SET payload=excluded.payload",
            (job["account_id"], json.dumps(job, allow_nan=False)),
        )

    @staticmethod
    def new_pass(job):
        """Freeze a new recent window; incomplete passes retain their exact original window."""
        end = int(time.time() * 1000)
        job.update(
            stream="open",
            cursor={},
            seen=[],
            pages=0,
            records=0,
            skipped=0,
            linked=0,
            deferred=0,
            start=end - job["days"] * DAY_MS,
            end=end,
            complete=False,
        )

    def snapshot(self):
        """Return safe local progress/capabilities; no credentials, native tokens or network reads."""
        with self.store.db() as db:
            jobs = [
                json.loads(row[0])
                for row in db.execute("SELECT payload FROM order_discovery ORDER BY account_id")
            ]
            counts = dict(
                db.execute(
                    "SELECT json_extract(payload,'$.request.connection_id'),COUNT(*) FROM exchange_orders WHERE json_extract(payload,'$.origin')='imported' GROUP BY 1"
                )
            )
        private = {"cursor", "seen", "revision"}
        return {
            "accounts": [
                {
                    **connection.model_dump(mode="json"),
                    "environment": environment(connection),
                    "supported": connection.exchange in DISCOVERY_PROVIDERS,
                    "history_requires_symbols": connection.exchange in {"binance", "binance-testnet"},
                }
                for connection in self.store.connections()
            ],
            "jobs": [
                {
                    **{key: value for key, value in job.items() if key not in private},
                    "retained_orders": counts.get(job["account_id"], 0),
                }
                for job in jobs
            ],
            "note": "Open spot orders plus bounded recent history, not complete account history. Imported orders are read-only. Missing orders are never inferred canceled. Coinbase Advanced covers the key's permitted Advanced Trade portfolio; delisted, margin and unknown instruments are excluded and counted.",
        }

    def enqueue(self, body: OrderDiscoveryRequest):
        """Enable only explicitly selected active reviewed accounts; never activate an account."""
        accounts = self.store.connections()
        if body.account_id:
            accounts = [row for row in accounts if row.id == body.account_id]
            if not accounts:
                raise LookupError("Account not found.")
            if not accounts[0].active or accounts[0].exchange not in DISCOVERY_PROVIDERS:
                raise ValueError("Choose an active account with reviewed order discovery.")
        accounts = [row for row in accounts if row.active and row.exchange in DISCOVERY_PROVIDERS]
        if not accounts or len(accounts) > 20:
            raise ValueError("Choose up to twenty active accounts with reviewed order discovery.")
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            for connection in accounts:
                if not db.execute(
                    "SELECT 1 FROM active_accounts WHERE account_id=?", (connection.id,)
                ).fetchone():
                    raise ValueError("Account selection changed; choose active accounts again.")
                job = self.read(db, connection.id)
                same = job and job["symbols"] == body.symbols and job["days"] == body.days
                if not same:
                    job = {
                        "account_id": connection.id,
                        "account": connection.label,
                        "exchange": connection.exchange,
                        "sandbox": connection.sandbox,
                        "environment": environment(connection),
                        "symbols": body.symbols,
                        "days": body.days,
                        "last_success_at": None,
                        "completed_at": None,
                    }
                    self.new_pass(job)
                elif job["complete"]:
                    self.new_pass(job)
                job.update(
                    enabled=True, state="queued", next_attempt=0, failures=0, error=None, revision=uuid4().hex
                )
                self.write(db, job)
        return self.snapshot()

    def pause(self, account_id, *, disconnected=False):
        """Stop future pages while retaining observations, filters and the saved checkpoint."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            job = self.read(db, account_id)
            if not job:
                raise LookupError("Order discovery job not found.")
            job.update(enabled=False, state="disconnected" if disconnected else "paused")
            self.write(db, job)
        return self.snapshot()

    def _upsert(self, db, connection, order):
        """Share account/market/native identity; no client-ID-only adoption or fabricated fills."""
        rows = db.execute(
            "SELECT payload FROM exchange_orders WHERE json_extract(payload,'$.request.connection_id')=? AND json_extract(payload,'$.request.symbol')=? AND json_extract(payload,'$.exchange_order_id')=?",
            (connection.id, order["symbol"], order["id"]),
        ).fetchall()
        if len(rows) > 1:
            raise ValueError("Conflicting native order attribution.")
        current = json.loads(rows[0][0]) if rows else None
        if current and current["request"]["side"] != order["side"]:
            raise ValueError("Native order side changed.")
        if current and (
            current["exchange"] != connection.exchange or current["sandbox"] != connection.sandbox
        ):
            raise ValueError("Account environment changed.")
        if current and current.get("origin") != "imported":
            request = current["request"]
            if order["side"] != request["side"] or order["amount"] not in {None, request["quantity"]}:
                raise ValueError("External amendment differs from the reviewed order.")
            self.trading.lifecycle.merge_observation(db, current, order)
            return "linked"
        if not current and order["clientOrderId"]:
            uncertain = db.execute(
                "SELECT 1 FROM exchange_orders WHERE json_extract(payload,'$.request.connection_id')=? AND json_extract(payload,'$.client_order_id')=? AND json_extract(payload,'$.exchange_order_id') IS NULL AND json_extract(payload,'$.status') IN ('preview','submitting','unknown') LIMIT 1",
                (connection.id, order["clientOrderId"]),
            ).fetchone()
            if uncertain:
                return "deferred"
        stamp = now_iso()
        if current and (
            (
                current.get("filled") is not None
                and order["filled"] is not None
                and order["filled"] < current["filled"]
            )
            or (current["status"] in TERMINAL and order["status"] not in TERMINAL)
        ):
            raise ValueError("Older imported observation; retained evidence was preserved.")
        identity = (
            current["id"]
            if current
            else "imported-"
            + hashlib.sha256(json.dumps([connection.id, order["symbol"], order["id"]]).encode()).hexdigest()
        )
        created = (
            datetime.fromtimestamp(order["timestamp"] / 1000, UTC).isoformat()
            if order["timestamp"]
            else (current or {}).get("order_created_at")
        )
        intent = {
            **(current or {}),
            "id": identity,
            "origin": "imported",
            "read_only": True,
            "account": connection.label,
            "exchange": connection.exchange,
            "sandbox": connection.sandbox,
            "environment": environment(connection),
            "mode": "paper" if connection.exchange == "demo" else "exchange",
            "exchange_order_id": order["id"],
            "client_order_id": order["clientOrderId"],
            "request": {
                "connection_id": connection.id,
                "symbol": order["symbol"],
                "side": order["side"],
                "quantity": order["amount"],
                "order_type": order["type"],
                "limit_price": order["price"] if order["type"] == "limit" else None,
            },
            "status": "closed" if current and current["status"] == "closed" else order["status"],
            "price": order["price"],
            "notional": order["cost"],
            "cost": order["cost"],
            "filled": order["filled"],
            "remaining": order["remaining"],
            "average": order["average"],
            "time_in_force": order["timeInForce"],
            "created_at": created or (current or {}).get("created_at", stamp),
            "order_created_at": created,
            "discovered_at": (current or {}).get("discovered_at", stamp),
            "refreshed_at": stamp,
            "tracking": (current or {}).get("tracking", order["status"] not in TERMINAL),
            "sync_error": None,
            "sync_failures": 0,
            "next_check": time.time() + 20,
            "message": "Imported native observation. Manage this read-only order at the exchange; execution checks link retained fills separately.",
        }
        if intent["status"] in TERMINAL:
            intent["tracking"] = False
        if not current:
            db.execute(
                "INSERT INTO exchange_orders VALUES(?,?,?)",
                (identity, identity, json.dumps(intent, allow_nan=False)),
            )
        else:
            self.trading.lifecycle.write(db, intent)
        self.trading.reconciliation.schedule(db, intent)
        return "imported"

    def commit(self, job, connection, page):
        """Validate the complete page before atomically retaining orders and advancing its cursor."""
        if (
            not isinstance(page, OrderDiscoveryPage)
            or not isinstance(page.items, list)
            or not isinstance(page.cursor, dict)
            or not isinstance(page.complete, bool)
            or len(page.items) > 1000
            or not isinstance(page.skipped, int)
            or page.skipped < 0
        ):
            raise ValueError("Invalid account order page.")
        if job["records"] + len(page.items) > 10_000:
            raise ccxt.NotSupported("Order discovery exceeded the reviewed record budget.")
        signature = hashlib.sha256(
            json.dumps(page.cursor, sort_keys=True, allow_nan=False).encode()
        ).hexdigest()
        if not page.complete and (page.cursor == job["cursor"] or signature in job["seen"]):
            raise ValueError("Account order cursor did not advance.")
        orders = {}
        for item in page.items:
            order = normalized_order(item)
            key = (order["symbol"], order["id"])
            if key in orders and orders[key] != order:
                raise ValueError("Conflicting native observations on one page.")
            orders[key] = order
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.read(db, connection.id)
            if not current or current["revision"] != job["revision"]:
                return
            counts = {"linked": 0, "imported": 0, "deferred": 0}
            for order in orders.values():
                counts[self._upsert(db, connection, order)] += 1
            current.update(
                cursor=page.cursor,
                seen=[*job["seen"], signature],
                pages=job["pages"] + 1,
                records=job["records"] + len(page.items),
                linked=job["linked"] + counts["linked"],
                deferred=job["deferred"] + counts["deferred"],
                skipped=job["skipped"] + page.skipped,
                last_success_at=now_iso(),
                failures=0,
                error=None,
                next_attempt=time.time() + 1,
            )
            if page.complete:
                if job["stream"] == "open":
                    current.update(stream="recent", cursor={}, seen=[])
                else:
                    current.update(complete=True, completed_at=now_iso(), next_attempt=time.time() + 300)
            if current["enabled"]:
                current["state"] = "idle" if current["complete"] else "queued"
            if not db.execute("SELECT 1 FROM connections WHERE id=?", (connection.id,)).fetchone():
                current.update(enabled=False, state="disconnected")
            self.write(db, current)

    def refresh(self, identity):
        """Refresh an imported native order without enabling cancellation or the Demo matcher."""
        with self.trading.lifecycle.lock(identity):
            with self.store.db() as db:
                intent = self.trading.lifecycle.read(db, identity)
            connection = self.trading._connection(intent["request"]["connection_id"], allow_demo=True)
            if connection.exchange != intent["exchange"] or connection.sandbox != intent["sandbox"]:
                raise ValueError("Account environment changed.")
            with self.market.adapter(connection) as client:
                order = normalized_order(
                    client.fetch_order(intent["exchange_order_id"], intent["request"]["symbol"])
                )
            if (
                order["id"] != intent["exchange_order_id"]
                or order["symbol"] != intent["request"]["symbol"]
                or order["side"] != intent["request"]["side"]
            ):
                raise ValueError("Native order identity changed.")
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                self._upsert(db, connection, order)
                return self.trading.lifecycle.read(db, identity)

    def tick(self):
        """Read at most one due page; inactive accounts wait and failures retain their checkpoints."""
        with self._worker:
            if self._closed:
                return
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute(
                    "SELECT payload FROM order_discovery WHERE json_extract(payload,'$.enabled')=1 AND json_extract(payload,'$.next_attempt')<=? ORDER BY json_extract(payload,'$.next_attempt'),rowid LIMIT 1",
                    (time.time(),),
                ).fetchone()
                if not row:
                    return
                job = json.loads(row[0])
                if job["complete"]:
                    self.new_pass(job)
                job["state"] = "running"
                self.write(db, job)
            try:
                connection = self.trading._connection(job["account_id"], allow_demo=True)
                if connection.exchange != job["exchange"] or connection.sandbox != job["sandbox"]:
                    raise ValueError("Account environment changed.")
                if not connection.active:
                    raise ccxt.ExchangeNotAvailable("Account is inactive.")
                if job["pages"] >= 100 or job["records"] >= 10_000:
                    raise ccxt.NotSupported("Order discovery exceeded the reviewed budget.")
                with self.market.adapter(connection) as client:
                    page = client.fetch_account_order_page(
                        job["stream"], job["cursor"], job["start"], job["end"], job["symbols"]
                    )
                self.commit(job, connection, page)
            except Exception as error:
                self._failure(job, error)

    def _failure(self, job, error):
        """Persist fixed messages only, with bounded retries and no submission/cancellation fallback."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.read(db, job["account_id"])
            if not current or current["revision"] != job["revision"]:
                return
            connection = next((row for row in self.store.connections() if row.id == job["account_id"]), None)
            deferred = isinstance(error, ProviderDeferred)
            failures = current.get("failures", 0) + int(not deferred)
            transient = isinstance(error, (ccxt.NetworkError, ccxt.RateLimitExceeded))
            current.update(
                failures=failures,
                error="Order reads failed or returned invalid evidence. Retained orders and the last successful checkpoint are preserved.",
                next_attempt=time.time()
                + (error.retry_after if deferred else min(900, 20 * 2 ** min(failures, 6))),
            )
            if not connection:
                current.update(
                    enabled=False,
                    state="disconnected",
                    error="Account disconnected. Retained order evidence remains available.",
                )
            elif not connection.active and current["enabled"]:
                current.update(
                    state="waiting_account",
                    error="Activate this saved account to resume discovery.",
                    failures=job.get("failures", 0),
                    next_attempt=time.time() + 60,
                )
            elif current["enabled"]:
                if isinstance(error, ccxt.NotSupported):
                    current.update(
                        enabled=False,
                        state="limited",
                        error="Order discovery is unsupported or reached its page/record budget. Choose a smaller range and restart.",
                    )
                elif deferred or (transient and failures < 5):
                    current["state"] = "retrying"
                else:
                    current.update(enabled=False, state="error")
                    if isinstance(error, (ccxt.AuthenticationError, ccxt.PermissionDenied)):
                        current["error"] = (
                            "Order history access denied. Check this account's read permissions and credentials."
                        )
                    elif isinstance(error, ccxt.BadSymbol):
                        current["error"] = (
                            "A selected Binance history pair is unavailable. Choose exact spot pairs supported by this account's environment."
                        )
            self.write(db, current)

    def close(self):
        """Wait for an in-flight page before closing shared transports."""
        with self._worker:
            self._closed = True
