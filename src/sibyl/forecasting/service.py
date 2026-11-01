"""Local model registry and explicit research operations over immutable daily input.

HTTP routes may train or retain forecasts. Native agent tools read models and
saved results, or calculate from retained inputs without writing or fetching.
Artifacts are versioned JSON, never pickle or executable uploaded model files.
"""

import json
import threading
from uuid import uuid4

from sibyl import __version__
from sibyl.forecasting.contracts import ForecastRequest, TrainForecast
from sibyl.forecasting.engine import ENGINE, fingerprint, predict, train
from sibyl.market_data.archive import iso, milliseconds, now_ms, step_ms


class ForecastModels:
    """Own bounded fits, immutable model versions and the latest twenty forecasts per version."""

    def __init__(self, market, store):
        self.market, self.store = market, store
        self._training = threading.Lock()
        with store.db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS forecast_models (
                    id TEXT PRIMARY KEY, series_id TEXT NOT NULL, version INTEGER NOT NULL,
                    metadata TEXT NOT NULL, payload TEXT NOT NULL,
                    UNIQUE(series_id,version)
                );
                CREATE TABLE IF NOT EXISTS forecast_outputs (
                    id TEXT PRIMARY KEY, model_id TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS forecast_outputs_model ON forecast_outputs(model_id);
            """)

    def _input(self, body):
        if body.input_kind == "saved_dataset":
            document = self.market.archive.dataset(body.dataset_id)
        else:
            with self.market.snapshot("demo" if body.input_kind == "demo" else None):
                self.market.client().market(body.symbol)
                candles = self.market.candles(body.symbol, body.candles, "1d")
                if len(candles) < 360:
                    raise ValueError(
                        "This feed returned fewer than 360 closed daily candles. Import a longer saved dataset in Markets."
                    )
                dataset = self.market.archive.snapshot(
                    self.market.metadata(),
                    body.symbol,
                    "1d",
                    candles[0]["timestamp"],
                    iso(milliseconds(candles[-1]["timestamp"]) + step_ms("1d")),
                    body.label,
                )
                document = self.market.archive.dataset(dataset["id"])
        dataset = document["dataset"]
        if dataset["timeframe"] != "1d" or dataset["symbol"] != body.symbol:
            raise ValueError("Use a daily dataset for the exact selected spot pair.")
        if not 360 <= dataset["count"] <= 5000:
            raise ValueError("Forecast training needs 360–5,000 consecutive daily candles.")
        return document

    def train(self, body: TrainForecast, *, parent_id=None):
        """Explicitly fit and evaluate, committing a complete model version only on success."""
        if not self._training.acquire(blocking=False):
            raise ValueError("A forecast model is already training. Wait for it to finish.")
        try:
            with self.store.db() as db:
                if db.execute("SELECT COUNT(*) FROM forecast_models").fetchone()[0] >= 100:
                    raise ValueError("The workspace model budget (100 versions) has been reached.")
            document = self._input(body)
            artifact = train(document["candles"], body)
            digest = fingerprint({"dataset": document["dataset"], "artifact": artifact})
            parent = self._load(parent_id) if parent_id else None
            identity, series = uuid4().hex, parent["metadata"]["series_id"] if parent else uuid4().hex
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                if db.execute("SELECT COUNT(*) FROM forecast_models").fetchone()[0] >= 100:
                    raise ValueError("The workspace model budget (100 versions) has been reached.")
                version = db.execute(
                    "SELECT COALESCE(MAX(version),0)+1 FROM forecast_models WHERE series_id=?", (series,)
                ).fetchone()[0]
                metadata = {
                    "id": identity,
                    "series_id": series,
                    "version": version,
                    "label": body.label,
                    "created_at": iso(now_ms()),
                    "symbol": body.symbol,
                    "source": document["dataset"]["source"],
                    "environment": document["dataset"]["environment"],
                    "dataset": document["dataset"],
                    "engine": ENGINE,
                    "app_version": __version__,
                    "fingerprint": digest,
                    "parameters": artifact["parameters"],
                    "parent_id": parent_id,
                }
                payload = {"metadata": metadata, "artifact": artifact, "request": body.model_dump()}
                db.execute(
                    "INSERT INTO forecast_models VALUES(?,?,?,?,?)",
                    (identity, series, version, json.dumps(metadata), json.dumps(payload, allow_nan=False)),
                )
            return self.detail(identity)
        finally:
            self._training.release()

    def _load(self, identity):
        with self.store.db() as db:
            row = db.execute("SELECT payload FROM forecast_models WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise LookupError("Forecast model not found.")
        result = json.loads(row[0])
        metadata = result["metadata"]
        if (
            metadata["id"] != identity
            or metadata["parameters"] != result["artifact"]["parameters"]
            or any(metadata[key] != metadata["dataset"][key] for key in ("symbol", "source", "environment"))
        ):
            raise ValueError("Saved model provenance check failed.")
        actual = fingerprint({"dataset": result["metadata"]["dataset"], "artifact": result["artifact"]})
        if actual != result["metadata"]["fingerprint"]:
            raise ValueError("Saved model integrity check failed.")
        return result

    def list(self):
        """Return all bounded registry metadata without reading providers or constructing LLMs."""
        with self.store.db() as db:
            rows = db.execute("SELECT metadata FROM forecast_models ORDER BY rowid DESC LIMIT 100").fetchall()
        return {"items": [json.loads(row[0]) for row in rows], "limit": 100}

    def detail(self, identity, horizon=None):
        """Read all compact metrics and only the requested horizon's test trace."""
        model = self._load(identity)
        artifact = model["artifact"]
        horizon = min(7, artifact["parameters"]["max_horizon"]) if horizon is None else horizon
        if not 1 <= horizon <= artifact["parameters"]["max_horizon"]:
            raise ValueError("Choose a horizon supported by this trained model.")
        return {
            "model": model["metadata"],
            "partitions": artifact["partitions"],
            "notes": artifact["notes"],
            "evaluation": [
                {key: value for key, value in item.items() if key != "trace"}
                for item in artifact["evaluation"]
            ],
            "test_trace": artifact["evaluation"][horizon - 1]["trace"],
            "trace_horizon": horizon,
            "nominal_coverage": artifact["nominal_coverage"],
            "outputs": self.outputs(identity),
        }

    def rerun(self, identity):
        """Fit a new numbered version with the original frozen data and parameters, offline."""
        previous = self._load(identity)
        body = TrainForecast(
            **{
                **previous["request"],
                "input_kind": "saved_dataset",
                "dataset_id": previous["metadata"]["dataset"]["id"],
            }
        )
        return self.train(body, parent_id=identity)

    def export(self, identity):
        """Export JSON coefficients, input provenance, partition evidence and full evaluation traces."""
        return self._load(identity)

    def preview(self, identity, horizon=14, *, run_id=None):
        """Read a saved forecast, or calculate from the original retained dataset; never fetch or write."""
        if run_id:
            result = self.output(run_id)
            if result["model_id"] != identity:
                raise ValueError("The saved forecast does not belong to this model.")
            if horizon > result["horizon"]:
                raise ValueError("This saved forecast does not include that horizon.")
            if horizon == result["horizon"]:
                return result
            # The saved fingerprint describes the complete original output, not this view.
            digest = result.pop("result_fingerprint")
            return {
                **result,
                "points": result["points"][:horizon],
                "saved_horizon": result["horizon"],
                "horizon": horizon,
                "saved_result_fingerprint": digest,
            }
        model = self._load(identity)
        document = self.market.archive.dataset(model["metadata"]["dataset"]["id"])
        return self._predict(model, document["candles"][-90:], horizon, "saved_input")

    def _predict(self, model, candles, horizon, input_kind):
        metadata = model["metadata"]
        if milliseconds(candles[-1]["timestamp"]) < milliseconds(metadata["dataset"]["end"]) - step_ms("1d"):
            raise ValueError("Forecast observations predate the model's retained research input.")
        result = predict(model["artifact"], candles, horizon)
        age = max(0, (now_ms() - milliseconds(result["origin"])) / step_ms("1d"))
        window = {
            "source": metadata["source"],
            "environment": metadata["environment"],
            "symbol": metadata["symbol"],
            "candles": candles,
        }
        return {
            **result,
            "model_id": metadata["id"],
            "model_version": metadata["version"],
            "model_fingerprint": metadata["fingerprint"],
            "symbol": metadata["symbol"],
            "source": metadata["source"],
            "environment": metadata["environment"],
            "input_kind": input_kind,
            "input_fingerprint": fingerprint(window),
            "age_days": age,
            "stale": age > 2,
            "observations": window,
        }

    def forecast(self, identity, body: ForecastRequest):
        """Retain one explicit forecast; current input must match the model's exact source and environment."""
        model = self._load(identity)
        metadata = model["metadata"]
        if body.input_kind == "saved_input":
            result = self.preview(identity, body.horizon)
        else:
            with self.market.snapshot(metadata["source"]):
                attribution = self.market.metadata()
                if (attribution["source"], attribution["environment"]) != (
                    metadata["source"],
                    metadata["environment"],
                ):
                    raise ValueError("The original market source or environment is unavailable.")
                self.market.client().market(metadata["symbol"])
                candles = self.market.candles(metadata["symbol"], 90, "1d")
            result = self._predict(model, candles, body.horizon, body.input_kind)
        result = {**result, "id": uuid4().hex, "created_at": iso(now_ms())}
        result["result_fingerprint"] = fingerprint(result)
        with self.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO forecast_outputs VALUES(?,?,?)",
                (result["id"], identity, json.dumps(result, allow_nan=False)),
            )
            db.execute(
                "DELETE FROM forecast_outputs WHERE model_id=? AND id NOT IN (SELECT id FROM forecast_outputs WHERE model_id=? ORDER BY rowid DESC LIMIT 20)",
                (identity, identity),
            )
        return result

    def outputs(self, identity):
        """Read twenty retained forecast headers without expanding observation windows."""
        with self.store.db() as db:
            rows = db.execute(
                "SELECT payload FROM forecast_outputs WHERE model_id=? ORDER BY rowid DESC LIMIT 20",
                (identity,),
            ).fetchall()
        return [
            {key: value for key, value in json.loads(row[0]).items() if key not in {"points", "observations"}}
            for row in rows
        ]

    def output(self, identity):
        """Read exact forecast observations and results without contacting its source."""
        with self.store.db() as db:
            row = db.execute("SELECT payload FROM forecast_outputs WHERE id=?", (identity,)).fetchone()
        if row is None:
            raise LookupError("Saved forecast not found.")
        result = json.loads(row[0])
        if fingerprint(result["observations"]) != result["input_fingerprint"]:
            raise ValueError("Saved forecast input integrity check failed.")
        if (
            fingerprint({key: value for key, value in result.items() if key != "result_fingerprint"})
            != result["result_fingerprint"]
        ):
            raise ValueError("Saved forecast result integrity check failed.")
        return result
