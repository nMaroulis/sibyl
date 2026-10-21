"""Reproducible backtests over immutable, attributable closed-candle datasets."""

from sibyl import __version__
from sibyl.market_data.archive import iso, milliseconds, step_ms
from sibyl.services.strategies import backtest


def saved_backtest(archive, store, request):
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
