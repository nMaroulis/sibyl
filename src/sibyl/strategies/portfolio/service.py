"""Attributable multi-asset research over exact saved inputs, with offline replay."""

import json
import math
import threading

from sibyl import __version__
from sibyl.market_data.archive import iso, milliseconds, step_ms
from sibyl.strategies.portfolio.contracts import PortfolioStudy
from sibyl.strategies.portfolio.engine import VERSION, simulate

KIND = "portfolio_backtest"


class PortfolioResearch:
    """Capture or load bounded same-source datasets; never read balances or submit orders."""

    def __init__(self, market, store):
        self.market, self.store, self.archive = market, store, market.archive
        self.lock = threading.Lock()

    def inputs(self):
        """List at most the archive budget of metadata, never candle bodies or providers."""
        with self.store.db() as db:
            rows = db.execute(
                "SELECT metadata FROM candle_datasets ORDER BY rowid DESC LIMIT 1000"
            ).fetchall()
        return {"datasets": [json.loads(row[0]) for row in rows], "max_assets": 8, "max_candles": 2000}

    def get(self, identity):
        with self.store.db() as db:
            row = db.execute("SELECT * FROM runs WHERE kind=? AND id=?", (KIND, identity)).fetchone()
        if not row:
            raise LookupError("Portfolio study not found.")
        return {"id": identity, "created_at": row["created_at"], **json.loads(row["payload"])}

    def list(self, demo=None):
        with self.store.db() as db:
            rows = db.execute(
                "SELECT id,created_at,json_remove(payload,'$.curve','$.allocations','$.fills','$.price_series','$.benchmarks','$.rebalance_events') AS payload FROM runs WHERE kind=? ORDER BY created_at DESC LIMIT 100",
                (KIND,),
            ).fetchall()
        return {
            "items": [
                {"id": row["id"], "created_at": row["created_at"], **json.loads(row["payload"])}
                for row in rows
                if demo is None or (json.loads(row["payload"])["source"] == "demo") == demo
            ]
        }

    def _capture(self, body):
        documents = []
        with self.market.snapshot("demo" if body.input_kind == "demo" else None):
            metadata = self.market.metadata()
            client = self.market.client()
            for leg in body.legs:
                if self.market.provider_symbol(leg.symbol) != leg.symbol:
                    raise ValueError(
                        "Portfolio studies require exact native quotes; source pair aliases are excluded."
                    )
                native = client.market(leg.symbol)
                if (
                    native.get("base") != leg.symbol.split("/")[0]
                    or native.get("quote") != leg.symbol.split("/")[1]
                ):
                    raise ValueError(
                        "Choose exact native pairs; provider quote aliases are not accepted in portfolio studies."
                    )
                candles = self.market.candles(leg.symbol, body.candles, body.timeframe)
                if len(candles) < 60:
                    raise ValueError("Every asset needs at least 60 closed candles.")
                start = milliseconds(candles[0]["timestamp"])
                end = milliseconds(candles[-1]["timestamp"]) + step_ms(body.timeframe)
                if (end - start) // step_ms(body.timeframe) != len(candles):
                    raise ValueError("An asset has gaps. Import a complete range before portfolio research.")
                saved = self.archive.snapshot(metadata, leg.symbol, body.timeframe, iso(start), iso(end))
                documents.append(self.archive.dataset(saved["id"]))
        return documents

    def _input(self, body):
        if body.input_kind == "saved_datasets":
            with self.store.db() as db:
                for leg in body.legs:
                    row = db.execute(
                        "SELECT metadata FROM candle_datasets WHERE id=?", (leg.dataset_id,)
                    ).fetchone()
                    if not row:
                        raise LookupError("Candle dataset not found.")
                    if not 60 <= json.loads(row[0])["count"] <= 2000:
                        raise ValueError("Choose saved datasets with 60–2,000 candles each.")
        documents = (
            [self.archive.dataset(leg.dataset_id) for leg in body.legs]
            if body.input_kind == "saved_datasets"
            else self._capture(body)
        )
        first = documents[0]["dataset"]
        step = step_ms(body.timeframe)
        left = max(milliseconds(d["dataset"]["start"]) for d in documents)
        right = min(milliseconds(d["dataset"]["end"]) for d in documents)
        count = (right - left) // step
        if right <= left or not 60 <= count <= 2000:
            raise ValueError(
                "The common exact window must contain 60–2,000 consecutive closed candles. Save narrower aligned inputs if needed."
            )
        expected = list(range(left, right, step))
        prices, datasets = {}, []
        for leg, document in zip(body.legs, documents, strict=True):
            meta, candles = document["dataset"], document["candles"]
            if (meta["source"], meta["environment"], meta["timeframe"]) != (
                first["source"],
                first["environment"],
                body.timeframe,
            ) or meta["symbol"] != leg.symbol:
                raise ValueError(
                    "Saved inputs must match each exact pair, timeframe, source and environment."
                )
            rows = [row for row in candles if left <= milliseconds(row["timestamp"]) < right]
            if [milliseconds(row["timestamp"]) for row in rows] != expected:
                raise ValueError(
                    "Every asset must have the same consecutive UTC candle grid. No fill-forward, dropped gaps or synthetic prices are allowed."
                )
            if any(
                type(row[key]) not in {int, float} or not math.isfinite(row[key]) or row[key] <= 0
                for row in rows
                for key in ("open", "high", "low", "close")
            ):
                raise ValueError("Portfolio inputs contain invalid prices.")
            prices[leg.symbol] = rows
            datasets.append(meta)
        return (
            prices,
            [iso(t) for t in expected],
            datasets,
            {
                "start": iso(left),
                "end": iso(right),
                "count": count,
                "trimmed": any(d["count"] != count for d in datasets),
                "join": "Exact consecutive intersection; no forward filling.",
            },
        )

    def run(self, body, *, previous=None):
        """Publish one cost-conserving historical artifact; failures never save a success."""
        if not self.lock.acquire(blocking=False):
            raise ValueError("Another portfolio study is running. Wait for its outcome.")
        try:
            with self.store.db() as db:
                if db.execute("SELECT COUNT(*) FROM runs WHERE kind=?", (KIND,)).fetchone()[0] >= 100:
                    raise ValueError("Keep at most 100 portfolio studies. Remove an old artifact first.")
            if previous and previous["engine_revision"] != VERSION:
                raise ValueError(
                    "The portfolio engine changed; exact replay is unavailable. Start a new study explicitly."
                )
            prices, timestamps, datasets, window = self._input(body)
            result = simulate(body, prices, timestamps)
            if previous and result["decision_fingerprint"] != previous["decision_fingerprint"]:
                raise ValueError(
                    "The stored study did not reproduce its original trades/equity. No replay was saved."
                )
            recipe = body.model_dump()
            recipe.update(
                input_kind="saved_datasets",
                legs=[
                    dict(leg.model_dump(), dataset_id=dataset["id"])
                    for leg, dataset in zip(body.legs, datasets, strict=True)
                ],
            )
            result.update(
                title=body.title,
                kind=KIND,
                simulation=True,
                source=datasets[0]["source"],
                source_label=datasets[0]["source_label"],
                environment=datasets[0]["environment"],
                quote=body.legs[0].symbol.split("/")[1],
                initial_capital=body.capital,
                timeframe=body.timeframe,
                datasets=datasets,
                window=window,
                parameters=recipe,
                captured_from=body.input_kind,
                target_cash_pct=100 - math.fsum(leg.weight_pct for leg in body.legs),
                engine_revision=VERSION,
                engine_version=__version__,
                price_series={
                    s: [{"timestamp": row["timestamp"], "value": row["close"]} for row in rows]
                    for s, rows in prices.items()
                },
                assumptions="User-fixed targets; interval schedules or previous-close drift trigger next-open execution. Post-cost sizing uses that observed open; sells precede buys. Fractional units, quote fees, fixed adverse slippage, unlimited modeled liquidity and zero cash interest. Final-close liquidation costs apply to both portfolios. Allocation history/pre-liquidation holdings are marked before the final exit. Historical simulation only; no exchange orders or account balance changes.",
            )
            if previous:
                result["rerun_of"] = previous["id"]
            json.dumps(result, allow_nan=False)
            record = self.store.record(KIND, result)
            return {"id": record["id"], "created_at": record["created_at"], **result}
        finally:
            self.lock.release()

    def rerun(self, identity):
        previous = self.get(identity)
        return self.run(PortfolioStudy(**previous["parameters"]), previous=previous)

    def delete(self, identity):
        self.get(identity)
        with self.store.db() as db:
            db.execute("DELETE FROM runs WHERE kind=? AND id=?", (KIND, identity))
