"""Persist bounded adaptive studies and exact-input/version replay without exchange access."""

import json
import threading
from importlib import metadata

from sibyl import __version__
from sibyl.strategies.backtest import BacktestEngine
from sibyl.strategies.plugins.contracts import PluginBacktest
from sibyl.strategies.research.adaptive.contracts import AdaptiveStudy
from sibyl.strategies.research.adaptive.engine import VERSION, AdaptiveEngine, available, optuna_module
from sibyl.strategies.validation import SEARCH_PRESETS, WalkForwardEngine

KIND = "adaptive_study"


class AdaptiveStudies:
    """Save research artifacts separately from jobs, live strategy deployment and native orders."""

    def __init__(self, store, archive, plugins):
        self.store, self.archive, self.plugins = store, archive, plugins
        self.lock = threading.Lock()

    def options(self):
        strategies = WalkForwardEngine.options()["strategies"]
        return {
            "available": available(),
            "optional_extra": "optimization",
            "library_version": metadata.version("optuna") if available() else None,
            "builtin": {
                strategy: [
                    {
                        "key": row["key"],
                        "kind": "float" if row["key"] in {"band_std", "volume_multiplier"} else "int",
                        "low": min(SEARCH_PRESETS[row["key"]]),
                        "high": max(SEARCH_PRESETS[row["key"]]),
                    }
                    for row in fields
                ]
                for strategy, fields in strategies.items()
            },
            "plugins": self.plugins.registry.catalog()["items"],
            "max_trials": 24,
            "max_distributions": 4,
            "max_folds": 5,
            "max_work_bars": 60000,
            "max_candles": 2000,
            "note": "Native Optuna TPE or random numeric distributions; training-prefix selection, independent later tests, no deployment. Trusted installed plugins are owner code, not sandboxed. Queued runs are one-off and never automatically repeated after interruption.",
        }

    def list(self, demo=None):
        items = []
        for record in self.store.runs(KIND):
            row = record["payload"]
            if demo is not None and (row["source"] == "demo") != demo:
                continue
            items.append(
                {
                    "id": record["id"],
                    "created_at": record["created_at"],
                    **{
                        key: row[key]
                        for key in (
                            "status",
                            "source",
                            "environment",
                            "dataset",
                            "summary",
                            "recipe",
                            "sampler",
                        )
                    },
                }
            )
        return {"items": items}

    def get(self, identity):
        with self.store.db() as db:
            row = db.execute("SELECT * FROM runs WHERE id=? AND kind=?", (identity, KIND)).fetchone()
        if row is None:
            raise LookupError("Adaptive strategy study not found.")
        return {"id": identity, "created_at": row["created_at"], **json.loads(row["payload"])}

    def _inputs(self, recipe):
        document = self.archive.dataset(recipe.dataset_id)
        dataset, candles = document["dataset"], document["candles"]
        if (dataset["symbol"], dataset["timeframe"], dataset["count"]) != (
            recipe.parameters.symbol,
            recipe.parameters.timeframe,
            recipe.parameters.candles,
        ):
            raise ValueError("Use the exact saved dataset's pair, timeframe and candle count.")
        plugin, plugin_metadata = None, None
        if recipe.engine == "plugin":
            factory, spec, _, implementation, revision = self.plugins.registry.resolve(
                recipe.plugin_id, recipe.plugin_revision
            )
            plugin = {"factory": factory, "spec": spec}
            plugin_metadata = {
                "id": recipe.plugin_id,
                "spec": spec.model_dump(),
                "implementation": implementation,
                "revision": revision,
            }
        return dataset, candles, plugin, plugin_metadata

    def validate(self, arguments):
        """Preflight a queued immutable recipe; reject missing dependencies or impossible budgets now."""
        recipe = AdaptiveStudy.model_validate(arguments)
        optuna_module()
        _, candles, plugin, _ = self._inputs(recipe)
        AdaptiveEngine(plugin).plan(recipe, len(candles))

    def validate_plugin(self, arguments):
        body = PluginBacktest.model_validate(arguments)
        if body.input_kind != "saved_dataset":
            raise ValueError("Queued custom backtests require an immutable saved dataset.")
        self.plugins.registry.resolve(body.plugin_id, body.revision)
        self.plugins._input(body)

    def run(self, recipe: AdaptiveStudy, *, previous=None):
        """Validate exact retained inputs and native versions before publishing one complete artifact."""
        if not self.lock.acquire(blocking=False):
            raise ValueError("Another adaptive study is running. Wait for its retained outcome.")
        try:
            optuna = optuna_module()
            if previous and (
                previous["method"] != VERSION
                or previous["sampler"]["version"] != optuna.__version__
                or previous["engine_revision"] != BacktestEngine.version
            ):
                raise ValueError(
                    "The sampler or backtest version changed. Start a new study; exact replay is unavailable."
                )
            with self.store.db() as db:
                if db.execute("SELECT COUNT(*) FROM runs WHERE kind=?", (KIND,)).fetchone()[0] >= 100:
                    raise ValueError("Keep at most 100 adaptive studies. Remove an old artifact first.")
            dataset, candles, plugin, plugin_metadata = self._inputs(recipe)
            result = AdaptiveEngine(plugin).run(candles, recipe)
            if plugin:
                self.plugins.registry.resolve(recipe.plugin_id, recipe.plugin_revision)
            if previous and result["decision_fingerprint"] != previous["decision_fingerprint"]:
                raise ValueError(
                    "This study no longer reproduces its recorded trials, decisions or test evidence. No replay artifact was saved."
                )
            result.update(
                recipe=recipe.model_dump(mode="json"),
                dataset=dataset,
                source=dataset["source"],
                environment=dataset["environment"],
                engine_version=__version__,
                engine_revision=BacktestEngine.version,
                plugin=plugin_metadata,
            )
            if previous:
                result["rerun_of"] = previous["id"]
            json.dumps(result, allow_nan=False)
            saved = self.store.record(KIND, result)
            return {"id": saved["id"], "created_at": saved["created_at"], **result}
        finally:
            self.lock.release()

    def rerun(self, identity):
        old = self.get(identity)
        return self.run(AdaptiveStudy(**old["recipe"]), previous=old)

    def delete(self, identity):
        with self.store.db() as db:
            if not db.execute("DELETE FROM runs WHERE id=? AND kind=?", (identity, KIND)).rowcount:
                raise LookupError("Adaptive strategy study not found.")

    def pinned_plugin_run(self, arguments):
        """Only immutable dataset plugin recipes may enter the local research job queue."""
        body = PluginBacktest.model_validate(arguments)
        if body.input_kind != "saved_dataset":
            raise ValueError("Queued custom backtests require an immutable saved dataset.")
        result = self.plugins.run(body)
        return {
            "report_id": result["id"],
            "kind": "plugin_backtest",
            "url": "/strategies",
            "note": "A historical research artifact was retained. This job did not deploy a strategy or submit orders.",
        }
