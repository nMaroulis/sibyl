"""Reproducible backtests over immutable, attributable closed-candle datasets."""

from sibyl import __version__
from sibyl.market_data.archive import iso, milliseconds, step_ms
from sibyl.strategies import backtest


def rerun_backtest(archive, store, identity: str):
    """Replay the saved immutable input and exact parameters, without provider reads."""
    import json

    from sibyl.market_data.backfills import DatasetBacktest

    with store.db() as db:
        row = db.execute("SELECT payload FROM runs WHERE id=? AND kind='backtest'", (identity,)).fetchone()
    if row is None:
        raise LookupError("Backtest not found.")
    previous = json.loads(row[0])
    if not previous.get("dataset"):
        raise ValueError("This older run has no retained input. Choose a saved dataset to rerun it.")
    request = DatasetBacktest(**{**previous["parameters"], "dataset_id": previous["dataset"]["id"]})
    return saved_backtest(archive, store, request, rerun_of=identity)


def saved_backtest(archive, store, request, *, rerun_of: str | None = None):
    """Use the entire saved dataset, without fetching any provider data."""
    document = archive.dataset(request.dataset_id)
    dataset, candles = document["dataset"], document["candles"]
    if (request.symbol, request.timeframe, request.candles) != (
        dataset["symbol"],
        dataset["timeframe"],
        dataset["count"],
    ):
        raise ValueError(
            "Backtest pair, timeframe and observation count must match the selected saved dataset."
        )
    result = {
        **backtest(candles, request),
        "source": dataset["source"],
        "environment": dataset["environment"],
        "dataset": dataset,
        "engine_version": __version__,
        "input_kind": "saved_dataset",
    }
    if rerun_of:
        result["rerun_of"] = rerun_of
    record = store.record("backtest", result)
    return {**result, "id": record["id"]}


def current_backtest(market, store, request):
    """Capture an exact current feed window before computing and retaining its result."""
    with market.snapshot():
        market.client().market(request.symbol)
        candles = market.candles(request.symbol, request.candles, request.timeframe)
        if len(candles) < 60:
            raise ValueError("At least 60 closed candles are required for a reproducible backtest.")
        start = milliseconds(candles[0]["timestamp"])
        end = milliseconds(candles[-1]["timestamp"]) + step_ms(request.timeframe)
        if (end - start) // step_ms(request.timeframe) != len(candles):
            raise ValueError(
                "The provider candle page has gaps. Review retained coverage and choose a complete range."
            )
        dataset = market.archive.snapshot(
            market.metadata(), request.symbol, request.timeframe, iso(start), iso(end)
        )
    from sibyl.market_data.backfills import DatasetBacktest

    parameters = DatasetBacktest(
        **{**request.model_dump(), "candles": len(candles), "dataset_id": dataset["id"]}
    )
    return saved_backtest(market.archive, store, parameters)
