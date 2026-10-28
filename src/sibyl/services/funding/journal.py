"""Durable, bounded pending-record rechecks independent of manual import ranges.

A pass freezes at most one minute of creation times and the versions of retained
targets. Pages may update only those unchanged targets. Missing records remain
observations, not cancellations; five exhausted misses request human review.
"""

import hashlib
import json
import time
from datetime import UTC, datetime
from uuid import uuid4

from sibyl.accounting.funding.rules import fingerprint
from sibyl.services.funding.contracts import MISSING_LIMIT, PAGE_LIMIT, READ_GAP, TARGET_LIMIT
from sibyl.services.funding_ledger import validated_page, write_event
from sibyl.services.ledger import now_iso


def account_version(db, account_id):
    """Bind an in-flight read to encrypted account configuration without decrypting it."""
    row = db.execute(
        "SELECT exchange,sandbox,credentials FROM connections WHERE id=?", (account_id,)
    ).fetchone()
    return hashlib.sha256(json.dumps([row[0], row[1], row[2].hex()]).encode()).hexdigest() if row else None


class RefreshJournal:
    """Persist controls, native cursors and per-record outcomes in the workspace SQLite database."""

    def __init__(self, store):
        self.store = store
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS funding_refresh (
                    account_id TEXT NOT NULL, stream TEXT NOT NULL, status TEXT NOT NULL,
                    next_attempt REAL NOT NULL, last_attempt REAL NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(account_id,stream)
                );
                CREATE TABLE IF NOT EXISTS funding_rechecks (
                    event_id TEXT PRIMARY KEY, next_attempt REAL NOT NULL,
                    missing_checks INTEGER NOT NULL, checked_at TEXT NOT NULL,
                    found_at TEXT, outcome TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS funding_pending ON funding_events(account_id,stream,status,timestamp_ms);
            """)
            for row in db.execute("SELECT payload FROM funding_refresh WHERE status='running'").fetchall():
                job = json.loads(row[0])
                job.update(status="queued", next_attempt=0)
                self.write_job(db, job)

    @staticmethod
    def read_job(db, account_id, stream):
        row = db.execute(
            "SELECT payload FROM funding_refresh WHERE account_id=? AND stream=?", (account_id, stream)
        ).fetchone()
        return json.loads(row[0]) if row else None

    @staticmethod
    def write_job(db, job):
        db.execute(
            "INSERT INTO funding_refresh VALUES(?,?,?,?,?,?) ON CONFLICT(account_id,stream) DO UPDATE SET "
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

    @staticmethod
    def pending(db, account_id, stream, *, due=None):
        """Select a bounded watch batch; provider-wide discovery is deliberately outside this worker."""
        return db.execute(
            "SELECT e.payload FROM funding_events e LEFT JOIN funding_rechecks r ON r.event_id=e.id "
            "WHERE e.account_id=? AND e.stream=? AND e.status IN ('pending','restricted','unknown') "
            + (
                "AND COALESCE(r.next_attempt,0)<=? AND COALESCE(r.missing_checks,0)<? AND e.timestamp_ms<=? "
                if due is not None
                else ""
            )
            + "ORDER BY COALESCE(r.next_attempt,0),e.timestamp_ms,e.id LIMIT ?",
            [
                account_id,
                stream,
                *([due, MISSING_LIMIT, due * 1000 - 1000] if due is not None else []),
                TARGET_LIMIT + 1,
            ],
        ).fetchall()

    def schedule(self, now):
        """Queue one creation-time window with frozen source versions, never a whole historical scan."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT payload FROM funding_refresh WHERE status='idle' AND next_attempt<=? ORDER BY last_attempt,account_id,stream LIMIT 1",
                (now,),
            ).fetchone()
            if not row:
                return
            job = json.loads(row[0])
            if not job["enabled"]:
                return
            active = db.execute(
                "SELECT 1 FROM active_accounts WHERE account_id=?", (job["account_id"],)
            ).fetchone()
            scope = account_version(db, job["account_id"])
            if scope != job["account_version"] or not active:
                job.update(
                    enabled=False,
                    status="paused" if scope else "disconnected",
                    revision=uuid4().hex,
                    error="Account configuration or activation changed. Review before enabling pending updates again.",
                )
            else:
                rows = [
                    json.loads(item[0])
                    for item in self.pending(db, job["account_id"], job["stream"], due=now)
                ]
                job.update(next_attempt=now + job["interval_minutes"] * 60)
                if rows:
                    start = max(1, int(rows[0]["timestamp_ms"]) // 60_000 * 60_000 - 1000)
                    end = min(int(now * 1000), start + 62_000)
                    targets = [item for item in rows if start <= item["timestamp_ms"] <= end][:TARGET_LIMIT]
                    job.update(
                        status="queued",
                        start_ms=start,
                        end_ms=end,
                        cursor={"start": start, "end": end},
                        targets={item["id"]: fingerprint(item) for item in targets},
                        outcomes={},
                        pages=0,
                        seen_pages=[],
                        seen_cursors=[],
                        retries=0,
                        retry_at=None,
                        error=None,
                        next_attempt=0,
                        pass_updated=0,
                    )
            self.write_job(db, job)

    def commit_page(self, job, page):
        """Commit only unchanged retained targets, with the refresh cursor and per-record outcomes."""
        events, signature, page_signature = validated_page(job, page, PAGE_LIMIT)
        now, seen = time.time(), now_iso()
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.read_job(db, job["account_id"], job["stream"])
            if not current or not current["enabled"] or current["revision"] != job["revision"]:
                return
            active = db.execute(
                "SELECT 1 FROM active_accounts WHERE account_id=?", (job["account_id"],)
            ).fetchone()
            if account_version(db, job["account_id"]) != current["account_version"] or not active:
                current.update(
                    enabled=False,
                    status="paused",
                    revision=uuid4().hex,
                    error="Account configuration or activation changed; the in-flight page was discarded.",
                )
                self.write_job(db, current)
                return
            updated = 0
            for event in events:
                if event["id"] not in current["targets"]:
                    continue
                if event["id"] in current["outcomes"]:
                    raise ValueError("A funding target repeated across native pages.")
                saved = db.execute("SELECT payload FROM funding_events WHERE id=?", (event["id"],)).fetchone()
                if not saved or fingerprint(json.loads(saved[0])) != current["targets"][event["id"]]:
                    current["outcomes"][event["id"]] = "source_changed"
                    continue
                _, changed = write_event(db, event, seen)
                updated += changed
                current["outcomes"][event["id"]] = "found"
            current.update(
                cursor=page.cursor,
                pages=current["pages"] + 1,
                retries=0,
                error=None,
                retry_at=None,
                last_success_at=seen,
                pass_updated=current["pass_updated"] + updated,
                updated=current["updated"] + updated,
                next_attempt=0,
                seen_cursors=[*job.get("seen_cursors", []), signature],
                seen_pages=[*job.get("seen_pages", []), *([page_signature] if page_signature else [])],
            )
            current["status"] = "idle" if page.caught_up else "queued"
            if page.caught_up:
                for event_id in current["targets"]:
                    outcome = current["outcomes"].get(event_id, "not_returned")
                    previous = db.execute(
                        "SELECT missing_checks,found_at FROM funding_rechecks WHERE event_id=?", (event_id,)
                    ).fetchone()
                    misses = (previous[0] if previous else 0) + 1 if outcome == "not_returned" else 0
                    found_at = seen if outcome == "found" else previous[1] if previous else None
                    db.execute(
                        "INSERT INTO funding_rechecks VALUES(?,?,?,?,?,?) ON CONFLICT(event_id) DO UPDATE SET "
                        "next_attempt=excluded.next_attempt,missing_checks=excluded.missing_checks,checked_at=excluded.checked_at,found_at=excluded.found_at,outcome=excluded.outcome",
                        (event_id, now + current["interval_minutes"] * 60, misses, seen, found_at, outcome),
                    )
                current.update(
                    last_checked_at=seen,
                    checked=current["checked"] + len(current["targets"]),
                    next_attempt=now + READ_GAP,
                    targets={},
                    outcomes={},
                    cursor={},
                )
            self.write_job(db, current)

    def snapshot(self):
        """Expose progress and ten records needing review; keep cursors and credential hashes private."""
        public = []
        with self.store.db() as db:
            db.execute("BEGIN")
            for row in db.execute("SELECT payload FROM funding_refresh ORDER BY account_id,stream"):
                job = json.loads(row[0])
                stats = db.execute(
                    "SELECT COUNT(*),COALESCE(SUM(COALESCE(r.missing_checks,0)>=?),0) "
                    "FROM funding_events e LEFT JOIN funding_rechecks r ON r.event_id=e.id "
                    "WHERE e.account_id=? AND e.stream=? AND e.status IN ('pending','restricted','unknown')",
                    (MISSING_LIMIT, job["account_id"], job["stream"]),
                ).fetchone()
                fields = (
                    "account_id",
                    "account",
                    "exchange",
                    "environment",
                    "stream",
                    "revision",
                    "enabled",
                    "interval_minutes",
                    "status",
                    "last_checked_at",
                    "last_success_at",
                    "checked",
                    "updated",
                    "pages",
                    "error",
                    "retry_at",
                )
                public.append(
                    {
                        **{key: job.get(key) for key in fields},
                        "pending_count": stats[0],
                        "needs_review": stats[1],
                        "next_check_at": datetime.fromtimestamp(job["next_attempt"], UTC).isoformat()
                        if job["enabled"] and job["next_attempt"]
                        else None,
                    }
                )
                attention = db.execute(
                    "SELECT e.id,json_extract(e.payload,'$.native_id'),e.asset,e.status,r.checked_at,r.missing_checks "
                    "FROM funding_events e JOIN funding_rechecks r ON r.event_id=e.id "
                    "WHERE e.account_id=? AND e.stream=? AND e.status IN ('pending','restricted','unknown') "
                    "AND r.missing_checks>=? ORDER BY r.checked_at DESC,e.id LIMIT 10",
                    (job["account_id"], job["stream"], MISSING_LIMIT),
                ).fetchall()
                public[-1]["attention"] = [
                    dict(
                        zip(
                            ("id", "native_id", "asset", "status", "checked_at", "missing_checks"),
                            item,
                            strict=True,
                        )
                    )
                    for item in attention
                ]
                public[-1]["attention_limit"] = 10
        return public
