"""SQLite persistence for public excerpts and publisher collection state."""

import hashlib
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path


class NewsRepository:
    """Retain bounded public news separately from the encrypted account vault."""

    def __init__(self, data_dir: Path):
        data_dir.mkdir(parents=True, exist_ok=True)
        self.path = data_dir / "news.sqlite3"
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS articles (
                    id TEXT PRIMARY KEY, source_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    observed_at TEXT NOT NULL, sort_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS articles_source_title ON articles(source_id, fingerprint);
                CREATE TABLE IF NOT EXISTS feed_states (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS observations (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        """Give each worker its own short-lived connection and transaction."""
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def states(self) -> dict[str, dict]:
        """Read last attempts, last successes, HTTP validators, and safe error messages."""
        with self.connect() as db:
            return {r["id"]: json.loads(r["payload"]) for r in db.execute("SELECT * FROM feed_states")}

    def save(self, source_id: str, state: dict, items: list[dict], now: datetime, retention_days: int):
        """Upsert URL identities, merge same-source/day exact titles, and prune the archive."""
        observed = now.isoformat()
        cutoff = (now - timedelta(days=retention_days)).isoformat()
        with self.connect() as db:
            for item in items:
                day = (item.get("published_at") or observed)[:10]
                title = re.sub(r"\W+", " ", item["title"].casefold()).strip()
                fingerprint = hashlib.sha256(f"{day}:{title}".encode()).hexdigest()
                existing = db.execute(
                    "SELECT id, observed_at, source_id, payload FROM articles WHERE id=? OR (source_id=? AND fingerprint=?) LIMIT 1",
                    (item["id"], source_id, fingerprint),
                ).fetchone()
                previous = json.loads(existing["payload"]) if existing else {}
                collectors = set(
                    previous.get("collector_ids", [previous["source_id"]] if previous else [])
                ) | {source_id}
                content = (
                    previous
                    if existing and source_id == "newsapi" and existing["source_id"] != "newsapi"
                    else item
                )
                payload = {
                    **content,
                    "collector_ids": sorted(collectors),
                    "id": existing["id"] if existing else item["id"],
                    "first_seen_at": existing["observed_at"] if existing else observed,
                    "collected_at": observed,
                }
                sort_at = payload.get("published_at") or payload["first_seen_at"]
                title = re.sub(r"\W+", " ", payload["title"].casefold()).strip()
                fingerprint = hashlib.sha256(f"{sort_at[:10]}:{title}".encode()).hexdigest()
                db.execute(
                    """INSERT INTO articles VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                    source_id=excluded.source_id, fingerprint=excluded.fingerprint,
                    sort_at=excluded.sort_at, payload=excluded.payload""",
                    (
                        payload["id"],
                        payload["source_id"],
                        fingerprint,
                        payload["first_seen_at"],
                        sort_at,
                        json.dumps(payload),
                    ),
                )
            db.execute(
                "INSERT INTO feed_states VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (source_id, json.dumps(state)),
            )
            db.execute("DELETE FROM articles WHERE sort_at < ?", (cutoff,))
            db.execute(
                "DELETE FROM articles WHERE id IN (SELECT id FROM articles ORDER BY sort_at DESC, id DESC LIMIT -1 OFFSET 5000)"
            )

    def items(self) -> list[dict]:
        """Read the bounded archive newest first with stable pagination order."""
        with self.connect() as db:
            return [
                json.loads(r["payload"])
                for r in db.execute("SELECT payload FROM articles ORDER BY sort_at DESC, id DESC LIMIT 5000")
            ]

    def observation(self, name: str) -> dict:
        """Read a bounded public research observation and its cache state."""
        with self.connect() as db:
            row = db.execute("SELECT payload FROM observations WHERE id=?", (name,)).fetchone()
        return json.loads(row[0]) if row else {}

    def save_observation(self, name: str, payload: dict):
        """Replace one public observation atomically."""
        with self.connect() as db:
            db.execute(
                "INSERT INTO observations VALUES(?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (name, json.dumps(payload)),
            )
