"""Version-bound drift observations and explicit retained-data recalibration.

No worker fetches prices or silently promotes a model. A saved policy authorizes
new candidate versions only from the parent's exact retained daily series. Local
jobs can invoke this bounded domain operation; execution checkpoints are not
reimplemented here. Divergence thresholds are descriptive, not calibrated tests.
"""

import json
import threading
from uuid import uuid4

import numpy as np
from pydantic import Field

from sibyl.forecasting.contracts import TrainForecast
from sibyl.forecasting.engine import fingerprint, validate
from sibyl.market_data.archive import iso, milliseconds, now_ms, series_key, step_ms
from sibyl.models import Request

DAY = step_ms("1d")
CONFIRMATION = "SAVE RECALIBRATION POLICY"


class DriftPolicy(Request):
    revision: int = Field(ge=0, strict=True)
    enabled: bool = Field(default=False, strict=True)
    recent_days: int = Field(default=60, ge=30, le=180, strict=True)
    divergence_threshold: float = Field(default=0.1, gt=0, le=0.69, strict=True)
    min_new_days: int = Field(default=30, ge=30, le=365, strict=True)
    cooldown_days: int = Field(default=30, ge=1, le=365, strict=True)
    confirmation: str = Field(max_length=100)


class Recalibrate(Request):
    model_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    revision: int = Field(ge=1, strict=True)


def divergence(reference, recent):
    """Jensen–Shannon divergence using training-only decile bins and fixed smoothing."""
    reference, recent = np.asarray(reference), np.asarray(recent)
    if (
        min(len(reference), len(recent)) < 30
        or not np.isfinite(reference).all()
        or not np.isfinite(recent).all()
    ):
        raise ValueError("Drift comparison needs at least thirty finite returns per period.")
    inner = np.unique(np.quantile(reference, np.arange(0.1, 1, 0.1)))
    edges = np.r_[-np.inf, inner, np.inf]
    a, b = np.histogram(reference, edges)[0] + 0.5, np.histogram(recent, edges)[0] + 0.5
    a, b = a / a.sum(), b / b.sum()
    middle = (a + b) / 2
    js = float((np.sum(a * np.log(a / middle)) + np.sum(b * np.log(b / middle))) / 2)
    std = float(reference.std())
    return dict(
        js_divergence=max(0.0, js),
        reference_mean=float(reference.mean()),
        recent_mean=float(recent.mean()),
        reference_volatility=std,
        recent_volatility=float(recent.std()),
        mean_shift_in_reference_std=float((recent.mean() - reference.mean()) / std) if std > 1e-12 else None,
        volatility_ratio=float(recent.std() / std) if std > 1e-12 else None,
        bins=edges[1:-1].tolist(),
        reference_probabilities=a.tolist(),
        recent_probabilities=b.tolist(),
    )


class ForecastDrift:
    """Retain latest drift evidence and twenty candidate-training outcomes per parent."""

    def __init__(self, owner):
        self.owner, self.store = owner, owner.store
        self.lock = threading.Lock()
        with self.store.db() as db:
            db.executescript(
                "CREATE TABLE IF NOT EXISTS forecast_drift(model_id TEXT PRIMARY KEY,revision INTEGER NOT NULL,payload TEXT NOT NULL); CREATE TABLE IF NOT EXISTS forecast_recalibrations(id TEXT PRIMARY KEY,model_id TEXT NOT NULL,input_hash TEXT NOT NULL,payload TEXT NOT NULL,UNIQUE(model_id,input_hash));"
            )
            for row in db.execute(
                "SELECT id,payload FROM forecast_recalibrations WHERE json_extract(payload,'$.status')='training'"
            ).fetchall():
                payload = json.loads(row[1])
                payload.update(
                    status="interrupted", error="Training was interrupted; it is not replayed automatically."
                )
                db.execute(
                    "UPDATE forecast_recalibrations SET payload=? WHERE id=?", (json.dumps(payload), row[0])
                )

    def state(self, identity):
        self.owner._load(identity)
        with self.store.db() as db:
            row = db.execute(
                "SELECT revision,payload FROM forecast_drift WHERE model_id=?", (identity,)
            ).fetchone()
            state = (
                json.loads(row[1])
                if row
                else dict(
                    revision=0,
                    policy=dict(
                        enabled=False,
                        recent_days=60,
                        divergence_threshold=0.1,
                        min_new_days=30,
                        cooldown_days=30,
                    ),
                    assessment=None,
                )
            )
            history = [
                json.loads(r[0])
                for r in db.execute(
                    "SELECT payload FROM forecast_recalibrations WHERE model_id=? ORDER BY rowid DESC LIMIT 20",
                    (identity,),
                )
            ]
        return dict(
            model_id=identity,
            **state,
            history=history,
            confirmation=CONFIRMATION,
            note="Retained exact-source daily data only. Jensen–Shannon divergence is descriptive, not a calibrated regime test. New versions are research candidates, never automatic replacements.",
        )

    def save(self, identity, body):
        model = self.owner._load(identity)
        if body.confirmation != CONFIRMATION:
            raise ValueError("Type " + CONFIRMATION + " to save this policy.")
        if body.enabled and model["metadata"].get("archived"):
            raise ValueError("Restore this model before enabling recalibration.")
        if body.enabled and (
            model["metadata"]["environment"] in {"demo", "imported"} or model["metadata"]["source"] == "demo"
        ):
            raise ValueError(
                "Automated recalibration requires an observed source, not Demo or imported origin."
            )
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT revision,payload FROM forecast_drift WHERE model_id=?", (identity,)
            ).fetchone()
            if (old[0] if old else 0) != body.revision:
                raise ValueError("The recalibration policy changed. Refresh before saving.")
            state = dict(
                revision=body.revision + 1,
                policy=body.model_dump(exclude={"revision", "confirmation"}),
                assessment=None,
                changed_at=iso(now_ms()),
            )
            db.execute(
                "INSERT OR REPLACE INTO forecast_drift VALUES(?,?,?)",
                (identity, state["revision"], json.dumps(state)),
            )
        return self.state(identity)

    def _observations(self, model):
        meta = model["metadata"]
        key = series_key(meta["source"], meta["environment"], meta["symbol"], "1d")
        count = min(1000 if model["request"].get("family") == "mlp" else 5000, meta["dataset"]["count"])
        with self.store.db() as db:
            rows = db.execute(
                "SELECT timestamp,open,high,low,close,volume FROM candle_rows WHERE series_id=? AND timestamp+?<=? ORDER BY timestamp DESC LIMIT ?",
                (key, DAY, now_ms(), count),
            ).fetchall()
        candles = [
            dict(
                timestamp=iso(row[0]),
                **dict(zip(("open", "high", "low", "close", "volume"), row[1:], strict=True)),
            )
            for row in reversed(rows)
        ]
        if len(candles) < 360:
            raise ValueError(
                "Retain at least 360 matching closed daily candles in Markets before checking or recalibrating."
            )
        validate(candles, minimum=360)
        return candles

    def check(self, identity):
        model, state = self.owner._load(identity), self.state(identity)
        candles = self._observations(model)
        reference = self.owner.market.archive.dataset(model["metadata"]["dataset"]["id"])["candles"][
            : model["artifact"]["partitions"]["train"]["candles"]
        ]
        recent = [
            row
            for row in candles
            if milliseconds(row["timestamp"]) >= milliseconds(model["metadata"]["dataset"]["end"])
        ]
        count = state["policy"]["recent_days"]
        if len(recent) < count + 1:
            assessment = dict(
                status="insufficient",
                new_candles=len(recent),
                required_candles=count + 1,
                checked_at=iso(now_ms()),
                message="More closed days after this model's entire original input are required. Training/test days are not reused as recent drift evidence.",
            )
        else:
            recent = recent[-count - 1 :]
            result = divergence(
                np.diff(np.log([r["close"] for r in reference])),
                np.diff(np.log([r["close"] for r in recent])),
            )
            assessment = dict(
                status="shift"
                if result["js_divergence"] >= state["policy"]["divergence_threshold"]
                else "within_threshold",
                **result,
                new_candles=len(
                    [
                        r
                        for r in candles
                        if milliseconds(r["timestamp"]) >= milliseconds(model["metadata"]["dataset"]["end"])
                    ]
                ),
                recent_start=recent[0]["timestamp"],
                recent_end=iso(milliseconds(recent[-1]["timestamp"]) + DAY),
                checked_at=iso(now_ms()),
                input_fingerprint=fingerprint(candles),
                model_fingerprint=model["metadata"]["fingerprint"],
            )
        assessment["latest_close_at"] = iso(milliseconds(candles[-1]["timestamp"]) + DAY)
        assessment["stale"] = now_ms() - milliseconds(assessment["latest_close_at"]) > 2 * DAY
        if assessment["stale"] and assessment["status"] != "insufficient":
            assessment["status"] = "stale"
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT revision,payload FROM forecast_drift WHERE model_id=?", (identity,)
            ).fetchone()
            if (current[0] if current else 0) != state["revision"]:
                raise ValueError("The policy changed while drift was calculated.")
            payload = json.loads(current[1]) if current else {k: state[k] for k in ("revision", "policy")}
            payload["assessment"] = assessment
            db.execute(
                "INSERT OR REPLACE INTO forecast_drift VALUES(?,?,?)",
                (identity, state["revision"], json.dumps(payload, allow_nan=False)),
            )
        return self.state(identity)

    def recalibrate(self, body):
        if not self.lock.acquire(blocking=False):
            raise ValueError("A recalibration is already running.")
        identity, receipt = body.model_id, None
        try:
            state = self.check(identity)
            if state["revision"] != body.revision or not state["policy"]["enabled"]:
                raise ValueError("Recalibration needs the current explicitly enabled policy.")
            evidence, policy = state["assessment"], state["policy"]
            if evidence["status"] != "shift" or evidence.get("new_candles", 0) < policy["min_new_days"]:
                return dict(
                    status="not_due",
                    assessment=evidence,
                    note="No candidate trained: drift/new-day policy was not met.",
                )
            model = self.owner._load(identity)
            if model["metadata"].get("archived"):
                raise ValueError("Restore this model before recalibrating it.")
            candles = self._observations(model)
            if fingerprint(candles) != evidence["input_fingerprint"]:
                raise ValueError("Retained observations changed after drift assessment. Check again.")
            digest = fingerprint(dict(input=evidence["input_fingerprint"], revision=state["revision"]))
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute(
                    "SELECT revision FROM forecast_drift WHERE model_id=?", (identity,)
                ).fetchone()
                if not current or current[0] != body.revision:
                    raise ValueError("The policy changed before candidate admission.")
                existing = db.execute(
                    "SELECT payload FROM forecast_recalibrations WHERE model_id=? AND input_hash=?",
                    (identity, digest),
                ).fetchone()
                if existing:
                    return json.loads(existing[0])
                latest = db.execute(
                    "SELECT payload FROM forecast_recalibrations WHERE model_id=? AND json_extract(payload,'$.status')='completed' ORDER BY rowid DESC LIMIT 1",
                    (identity,),
                ).fetchone()
                if (
                    latest
                    and now_ms() - milliseconds(json.loads(latest[0])["created_at"])
                    < policy["cooldown_days"] * DAY
                ):
                    return dict(
                        status="cooldown", note="The previous candidate is still inside the saved cooldown."
                    )
                receipt = dict(
                    id=uuid4().hex,
                    model_id=identity,
                    status="training",
                    created_at=iso(now_ms()),
                    input_hash=digest,
                    policy_revision=body.revision,
                    assessment=evidence,
                )
                db.execute(
                    "INSERT INTO forecast_recalibrations VALUES(?,?,?,?)",
                    (receipt["id"], identity, digest, json.dumps(receipt)),
                )
            meta = model["metadata"]
            dataset = self.owner.market.archive.snapshot(
                dict(
                    source=meta["source"],
                    source_label=meta["dataset"]["source_label"],
                    environment=meta["environment"],
                ),
                meta["symbol"],
                "1d",
                candles[0]["timestamp"],
                iso(milliseconds(candles[-1]["timestamp"]) + DAY),
                "Recalibration candidate",
            )
            # Pin the copied snapshot too: concurrent archive corrections cannot alter this fit.
            retained = self.owner.market.archive.dataset(dataset["id"])["candles"]
            if fingerprint(retained) != evidence["input_fingerprint"]:
                raise ValueError("The snapshot changed before fitting; no candidate was trained.")
            request = TrainForecast(
                **(
                    model["request"]
                    | dict(input_kind="saved_dataset", dataset_id=dataset["id"], candles=len(candles))
                )
            )
            result = self.owner.train(request, parent_id=identity)
            receipt.update(
                status="completed",
                candidate_id=result["model"]["id"],
                candidate_version=result["model"]["version"],
                evaluation=result["evaluation"],
                note="Candidate retained with independent chronological test evidence. The parent remains unchanged.",
            )
            self._finish(receipt)
            return receipt
        except Exception:
            if receipt:
                receipt.update(
                    status="failed",
                    error="Candidate training did not finish. Inspect the model registry before creating another policy revision.",
                )
                self._finish(receipt)
            raise
        finally:
            self.lock.release()

    def _finish(self, row):
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE forecast_recalibrations SET payload=? WHERE id=?",
                (json.dumps(row, allow_nan=False), row["id"]),
            )
            db.execute(
                "DELETE FROM forecast_recalibrations WHERE model_id=? AND id NOT IN (SELECT id FROM forecast_recalibrations WHERE model_id=? ORDER BY rowid DESC LIMIT 20)",
                (row["model_id"], row["model_id"]),
            )
