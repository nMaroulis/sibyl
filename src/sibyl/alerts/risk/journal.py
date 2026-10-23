"""Bounded local valuation evidence, independent of the retained notification inbox."""

import json
import time
from datetime import UTC, datetime, timedelta

MAX_SAMPLES = 2000
SAMPLES_PER_RULE = 120
RETENTION_DAYS = 14


class RiskJournal:
    """Keep recent complete samples; original notification summaries survive pruning."""

    def __init__(self, store, *, clock=time.time):
        self.store, self.clock = store, clock
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS risk_alerts (
                    id TEXT PRIMARY KEY, status TEXT NOT NULL, next_check REAL NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS risk_alerts_due ON risk_alerts(status,next_check);
                CREATE TABLE IF NOT EXISTS risk_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, rule_id TEXT NOT NULL,
                    revision INTEGER NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS risk_samples_rule ON risk_samples(rule_id,revision,id);
            """)
            db.execute("DELETE FROM risk_samples WHERE created_at<?", (self._cutoff(),))

    def _cutoff(self):
        return (datetime.fromtimestamp(self.clock(), UTC) - timedelta(days=RETENTION_DAYS)).isoformat()

    @staticmethod
    def read(db, identity):
        row = db.execute("SELECT payload FROM risk_alerts WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise LookupError("Account risk alert not found.")
        return json.loads(row[0])

    @staticmethod
    def write(db, rule):
        db.execute(
            "UPDATE risk_alerts SET status=?,next_check=?,payload=? WHERE id=?",
            (rule["status"], rule["next_check"], json.dumps(rule, allow_nan=False), rule["id"]),
        )

    @staticmethod
    def append(db, rule, sample, now):
        """Insert and prune inside the same rule/notification transaction."""
        identity = db.execute(
            "INSERT INTO risk_samples(rule_id,revision,created_at,payload) VALUES(?,?,?,?)",
            (rule["id"], rule["revision"], sample["as_of"], json.dumps(sample, allow_nan=False)),
        ).lastrowid
        cutoff = (datetime.fromtimestamp(now, UTC) - timedelta(days=RETENTION_DAYS)).isoformat()
        db.execute("DELETE FROM risk_samples WHERE created_at<? OR id<=?", (cutoff, identity - MAX_SAMPLES))
        db.execute(
            "DELETE FROM risk_samples WHERE id IN (SELECT id FROM risk_samples WHERE rule_id=? ORDER BY id DESC LIMIT -1 OFFSET ?)",
            (rule["id"], SAMPLES_PER_RULE),
        )
        return identity

    def evidence(self, identity, sample_id=None):
        """Read exact retained evidence, including an older revision selected by its notice."""
        with self.store.db() as db:
            db.execute("BEGIN")
            rule = self.read(db, identity)
            chosen = sample_id if sample_id is not None else rule["last_sample_id"]
            row = db.execute(
                "SELECT id,revision,payload FROM risk_samples WHERE rule_id=? AND id=? AND created_at>=?",
                (identity, chosen, self._cutoff()),
            ).fetchone()
            revision = row["revision"] if row else rule["revision"]
            rows = db.execute(
                "SELECT id,payload FROM risk_samples WHERE rule_id=? AND revision=? AND created_at>=? ORDER BY id DESC LIMIT ?",
                (identity, revision, self._cutoff(), SAMPLES_PER_RULE),
            ).fetchall()
        return dict(
            rule=rule,
            sample={"id": row["id"], "revision": row["revision"], **json.loads(row["payload"])}
            if row
            else None,
            samples=[
                dict(
                    id=item["id"], **{key: payload[key] for key in ("as_of", "total", "metric_value", "peak")}
                )
                for item, payload in ((item, json.loads(item["payload"])) for item in reversed(rows))
            ],
            selected_sample_id=chosen,
            revision=revision,
            retention_days=RETENTION_DAYS,
            sample_limit=SAMPLES_PER_RULE,
            note="Recent complete checks only; gaps are unobserved. Sample details can expire; notifications retain their original summary. Values include deposits/withdrawals and are not investment returns.",
        )
