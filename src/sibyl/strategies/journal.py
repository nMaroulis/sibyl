"""Durable strategy events, bounded quote observations, and read-only monitor queries."""

import csv
import io
import json
from datetime import UTC, datetime

from sibyl.storage import Store

EVENT_COLUMNS = (
    "id",
    "job_id",
    "symbol",
    "quote",
    "source",
    "timestamp",
    "kind",
    "action",
    "signal",
    "candle_timestamp",
    "candle_close",
    "reference_price",
    "fill_price",
    "slippage",
    "slippage_bps",
    "quantity",
    "fee",
    "cash",
    "position",
    "equity",
    "reason",
    "order_id",
    "native_fill_id",
    "fees",
    "cancel_state",
    "cancellation_id",
    "expires_at",
    "close_review_id",
)


class StrategyJournal:
    """Persist a job and its observations in one transaction, retaining every event.

    Quote samples retain the newest 2,000 observations per run. Events are paged
    independently and remain available for complete CSV export. No provider call
    occurs during a monitor read, and no quote is fabricated for missing history.
    """

    def __init__(self, store: Store):
        self.store = store
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS strategy_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS strategy_events_job ON strategy_events(job_id, id);
                CREATE TABLE IF NOT EXISTS strategy_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS strategy_observations_job ON strategy_observations(job_id, id);
            """)

    def save(self, job: dict, event: dict | None = None, sample: dict | None = None) -> dict:
        """Atomically commit balances, the processed candle, and any event/sample."""
        with self.store.db() as db:
            db.execute(
                "INSERT INTO strategy_jobs VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET payload = excluded.payload",
                (job["id"], json.dumps(job, allow_nan=False)),
            )
            if event:
                db.execute(
                    "INSERT INTO strategy_events(job_id, payload) VALUES (?, ?)",
                    (job["id"], json.dumps(event, allow_nan=False)),
                )
            if sample:
                db.execute(
                    "INSERT INTO strategy_observations(job_id, payload) VALUES (?, ?)",
                    (job["id"], json.dumps(sample, allow_nan=False)),
                )
                db.execute(
                    "DELETE FROM strategy_observations WHERE job_id = ? AND id NOT IN "
                    "(SELECT id FROM strategy_observations WHERE job_id = ? ORDER BY id DESC LIMIT 2000)",
                    (job["id"], job["id"]),
                )
        return job

    def job(self, job_id: str) -> dict:
        """Read a single persisted strategy, including terminal runs."""
        with self.store.db() as db:
            row = db.execute("SELECT payload FROM strategy_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise LookupError("Strategy not found.")
        return json.loads(row[0])

    def events(self, job_id: str, limit: int = 100, before: int | None = None, action: str = "all") -> dict:
        """Read newest-first events with a stable older-page cursor and action filter."""
        self.job(job_id)
        clause, values = self._where(job_id, before, action)
        with self.store.db() as db:
            total = db.execute(f"SELECT COUNT(*) FROM strategy_events WHERE {clause}", values).fetchone()[0]
            rows = db.execute(
                f"SELECT id, payload FROM strategy_events WHERE {clause} ORDER BY id DESC LIMIT ?",
                [*values, limit + 1],
            ).fetchall()
        items = [{**json.loads(row["payload"]), "id": row["id"]} for row in rows[:limit]]
        return {
            "items": items,
            "has_more": len(rows) > limit,
            "next_before": items[-1]["id"] if len(rows) > limit else None,
            "matching_count": total,
        }

    @staticmethod
    def _where(job_id: str, before: int | None, action: str) -> tuple[str, list]:
        """Build parameterized journal filters; SQL identifiers never come from input."""
        clause, values = "job_id = ?", [job_id]
        if before is not None:
            clause += " AND id < ?"
            values.append(before)
        if action == "fills":
            clause += " AND json_extract(payload, '$.action') IN ('BUY', 'SELL')"
        elif action != "all":
            clause += " AND json_extract(payload, '$.action') = ?"
            values.append(action)
        return clause, values

    def export(self, job_id: str, action: str = "all"):
        """Stream all matching events chronologically, excluding later arrivals.

        Short database reads avoid holding a transaction open while the browser
        downloads. CSV text fields are neutralized against spreadsheet formulas.
        """
        job = self.job(job_id)
        clause, values = self._where(job_id, None, action)
        with self.store.db() as db:
            boundary = db.execute(
                "SELECT COALESCE(MAX(id), 0) FROM strategy_events WHERE job_id = ?", (job_id,)
            ).fetchone()[0]

        def chunks():
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(EVENT_COLUMNS)
            yield buffer.getvalue()
            after = 0
            while after < boundary:
                with self.store.db() as db:
                    rows = db.execute(
                        f"SELECT id, payload FROM strategy_events WHERE {clause} AND id > ? AND id <= ? ORDER BY id LIMIT 500",
                        [*values, after, boundary],
                    ).fetchall()
                if not rows:
                    break
                buffer.seek(0)
                buffer.truncate(0)
                for row in rows:
                    event = {
                        **json.loads(row["payload"]),
                        "id": row["id"],
                        "job_id": job_id,
                        "symbol": job["parameters"]["symbol"],
                        "quote": job["parameters"]["symbol"].split("/")[1],
                        "source": job["source"],
                    }
                    values_row = []
                    for column in EVENT_COLUMNS:
                        value = event.get(column)
                        if isinstance(value, (dict, list)):
                            value = json.dumps(value, sort_keys=True)
                        if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                            value = "'" + value
                        values_row.append(value)
                    writer.writerow(values_row)
                after = rows[-1]["id"]
                yield buffer.getvalue()

        return chunks()

    def monitor(self, job_id: str, limit: int = 300) -> dict:
        """Return a coherent job, chart observations, and recorded fill markers."""
        with self.store.db() as db:
            # A read transaction keeps the job, chart, and marker queries on one snapshot.
            db.execute("BEGIN")
            row = db.execute("SELECT payload FROM strategy_jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                raise LookupError("Strategy not found.")
            job = json.loads(row[0])
            samples = db.execute(
                "SELECT payload FROM strategy_observations WHERE job_id = ? ORDER BY id DESC LIMIT ?",
                (job_id, limit),
            ).fetchall()
            observations = [json.loads(sample[0]) for sample in reversed(samples)]
            start = observations[0]["timestamp"] if observations else job["created_at"]
            rows = db.execute(
                "SELECT id, payload FROM strategy_events WHERE job_id = ? AND json_extract(payload, '$.timestamp') >= ? "
                "AND json_extract(payload, '$.action') IN ('BUY', 'SELL', 'SKIP_BUY', 'SKIP_SELL', 'ERROR') ORDER BY id",
                (job_id, start),
            ).fetchall()
            markers = [{**json.loads(row["payload"]), "id": row["id"]} for row in rows]
            event_count = db.execute(
                "SELECT COUNT(*) FROM strategy_events WHERE job_id = ?", (job_id,)
            ).fetchone()[0]
        # Old runs expose their retained fills honestly, without inventing prior decisions or quotes.
        legacy_fills = [fill for fill in job["fills"] if "event_recorded" not in fill]
        return {
            "job": job,
            "observations": observations,
            "markers": markers,
            "legacy_fills": legacy_fills,
            "event_count": event_count,
            "worker_interval": 30,
            "as_of": datetime.now(UTC).isoformat(),
            "retention": {"observations": 2000, "events": "all"},
        }
