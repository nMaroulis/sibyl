"""Reproducible backtests over immutable, attributable closed-candle datasets."""

import json

from pydantic import AwareDatetime, Field

from sibyl import __version__
from sibyl.market_data.archive import (
    InsufficientClosedCandles,
    boundaries,
    iso,
    milliseconds,
    step_ms,
    validated_rows,
)
from sibyl.models import BacktestRequest
from sibyl.strategies import backtest

MAX_RANGE_BACKTEST_CANDLES = 720


class RangeBacktest(BacktestRequest):
    """Pin a historical interval; the aligned date range determines the candle count."""

    start: AwareDatetime
    end: AwareDatetime
    candles: int = Field(default=MAX_RANGE_BACKTEST_CANDLES, ge=60, le=MAX_RANGE_BACKTEST_CANDLES)


def retained_backtest(store, identity: str) -> dict:
    """Read a saved single-pair backtest by ID, independent of the recent list."""
    with store.db() as db:
        row = db.execute("SELECT payload FROM runs WHERE id=? AND kind='backtest'", (identity,)).fetchone()
    if row is None:
        raise LookupError("Backtest not found.")
    return {**json.loads(row[0]), "id": identity}


def rerun_backtest(archive, store, identity: str):
    """Replay the saved immutable input and exact parameters, without provider reads."""
    from sibyl.market_data.backfills import DatasetBacktest

    previous = retained_backtest(store, identity)
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


def _short_backtest_history(request, metadata, available, minimum):
    environment = " (test feed)" if metadata["environment"] == "test" else ""
    return ValueError(
        f"{metadata['source_label']}{environment} returned {available} of {request.candles} "
        f"requested closed candles for {request.symbol} ({request.timeframe}). "
        f"This backtest needs at least {minimum} for its historical window and indicator settings. "
        "Choose a shorter timeframe, a feed with more history, or a complete saved dataset."
    )


def current_backtest(market, store, request):
    """Capture an exact current feed window before computing and retaining its result."""
    with market.snapshot():
        market.client().market(request.symbol)
        metadata = market.metadata()
        minimum = max(60, request.warmup + 1)
        try:
            candles = market.candles(request.symbol, request.candles, request.timeframe)
        except InsufficientClosedCandles as error:
            raise _short_backtest_history(request, metadata, error.available, minimum) from None
        if len(candles) < minimum:
            raise _short_backtest_history(request, metadata, len(candles), minimum)
        start = milliseconds(candles[0]["timestamp"])
        end = milliseconds(candles[-1]["timestamp"]) + step_ms(request.timeframe)
        if (end - start) // step_ms(request.timeframe) != len(candles):
            raise ValueError(
                "The provider candle page has gaps. Review retained coverage and choose a complete range."
            )
        dataset = market.archive.snapshot(metadata, request.symbol, request.timeframe, iso(start), iso(end))
    return _run_window(market.archive, store, request, dataset)


def _run_window(archive, store, request, dataset):
    from sibyl.market_data.backfills import DatasetBacktest

    parameters = DatasetBacktest(
        **{
            **request.model_dump(exclude={"start", "end"}),
            "candles": dataset["count"],
            "dataset_id": dataset["id"],
        }
    )
    return saved_backtest(archive, store, parameters)


def _fetch_missing_range(market, metadata, request, start, end, retained):
    """Use bounded native pages from this exact feed and only query incomplete pages."""
    client = market.client()
    if not client.candle_history or request.timeframe not in client.timeframes:
        raise ValueError(
            "This feed can backtest a complete retained range. Direct historical downloads are "
            "unavailable for the selected timeframe. Choose a range saved in Market History or another feed."
        )
    step = step_ms(request.timeframe)
    page_span = client.candle_page_size(request.timeframe) * step
    rows = []
    for left in range(start, end, page_span):
        right = min(left + page_span, end)
        if all(stamp in retained for stamp in range(left, right, step)):
            continue
        page = validated_rows(
            client.fetch_candle_page(request.symbol, request.timeframe, left, right),
            request.timeframe,
        )
        if any(not left <= row[0] < right for row in page):
            raise ValueError("The provider returned candles outside the requested historical window.")
        rows.extend(page)
    if rows:
        with market.store.db() as db:
            db.execute("BEGIN IMMEDIATE")
            market.archive.commit_rows(db, metadata, request.symbol, request.timeframe, rows)


def range_backtest(market, store, request: RangeBacktest):
    """Backtest the exact closed date window and keep its immutable candle input."""
    start, end = boundaries(request.start, request.end, request.timeframe)
    count = (end - start) // step_ms(request.timeframe)
    minimum = max(60, request.warmup + 1)
    if not minimum <= count <= MAX_RANGE_BACKTEST_CANDLES:
        raise ValueError(
            f"These dates contain {count} complete {request.timeframe} candles. Choose a range "
            f"with {minimum}–{MAX_RANGE_BACKTEST_CANDLES} candles for this strategy."
        )
    with market.snapshot():
        metadata = market.metadata()
        window_args = (
            metadata["source"],
            metadata["environment"],
            request.symbol,
            request.timeframe,
            iso(start),
            iso(end),
        )
        window = market.archive.window(*window_args)
        if not window["coverage"]["complete"]:
            retained = {milliseconds(candle["timestamp"]) for candle in window["candles"]}
            _fetch_missing_range(market, metadata, request, start, end, retained)
            coverage = market.archive.window(*window_args, limit=1)["coverage"]
            if not coverage["complete"]:
                raise ValueError(
                    f"{metadata['source_label']} has {coverage['stored']} of {count} required closed "
                    f"candles for {request.symbol} ({request.timeframe}) in those dates. "
                    "Choose a complete date range or a feed with more history."
                )
        dataset = market.archive.snapshot(metadata, request.symbol, request.timeframe, iso(start), iso(end))
    return _run_window(market.archive, store, request, dataset)
