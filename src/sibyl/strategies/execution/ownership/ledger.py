"""Immutable attribution receipts and pinned native evidence for strategy replay.

Attributions are not trades. Their base units/cost basis join native fill replay,
and their dated reference value is a capital flow, never exchange cash or sale
proceeds. Old-order fill corrections invalidate the attribution and its descendants;
new orders after an attribution do not invalidate it.
"""

import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def scope(job):
    return {key: job[key] for key in ("id", "connection_id", "exchange", "sandbox")} | {
        "symbol": job["parameters"]["symbol"]
    }


def native(db, job, order_ids=None):
    orders = [
        json.loads(row[0])
        for row in db.execute(
            "SELECT payload FROM exchange_orders WHERE json_extract(payload,'$.strategy_job_id')=? ORDER BY id",
            (job["id"],),
        )
    ]
    if order_ids is not None:
        orders = [row for row in orders if row["id"] in order_ids]
    values = []
    for row in orders:
        fills = [
            json.loads(f[0])
            for f in db.execute(
                "SELECT payload FROM account_fills WHERE account_id=? AND symbol=? "
                "AND json_extract(payload,'$.order_id')=? ORDER BY id",
                (job["connection_id"], job["parameters"]["symbol"], row.get("exchange_order_id")),
            )
        ]
        sync = db.execute("SELECT payload FROM order_fill_sync WHERE intent_id=?", (row["id"],)).fetchone()
        caught_up = json.loads(sync[0]).get("caught_up") if sync else None
        values.append(
            {
                "caught_up": caught_up,
                "order": {
                    key: row.get(key)
                    for key in (
                        "id",
                        "status",
                        "exchange_order_id",
                        "filled",
                        "cost",
                        "request",
                        "strategy_abandoned",
                    )
                },
                "fills": [
                    {
                        key: f.get(key)
                        for key in (
                            "id",
                            "order_id",
                            "timestamp_ms",
                            "side",
                            "quantity",
                            "price",
                            "notional",
                            "fees_known",
                            "fees",
                        )
                    }
                    for f in fills
                ],
            }
        )
    return values


def pin(db, job):
    """Pin the economic facts of existing orders; later new orders remain independent."""
    values = native(db, job)
    return {
        "job_id": job["id"],
        "scope": scope(job),
        "order_ids": [v["order"]["id"] for v in values],
        "digest": digest(values),
    }


def current(db, evidence):
    row = db.execute("SELECT payload FROM strategy_jobs WHERE id=?", (evidence["job_id"],)).fetchone()
    if row is None:
        return False
    job = json.loads(row[0])
    return (
        scope(job) == evidence["scope"]
        and digest(native(db, job, evidence["order_ids"])) == evidence["digest"]
    )


def events(db, identity):
    return [
        json.loads(row[0])
        for row in db.execute(
            "SELECT payload FROM strategy_ownership_events WHERE job_id=? ORDER BY sequence",
            (identity,),
        )
    ]


def dependencies(db, job):
    """Carry source dependencies across handoffs so late corrections block descendants."""
    result = {digest(value): value for event in events(db, job["id"]) for value in event["pins"]}
    evidence = pin(db, job)
    result[digest(evidence)] = evidence
    return list(result.values())


def append(db, event):
    db.execute(
        "INSERT INTO strategy_ownership_events(id,job_id,payload) VALUES(?,?,?)",
        (event["id"], event["job_id"], json.dumps(event, allow_nan=False)),
    )


def replay(db, identity):
    """Read receipts and detect changed ancestors without contacting any exchange."""
    items = events(db, identity)
    stale = any(not current(db, evidence) for item in items for evidence in item["pins"])
    return items, stale
