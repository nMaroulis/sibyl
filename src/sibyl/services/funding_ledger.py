"""Normalized funding observations and atomic, range-specific import checkpoints."""

import hashlib
import json
import re
from datetime import UTC, datetime

from sibyl.exchanges.base import number
from sibyl.exchanges.funding import FundingPage
from sibyl.services.import_worker import ImportLimitError
from sibyl.services.ledger import _identity, now_iso
from sibyl.storage import Store

NOTE = (
    "Reported native-asset movements, not investment returns or reconciled cash flows. "
    "Amounts and fees are shown separately; fee inclusion in the reported amount is not inferred. "
    "Internal records are not automatically paired across accounts. Pending/failed/unknown records "
    "are excluded from completed totals. Provider retention and late updates can limit coverage."
)
MAX_PAGES = 2000


def funding_event(row: dict, job: dict) -> dict:
    """Reject a whole page on invalid facts and strip addresses, secrets and provider metadata."""
    identity = _identity(row.get("native_id"))
    asset = row.get("asset")
    stamp, quantity = number(row.get("timestamp_ms")), number(row.get("quantity"))
    fee = row.get("fee") or {}
    currency, cost = fee.get("currency"), number(fee.get("cost"))
    if (
        row.get("kind") != job["stream"]
        or row.get("direction") not in {"in", "out"}
        or row.get("status") not in {"pending", "completed", "failed", "cancelled", "restricted", "unknown"}
        or not isinstance(asset, str)
        or not re.fullmatch(r"[A-Z0-9][A-Z0-9.]{0,19}", asset)
        or stamp is None
        or stamp <= 0
        or not job["start_ms"] <= stamp <= job["end_ms"]
        or stamp > datetime.now(UTC).timestamp() * 1000 + 300_000
        or quantity is None
        or not 0 <= quantity <= 1e30
        or (fee.get("cost") is not None and (cost is None or abs(cost) > 1e30))
        or (
            currency is not None
            and (not isinstance(currency, str) or not re.fullmatch(r"[A-Z0-9][A-Z0-9.]{0,19}", currency))
        )
        or (quantity == 0 and not cost)
        or row.get("amount_basis") not in {"provider_reported", "ledger_amount"}
        or not isinstance(row.get("internal"), bool)
    ):
        raise ValueError("Invalid funding event.")
    return {
        "id": hashlib.sha256(json.dumps([job["account_id"], job["stream"], identity]).encode()).hexdigest(),
        "native_id": identity,
        "reference": _identity(row.get("reference"), optional=True),
        **{key: job[key] for key in ("account_id", "account", "exchange", "environment")},
        "kind": job["stream"],
        "asset": asset,
        "timestamp_ms": stamp,
        "created_at": datetime.fromtimestamp(stamp / 1000, UTC).isoformat(),
        "direction": row["direction"],
        "quantity": quantity,
        "status": row["status"],
        "fee": {"currency": currency, "cost": cost},
        "fee_known": currency is not None and cost is not None,
        "internal": row["internal"],
        "amount_basis": row["amount_basis"],
    }


class FundingLedger:
    """Keep funding observations distinct from fills, virtual balances and user cost basis."""

    def __init__(self, store: Store):
        self.store = store
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS funding_events (
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL, stream TEXT NOT NULL,
                    native_id TEXT NOT NULL, asset TEXT NOT NULL, timestamp_ms REAL NOT NULL,
                    status TEXT NOT NULL, payload TEXT NOT NULL, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
                    UNIQUE(account_id,stream,native_id)
                );
                CREATE INDEX IF NOT EXISTS funding_events_scope ON funding_events(account_id,asset,timestamp_ms);
                CREATE TABLE IF NOT EXISTS funding_sync (
                    account_id TEXT NOT NULL, stream TEXT NOT NULL, status TEXT NOT NULL,
                    next_attempt REAL NOT NULL, last_attempt REAL NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(account_id,stream)
                );
            """)
            for row in db.execute("SELECT payload FROM funding_sync WHERE status='running'").fetchall():
                job = json.loads(row[0])
                job.update(status="queued", next_attempt=0)
                self.write_job(db, job)

    @staticmethod
    def read_job(db, account_id: str, stream: str) -> dict | None:
        """Read a private cursor inside the caller's transaction."""
        row = db.execute(
            "SELECT payload FROM funding_sync WHERE account_id=? AND stream=?", (account_id, stream)
        ).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def write_job(db, job: dict) -> None:
        """Update the scheduler index and private state together."""
        db.execute(
            "INSERT INTO funding_sync VALUES(?,?,?,?,?,?) ON CONFLICT(account_id,stream) DO UPDATE SET "
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

    def jobs(self) -> list[dict]:
        """Expose range/progress without cursors, fingerprints or raw provider errors."""
        with self.store.db() as db:
            rows = db.execute("SELECT payload FROM funding_sync ORDER BY account_id,stream").fetchall()
            counts = {
                (row[0], row[1]): row[2]
                for row in db.execute("SELECT account_id,stream,COUNT(*) FROM funding_events GROUP BY 1,2")
            }
        return [
            {
                **{
                    key: value
                    for key, value in job.items()
                    if key not in {"cursor", "seen_cursors", "seen_pages", "revision", "last_attempt"}
                },
                "record_count": counts.get((job["account_id"], job["stream"]), 0),
                "complete_history": False,
            }
            for job in (json.loads(row[0]) for row in rows)
        ]

    def commit_page(self, job: dict, page: FundingPage) -> None:
        """Commit observations and checkpoint together; a new range invalidates an old in-flight read."""
        signature = hashlib.sha256(json.dumps(page.cursor, sort_keys=True).encode()).hexdigest()
        if job["pages"] >= MAX_PAGES:
            raise ImportLimitError("Funding page budget reached; choose a smaller date range.")
        if len(page.items) > 50 or (
            not page.caught_up and (page.cursor == job["cursor"] or signature in job.get("seen_cursors", []))
        ):
            raise ValueError("Funding cursor did not advance.")
        events = [funding_event(row, job) for row in page.items]
        if len({row["id"] for row in events}) != len(events):
            raise ValueError("Duplicate funding identities in one page.")
        # Detect offset endpoints ignoring pagination, even when their synthetic offset advances.
        page_signature = (
            hashlib.sha256(json.dumps(sorted(row["id"] for row in events)).encode()).hexdigest()
            if events
            else None
        )
        if page_signature and page_signature in job.get("seen_pages", []):
            raise ValueError("Funding page repeated without progress.")
        seen = now_iso()
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.read_job(db, job["account_id"], job["stream"])
            if current["revision"] != job["revision"]:
                return
            inserted, updated = 0, 0
            for row in events:
                payload = json.dumps(row, sort_keys=True, allow_nan=False)
                previous = db.execute(
                    "SELECT payload FROM funding_events WHERE id=?", (row["id"],)
                ).fetchone()
                inserted += previous is None
                updated += previous is not None and previous[0] != payload
                db.execute(
                    "INSERT INTO funding_events VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                    "asset=excluded.asset,timestamp_ms=excluded.timestamp_ms,status=excluded.status,payload=excluded.payload,last_seen_at=excluded.last_seen_at",
                    (
                        row["id"],
                        row["account_id"],
                        row["kind"],
                        row["native_id"],
                        row["asset"],
                        row["timestamp_ms"],
                        row["status"],
                        payload,
                        seen,
                        seen,
                    ),
                )
            current.update(
                cursor=page.cursor,
                pages=current["pages"] + 1,
                inserted=current["inserted"] + inserted,
                updated=current["updated"] + updated,
                last_success_at=seen,
                retries=0,
                error=None,
                next_attempt=0,
                retry_at=None,
                seen_cursors=[*job.get("seen_cursors", []), signature][-128:],
                seen_pages=[*job.get("seen_pages", []), *([page_signature] if page_signature else [])][-128:],
            )
            if current["status"] not in {"paused", "disconnected"}:
                current["status"] = "caught_up" if page.caught_up else "queued"
            if page.caught_up:
                current["caught_up_at"] = seen
            saved = db.execute("SELECT 1 FROM connections WHERE id=?", (job["account_id"],)).fetchone()
            active = db.execute(
                "SELECT 1 FROM active_accounts WHERE account_id=?", (job["account_id"],)
            ).fetchone()
            if not saved:
                current["status"] = "disconnected"
            elif not active:
                current["status"] = "paused"
            self.write_job(db, current)

    def events(
        self,
        account_id: str = "",
        asset: str = "",
        kind: str = "",
        status: str = "",
        environment: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Page original observations and summarize completed quantities without mixing native assets."""
        clauses, values = [], []
        for column, value in [
            ("account_id", account_id),
            ("asset", asset),
            ("stream", kind),
            ("status", status),
            ("json_extract(payload,'$.environment')", environment),
        ]:
            if value:
                clauses.append(f"{column}=?")
                values.append(value)
        where = " AND ".join(clauses) or "1=1"
        with self.store.db() as db:
            db.execute("BEGIN")
            total = db.execute(f"SELECT COUNT(*) FROM funding_events WHERE {where}", values).fetchone()[0]
            items = db.execute(
                f"SELECT payload,first_seen_at,last_seen_at FROM funding_events WHERE {where} ORDER BY timestamp_ms DESC,id DESC LIMIT ? OFFSET ?",
                [*values, limit, offset],
            ).fetchall()
            summaries = db.execute(
                f"SELECT account_id,MAX(json_extract(payload,'$.account')),json_extract(payload,'$.environment'),asset,stream,"
                "json_extract(payload,'$.direction'),SUM(json_extract(payload,'$.quantity')),COUNT(*) "
                f"FROM funding_events WHERE {where} AND status='completed' GROUP BY 1,3,4,5,6 ORDER BY 3,2,4,5,6",
                values,
            ).fetchall()
            fees = db.execute(
                "SELECT account_id,json_extract(payload,'$.environment'),json_extract(payload,'$.fee.currency'),SUM(json_extract(payload,'$.fee.cost')) "
                f"FROM funding_events WHERE {where} AND status='completed' AND json_extract(payload,'$.fee_known')=1 GROUP BY 1,2,3 ORDER BY 1,2,3",
                values,
            ).fetchall()
            from sibyl.services.transfer_reconciliation import memberships

            reconciliation = memberships(db, [json.loads(row[0])["id"] for row in items])
        return {
            "items": [
                {
                    **json.loads(row[0]),
                    "first_seen_at": row[1],
                    "last_seen_at": row[2],
                    "reconciliation": reconciliation.get(json.loads(row[0])["id"]),
                }
                for row in items
            ],
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(items) < total,
            "summaries": [
                dict(
                    zip(
                        (
                            "account_id",
                            "account",
                            "environment",
                            "asset",
                            "kind",
                            "direction",
                            "quantity",
                            "count",
                        ),
                        row,
                        strict=True,
                    )
                )
                for row in summaries
            ],
            "fees": [
                dict(zip(("account_id", "environment", "currency", "quantity"), row, strict=True))
                for row in fees
            ],
            "complete_history": False,
            "note": NOTE,
        }
