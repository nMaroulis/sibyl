"""Portable research recipes and data, verified by a local numerical refit on import.

Bundles contain JSON, not executable model files. Imported observations receive a
new unverified import namespace; claimed provider identity never becomes live
market evidence. Saved forecasts and prospective tracking are not imported.
"""

import json
import re
from uuid import uuid4

from sibyl import __version__
from sibyl.forecasting.contracts import TrainForecast
from sibyl.forecasting.engine import engine_for, fingerprint, parameters, train, validate
from sibyl.market_data.archive import FIELDS, iso, milliseconds, now_ms, step_ms, validated_rows

MAX_BUNDLE = 16 * 1024 * 1024
FORMAT = "sibyl-forecast-bundle"


def decode(content):
    """Parse finite, bounded JSON and reject duplicate keys rather than choosing one silently."""
    if len(content) > MAX_BUNDLE:
        raise ValueError("Forecast bundles are limited to 16 MiB.")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate bundle fields are not supported.")
            result[key] = value
        return result

    try:
        result = json.loads(
            content,
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Non-finite JSON is not supported.")),
        )
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("Use a valid finite JSON forecast bundle exported by Sibyl.") from None


class ForecastBundles:
    """Import recipes offline with the same bounded training admission and model budget."""

    def __init__(self, models):
        self.models, self.store = models, models.store

    def export(self, identity):
        """Include the complete immutable training input and recorded numerical evidence."""
        model = self.models._load(identity)
        document = self.models.market.archive.dataset(model["metadata"]["dataset"]["id"])
        value = {"format": FORMAT, "schema": 1, "model": model, "dataset": document}
        result = {**value, "digest": fingerprint(value)}
        if len(json.dumps(result, allow_nan=False).encode()) > MAX_BUNDLE:
            raise ValueError(
                "This model bundle exceeds the portable 16 MiB limit. Export its existing evidence separately."
            )
        return result

    @staticmethod
    def validate(document):
        """Check content hashes, known engine, complete daily OHLCV and a bounded training recipe."""
        if (
            set(document) != {"format", "schema", "model", "dataset", "digest"}
            or document["format"] != FORMAT
            or type(document["schema"]) is not int
            or document["schema"] != 1
        ):
            raise ValueError("Unsupported forecast bundle format.")
        if document["digest"] != fingerprint(
            {key: value for key, value in document.items() if key != "digest"}
        ):
            raise ValueError("Forecast bundle integrity check failed.")
        model, data = document["model"], document["dataset"]
        if (
            not isinstance(model, dict)
            or set(model) != {"metadata", "artifact", "request"}
            or not isinstance(data, dict)
            or set(data) != {"dataset", "candles"}
        ):
            raise ValueError("Incomplete forecast bundle.")
        metadata, artifact, dataset, candles = (
            model["metadata"],
            model["artifact"],
            data["dataset"],
            data["candles"],
        )
        body = TrainForecast(**model["request"])
        if metadata["engine"] != engine_for(body.feature_set, body.family) or artifact[
            "engine"
        ] != engine_for(body.feature_set, body.family):
            raise ValueError("This forecast engine is not supported by the installed app.")
        expected_parameters = parameters(body)
        if (
            metadata["parameters"] != expected_parameters
            or artifact["parameters"] != expected_parameters
            or metadata["dataset"] != dataset
        ):
            raise ValueError("Model recipe and retained input do not agree.")
        if (
            not re.fullmatch(r"[A-Z0-9]{1,12}/[A-Z0-9]{1,12}", dataset["symbol"])
            or dataset["symbol"] != body.symbol
            or dataset["timeframe"] != "1d"
            or dataset["schema"] != 1
        ):
            raise ValueError("Use the exact daily spot input from the model.")
        if (
            not isinstance(candles, list)
            or not 360 <= len(candles) <= 5000
            or len(candles) != dataset["count"]
        ):
            raise ValueError("Portable models need 360–5,000 daily candles.")
        if any(not isinstance(row, dict) or set(row) != {"timestamp", *FIELDS} for row in candles):
            raise ValueError("Invalid portable candle fields.")
        identity = {key: dataset[key] for key in ("source", "environment", "symbol", "timeframe", "schema")}
        digest = fingerprint([identity, candles])
        if (
            digest != dataset["id"]
            or digest != dataset["digest"]
            or metadata["fingerprint"] != fingerprint({"dataset": dataset, "artifact": artifact})
        ):
            raise ValueError("Portable model/input fingerprint check failed.")
        if any(metadata[key] != dataset[key] for key in ("source", "environment", "symbol")):
            raise ValueError("Portable source attribution does not agree.")
        validate(candles, 360)
        for index in range(0, len(candles), 2000):
            validated_rows(
                [
                    [milliseconds(row["timestamp"]), *[row[key] for key in FIELDS]]
                    for row in candles[index : index + 2000]
                ],
                "1d",
            )
        if dataset["start"] != candles[0]["timestamp"] or milliseconds(dataset["end"]) != milliseconds(
            candles[-1]["timestamp"]
        ) + step_ms("1d"):
            raise ValueError("Portable input range does not match its candles.")
        for key in ("source", "environment", "source_label"):
            if (
                not isinstance(dataset[key], str)
                or len(dataset[key]) > 160
                or any(ord(char) < 32 for char in dataset[key])
            ):
                raise ValueError("Invalid portable source label.")
        return body, dataset, candles, artifact, metadata

    def import_bundle(self, content):
        """Refit the imported recipe locally and atomically retain a new unverified research version."""
        if not self.models._training.acquire(blocking=False):
            raise ValueError(
                "A forecast model is already training or being evaluated. Wait for it to finish."
            )
        try:
            document = decode(content)
            try:
                body, original, candles, recorded, old = self.validate(document)
            except (KeyError, TypeError, AttributeError, OverflowError, RecursionError):
                raise ValueError("Incomplete or malformed portable model evidence.") from None
            with self.store.db() as db:
                existing = db.execute(
                    "SELECT id FROM forecast_models WHERE json_extract(metadata,'$.imported_from.bundle_digest')=?",
                    (document["digest"],),
                ).fetchone()
                if existing:
                    return {
                        **self.models.detail(existing[0]),
                        "import_result": {"duplicate": True, "recomputed": False},
                    }
                if db.execute("SELECT COUNT(*) FROM forecast_models").fetchone()[0] >= 100:
                    raise ValueError(
                        "The workspace model budget (100 versions) has been reached; archiving does not delete evidence or free storage."
                    )
            artifact = train(
                candles, body
            )  # Uploaded coefficients and metrics are never trusted as computed evidence.
            source = "import:" + original["digest"]
            identity = {
                "source": source,
                "environment": "imported",
                "symbol": body.symbol,
                "timeframe": "1d",
                "schema": 1,
            }
            digest = fingerprint([identity, candles])
            dataset = {
                **identity,
                "id": digest,
                "digest": digest,
                "label": body.label,
                "source_label": ("Imported · " + original["source_label"])[:160],
                "count": len(candles),
                "start": candles[0]["timestamp"],
                "end": iso(milliseconds(candles[-1]["timestamp"]) + step_ms("1d")),
                "created_at": iso(now_ms()),
                "immutable": True,
                "source_verified": False,
            }
            identity, series = uuid4().hex, uuid4().hex
            origin = {
                "bundle_digest": document["digest"],
                "model_id": str(old["id"])[:100],
                "claimed_source": original["source"],
                "claimed_environment": original["environment"],
                "original_fingerprint": old["fingerprint"],
                "recorded_fit_matches_local": fingerprint(recorded) == fingerprint(artifact),
                "verified": False,
                "method": "Input integrity checked; recipe refitted locally. Provider origin is user-supplied, not independently verified.",
            }
            metadata = {
                "id": identity,
                "series_id": series,
                "version": 1,
                "label": body.label,
                "created_at": iso(now_ms()),
                "symbol": body.symbol,
                "source": source,
                "environment": "imported",
                "dataset": dataset,
                "engine": artifact["engine"],
                "app_version": __version__,
                "fingerprint": fingerprint({"dataset": dataset, "artifact": artifact}),
                "parameters": artifact["parameters"],
                "parent_id": None,
                "imported_from": origin,
            }
            request = body.model_copy(
                update={"input_kind": "saved_dataset", "dataset_id": digest}
            ).model_dump()
            payload = {"metadata": metadata, "artifact": artifact, "request": request}
            with self.store.db() as db:
                db.execute("BEGIN IMMEDIATE")
                if db.execute("SELECT COUNT(*) FROM forecast_models").fetchone()[0] >= 100:
                    raise ValueError("The workspace model budget (100 versions) has been reached.")
                if not db.execute("SELECT 1 FROM candle_datasets WHERE id=?", (digest,)).fetchone():
                    if db.execute("SELECT COUNT(*) FROM candle_datasets").fetchone()[0] >= 1000:
                        raise ValueError("The workspace dataset budget (1,000) has been reached.")
                    db.execute(
                        "INSERT INTO candle_datasets VALUES(?,?,?)",
                        (digest, json.dumps(dataset), json.dumps(candles, allow_nan=False)),
                    )
                else:
                    # Reuse an identical immutable input's original metadata so its model fingerprint stays exact.
                    dataset = json.loads(
                        db.execute("SELECT metadata FROM candle_datasets WHERE id=?", (digest,)).fetchone()[0]
                    )
                    metadata["dataset"] = dataset
                    metadata["fingerprint"] = fingerprint({"dataset": dataset, "artifact": artifact})
                db.execute(
                    "INSERT INTO forecast_models VALUES(?,?,?,?,?)",
                    (identity, series, 1, json.dumps(metadata), json.dumps(payload, allow_nan=False)),
                )
            return {**self.models.detail(identity), "import_result": {"duplicate": False, "recomputed": True}}
        finally:
            self.models._training.release()
