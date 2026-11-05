"""Prospective forecast tracking against exact-source retained closed daily candles.

A saved prediction is immutable. Observations and corrections are separately
versioned; historical predictions made after their target are never live scores.
The automatic worker reads the archive only. Provider refresh is an explicit action.
"""

import json
import threading

import numpy as np
from pydantic import Field

from sibyl.forecasting.engine import metrics
from sibyl.market_data.archive import iso, milliseconds, now_ms, series_key, step_ms
from sibyl.models import Request

DAY = step_ms("1d")


class ForwardAction(Request):
    """Change tracking only; never retrain, deploy or rewrite a forecast."""

    revision: int = Field(ge=1, strict=True)
    action: str = Field(pattern=r"^(pause|resume)$")


class ForwardMonitor:
    """Retain at most 200 tracked outputs, with bounded per-target correction receipts."""

    def __init__(self, owner, clock=now_ms):
        self.owner, self.store, self.clock = owner, owner.store, clock
        self.lock = threading.Lock()
        self.closed = False
        with self.store.db() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS forecast_tracking (id TEXT PRIMARY KEY, model_id TEXT NOT NULL, next_check INTEGER NOT NULL, payload TEXT NOT NULL)"
            )

    @staticmethod
    def _read(db, identity):
        row = db.execute("SELECT payload FROM forecast_tracking WHERE id=?", (identity,)).fetchone()
        if not row:
            raise LookupError("Tracked forecast not found.")
        return json.loads(row[0])

    @staticmethod
    def _write(db, row):
        db.execute(
            "UPDATE forecast_tracking SET next_check=?,payload=? WHERE id=?",
            (row["next_check"], json.dumps(row, allow_nan=False), row["id"]),
        )

    def enroll(self, identity):
        output = self.owner.output(identity)
        accepted = milliseconds(output["created_at"])
        if (
            output["input_kind"] != "current_feed"
            or output["source"] == "demo"
            or output["environment"] == "demo"
        ):
            raise ValueError(
                "Track an explicitly saved current-feed forecast from a real reference source. Saved-input and Demo predictions are historical research, not live performance."
            )
        eligible = [
            i + 1 for i, point in enumerate(output["points"]) if milliseconds(point["timestamp"]) > accepted
        ]
        if not eligible:
            raise ValueError(
                "All targets predate this forecast's save time. Save a new current-feed forecast."
            )
        now = self.clock()
        row = dict(
            id=identity,
            model_id=output["model_id"],
            source=output["source"],
            environment=output["environment"],
            symbol=output["symbol"],
            created_at=iso(now),
            accepted_at=output["created_at"],
            revision=1,
            status="active",
            next_check=0,
            checked_at=None,
            eligible_horizons=eligible,
            observations={},
            result_fingerprint=output["result_fingerprint"],
            error=None,
        )
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM forecast_tracking WHERE id=?", (identity,)).fetchone():
                return self.detail(identity)
            if db.execute("SELECT COUNT(*) FROM forecast_tracking").fetchone()[0] >= 200:
                raise ValueError("The tracked-forecast budget is 200 outputs.")
            db.execute(
                "INSERT INTO forecast_tracking VALUES(?,?,?,?)",
                (identity, output["model_id"], 0, json.dumps(row)),
            )
        return self.detail(identity)

    def action(self, identity, body):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._read(db, identity)
            if row["revision"] != body.revision:
                raise ValueError("Tracking changed. Refresh before continuing.")
            row.update(
                status="paused" if body.action == "pause" else "active",
                revision=row["revision"] + 1,
                next_check=0,
            )
            self._write(db, row)
        return self.detail(identity)

    def evaluate(self, identity, *, refresh=False):
        """Read matching actuals; optionally fetch a bounded current page from the pinned source."""
        if not self.lock.acquire(blocking=False):
            raise ValueError("A forecast observation check is already running.")
        try:
            with self.store.db() as db:
                row = self._read(db, identity)
            output = self.owner.output(identity)
            if output["result_fingerprint"] != row["result_fingerprint"]:
                raise ValueError("The tracked prediction fingerprint changed.")
            if row["status"] == "paused":
                raise ValueError("Resume tracking before checking observations.")
            if refresh:
                with self.owner.market.snapshot(row["source"]):
                    meta = self.owner.market.metadata()
                    if (meta["source"], meta["environment"]) != (row["source"], row["environment"]):
                        raise ValueError("The pinned forecast source/environment is unavailable.")
                    self.owner.market.candles(row["symbol"], 90, "1d")
            key = series_key(row["source"], row["environment"], row["symbol"], "1d")
            now = self.clock()
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                current = self._read(db, identity)
                if current["revision"] != row["revision"] or current["status"] == "paused":
                    raise ValueError("Tracking changed while observations were being read.")
                for horizon in row["eligible_horizons"]:
                    point = output["points"][horizon - 1]
                    target = milliseconds(point["timestamp"])
                    if target > now:
                        continue
                    actual = db.execute(
                        "SELECT close,observed_at FROM candle_rows WHERE series_id=? AND timestamp=?",
                        (key, target - DAY),
                    ).fetchone()
                    if not actual or milliseconds(actual["observed_at"]) < target:
                        continue
                    previous = current["observations"].get(str(horizon))
                    value = float(actual["close"])
                    if not np.isfinite(value) or value <= 0:
                        raise ValueError("A retained actual close is invalid.")
                    if not previous or previous["actual"] != value:
                        receipt = dict(actual=value, observed_at=actual["observed_at"], checked_at=iso(now))
                        history = (previous or {}).get("history", [])
                        current["observations"][str(horizon)] = {
                            **receipt,
                            "version": (previous or {}).get("version", 0) + 1,
                            "history": (history + [receipt])[-5:],
                        }
                current.update(checked_at=iso(now), next_check=now + 3600_000, error=None)
                self._write(db, current)
            return self.detail(identity)
        finally:
            self.lock.release()

    def detail(self, identity):
        with self.store.db() as db:
            row = self._read(db, identity)
        output = self.owner.output(identity)
        points = []
        closes = np.asarray([c["close"] for c in output["observations"]["candles"]], dtype=float)
        drift_rate = float(np.mean(np.diff(np.log(closes))))
        for horizon in row["eligible_horizons"]:
            prediction = output["points"][horizon - 1]
            observation = row["observations"].get(str(horizon))
            points.append(
                dict(
                    horizon=horizon,
                    **prediction,
                    observation=observation,
                    state="observed"
                    if observation
                    else "awaiting_archive"
                    if milliseconds(prediction["timestamp"]) <= self.clock()
                    else "not_due",
                    naive=output["last_price"],
                    drift=float(output["last_price"] * np.exp(np.clip(drift_rate * horizon, -40, 40))),
                )
            )
        scored = [point for point in points if point["observation"]]
        actual = np.asarray([point["observation"]["actual"] for point in scored])
        predicted = np.asarray([point["value"] for point in scored])
        naive = np.asarray([point["naive"] for point in scored])
        score = metrics(actual, predicted) if scored else None
        benchmark = metrics(actual, naive) if scored else None
        return {
            **row,
            "points": points,
            "observed": len(scored),
            "pending": len(points) - len(scored),
            "metrics": score,
            "naive": benchmark,
            "coverage_pct": float(
                np.mean([p["lower"] <= p["observation"]["actual"] <= p["upper"] for p in scored]) * 100
            )
            if scored
            else None,
            "mae_skill_vs_naive_pct": (1 - score["mae"] / benchmark["mae"]) * 100
            if scored and benchmark["mae"] > 1e-12
            else None,
            "note": "Prospective targets only, scored against the pinned source's retained daily closes. Missing closes remain missing. Horizon errors are not independent samples or proof of trading profitability. Corrections retain the latest five observation receipts per target.",
        }

    def list(self, model_id):
        with self.store.db() as db:
            identities = [
                r[0]
                for r in db.execute(
                    "SELECT id FROM forecast_tracking WHERE model_id=? ORDER BY rowid DESC LIMIT 200",
                    (model_id,),
                )
            ]
        items = [self.detail(identity) for identity in identities]
        by_horizon = []
        for horizon in range(1, 31):
            unique = {}
            duplicates = 0
            for item in sorted(items, key=lambda r: (r["accepted_at"], r["id"])):
                for point in item["points"]:
                    if point["horizon"] == horizon and point["observation"]:
                        if point["timestamp"] in unique:
                            duplicates += 1
                        else:
                            unique[point["timestamp"]] = point
            points = list(unique.values())
            if points:
                actual = np.asarray([p["observation"]["actual"] for p in points])
                by_horizon.append(
                    dict(
                        horizon=horizon,
                        samples=len(points),
                        duplicate_origins_excluded=duplicates,
                        model=metrics(actual, np.asarray([p["value"] for p in points])),
                        naive=metrics(actual, np.asarray([p["naive"] for p in points])),
                        drift=metrics(actual, np.asarray([p["drift"] for p in points])),
                        coverage_pct=float(
                            np.mean([p["lower"] <= p["observation"]["actual"] <= p["upper"] for p in points])
                            * 100
                        ),
                    )
                )
        return {"items": items, "by_horizon": by_horizon, "limit": 200}

    def forget(self, identity, revision):
        """Remove tracking receipts explicitly; retain the original recent forecast output."""
        with self.lock, self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._read(db, identity)
            if row["revision"] != revision:
                raise ValueError("Tracking changed. Refresh before removing it.")
            db.execute("DELETE FROM forecast_tracking WHERE id=?", (identity,))
        return {"removed": True}

    def tick(self):
        """Process at most five hourly due outputs per minute, using retained data only."""
        for _ in range(5):
            if self.closed or self.lock.locked():
                return
            with self.store.db() as db:
                row = db.execute(
                    "SELECT id FROM forecast_tracking WHERE next_check<=? AND json_extract(payload,'$.status')='active' ORDER BY next_check,rowid LIMIT 1",
                    (self.clock(),),
                ).fetchone()
            if not row:
                return
            try:
                self.evaluate(row[0])
            except (ValueError, LookupError):
                with self.store.db() as db:
                    db.execute("BEGIN IMMEDIATE")
                    if not db.execute("SELECT 1 FROM forecast_tracking WHERE id=?", (row[0],)).fetchone():
                        continue
                    item = self._read(db, row[0])
                    item.update(
                        error="Observation check could not complete. Review the saved forecast and source.",
                        next_check=self.clock() + 3600_000,
                    )
                    self._write(db, item)

    def close(self):
        self.closed = True
        with self.lock:
            pass
