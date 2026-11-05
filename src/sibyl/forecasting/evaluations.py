"""Bounded saved rolling-evaluation reports; fitting stays an explicit application action."""

import json
from uuid import uuid4

from sibyl import __version__
from sibyl.forecasting.contracts import RollingEvaluationRequest
from sibyl.forecasting.engine import fingerprint
from sibyl.forecasting.rolling import ROLLING_ENGINE, evaluate
from sibyl.market_data.archive import iso, now_ms


class RollingEvaluations:
    """Share forecast fit admission and retain ten reports per model, one hundred per workspace."""

    def __init__(self, owner):
        self.owner = owner
        with owner.store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS forecast_evaluations (
                    id TEXT PRIMARY KEY, model_id TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS forecast_evaluations_model ON forecast_evaluations(model_id);
            """)

    def run(self, model_id: str, request: RollingEvaluationRequest):
        """Refit from the selected model's original input/recipe and atomically save complete evidence."""
        owner = self.owner
        if not owner._training.acquire(blocking=False):
            raise ValueError("A forecast fit or evaluation is already running. Wait for it to finish.")
        try:
            model = owner._load(model_id)["metadata"]
            data = owner.market.archive.dataset(model["dataset"]["id"])
            if data["dataset"] != model["dataset"]:
                raise ValueError("Saved evaluation input provenance check failed.")
            result = evaluate(data["candles"], model["parameters"], request)
            report = {
                "id": uuid4().hex,
                "model_id": model_id,
                "model_version": model["version"],
                "model_fingerprint": model["fingerprint"],
                "label": model["label"],
                "symbol": model["symbol"],
                "source": model["source"],
                "environment": model["environment"],
                "dataset": model["dataset"],
                "created_at": iso(now_ms()),
                "app_version": __version__,
                "request": request.model_dump(),
                "result": result,
                "result_fingerprint": fingerprint(result),
            }
            report["fingerprint"] = fingerprint(report)
            with owner.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "INSERT INTO forecast_evaluations VALUES(?,?,?)",
                    (report["id"], model_id, json.dumps(report, allow_nan=False)),
                )
                db.execute(
                    "DELETE FROM forecast_evaluations WHERE model_id=? AND id NOT IN (SELECT id FROM forecast_evaluations WHERE model_id=? ORDER BY rowid DESC LIMIT 10)",
                    (model_id, model_id),
                )
                db.execute(
                    "DELETE FROM forecast_evaluations WHERE id NOT IN (SELECT id FROM forecast_evaluations ORDER BY rowid DESC LIMIT 100)"
                )
            return report
        finally:
            owner._training.release()

    def detail(self, identity):
        """Read one retained report without refitting, fetching prices or changing a model."""
        with self.owner.store.db() as db:
            row = db.execute(
                "SELECT model_id,payload FROM forecast_evaluations WHERE id=?", (identity,)
            ).fetchone()
        if row is None:
            raise LookupError("Saved rolling evaluation not found.")
        report = json.loads(row["payload"])
        if (
            report["id"] != identity
            or report["model_id"] != row["model_id"]
            or report["result"]["engine"] != ROLLING_ENGINE
            or fingerprint(report["result"]) != report["result_fingerprint"]
            or fingerprint({key: value for key, value in report.items() if key != "fingerprint"})
            != report["fingerprint"]
        ):
            raise ValueError("Saved rolling evaluation integrity check failed.")
        return report

    @staticmethod
    def header(report):
        """Summarize a checked report without sending per-fold coefficients or traces."""
        return {
            **{key: value for key, value in report.items() if key != "result"},
            "aggregate": report["result"]["aggregate"],
        }

    def list(self, model_id):
        """List this model's retained evaluation headers, including limits and exact provenance."""
        self.owner._load(model_id)
        with self.owner.store.db() as db:
            ids = [
                row[0]
                for row in db.execute(
                    "SELECT id FROM forecast_evaluations WHERE model_id=? ORDER BY rowid DESC LIMIT 10",
                    (model_id,),
                )
            ]
        return {
            "items": [self.header(self.detail(identity)) for identity in ids],
            "limit": 10,
            "workspace_limit": 100,
        }
