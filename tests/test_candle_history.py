"""Retained research data: exact provenance, atomic progress and offline reproducibility."""

import json
from copy import deepcopy

import ccxt
import httpx
import pytest

from sibyl.exchanges import create_client
from sibyl.exchanges.demo import DemoClient
from sibyl.market_data.archive import (
    CandleArchive,
    boundaries,
    floor_time,
    iso,
    milliseconds,
    now_ms,
    step_ms,
    validated_rows,
)
from sibyl.market_data.backfills import CandleHistory, CandleRange, DatasetBacktest
from sibyl.market_data.clients import CryptoCompareClient
from sibyl.market_data.research import saved_backtest
from sibyl.services.data_settings import DataSettings
from sibyl.services.market import Market

META = {"source": "demo", "source_label": "Demo", "environment": "demo", "provider": "demo"}
DAY = 86400000
START = 1704067200000  # Jan 1 2024, UTC Monday


def rows(count=90, start=START, step=DAY):
    return [[start + i * step, 100 + i, 102 + i, 99 + i, 101 + i, 10] for i in range(count)]


def insert(archive, data, meta=None, symbol="BTC/USDT", frame="1d"):
    with archive.store.db() as db:
        db.execute("BEGIN IMMEDIATE")
        return archive.commit_rows(db, meta or META, symbol, frame, validated_rows(data, frame))


def snapshot(archive, count=90):
    return archive.snapshot(META, "BTC/USDT", "1d", iso(START), iso(START + count * DAY), "Research fixture")


@pytest.fixture
def archive(store):
    return CandleArchive(store)


@pytest.fixture
def history(settings, store):
    market = Market(settings, store, DataSettings(settings, store))
    service = CandleHistory(market, store)
    yield service
    service.close()
    market.close()


def current_request(count=250, frame="1d", age=0):
    step = step_ms(frame)
    end = floor_time(now_ms(), frame) - age * step
    return CandleRange(
        source="demo", symbol="BTC/USDT", timeframe=frame, start=iso(end - count * step), end=iso(end)
    )


def due(service):
    with service.store.db() as db:
        for row in db.execute("SELECT payload FROM candle_imports").fetchall():
            job = json.loads(row[0])
            job["next_attempt"] = 0
            service._write(db, job)
    service.tick()


def test_series_partitions_and_idempotent_revisions(archive):
    assert insert(archive, rows()) == 90
    assert insert(archive, rows()) == 0
    for meta, symbol, frame in [
        ({**META, "source": "other"}, "BTC/USDT", "1d"),
        ({**META, "environment": "test"}, "BTC/USDT", "1d"),
        (META, "BTC/USD", "1d"),
        (META, "BTC/USDT", "1h"),
    ]:
        insert(archive, rows(), meta, symbol, frame)
    result = archive.window("demo", "demo", "BTC/USDT", "1d")
    assert result["revision"] == 1 and result["retained"] == 90 and result["coverage"]["complete"]
    assert len(archive.catalog()["items"]) == 5
    corrected = rows()
    corrected[0][4] = 100.5
    assert insert(archive, corrected) == 1
    assert archive.window("demo", "demo", "BTC/USDT", "1d")["revision"] == 2


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.__setitem__(0, r[0] + 1),
        lambda r: r.__setitem__(2, 1),
        lambda r: r.__setitem__(5, -1),
        lambda r: r.__setitem__(4, float("nan")),
        lambda r: r.__setitem__(1, True),
        lambda r: r.__setitem__(3, 10000),
    ],
)
def test_invalid_provider_bars_rejected(change):
    page = rows(1)
    change(page[0])
    with pytest.raises(ValueError):
        validated_rows(page, "1d")


def test_open_duplicate_and_weekly_contracts():
    page = rows(2)
    assert validated_rows(page + page, "1d", closed_at=START + DAY) == page[:1]
    conflict = deepcopy(page)
    conflict[0][4] = 100.5
    with pytest.raises(ValueError, match="conflicting"):
        validated_rows(page + conflict, "1d")
    assert floor_time(START + 3 * DAY, "1w") == START
    assert validated_rows(rows(2, step=7 * DAY), "1w") == rows(2, step=7 * DAY)
    with pytest.raises(ValueError):
        validated_rows(rows(2, start=START + DAY, step=7 * DAY), "1w")


@pytest.mark.parametrize(
    "left,right",
    [
        ("2024-01-01", "2024-02-01"),
        (iso(START), iso(START)),
        (iso(START), iso(START + 50001 * DAY)),
        (iso(START), iso(now_ms() + DAY)),
    ],
)
def test_invalid_dates_and_range_budgets(left, right):
    with pytest.raises(ValueError):
        boundaries(left, right, "1d")


def test_coverage_missing_runs_and_preview_bound(archive):
    start = START - 2000 * DAY
    data = rows(2100, start)
    data.pop(100)
    data.pop(100)
    insert(archive, data[:2000])
    insert(archive, data[2000:])
    result = archive.window("demo", "demo", "BTC/USDT", "1d", iso(start), iso(start + 2100 * DAY))
    assert len(result["candles"]) == 2000 and result["preview_truncated"]
    assert result["coverage"]["missing"] == 2
    assert result["coverage"]["gaps"] == [
        {"start": iso(start + 100 * DAY), "end": iso(start + 102 * DAY), "candles": 2}
    ]
    with pytest.raises(ValueError, match="missing candles"):
        archive.snapshot(META, "BTC/USDT", "1d", iso(start), iso(start + 200 * DAY))


def test_storage_quota_rolls_back_whole_page(archive):
    archive.per_series_limit = 3
    insert(archive, rows(2))
    with pytest.raises(ValueError, match="budget"):
        insert(archive, rows(4))
    result = archive.window("demo", "demo", "BTC/USDT", "1d")
    assert result["retained"] == 2 and result["revision"] == 1


def test_snapshot_immutable_after_correction_and_pruning(archive):
    insert(archive, rows())
    saved = snapshot(archive)
    original = archive.dataset(saved["id"])
    assert snapshot(archive)["id"] == saved["id"]
    corrected = rows()
    corrected[0][4] = 100.5
    insert(archive, corrected)
    assert snapshot(archive)["id"] != saved["id"]
    with pytest.raises(ValueError, match="Type PRUNE"):
        archive.prune("demo", "demo", "BTC/USDT", "1d", iso(START + DAY), "yes")
    assert (
        archive.prune("demo", "demo", "BTC/USDT", "1d", iso(START + 90 * DAY), "PRUNE BTC/USDT")["removed"]
        == 90
    )
    assert archive.dataset(saved["id"]) == original
    assert archive.datasets()["total"] == 2


def test_dataset_integrity_and_exact_research_contract(archive, store):
    insert(archive, rows())
    saved = snapshot(archive)
    request = DatasetBacktest(
        dataset_id=saved["id"], symbol="BTC/USDT", timeframe="1d", candles=90, strategy="ema"
    )
    first = saved_backtest(archive, store, request)
    second = saved_backtest(archive, store, request)
    assert first["curve"] == second["curve"] and first["fills"] == second["fills"]
    assert first["dataset"]["digest"] == saved["id"] and first["engine_version"]
    with pytest.raises(ValueError, match="must match"):
        saved_backtest(archive, store, request.model_copy(update={"symbol": "BTC/USD"}))
    with archive.store.db() as db:
        corrupted = archive.dataset(saved["id"])["candles"]
        corrupted[0]["close"] = 999
        db.execute("UPDATE candle_datasets SET candles=? WHERE id=?", (json.dumps(corrupted), saved["id"]))
    with pytest.raises(ValueError, match="integrity"):
        archive.dataset(saved["id"])


def test_import_page_checkpoint_resume_and_restart(history):
    request = current_request()
    job = history.queue(request)
    due(history)
    status = history.status("demo", "BTC/USDT", "1d")
    assert status["retained"] == 200 and status["job"]["pages"] == 1
    assert status["job"]["cursor"] == milliseconds(request.start) + 200 * DAY
    history.action(job["id"], "pause")
    due(history)
    assert history.status("demo", "BTC/USDT", "1d")["retained"] == 200
    with pytest.raises(ValueError, match="Pause"):
        history.action(job["id"], "resume")
        history.queue(current_request(251))
    with history.store.db() as db:
        interrupted = history._read(db, job["id"])
        interrupted["status"] = "running"
        history._write(db, interrupted)
    resumed = CandleHistory(history.market, history.store)
    due(resumed)
    result = resumed.status("demo", "BTC/USDT", "1d")
    assert result["job"]["status"] == "complete" and result["retained"] == 250
    assert result["job"]["pages"] == 2
    resumed.close()


def test_delayed_page_cannot_override_pause_or_checkpoint(history, monkeypatch):
    job = history.queue(current_request())
    with history.market.snapshot("demo"):
        client = history.market.client()
    original = client.fetch_candle_page

    def delayed(*args):
        history.action(job["id"], "pause")
        return original(*args)

    monkeypatch.setattr(client, "fetch_candle_page", delayed)
    due(history)
    result = history.status("demo", "BTC/USDT", "1d")
    assert result["job"]["status"] == "paused" and result["retained"] == 0
    assert result["job"]["cursor"] == job["start_ms"]


def test_backfill_empty_data_is_gaps_and_dataset_refused(history, monkeypatch):
    request = current_request(90)
    history.queue(request)
    with history.market.snapshot("demo"):
        client = history.market.client()
    monkeypatch.setattr(client, "fetch_candle_page", lambda *a: [])
    due(history)
    result = history.status("demo", "BTC/USDT", "1d", request.start, request.end)
    assert result["job"]["status"] == "gaps" and result["coverage"]["missing"] == 90
    with pytest.raises(ValueError, match="missing"):
        history.archive.snapshot(META, "BTC/USDT", "1d", request.start, request.end)


@pytest.mark.parametrize(
    "failure,retry", [(ccxt.NetworkError("PRIVATE-KEY"), True), (ValueError("PRIVATE-KEY"), False)]
)
def test_import_errors_sanitized_and_no_cursor_advance(history, monkeypatch, failure, retry):
    job = history.queue(current_request())
    with history.market.snapshot("demo"):
        client = history.market.client()

    def fail(*args):
        raise failure

    monkeypatch.setattr(client, "fetch_candle_page", fail)
    due(history)
    result = history.status("demo", "BTC/USDT", "1d")
    assert result["job"]["cursor"] == job["start_ms"] and result["retained"] == 0
    assert result["job"]["status"] == ("retrying" if retry else "error")
    assert "PRIVATE" not in json.dumps(result)


def test_quota_failure_rolls_back_import_and_checkpoint(history):
    history.archive.per_series_limit = 100
    job = history.queue(current_request())
    due(history)
    result = history.status("demo", "BTC/USDT", "1d")
    assert result["job"]["status"] == "error" and result["retained"] == 0
    assert result["job"]["cursor"] == job["start_ms"]


def test_active_import_blocks_prune_and_rescan_preserves_snapshots(history):
    request = current_request(90)
    job = history.queue(request)
    with pytest.raises(ValueError, match="Pause"):
        history.archive.prune("demo", "demo", "BTC/USDT", "1d", request.end, "PRUNE BTC/USDT")
    due(history)
    meta = history.metadata("demo")
    saved = history.archive.snapshot(meta, "BTC/USDT", "1d", request.start, request.end)
    reset = history.action(job["id"], "rescan")
    assert reset["cursor"] == job["start_ms"] and reset["pages"] == 0
    assert history.archive.dataset(saved["id"])["dataset"] == saved


def test_read_only_history_and_saved_test_never_query_provider(client, monkeypatch):
    assert client.get("/api/v1/markets/analysis?source=demo&symbol=BTC/USDT&limit=90").status_code == 200
    history = client.get("/api/v1/market-history?source=demo&symbol=BTC/USDT").json()
    saved = client.post(
        "/api/v1/market-history/datasets",
        json={
            "source": "demo",
            "symbol": "BTC/USDT",
            "timeframe": "1d",
            "start": history["start"],
            "end": history["end"],
        },
    ).json()

    def network_forbidden(*args, **kwargs):
        raise AssertionError("offline path contacted a provider")

    monkeypatch.setattr(client.app.state.services.market, "snapshot", network_forbidden)
    for path in [
        "/market-history?source=demo&symbol=BTC/USDT",
        "/market-history/series",
        "/market-history/datasets",
        f"/market-history/datasets/{saved['id']}",
        f"/market-history/datasets/{saved['id']}/metadata",
    ]:
        response = client.get("/api/v1" + path)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
    response = client.post(
        "/api/v1/strategies/backtest/dataset",
        json={
            "dataset_id": saved["id"],
            "symbol": "BTC/USDT",
            "timeframe": "1d",
            "candles": 90,
            "strategy": "ema",
        },
    )
    assert response.status_code == 200 and response.json()["dataset"]["id"] == saved["id"]


def test_current_backtest_saves_input_and_rejects_exact_pair_substitution(client):
    response = client.post(
        "/api/v1/strategies/backtest", json={"strategy": "ema", "symbol": "BTC/USDT", "candles": 90}
    )
    assert response.status_code == 200 and response.json()["dataset"]["count"] == 90
    assert client.get("/api/v1/market-history/datasets").json()["total"] == 1
    assert (
        client.post(
            "/api/v1/strategies/backtest", json={"strategy": "ema", "symbol": "BTC/EUR", "candles": 90}
        ).status_code
        >= 400
    )


@pytest.mark.parametrize(
    "provider", ["binance", "binanceus", "binance-testnet", "coinbase", "coinbase-sandbox", "kraken"]
)
def test_reviewed_ccxt_pagination_is_exact_and_bounded(provider, monkeypatch):
    adapter = create_client(provider)
    adapter._markets = {"BTC/USDT": {"symbol": "BTC/USDT", "base": "BTC", "quote": "USDT"}}
    end = floor_time(now_ms(), "1d")
    start = end - 90 * DAY
    seen = []

    def read(symbol, frame, **kwargs):
        seen.append((symbol, frame, kwargs))
        return rows(90, start)

    monkeypatch.setattr(adapter._exchange, "fetch_ohlcv", read)
    assert len(adapter.fetch_candle_page("BTC/USDT", "1d", start, end)) == 90
    kwargs = seen[0][2]
    assert kwargs == {
        "since": start,
        "limit": 200,
        "params": {} if provider == "kraken" else {"until": end - 1},
    }
    with pytest.raises(ValueError):
        adapter.fetch_candle_page("BTC/USDT", "1d", start - 201 * DAY, end)
    monkeypatch.setattr(adapter._exchange, "fetch_ohlcv", lambda *a, **kw: rows(1, START))
    with pytest.raises(ValueError, match="requested historical"):
        adapter.fetch_candle_page("BTC/USDT", "1d", start, end)
    adapter.close()


def test_kraken_does_not_claim_old_history():
    adapter = create_client("kraken")
    with pytest.raises(ValueError, match="720"):
        adapter.fetch_candle_page("BTC/USD", "1d", START, START + DAY)
    adapter.close()


def test_cryptocompare_uses_native_endtime_and_demo_pages_same_series():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "Data": {
                    "Data": [
                        dict(
                            zip(
                                ("time", "open", "high", "low", "close", "volumefrom"),
                                [r[0] // 1000, *r[1:]],
                                strict=True,
                            )
                        )
                        for r in rows(90)
                    ]
                }
            },
        )

    adapter = CryptoCompareClient(transport=httpx.MockTransport(handler))
    adapter._markets = {"BTC/USDT": {"base": "BTC", "quote": "USDT", "spot": True}}
    assert len(adapter.fetch_candle_page("BTC/USDT", "1d", START, START + 90 * DAY)) == 90
    assert seen[-1].url.params["toTs"] == str((START + 90 * DAY) // 1000 - 1)
    assert seen[-1].url.params["tryConversion"] == "false"
    adapter.close()
    demo = DemoClient()
    full = demo.fetch_ohlcv("BTC/USDT", "1w", 730)
    assert full[0][0] == floor_time(int(full[0][0]), "1w")
    assert demo.fetch_candle_page("BTC/USDT", "1w", int(full[0][0]), int(full[100][0])) == full[:100]


@pytest.mark.parametrize("frame", list(CryptoCompareClient.intervals))
def test_aggregator_page_size_respects_underlying_interval_budget(frame):
    adapter = CryptoCompareClient()
    limit = adapter.candle_page_size(frame)
    assert 1 <= limit <= 200
    assert (limit + 1) * adapter.intervals[frame][1] <= 2000
    adapter.close()


def test_disconnected_archive_remains_offline(history, monkeypatch):
    insert(
        history.archive,
        rows(),
        {**META, "source": "connection:removed", "source_label": "Removed account", "environment": "test"},
    )

    def no_snapshot(*a, **kw):
        raise AssertionError("Provider must not be opened")

    monkeypatch.setattr(history.market, "snapshot", no_snapshot)
    retained = history.status("connection:removed", "BTC/USDT", "1d")
    assert retained["retained"] == 90 and not retained["available"] and retained["environment"] == "test"


def test_default_coverage_truncation_is_disclosed(archive, monkeypatch):
    insert(archive, rows(20))
    monkeypatch.setattr("sibyl.market_data.archive.MAX_RANGE", 10)
    result = archive.window("demo", "demo", "BTC/USDT", "1d")
    assert result["range_truncated"] and result["coverage"]["expected"] == 10
    assert result["retained"] == 20


def test_invalid_out_of_range_page_cannot_advance(history, monkeypatch):
    job = history.queue(current_request(90))
    with history.market.snapshot("demo"):
        client = history.market.client()
    monkeypatch.setattr(client, "fetch_candle_page", lambda *a: rows(1))
    due(history)
    result = history.status("demo", "BTC/USDT", "1d")
    assert result["job"]["status"] == "error" and result["job"]["cursor"] == job["cursor"]
    assert result["retained"] == 0


def test_import_retry_budget_is_finite(history, monkeypatch):
    history.queue(current_request(90))
    with history.market.snapshot("demo"):
        client = history.market.client()

    def unavailable(*a):
        raise ccxt.RateLimitExceeded("PRIVATE")

    monkeypatch.setattr(client, "fetch_candle_page", unavailable)
    for _ in range(6):
        due(history)
    result = history.status("demo", "BTC/USDT", "1d")
    assert result["job"]["status"] == "error" and result["job"]["failures"] == 6
    assert result["job"]["pages"] == 0


def test_maximum_saved_dataset_runs_beyond_live_page_limit(archive, store):
    page = rows(20_000, step=3_600_000)
    for start in range(0, len(page), 2000):
        insert(archive, page[start : start + 2000], frame="1h")
    saved = archive.snapshot(META, "BTC/USDT", "1h", iso(START), iso(START + 20_000 * 3_600_000))
    request = DatasetBacktest(
        dataset_id=saved["id"], symbol="BTC/USDT", timeframe="1h", candles=20_000, strategy="ema"
    )
    result = saved_backtest(archive, store, request)
    assert result["dataset"]["count"] == 20_000 and len(result["curve"]) > 19_000
    assert result["parameters"]["candles"] == 20_000
