"""Research-only plugin execution and exact-input replay, separate from strategy jobs."""

import json
import threading

from sibyl import __version__
from sibyl.forecasting.engine import fingerprint
from sibyl.market_data.archive import iso, milliseconds, step_ms
from sibyl.models import BacktestRequest
from sibyl.strategies.backtest import BacktestEngine
from sibyl.strategies.plugins.contracts import PluginBacktest
from sibyl.strategies.plugins.engine import plugin_signals
from sibyl.strategies.plugins.registry import PluginRegistry

KIND = "plugin_backtest"


class PluginResearch:
    def __init__(self, market, store):
        self.market, self.store = market, store
        self.registry = PluginRegistry(market.settings.strategy_plugins)
        self.lock = threading.Lock()

    def list(self):
        return {
            "items": [
                {
                    "id": r["id"],
                    "created_at": r["created_at"],
                    **{
                        k: r["payload"][k]
                        for k in ("plugin", "symbol", "source", "environment", "return_pct", "trades")
                    },
                }
                for r in self.store.runs(KIND)
            ]
        }

    def get(self, identity):
        with self.store.db() as db:
            row = db.execute("SELECT payload FROM runs WHERE id=? AND kind=?", (identity, KIND)).fetchone()
        if not row:
            raise LookupError("Custom strategy backtest not found.")
        return {"id": identity, **json.loads(row[0])}

    def _input(self, body):
        if body.input_kind == "saved_dataset":
            document = self.market.archive.dataset(body.dataset_id)
            dataset, candles = document["dataset"], document["candles"]
            if (body.symbol, body.timeframe, body.candles) != (
                dataset["symbol"],
                dataset["timeframe"],
                dataset["count"],
            ):
                raise ValueError("Pair, interval and count must match the exact saved dataset.")
            if len(candles) > 2000:
                raise ValueError("Custom backtests support at most 2,000 saved candles.")
            return dataset, candles
        with self.market.snapshot("demo" if body.input_kind == "demo" else None):
            self.market.client().market(body.symbol)
            candles = self.market.candles(body.symbol, body.candles, body.timeframe)
            if not 60 <= len(candles) <= 720:
                raise ValueError("Custom current/Demo research needs 60–720 closed candles.")
            start = milliseconds(candles[0]["timestamp"])
            end = milliseconds(candles[-1]["timestamp"]) + step_ms(body.timeframe)
            if (end - start) // step_ms(body.timeframe) != len(candles):
                raise ValueError("Custom input contains missing intervals.")
            dataset = self.market.archive.snapshot(
                self.market.metadata(), body.symbol, body.timeframe, iso(start), iso(end)
            )
            return dataset, candles

    def run(self, body, *, previous=None):
        if not self.lock.acquire(blocking=False):
            raise ValueError("Another custom backtest is running. Wait for it to finish.")
        try:
            with self.store.db() as db:
                if db.execute("SELECT COUNT(*) FROM runs WHERE kind=?", (KIND,)).fetchone()[0] >= 100:
                    raise ValueError("Keep at most 100 custom backtests. Remove an old result first.")
            factory, spec, _, implementation, revision = self.registry.resolve(body.plugin_id, body.revision)
            values = spec.values(body.values)
            dataset, candles = self._input(body)
            parameters = BacktestRequest(
                strategy="ema",
                symbol=body.symbol,
                timeframe=body.timeframe,
                capital=body.capital,
                fee_bps=body.fee_bps,
                slippage_bps=body.slippage_bps,
                candles=min(720, len(candles)),
                stop_loss_pct=body.stop_loss_pct,
                take_profit_pct=body.take_profit_pct,
                max_trades=body.max_trades,
            )
            if spec.warmup >= len(candles):
                raise ValueError("Choose more closed candles than this plugin's warmup.")
            directions = plugin_signals(factory, spec, values, candles)
            signal_hash = fingerprint(directions)
            if previous and previous["signal_fingerprint"] != signal_hash:
                raise ValueError(
                    "This plugin no longer reproduces its recorded decisions. No rerun was saved."
                )
            result = BacktestEngine().run(
                candles, parameters, evaluation_start=spec.warmup, signal_override=directions
            )
            # A package changed during execution must not receive a successful pinned receipt.
            self.registry.resolve(body.plugin_id, body.revision)
            canonical = body.model_copy(
                update={
                    "values": values,
                    "input_kind": "saved_dataset",
                    "dataset_id": dataset["id"],
                    "candles": len(candles),
                }
            )
            result.update(
                strategy="plugin:" + body.plugin_id,
                plugin={
                    "id": body.plugin_id,
                    "name": spec.name,
                    "revision": revision,
                    "implementation": implementation,
                    "spec": spec.model_dump(),
                },
                source=dataset["source"],
                source_label=dataset["source_label"],
                environment=dataset["environment"],
                dataset=dataset,
                parameters=canonical.model_dump(),
                input_kind=body.input_kind,
                engine_version=__version__,
                signal_fingerprint=signal_hash,
                plugin_signals=[
                    {"timestamp": row["timestamp"], "signal": value}
                    for row, value in zip(candles, directions, strict=True)
                ],
                note="Trusted local custom strategy, historical research only. Previous-close signals fill next open with costs; no live orders, automatic deployment or profitability guarantee. Pinned queued research and adaptive studies are separate explicit actions.",
            )
            if previous:
                result["rerun_of"] = previous["id"]
            # Fail closed on non-finite output before the general record writer.
            json.dumps(result, allow_nan=False)
            saved = self.store.record(KIND, result)
            return {**result, "id": saved["id"]}
        finally:
            self.lock.release()

    def rerun(self, identity):
        old = self.get(identity)
        return self.run(PluginBacktest(**old["parameters"]), previous=old)

    def delete(self, identity):
        with self.store.db() as db:
            if not db.execute("DELETE FROM runs WHERE id=? AND kind=?", (identity, KIND)).rowcount:
                raise LookupError("Custom strategy backtest not found.")
