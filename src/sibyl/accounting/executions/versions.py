"""Append-only normalized fill observations, committed with the authoritative ledger.

The first retained baseline is not a reconstruction of unseen provider changes.
Identical imports do not create revisions; corrections retain the entire prior
normalized fact without provider payloads or credentials.
"""

import hashlib
import json


def schema(db):
    """Create revision storage on an existing caller-owned transaction."""
    db.execute(
        "CREATE TABLE IF NOT EXISTS fill_versions (fill_id TEXT NOT NULL, revision INTEGER NOT NULL, observed_at TEXT NOT NULL, kind TEXT NOT NULL, digest TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(fill_id,revision))"
    )


def record(db, before, after, observed_at):
    """Append only material changes; rollback follows the fill/checkpoint transaction."""
    latest = db.execute(
        "SELECT revision,digest FROM fill_versions WHERE fill_id=? ORDER BY revision DESC LIMIT 1",
        (after["id"],),
    ).fetchone()
    if latest is None and before is not None:
        _append(db, before, observed_at, 1, "retained_baseline")
        latest = (1, _digest(before))
    digest = _digest(after)
    if latest is None or latest[1] != digest:
        _append(
            db,
            after,
            observed_at,
            latest[0] + 1 if latest else 1,
            "correction" if latest else "first_observed",
        )


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _append(db, value, observed_at, revision, kind):
    db.execute(
        "INSERT INTO fill_versions VALUES(?,?,?,?,?,?)",
        (
            value["id"],
            revision,
            observed_at,
            kind,
            _digest(value),
            json.dumps(value, sort_keys=True, allow_nan=False),
        ),
    )


def history(store, fill_id, offset=0, limit=50):
    """Read a bounded newest-first history; legacy baselines are labeled explicitly."""
    with store.db() as db:
        if not db.execute("SELECT 1 FROM account_fills WHERE id=?", (fill_id,)).fetchone():
            raise LookupError("Fill not found.")
        rows = db.execute(
            "SELECT * FROM fill_versions WHERE fill_id=? ORDER BY revision DESC LIMIT ? OFFSET ?",
            (fill_id, limit, offset),
        ).fetchall()
        count = db.execute("SELECT COUNT(*) FROM fill_versions WHERE fill_id=?", (fill_id,)).fetchone()[0]
    return {
        "fill_id": fill_id,
        "items": [{**dict(row), "payload": json.loads(row["payload"])} for row in rows],
        "total": count,
        "offset": offset,
        "limit": limit,
    }
