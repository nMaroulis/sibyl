"""Dated reference prices using Sibyl's bounded, exact-path valuation service."""

import hashlib
import json
from datetime import UTC, datetime

from sibyl.services.valuation import Valuation
from sibyl.strategies.execution.contracts import ExecutionGuard

MAX_AGE = 60


def configuration(db, source):
    """Hash encrypted feed configuration privately, without decrypting or exposing credentials."""
    row = db.execute("SELECT value FROM workspace_settings WHERE key='data:market'").fetchone()
    values = [row[0] if row else None]
    if source.startswith("connection:"):
        row = db.execute(
            "SELECT exchange,sandbox,credentials,EXISTS(SELECT 1 FROM active_accounts "
            "WHERE account_id=connections.id) FROM connections WHERE id=?",
            (source[11:],),
        ).fetchone()
        values.append([value.hex() if isinstance(value, bytes) else value for value in row] if row else None)
    return hashlib.sha256(json.dumps(values, default=lambda value: value.hex()).encode()).hexdigest()


def read(market, source, rows):
    """Price every required native asset; no balances, candles or exchange writes are requested."""
    assets = set()
    for row in rows:
        base, quote = row["symbol"].split("/")
        assets.add(quote)
        if row["retained"] or row.get("quantity", 0):
            assets.add(base)
    with market.snapshot(source):
        valuation = Valuation(market)
        metadata = valuation.metadata
        if metadata["environment"] != "production" or metadata["source"] == "demo":
            raise ExecutionGuard(
                "Choose a live public reference feed for shared limits, including test funds."
            )
        rates = {}
        for asset in sorted(assets):
            rate = valuation.price(asset)
            if rate["status"] not in {"fresh", "identity"} or rate["price"] is None:
                raise ExecutionGuard("Some strategy assets lack fresh dated conversion prices on this feed.")
            rates[asset] = {key: rate[key] for key in ("price", "path", "observed_at", "status")}
    return rates, {key: metadata[key] for key in ("source", "source_label", "environment")}


def fresh(sample, timestamp):
    """Recheck the assembly and original quote ages immediately before admitting a write."""
    age = (timestamp - datetime.fromisoformat(sample["as_of"])).total_seconds()
    if not 0 <= age <= MAX_AGE:
        raise ExecutionGuard("Shared strategy assessment expired. Refresh the portfolio limits assessment.")
    for rate in sample["rates"].values():
        if rate["status"] == "identity":
            continue
        age = (timestamp - datetime.fromisoformat(rate["observed_at"])).total_seconds()
        if not -60 <= age <= 300:
            raise ExecutionGuard("A shared strategy conversion price is stale or future-dated.")


def utcnow():
    return datetime.now(UTC)
