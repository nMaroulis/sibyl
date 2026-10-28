"""Shared SQLite job storage and private account binding for automatic funding reads."""

import hashlib
import json


def account_version(db, account_id):
    """Bind an in-flight read to encrypted account configuration without decrypting it."""
    row = db.execute(
        "SELECT exchange,sandbox,credentials FROM connections WHERE id=?", (account_id,)
    ).fetchone()
    return hashlib.sha256(json.dumps([row[0], row[1], row[2].hex()]).encode()).hexdigest() if row else None


class FundingJobs:
    """Read/write fixed internal job tables inside the caller's transaction."""

    table: str

    @classmethod
    def read_job(cls, db, account_id, stream):
        """Read one private job inside the caller's transaction."""
        row = db.execute(
            f"SELECT payload FROM {cls.table} WHERE account_id=? AND stream=?", (account_id, stream)
        ).fetchone()
        return json.loads(row[0]) if row else None

    @classmethod
    def write_job(cls, db, job):
        """Keep the scheduler index and serialized job state consistent."""
        db.execute(
            f"INSERT INTO {cls.table} VALUES(?,?,?,?,?,?) ON CONFLICT(account_id,stream) DO UPDATE SET "
            "status=excluded.status,next_attempt=excluded.next_attempt,last_attempt=excluded.last_attempt,payload=excluded.payload",
            (
                job["account_id"],
                job["stream"],
                job["status"],
                job["next_attempt"],
                job["last_attempt"],
                json.dumps(job, allow_nan=False),
            ),
        )
