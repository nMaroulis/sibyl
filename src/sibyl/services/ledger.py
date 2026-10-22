"""Normalized, attributable account fills and atomic history-import checkpoints."""

import hashlib
import json
import re
from datetime import UTC, datetime

from sibyl.exchanges.base import number
from sibyl.exchanges.history import TradePage
from sibyl.storage import Store


def now_iso() -> str:
    """Return a timezone-aware timestamp for local observations, not execution time."""
    return datetime.now(UTC).isoformat()


def _identity(value, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise ValueError("A fill is missing its native identity.")
    text = str(value)
    if not text or len(text) > 256 or any(ord(char) < 32 for char in text):
        raise ValueError("A fill has an invalid native identity.")
    return text


def ledger_fill(row: dict, job: dict) -> dict:
    """Validate a full fill before advancing a checkpoint; unknown fees stay unknown.

    Fill IDs are scoped to account and exact market. Fees retain their reported
    currencies and sign; no quote conversion, cost basis or P&L is invented.
    Invalid rows fail the whole page so a cursor cannot skip rejected records.
    """
    trade_id = _identity(row.get("id"))
    if row.get("symbol") != job["symbol"] or row.get("side") not in {"buy", "sell"}:
        raise ValueError("A fill has an unexpected market or direction.")
    stamp, quantity, price = (number(row.get(key)) for key in ("timestamp", "amount", "price"))
    notional = number(row.get("cost"))
    if (
        stamp is None
        or stamp <= 0
        or stamp > datetime.now(UTC).timestamp() * 1000 + 300_000
        or quantity is None
        or quantity <= 0
        or price is None
        or price <= 0
        or (row.get("cost") is not None and (notional is None or notional < 0))
    ):
        raise ValueError("A fill has invalid execution values.")
    fees = row.get("fees") or ([row["fee"]] if row.get("fee") else [])
    if not isinstance(fees, list) or len(fees) > 20:
        raise ValueError("A fill has invalid fee records.")
    normalized_fees = []
    for fee in fees:
        currency, cost = fee.get("currency"), number(fee.get("cost"))
        if currency is not None and (
            not isinstance(currency, str) or not re.fullmatch(r"[A-Z0-9]{1,20}", currency)
        ):
            raise ValueError("A fill has an invalid fee currency.")
        if fee.get("cost") is not None and cost is None:
            raise ValueError("A fill has an invalid fee quantity.")
        if currency is not None or cost is not None:
            normalized_fees.append({"currency": currency, "cost": cost})
    base, quote = job["symbol"].split("/")
    identity = hashlib.sha256(json.dumps([job["account_id"], job["symbol"], trade_id]).encode()).hexdigest()
    return {
        "id": identity,
        "trade_id": trade_id,
        "order_id": _identity(row.get("order"), optional=True),
        "account_id": job["account_id"],
        "account": job["account"],
        "exchange": job["exchange"],
        "environment": job["environment"],
        "symbol": job["symbol"],
        "base": base,
        "quote": quote,
        "timestamp_ms": stamp,
        "created_at": datetime.fromtimestamp(stamp / 1000, UTC).isoformat(),
        "side": row["side"],
        "quantity": quantity,
        "price": price,
        "notional": notional,
        "fees": normalized_fees,
        "fees_known": bool(normalized_fees)
        and all(fee["currency"] is not None and fee["cost"] is not None for fee in normalized_fees),
    }


class AccountLedger:
    """Keep fills and page cursors in the workspace database, without credentials.

    Each successful page and its checkpoint commit together. A crash before the
    commit repeats that page; unique native IDs make that repeat idempotent.
    Disconnecting keeps the audit history and stops its import jobs.
    """

    def __init__(self, store: Store, *, recover: bool = True):
        self.store = store
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS account_fills (
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL, symbol TEXT NOT NULL,
                    trade_id TEXT NOT NULL, timestamp_ms REAL NOT NULL,
                    payload TEXT NOT NULL, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
                    UNIQUE(account_id, symbol, trade_id)
                );
                CREATE INDEX IF NOT EXISTS account_fills_time ON account_fills(timestamp_ms DESC, id DESC);
                CREATE INDEX IF NOT EXISTS account_fills_account ON account_fills(account_id, symbol);
                CREATE INDEX IF NOT EXISTS account_fills_order ON account_fills(
                    account_id, symbol, json_extract(payload,'$.order_id')
                );
                CREATE TABLE IF NOT EXISTS account_sync (
                    account_id TEXT NOT NULL, symbol TEXT NOT NULL, status TEXT NOT NULL,
                    next_attempt REAL NOT NULL, last_attempt REAL NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(account_id, symbol)
                );
            """)
            # The application deliberately runs one API worker. Recover interrupted reads.
            rows = (
                db.execute("SELECT payload FROM account_sync WHERE status='running'").fetchall()
                if recover
                else []
            )
            for row in rows:
                job = json.loads(row[0])
                job["status"], job["next_attempt"] = "queued", 0
                self.write_job(db, job)

    @staticmethod
    def write_job(db, job: dict) -> None:
        """Write indexed scheduling fields and their complete private state together."""
        db.execute(
            "INSERT INTO account_sync VALUES(?,?,?,?,?,?) ON CONFLICT(account_id,symbol) DO UPDATE SET "
            "status=excluded.status,next_attempt=excluded.next_attempt,last_attempt=excluded.last_attempt,"
            "payload=excluded.payload",
            (
                job["account_id"],
                job["symbol"],
                job["status"],
                job["next_attempt"],
                job["last_attempt"],
                json.dumps(job, allow_nan=False),
            ),
        )

    @staticmethod
    def read_job(db, account_id: str, symbol: str) -> dict | None:
        """Read private checkpoint state inside the caller's transaction."""
        row = db.execute(
            "SELECT payload FROM account_sync WHERE account_id=? AND symbol=?", (account_id, symbol)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def jobs(self) -> list[dict]:
        """Return public progress without opaque provider cursors or raw errors."""
        with self.store.db() as db:
            rows = db.execute("SELECT payload FROM account_sync ORDER BY account_id,symbol").fetchall()
            counts = {
                (row[0], row[1]): {
                    "record_count": row[2],
                    "oldest_timestamp_ms": row[3],
                    "newest_timestamp_ms": row[4],
                }
                for row in db.execute(
                    "SELECT account_id,symbol,COUNT(*),MIN(timestamp_ms),MAX(timestamp_ms) FROM account_fills GROUP BY 1,2"
                )
            }
        return [
            {
                **{
                    key: value
                    for key, value in job.items()
                    if key not in {"cursor", "seen_cursors", "seen_pages", "revision", "last_attempt"}
                },
                **counts.get(
                    (job["account_id"], job["symbol"]),
                    {"record_count": 0, "oldest_timestamp_ms": None, "newest_timestamp_ms": None},
                ),
                "complete_history": False,
            }
            for job in (json.loads(row[0]) for row in rows)
        ]

    @staticmethod
    def upsert_fills(db, fills: list[dict], seen: str) -> tuple[int, int]:
        """Share native execution identities across history imports and order reconciliation."""
        inserted, updated = 0, 0
        for fill in fills:
            payload = json.dumps(fill, sort_keys=True, allow_nan=False)
            previous = db.execute("SELECT payload FROM account_fills WHERE id=?", (fill["id"],)).fetchone()
            inserted += previous is None
            updated += previous is not None and previous[0] != payload
            db.execute(
                "INSERT INTO account_fills VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "payload=excluded.payload,last_seen_at=excluded.last_seen_at,timestamp_ms=excluded.timestamp_ms",
                (
                    fill["id"],
                    fill["account_id"],
                    fill["symbol"],
                    fill["trade_id"],
                    fill["timestamp_ms"],
                    payload,
                    seen,
                    seen,
                ),
            )
        return inserted, updated

    def commit_page(self, job: dict, page: TradePage) -> None:
        """Atomically upsert a validated page, preserving concurrent pause/disconnect."""
        signature = hashlib.sha256(json.dumps(page.cursor, sort_keys=True).encode()).hexdigest()
        if len(page.items) > 100 or (
            not page.caught_up and (page.cursor == job["cursor"] or signature in job.get("seen_cursors", []))
        ):
            raise ValueError("The provider history cursor did not advance.")
        fills = [ledger_fill(row, job) for row in page.items]
        if len({fill["id"] for fill in fills}) != len(fills):
            raise ValueError("Duplicate fill identities in one page.")
        page_signature = (
            hashlib.sha256(
                json.dumps(sorted(fills, key=lambda row: row["id"]), sort_keys=True).encode()
            ).hexdigest()
            if fills
            else None
        )
        if page_signature and page_signature in job.get("seen_pages", []):
            raise ValueError("Fill history repeated a page without progress.")
        seen = now_iso()
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.read_job(db, job["account_id"], job["symbol"])
            if not current or current.get("revision") != job.get("revision"):
                return
            inserted, updated = self.upsert_fills(db, fills, seen)
            current.update(
                cursor=page.cursor,
                pages=current["pages"] + 1,
                inserted=current["inserted"] + inserted,
                updated=current["updated"] + updated,
                pass_pages=current.get("pass_pages", 0) + 1,
                pass_inserted=current.get("pass_inserted", 0) + inserted,
                pass_updated=current.get("pass_updated", 0) + updated,
                pass_complete=page.caught_up,
                last_success_at=seen,
                error=None,
                retries=0,
                next_attempt=0,
                retry_at=None,
                seen_cursors=[] if page.caught_up else [*job.get("seen_cursors", []), signature][-64:],
                seen_pages=[]
                if page.caught_up
                else [*job.get("seen_pages", []), *([page_signature] if page_signature else [])][-64:],
            )
            if current["status"] not in {"paused", "disconnected"}:
                current["status"] = "caught_up" if page.caught_up else "queued"
            if page.caught_up:
                current["caught_up_at"] = seen
                current["last_pass"] = {
                    "mode": current.get("mode", "incremental"),
                    "started_at": current.get("pass_started_at", current["started_at"]),
                    "completed_at": seen,
                    "pages": current["pass_pages"],
                    "inserted": current["pass_inserted"],
                    "updated": current["pass_updated"],
                }
            if not db.execute("SELECT 1 FROM connections WHERE id=?", (job["account_id"],)).fetchone():
                current["status"] = "disconnected"
            self.write_job(db, current)

    def fills(
        self,
        account_id: str = "",
        symbol: str = "",
        side: str = "",
        environment: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        """Read bounded retained fills and aggregate fee quantities by native currency."""
        clauses, values = [], []
        for column, value in (
            ("account_id", account_id),
            ("symbol", symbol),
            ("json_extract(payload,'$.side')", side),
            ("json_extract(payload,'$.environment')", environment),
        ):
            if value:
                clauses.append(f"{column}=?")
                values.append(value)
        where = " AND ".join(clauses) or "1=1"
        with self.store.db() as db:
            db.execute("BEGIN")
            total, oldest, newest = db.execute(
                f"SELECT COUNT(*),MIN(timestamp_ms),MAX(timestamp_ms) FROM account_fills WHERE {where}",
                values,
            ).fetchone()
            rows = db.execute(
                f"SELECT payload,first_seen_at,last_seen_at FROM account_fills WHERE {where} "
                "ORDER BY timestamp_ms DESC,id DESC LIMIT ? OFFSET ?",
                [*values, limit, offset],
            ).fetchall()
            fee_totals = db.execute(
                f"SELECT json_extract(f.value,'$.currency'), SUM(json_extract(f.value,'$.cost')) "
                f"FROM account_fills,json_each(payload,'$.fees') f WHERE {where} "
                "AND json_extract(f.value,'$.currency') IS NOT NULL "
                "AND json_extract(f.value,'$.cost') IS NOT NULL GROUP BY 1",
                values,
            ).fetchall()
            missing_fees = db.execute(
                f"SELECT COUNT(*) FROM account_fills WHERE {where} AND json_extract(payload,'$.fees_known')=0",
                values,
            ).fetchone()[0]
        return {
            "items": [
                {**json.loads(row[0]), "first_seen_at": row[1], "last_seen_at": row[2]} for row in rows
            ],
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": offset + len(rows) < total,
            "oldest_timestamp_ms": oldest,
            "newest_timestamp_ms": newest,
            "fee_totals": dict(fee_totals),
            "missing_fee_count": missing_fees,
            "complete_history": False,
            "note": "Retained fills for explicitly selected spot markets. Provider retention and late records can limit coverage. Funding movements have a separate ledger; opening inventory and cost basis are not established by these fills. These are not P&L or tax results.",
        }
