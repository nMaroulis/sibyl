"""Explicit private balance reads and local, immutable comparison reports."""

import json
import math
import threading
import time
from collections import defaultdict
from datetime import UTC, datetime
from uuid import uuid4

from sibyl.accounting.balance_checks.contracts import MAX_ASSETS
from sibyl.accounting.balance_checks.journal import CheckJournal
from sibyl.accounting.balance_checks.movements import compare
from sibyl.exchanges.catalog import exchange_spec
from sibyl.services.accounts import Accounts


class BalanceChecks:
    """Compare one account's observed quantities without writing to its exchange.

    Checkpoints freeze both a balance observation and the then-retained ledger.
    Reads are deliberately explicit, uncached and bounded. No worker imports
    history, replaces checkpoints or repairs differences on the user's behalf.
    """

    def __init__(self, market, store):
        self.market, self.store = market, store
        self.journal = CheckJournal(store)
        self.locks = defaultdict(threading.RLock)

    def _connection(self, account_id):
        connection = next((row for row in self.store.connections() if row.id == account_id), None)
        if connection is None:
            raise LookupError("Saved account not found.")
        if not connection.active:
            raise ValueError(
                "Activate this account before reading balances. Retained checks remain available."
            )
        return connection

    def accounts(self, scope="all"):
        """List active page-scope accounts and checkpoint state without a provider read."""
        return {
            "accounts": [
                {
                    "id": row.id,
                    "name": row.label,
                    "exchange": row.exchange,
                    "sandbox": row.sandbox,
                    "environment": "demo"
                    if row.exchange == "demo"
                    else "test"
                    if row.sandbox
                    else "production",
                }
                for row in Accounts(self.store).resolve(scope)
            ]
        }

    def _observe(self, connection):
        started = time.time()
        with self.store.db() as db:
            scope = self.journal.scope(db, connection.id)
        try:
            with self.market.adapter(connection) as client:
                raw = client.fetch_balance_snapshot()
            totals = raw.get("total")
            if not isinstance(totals, dict) or len(totals) > MAX_ASSETS:
                raise ValueError("Missing or oversized native balance map.")
            assets = set(totals) | set(raw.get("free") or {}) | set(raw.get("used") or {})
            balances = {}
            for asset in assets:
                value = totals.get(asset)
                if (
                    not isinstance(asset, str)
                    or not 1 <= len(asset) <= 64
                    or not asset.isprintable()
                    or asset.strip() != asset
                    or isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or not 0 <= value <= 1e30
                ):
                    raise ValueError("Native balance quantities are incomplete or invalid.")
                balances[asset] = float(value)
            stamp = raw.get("timestamp")
            if stamp is not None and (
                isinstance(stamp, bool)
                or not isinstance(stamp, (int, float))
                or not math.isfinite(stamp)
                or not 0 <= stamp <= time.time() * 1000 + 5_000
            ):
                raise ValueError("Native balance update timestamp is invalid or future-dated.")
        except Exception as error:
            raise ValueError(
                "Could not obtain a complete fresh balance observation. Check account access and provider data; retained checks were preserved."
            ) from error
        with self.store.db() as db:
            db.execute("BEGIN")
            inputs = self.journal.inputs(db, connection.id)
            if scope != self.journal.scope(db, connection.id):
                raise ValueError("Account credentials or wallet scope changed during the read. Try again.")
        ended = time.time()
        if not 0 <= ended - started <= 30:
            raise ValueError("Balance observation took too long or the clock changed. Try again.")
        environment = (
            "demo" if connection.exchange == "demo" else "test" if connection.sandbox else "production"
        )
        if any(
            row["exchange"] != connection.exchange or row["environment"] != environment
            for kind in ("fills", "funding")
            for row in inputs[kind]
        ):
            raise ValueError("Retained history belongs to a different provider or funds environment.")
        return {
            "account_id": connection.id,
            "account": connection.label,
            "exchange": connection.exchange,
            "environment": environment,
            "wallet_scope": exchange_spec(connection.exchange).account,
            "scope": scope,
            "balances": balances,
            "started_ms": started * 1000,
            "ended_ms": ended * 1000,
            "observed_at": datetime.fromtimestamp(ended, UTC).isoformat(),
            "provider_timestamp": stamp,
            **inputs,
        }

    def _current(self, db, account_id, expected_id):
        current = self.journal.checkpoint(db, account_id)
        if (current["id"] if current else None) != expected_id:
            raise ValueError("The starting checkpoint changed. Refresh before trying again.")
        self._connection(account_id)
        return current

    def capture(self, account_id, replace_id=None):
        """Save a new starting observation, retaining prior comparison reports."""
        with self.locks[account_id]:
            connection = self._connection(account_id)
            with self.store.db() as db:
                self._current(db, account_id, replace_id)
            observed = self._observe(connection)
            observed["id"] = uuid4().hex
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                self._current(db, account_id, replace_id)
                if observed["scope"] != self.journal.scope(db, account_id):
                    raise ValueError("Account scope changed. Capture a new observation.")
                db.execute(
                    "INSERT INTO balance_checkpoints VALUES(?,?) ON CONFLICT(account_id) DO UPDATE SET payload=excluded.payload",
                    (account_id, json.dumps(observed, allow_nan=False)),
                )
            return self.journal.state(account_id)

    def check(self, account_id, checkpoint_id):
        """Read current balances and preserve an immutable per-asset comparison."""
        with self.locks[account_id]:
            connection = self._connection(account_id)
            with self.store.db() as db:
                checkpoint = self._current(db, account_id, checkpoint_id)
                if checkpoint["scope"] != self.journal.scope(db, account_id):
                    raise ValueError(
                        "Saved credentials, provider or wallet scope changed. Capture a new starting checkpoint."
                    )
            current = self._observe(connection)
            if current["started_ms"] <= checkpoint["ended_ms"]:
                raise ValueError(
                    "The clock moved behind the starting checkpoint. Try again after reviewing system time."
                )
            report = {
                "id": uuid4().hex,
                "checkpoint_id": checkpoint_id,
                **{
                    key: current[key]
                    for key in (
                        "account_id",
                        "account",
                        "exchange",
                        "environment",
                        "observed_at",
                        "wallet_scope",
                    )
                },
                "starting_at": checkpoint["observed_at"],
                **compare(checkpoint, current),
            }
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                self._current(db, account_id, checkpoint_id)
                if current["scope"] != self.journal.scope(db, account_id):
                    raise ValueError("Account scope changed during comparison. Saved evidence was preserved.")
                self.journal.save_report(db, report)
            return self.journal.state(account_id)
