"""Frozen rolling-window passes, source-version guards and bounded observed coverage reports."""

import json
import time
from datetime import UTC, datetime
from uuid import uuid4

from sibyl.accounting.funding.versions import source_version as fingerprint
from sibyl.exchanges.funding import DAY
from sibyl.services.funding.contracts import SCAN_PAGE_LIMIT, SCAN_SOURCE_LIMIT
from sibyl.services.funding.coverage import cover_gaps
from sibyl.services.funding.state import FundingJobs, account_version
from sibyl.services.funding_ledger import validated_page, write_event
from sibyl.services.ledger import now_iso


class ScanJournal(FundingJobs):
    """Store a bounded current pass and twenty completed reports per account/stream."""

    table = "funding_scans"

    def __init__(self, store):
        self.store = store
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS funding_scans (
                    account_id TEXT NOT NULL, stream TEXT NOT NULL, status TEXT NOT NULL,
                    next_attempt REAL NOT NULL, last_attempt REAL NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(account_id,stream)
                );
                CREATE TABLE IF NOT EXISTS funding_scan_sources (
                    account_id TEXT NOT NULL, stream TEXT NOT NULL, event_id TEXT NOT NULL, source_version TEXT NOT NULL,
                    PRIMARY KEY(account_id,stream,event_id)
                );
                CREATE TABLE IF NOT EXISTS funding_scan_seen (
                    account_id TEXT NOT NULL, stream TEXT NOT NULL, event_id TEXT NOT NULL,
                    PRIMARY KEY(account_id,stream,event_id)
                );
                CREATE TABLE IF NOT EXISTS funding_scan_reports (
                    id TEXT PRIMARY KEY, account_id TEXT NOT NULL, stream TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS funding_scan_report_account ON funding_scan_reports(account_id,stream);
            """)
            for row in db.execute("SELECT payload FROM funding_scans WHERE status='running'").fetchall():
                job = json.loads(row[0])
                job.update(status="queued", next_attempt=0)
                self.write_job(db, job)

    @staticmethod
    def clear_pass(db, account_id, stream):
        """Discard only temporary frozen-source/seen indexes; preserve observations and reports."""
        for table in ("funding_scan_sources", "funding_scan_seen"):
            db.execute(f"DELETE FROM {table} WHERE account_id=? AND stream=?", (account_id, stream))

    def schedule(self, now):
        """Freeze a recent window ending one minute behind now; oversize inputs stop visibly."""
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT payload FROM funding_scans WHERE status='idle' AND next_attempt<=? ORDER BY last_attempt,account_id,stream LIMIT 1",
                (now,),
            ).fetchone()
            if not row:
                return
            job = json.loads(row[0])
            if not job["enabled"]:
                return
            scope = account_version(db, job["account_id"])
            active = db.execute(
                "SELECT 1 FROM active_accounts WHERE account_id=?", (job["account_id"],)
            ).fetchone()
            if scope != job["account_version"] or not active:
                job.update(
                    enabled=False,
                    status="paused" if scope else "disconnected",
                    revision=uuid4().hex,
                    error="Account configuration or activation changed. Review before enabling recent sync again.",
                )
            else:
                end = int(now * 1000) - 60_000
                start = max(1, end - job["lookback_days"] * DAY)
                sources = db.execute(
                    "SELECT payload FROM funding_events WHERE account_id=? AND stream=? AND timestamp_ms BETWEEN ? AND ? LIMIT ?",
                    (job["account_id"], job["stream"], start, end, SCAN_SOURCE_LIMIT + 1),
                ).fetchall()
                if len(sources) > SCAN_SOURCE_LIMIT:
                    job.update(
                        status="error",
                        error="Recent window exceeds 10,000 retained records. Choose a shorter lookback.",
                    )
                else:
                    self.clear_pass(db, job["account_id"], job["stream"])
                    db.executemany(
                        "INSERT INTO funding_scan_sources VALUES(?,?,?,?)",
                        [
                            (job["account_id"], job["stream"], event["id"], fingerprint(event))
                            for event in (json.loads(item[0]) for item in sources)
                        ],
                    )
                    job.update(
                        status="queued",
                        run_id=uuid4().hex,
                        start_ms=start,
                        end_ms=end,
                        cursor={"start": start, "end": end},
                        next_attempt=0,
                        pages=0,
                        seen_cursors=[],
                        seen_pages=[],
                        pass_inserted=0,
                        pass_updated=0,
                        conflicts=0,
                        retries=0,
                        retry_at=None,
                        error=None,
                    )
            self.write_job(db, job)

    def commit_page(self, job, page):
        """Preserve concurrent source changes and commit native facts, audit and cursor atomically."""
        events, signature, page_signature = validated_page(job, page, SCAN_PAGE_LIMIT)
        seen = now_iso()
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = self.read_job(db, job["account_id"], job["stream"])
            if (
                not current
                or not current["enabled"]
                or current["revision"] != job["revision"]
                or current.get("run_id") != job.get("run_id")
            ):
                return
            scope = account_version(db, job["account_id"])
            active = db.execute(
                "SELECT 1 FROM active_accounts WHERE account_id=?", (job["account_id"],)
            ).fetchone()
            if scope != current["account_version"] or not active:
                current.update(
                    enabled=False,
                    status="paused" if scope else "disconnected",
                    revision=uuid4().hex,
                    error="Account configuration or activation changed; the in-flight page was discarded.",
                )
                self.write_job(db, current)
                return
            for event in events:
                key = (job["account_id"], job["stream"], event["id"])
                if db.execute(
                    "SELECT 1 FROM funding_scan_seen WHERE account_id=? AND stream=? AND event_id=?", key
                ).fetchone():
                    raise ValueError("A funding record repeated across recent-history pages.")
                db.execute("INSERT INTO funding_scan_seen VALUES(?,?,?)", key)
                expected = db.execute(
                    "SELECT source_version FROM funding_scan_sources WHERE account_id=? AND stream=? AND event_id=?",
                    key,
                ).fetchone()
                saved = db.execute("SELECT payload FROM funding_events WHERE id=?", (event["id"],)).fetchone()
                if (saved is None) != (expected is None) or (
                    saved and fingerprint(json.loads(saved[0])) != expected[0]
                ):
                    current["conflicts"] += 1
                    continue
                new, changed = write_event(db, event, seen, origin="recent_sync")
                current["pass_inserted"] += new
                current["pass_updated"] += changed
                current["inserted"] += new
                current["updated"] += changed
            current.update(
                cursor=page.cursor,
                pages=current["pages"] + 1,
                retries=0,
                error=None,
                retry_at=None,
                next_attempt=0,
                status="idle" if page.caught_up else "queued",
                seen_cursors=[*job.get("seen_cursors", []), signature][-SCAN_PAGE_LIMIT:],
                seen_pages=[*job.get("seen_pages", []), *([page_signature] if page_signature else [])][
                    -SCAN_PAGE_LIMIT:
                ],
            )
            if page.caught_up:
                report = self.finish(db, current, seen)
                current.update(
                    last_checked_at=seen,
                    covered_start_ms=job["start_ms"],
                    covered_end_ms=job["end_ms"],
                    passes=current["passes"] + 1,
                    last_report=report,
                    cursor={},
                    next_attempt=time.time() + current["interval_minutes"] * 60,
                )
                self.clear_pass(db, job["account_id"], job["stream"])
            self.write_job(db, current)

    @staticmethod
    def finish(db, job, seen):
        """Retain a bounded pass report and update outstanding fetched-window gaps."""
        clause = "FROM funding_scan_sources s LEFT JOIN funding_scan_seen v ON v.account_id=s.account_id AND v.stream=s.stream AND v.event_id=s.event_id WHERE s.account_id=? AND s.stream=? AND v.event_id IS NULL"
        scope = (job["account_id"], job["stream"])
        missing = db.execute("SELECT COUNT(*) " + clause, scope).fetchone()[0]
        missing_ids = db.execute(
            "SELECT s.event_id " + clause + " ORDER BY s.event_id LIMIT 10", scope
        ).fetchall()
        preview = []
        for identity in missing_ids:
            event = db.execute("SELECT payload FROM funding_events WHERE id=?", (identity[0],)).fetchone()
            source = json.loads(event[0]) if event else {}
            preview.append(
                {
                    "id": identity[0],
                    "asset": source.get("asset"),
                    "native_id": source.get("native_id"),
                    "status": source.get("status"),
                }
            )
        previous_end = job.get("covered_end_ms")
        report = {
            "id": job["run_id"],
            "start_ms": job["start_ms"],
            "end_ms": job["end_ms"],
            "completed_at": seen,
            "pages": job["pages"],
            "inserted": job["pass_inserted"],
            "updated": job["pass_updated"],
            "concurrent_changes": job["conflicts"],
            "not_returned": missing,
            "not_returned_preview": preview,
            "not_returned_limit": 10,
            "gap": {"start_ms": previous_end + 1, "end_ms": job["start_ms"] - 1}
            if previous_end is not None and job["start_ms"] > previous_end + 1
            else None,
            "complete_history": False,
            "settlement_final": False,
        }
        if report["gap"]:
            db.execute(
                "INSERT OR IGNORE INTO funding_coverage_gaps VALUES(?,?,?,?)",
                (*scope, report["gap"]["start_ms"], report["gap"]["end_ms"]),
            )
        cover_gaps(db, *scope, job["start_ms"], job["end_ms"])
        db.execute(
            "INSERT INTO funding_scan_reports VALUES(?,?,?,?)",
            (report["id"], *scope, json.dumps(report, allow_nan=False)),
        )
        db.execute(
            "DELETE FROM funding_scan_reports WHERE account_id=? AND stream=? AND id NOT IN "
            "(SELECT id FROM funding_scan_reports WHERE account_id=? AND stream=? ORDER BY rowid DESC LIMIT 20)",
            (*scope, *scope),
        )
        return report

    def snapshot(self):
        """Return control/progress and the latest report; saved history is loaded separately."""
        fields = (
            "account_id",
            "account",
            "exchange",
            "environment",
            "stream",
            "revision",
            "enabled",
            "interval_minutes",
            "lookback_days",
            "status",
            "last_checked_at",
            "covered_start_ms",
            "covered_end_ms",
            "last_report",
            "passes",
            "inserted",
            "updated",
            "pages",
            "error",
            "retry_at",
        )
        result = []
        with self.store.db() as db:
            db.execute("BEGIN")
            for row in db.execute("SELECT payload FROM funding_scans ORDER BY account_id,stream"):
                job = json.loads(row[0])
                result.append(
                    {
                        **{key: job.get(key) for key in fields},
                        "history_limit": 20,
                        "next_scan_at": datetime.fromtimestamp(job["next_attempt"], UTC).isoformat()
                        if job["enabled"] and job["next_attempt"]
                        else None,
                    }
                )
                count = db.execute(
                    "SELECT COUNT(*) FROM funding_coverage_gaps WHERE account_id=? AND stream=?",
                    (job["account_id"], job["stream"]),
                ).fetchone()[0]
                gaps = db.execute(
                    "SELECT start_ms,end_ms FROM funding_coverage_gaps WHERE account_id=? AND stream=? ORDER BY start_ms DESC LIMIT 10",
                    (job["account_id"], job["stream"]),
                ).fetchall()
                result[-1].update(
                    uncovered_gap_count=count,
                    uncovered_gaps=[{"start_ms": item[0], "end_ms": item[1]} for item in gaps],
                    gap_preview_limit=10,
                )
        return result

    def history(self, account_id, stream):
        """Read twenty saved window reports without native reads, including for disconnected accounts."""
        with self.store.db() as db:
            if self.read_job(db, account_id, stream) is None:
                raise LookupError("Recent funding sync not found.")
            reports = db.execute(
                "SELECT payload FROM funding_scan_reports WHERE account_id=? AND stream=? ORDER BY rowid DESC LIMIT 20",
                (account_id, stream),
            ).fetchall()
        return {"items": [json.loads(item[0]) for item in reports], "limit": 20, "complete_history": False}
