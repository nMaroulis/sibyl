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

from sibyl.exchanges.catalog import exchange_spec
from sibyl.exchanges.data import DEMO_BALANCES
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
                CREATE TABLE IF NOT EXISTS active_accounts (account_id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS model_profiles (provider TEXT PRIMARY KEY, config BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS workspace_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS balances (asset TEXT PRIMARY KEY, quantity REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS paper_limits (
                    id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS source_snapshots (
                    scope TEXT NOT NULL, timestamp TEXT NOT NULL, value REAL NOT NULL,
                    PRIMARY KEY(scope, timestamp)
                );
                CREATE TABLE IF NOT EXISTS market_watchlists (
                    source TEXT PRIMARY KEY, symbols TEXT NOT NULL,
                    revision INTEGER NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS snapshots (
                    timestamp TEXT PRIMARY KEY, value REAL NOT NULL
                );
            """)
            db.executemany(
                "INSERT OR IGNORE INTO balances VALUES (?, ?)",
                DEMO_BALANCES.items(),
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

    def market_watchlist(self, source: str) -> dict | None:
        """Read an ordered feed-specific preference, distinguishing missing from empty."""
        with self.db() as db:
            row = db.execute(
                "SELECT symbols, revision, updated_at FROM market_watchlists WHERE source=?", (source,)
            ).fetchone()
        return {**dict(row), "symbols": json.loads(row["symbols"])} if row else None

    def seed_market_watchlist(self, source: str, symbols: list[str]) -> dict:
        """Provision defaults once; simultaneous first reads cannot overwrite saved choices."""
        with self.db() as db:
            db.execute(
                "INSERT OR IGNORE INTO market_watchlists VALUES (?, ?, 0, ?)",
                (source, json.dumps(symbols), datetime.now(UTC).isoformat()),
            )
        return self.market_watchlist(source)

    def change_market_watchlist(self, source: str, action: str, value, limit: int = 30) -> dict:
        """Serialize list edits so concurrent adds/removes cannot lose each other's work."""
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT symbols, revision, updated_at FROM market_watchlists WHERE source=?", (source,)
            ).fetchone()
            if row is None:
                raise LookupError("Watchlist not initialized.")
            current = json.loads(row["symbols"])
            changed = current.copy()
            if action == "add":
                if value not in changed:
                    if len(changed) >= limit:
                        raise ValueError(f"A watchlist can contain at most {limit} markets.")
                    changed.append(value)
            elif action == "remove":
                changed = [symbol for symbol in changed if symbol != value]
            elif action == "order":
                if len(value) != len(set(value)) or set(value) != set(current):
                    raise ValueError("The watchlist changed. Refresh it before reordering.")
                changed = value
            else:
                raise ValueError("Unknown watchlist edit.")
            revision = row["revision"] + (changed != current)
            updated = datetime.now(UTC).isoformat() if changed != current else row["updated_at"]
            db.execute(
                "UPDATE market_watchlists SET symbols=?, revision=?, updated_at=? WHERE source=?",
                (json.dumps(changed), revision, updated, source),
            )
            return {"symbols": changed, "revision": revision, "updated_at": updated}

    def model_profiles(self) -> tuple[str | None, dict[str, dict]]:
        """Read active selection and decrypt profiles for the model settings service only."""
        with self.db() as db:
            db.execute("BEGIN")
            active = db.execute("SELECT value FROM workspace_settings WHERE key = 'llm_provider'").fetchone()
            rows = db.execute("SELECT provider, config FROM model_profiles").fetchall()
        return (
            active[0] if active else None,
            {row["provider"]: json.loads(self.cipher.decrypt(row["config"])) for row in rows},
        )

    def data_profile(self, name: str) -> dict:
        """Decrypt one server-owned data-source profile, never exposed directly by routes."""
        with self.db() as db:
            row = db.execute("SELECT value FROM workspace_settings WHERE key=?", (f"data:{name}",)).fetchone()
        return json.loads(self.cipher.decrypt(row[0])) if row else {}

    def save_data_profile(self, name: str, profile: dict) -> None:
        """Persist data-source choices and optional provider keys as one encrypted snapshot."""
        value = self.cipher.encrypt(json.dumps(profile).encode())
        with self.db() as db:
            db.execute(
                "INSERT INTO workspace_settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (f"data:{name}", value),
            )

    def save_model_profile(
        self, provider: str, profile: dict, *, activate: bool = True, fallback_to_tools: bool = False
    ) -> None:
        """Commit an encrypted provider profile and its active selection atomically."""
        encrypted = self.cipher.encrypt(json.dumps(profile).encode())
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO model_profiles VALUES (?, ?) ON CONFLICT(provider) "
                "DO UPDATE SET config = excluded.config",
                (provider, encrypted),
            )
            if activate or fallback_to_tools:
                db.execute(
                    "INSERT INTO workspace_settings VALUES ('llm_provider', ?) ON CONFLICT(key) "
                    "DO UPDATE SET value = excluded.value",
                    ("none" if fallback_to_tools else provider,),
                )

    def connections(self) -> list[Connection]:
        """Return connection metadata without selecting encrypted credential columns."""
        with self.db() as db:
            rows = db.execute(
                "SELECT id, exchange, label, sandbox, created_at, "
                "EXISTS(SELECT 1 FROM active_accounts WHERE account_id=connections.id) AS active FROM connections"
            ).fetchall()
        return [Connection.model_validate(dict(row)) for row in rows]

    def add_connection(self, request: ConnectionCreate, *, activate: bool = True) -> Connection:
        """Save an explicitly requested account and normally activate it atomically.

        Real/test connections replace Demo activation and join other exchange
        accounts. Creating a Store alone never connects or activates anything.
        """
        item = Connection(
            id="demo" if request.exchange == "demo" else uuid4().hex,
            exchange=request.exchange,
            label=request.label,
            sandbox=request.sandbox or exchange_spec(request.exchange).test_environment,
            created_at=datetime.now(UTC),
        )
        credentials = {
            "apiKey": request.api_key.get_secret_value(),
            "secret": request.secret.get_secret_value(),
            "password": request.passphrase.get_secret_value(),
            "uid": request.uid.get_secret_value(),
        }
        if request.exchange == "demo":
            credentials = {}
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT OR IGNORE INTO connections VALUES (?, ?, ?, ?, ?, ?)",
                (
                    item.id,
                    item.exchange,
                    item.label,
                    item.sandbox,
                    item.created_at.isoformat(),
                    self.cipher.encrypt(json.dumps(credentials).encode()),
                ),
            )
            if activate:
                self._activate(db, item.id, True)
        return next(connection for connection in self.connections() if connection.id == item.id)

    @staticmethod
    def _activate(db, account_id: str, active: bool) -> None:
        """Change selection inside the caller's immediate transaction; Demo is exclusive."""
        account = db.execute("SELECT exchange FROM connections WHERE id=?", (account_id,)).fetchone()
        if account is None:
            raise LookupError("Connection not found.")
        if not active:
            db.execute("DELETE FROM active_accounts WHERE account_id=?", (account_id,))
            return
        if account["exchange"] == "demo":
            if db.execute(
                "SELECT 1 FROM active_accounts JOIN connections ON id=account_id WHERE exchange!='demo'"
            ).fetchone():
                raise ValueError("Deactivate exchange accounts before enabling Demo preview.")
        else:
            db.execute("DELETE FROM active_accounts WHERE account_id='demo'")
        db.execute("INSERT OR IGNORE INTO active_accounts VALUES (?)", (account_id,))

    def activate_account(self, account_id: str, active: bool) -> None:
        """Toggle one account while preserving concurrent changes to other accounts."""
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._activate(db, account_id, active)

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
            db.execute("DELETE FROM active_accounts WHERE account_id = ?", (connection_id,))

    def balances(self) -> dict[str, float]:
        """Read the independent paper ledger, denominated in native asset quantities."""
        with self.db() as db:
            return dict(db.execute("SELECT asset, quantity FROM balances").fetchall())

    def execute_paper(
        self, request: OrderRequest, price: float, fee_rate: float = 0.001, *, require_demo: bool = False
    ) -> dict:
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
            if db.execute(
                "SELECT 1 FROM paper_limits WHERE request_key=?", (request.idempotency_key,)
            ).fetchone():
                raise ValueError("This paper key belongs to a limit order.")
            if (
                require_demo
                and not db.execute("SELECT 1 FROM active_accounts WHERE account_id='demo'").fetchone()
            ):
                raise ValueError("Demo preview is no longer active. Review your account selection.")
            balances = dict(db.execute("SELECT asset, quantity FROM balances").fetchall())
            from sibyl.exchanges.paper_limits import reserved

            holds = reserved(db)
            notional = price * request.quantity
            fee = notional * fee_rate
            base_delta = request.quantity if request.side == "buy" else -request.quantity
            quote_delta = -(notional + fee) if request.side == "buy" else notional - fee
            spending_asset, needed = (
                (quote, notional + fee) if request.side == "buy" else (base, request.quantity)
            )
            if balances.get(spending_asset, 0) - holds.get(spending_asset, 0) < needed:
                raise ValueError("Insufficient paper balance after open-order reservations.")
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

    def snapshot(self, value: float | None, scope: str = "") -> list[dict]:
        """Save an hourly observation, or read without writing for incomplete reads."""
        timestamp = datetime.now(UTC).replace(minute=0, second=0, microsecond=0).isoformat()
        if scope:
            with self.db() as db:
                if value is not None:
                    db.execute(
                        "INSERT INTO source_snapshots VALUES (?, ?, ?) ON CONFLICT(scope, timestamp) DO UPDATE SET value=excluded.value",
                        (scope, timestamp, value),
                    )
                return [
                    dict(row)
                    for row in db.execute(
                        "SELECT timestamp, value FROM source_snapshots WHERE scope=? ORDER BY timestamp",
                        (scope,),
                    )
                ]
        with self.db() as db:
            if value is not None:
                db.execute(
                    "INSERT INTO snapshots VALUES (?, ?) ON CONFLICT(timestamp) "
                    "DO UPDATE SET value = excluded.value",
                    (timestamp, value),
                )
            return [dict(row) for row in db.execute("SELECT * FROM snapshots ORDER BY timestamp")]
