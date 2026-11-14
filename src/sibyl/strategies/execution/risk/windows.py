"""Observed rolling P&L, separate from UTC-day accounting and native write receipts.

Marks retain the first complete observation per minute for eight days and the
preceding boundary. Missing time intervals are never interpolated. The last mark
at or before the cutoff is carried forward, so an outage cannot erase a loss.
"""

import json
from datetime import datetime

from sibyl.strategies.execution.contracts import ExecutionGuard


def initialize(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS strategy_loss_marks(environment TEXT NOT NULL,minute INTEGER NOT NULL,as_of TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(environment,minute))"
    )


def measure(db, environment, current, now, hours):
    """Compare current native-fill P&L with the conservative observed window boundary."""
    last = db.execute(
        "SELECT as_of FROM strategy_loss_marks WHERE environment=? ORDER BY minute DESC LIMIT 1",
        (environment,),
    ).fetchone()
    if last and datetime.fromisoformat(last[0]) > now:
        raise ExecutionGuard("The UTC clock moved backwards. Rolling-loss assessment is blocked.")
    cutoff = int(now.timestamp() // 60) - hours * 60
    row = db.execute(
        "SELECT as_of,payload FROM strategy_loss_marks WHERE environment=? AND minute<=? ORDER BY minute DESC LIMIT 1",
        (environment, cutoff),
    ).fetchone()
    if row is None:
        row = db.execute(
            "SELECT as_of,payload FROM strategy_loss_marks WHERE environment=? ORDER BY minute LIMIT 1",
            (environment,),
        ).fetchone()
    baseline, started = (json.loads(row[1]), row[0]) if row else (current, now.isoformat())
    if set(baseline) - set(current):
        raise ExecutionGuard("A rolling-loss strategy is missing. Restore its ledger before submission.")
    pnl = sum(value - baseline.get(identity, 0.0) for identity, value in current.items())
    return dict(window_pnl=pnl, window_loss=max(0.0, -pnl), window_started_at=started, window_hours=hours)


def record(db, environment, sample):
    """Persist at most one immutable complete mark per minute in the admission transaction."""
    minute = int(datetime.fromisoformat(sample["as_of"]).timestamp() // 60)
    current = {row["id"]: row["pnl"] for row in sample["runs"]}
    db.execute(
        "INSERT OR IGNORE INTO strategy_loss_marks VALUES(?,?,?,?)",
        (environment, minute, sample["as_of"], json.dumps(current, allow_nan=False)),
    )
    cutoff = minute - 8 * 24 * 60
    db.execute(
        "DELETE FROM strategy_loss_marks WHERE environment=? AND minute<? AND minute<>(SELECT MAX(minute) FROM strategy_loss_marks WHERE environment=? AND minute<?)",
        (environment, cutoff, environment, cutoff),
    )
