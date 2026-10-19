"""Small SQLite repository with encrypted credentials and atomic paper execution."""

import json
import math
import os
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from cryptography.fernet import Fernet

from sibyl.models import Connection, ConnectionCreate, OrderRequest


class Store:
    """Own workspace persistence; each operation uses a short-lived connection.

    The Fernet key is a separate owner-readable file. Back up both files together.
    SQLite transactions serialize balance changes and duplicate order submissions.
    """

    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = directory / "sibyl.db"
        key_path = directory / "vault.key"
        try:
            with key_path.open("xb") as file:
                os.chmod(key_path, 0o600)
                file.write(Fernet.generate_key())
        except FileExistsError:
            pass
        self.cipher = Fernet(key_path.read_bytes())
        with self.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS connections (
                    id TEXT PRIMARY KEY, exchange TEXT NOT NULL, label TEXT NOT NULL,
                    sandbox INTEGER NOT NULL, created_at TEXT NOT NULL, credentials BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS balances (asset TEXT PRIMARY KEY, quantity REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS snapshots (
                    timestamp TEXT PRIMARY KEY, value REAL NOT NULL
                );
            """)
            db.executemany(
                "INSERT OR IGNORE INTO balances VALUES (?, ?)",
                [
                    ("USDT", 24_850.0),
                    ("BTC", 0.84),
                    ("ETH", 8.2),
                    ("SOL", 74.0),
                    ("LINK", 210.0),
                ],
            )
        os.chmod(self.path, 0o600)

    @contextmanager
    def db(self):
        """Commit on success and roll back on failure, including all balance mutations."""
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def connections(self) -> list[Connection]:
        """Return connection metadata without selecting encrypted credential columns."""
        with self.db() as db:
            rows = db.execute("SELECT id, exchange, label, sandbox, created_at FROM connections").fetchall()
        return [Connection.model_validate(dict(row)) for row in rows]

    def add_connection(self, request: ConnectionCreate) -> Connection:
        """Encrypt all secret fields before persisting an exchange connection."""
        item = Connection(
            id=uuid4().hex,
            exchange=request.exchange,
            label=request.label,
            sandbox=request.sandbox,
            created_at=datetime.now(UTC),
        )
        credentials = {
            "apiKey": request.api_key.get_secret_value(),
            "secret": request.secret.get_secret_value(),
            "password": request.passphrase.get_secret_value(),
        }
        with self.db() as db:
            db.execute(
                "INSERT INTO connections VALUES (?, ?, ?, ?, ?, ?)",
                (
                    item.id,
                    item.exchange,
                    item.label,
                    item.sandbox,
                    item.created_at.isoformat(),
                    self.cipher.encrypt(json.dumps(credentials).encode()),
                ),
            )
        return item

    def credentials(self, connection_id: str) -> dict:
        """Decrypt credentials only for the exchange adapter, never for API responses."""
        with self.db() as db:
            row = db.execute("SELECT credentials FROM connections WHERE id = ?", (connection_id,)).fetchone()
        if row is None:
            raise LookupError("Connection not found.")
        return json.loads(self.cipher.decrypt(row[0]))

    def delete_connection(self, connection_id: str) -> None:
        """Remove a connection; deleting an unknown ID is an idempotent operation."""
        with self.db() as db:
            db.execute("DELETE FROM connections WHERE id = ?", (connection_id,))

    def balances(self) -> dict[str, float]:
        """Read the independent paper ledger, denominated in native asset quantities."""
        with self.db() as db:
            return dict(db.execute("SELECT asset, quantity FROM balances").fetchall())

    def execute_paper(self, request: OrderRequest, price: float, fee_rate: float = 0.001) -> dict:
        """Fill a paper order exactly once, rejecting overspending and overselling.

        Fees are charged in the quote asset. An idempotency key cannot be reused
        with a different symbol, direction, or quantity.
        """
        if not math.isfinite(price) or price <= 0 or not 0 <= fee_rate < 1:
            raise ValueError("A positive finite price and valid fee rate are required.")
        base, quote = request.symbol.split("/")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT payload FROM orders WHERE idempotency_key = ?", (request.idempotency_key,)
            ).fetchone()
            if previous:
                order = json.loads(previous[0])
                if any(order[key] != getattr(request, key) for key in ("symbol", "side", "quantity")):
                    raise ValueError("This idempotency key belongs to a different order.")
                return order
            balances = dict(db.execute("SELECT asset, quantity FROM balances").fetchall())
            notional = price * request.quantity
            fee = notional * fee_rate
            base_delta = request.quantity if request.side == "buy" else -request.quantity
            quote_delta = -(notional + fee) if request.side == "buy" else notional - fee
            if balances.get(base, 0) + base_delta < -1e-10 or balances.get(quote, 0) + quote_delta < -1e-8:
                raise ValueError("Insufficient paper balance for this order and its fee.")
            for asset, delta in [(base, base_delta), (quote, quote_delta)]:
                db.execute(
                    "INSERT INTO balances VALUES (?, ?) ON CONFLICT(asset) DO UPDATE "
                    "SET quantity = quantity + excluded.quantity",
                    (asset, delta),
                )
            order = {
                "id": uuid4().hex,
                "symbol": request.symbol,
                "side": request.side,
                "quantity": request.quantity,
                "price": price,
                "notional": notional,
                "fee": fee,
                "status": "filled",
                "mode": "paper",
                "created_at": datetime.now(UTC).isoformat(),
            }
            db.execute(
                "INSERT INTO orders VALUES (?, ?, ?, ?)",
                (
                    order["id"],
                    request.idempotency_key,
                    json.dumps(order),
                    order["created_at"],
                ),
            )
        return order

    def orders(self) -> list[dict]:
        """Return up to 200 most recent paper fills."""
        with self.db() as db:
            return [
                json.loads(row[0])
                for row in db.execute("SELECT payload FROM orders ORDER BY created_at DESC LIMIT 200")
            ]

    def record(self, kind: str, payload: Any) -> dict:
        """Persist a backtest or agent result for inspection after restarting."""
        item = {"id": uuid4().hex, "kind": kind, "created_at": datetime.now(UTC).isoformat(), "data": payload}
        with self.db() as db:
            db.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?)",
                (item["id"], kind, json.dumps(payload), item["created_at"]),
            )
        return item

    def runs(self, kind: str | None = None) -> list[dict]:
        """Read the 50 latest persisted runs, optionally restricted to one kind."""
        with self.db() as db:
            rows = db.execute(
                "SELECT * FROM runs WHERE (? IS NULL OR kind = ?) ORDER BY created_at DESC LIMIT 50",
                (kind, kind),
            ).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    def snapshot(self, value: float) -> list[dict]:
        """Save one actual portfolio observation per UTC hour and return its history."""
        timestamp = datetime.now(UTC).replace(minute=0, second=0, microsecond=0).isoformat()
        with self.db() as db:
            db.execute(
                "INSERT INTO snapshots VALUES (?, ?) ON CONFLICT(timestamp) "
                "DO UPDATE SET value = excluded.value",
                (timestamp, value),
            )
            return [dict(row) for row in db.execute("SELECT * FROM snapshots ORDER BY timestamp")]
