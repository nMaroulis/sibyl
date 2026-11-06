"""Kraken v2 display protocol: native subscriptions, receipt attribution and safe lifecycle."""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import aiohttp
import pytest

from sibyl.market_data.streaming.kraken import ENDPOINT, SubscriptionRejected, observations
from sibyl.market_data.streams import LiveMarkets


def ticker(**changes):
    return {
        "channel": "ticker",
        "type": "snapshot",
        "data": [{"symbol": "BTC/USD", "last": 100.0, "change_pct": -1.0, **changes}],
    }


def candle(start=None, interval=1, **changes):
    start = int(time.time() // 60) * 60 if start is None else start
    return {
        "channel": "ohlc",
        "type": "update",
        "data": [
            {
                "symbol": "BTC/USD",
                "interval": interval,
                "interval_begin": datetime.fromtimestamp(start, UTC).isoformat(),
                "open": 100,
                "high": 105,
                "low": 95,
                "close": 102,
                "volume": 5,
                **changes,
            }
        ],
    }


def test_ticker_receipt_time_is_not_fabricated_provider_time():
    wall = time.time()
    event = observations(ticker(), "BTC/USD", "BTC/USD", "1m", wall=wall)[0]
    assert event["time_basis"] == "receipt" and event["received_at"] == event["observed_at"]
    assert event["snapshot"] and event["change"] == -1
    row = ticker(timestamp=datetime.fromtimestamp(wall - 1, UTC).isoformat())
    assert observations(row, "BTC/USD", "BTC/USD", "1m", wall=wall)[0]["time_basis"] == "provider"
    assert observations(ticker(timestamp="2020-01-01T00:00:00Z"), "BTC/USD", "BTC/USD", "1m", wall=wall) == []
    assert observations(ticker(symbol="ETH/USD"), "BTC/USD", "BTC/USD", "1m") == []


@pytest.mark.parametrize("value", [True, 0, -1, "nan", "inf"])
def test_invalid_prices_never_become_events(value):
    with pytest.raises(ValueError):
        observations(ticker(last=value), "BTC/USD", "BTC/USD", "1m")


def test_only_current_native_candles_are_previewed_without_a_fabricated_close_flag():
    wall = time.time()
    event = observations(candle(), "BTC/USD", "BTC/USD", "1m", wall=wall)[0]
    assert event["closed"] is False and event["time_basis"] == "receipt"
    assert observations(candle(start=int(wall // 60) * 60 - 60), "BTC/USD", "BTC/USD", "1m", wall=wall) == []
    assert observations(candle(interval=5), "BTC/USD", "BTC/USD", "1m", wall=wall) == []
    with pytest.raises(ValueError):
        observations(candle(high=90), "BTC/USD", "BTC/USD", "1m", wall=wall)
    # A native week can start on Monday; the Unix epoch's Thursday is not imposed.
    monday = datetime(2026, 11, 2, tzinfo=UTC).timestamp()
    weekly = observations(
        candle(start=monday, interval=10080), "BTC/USD", "BTC/USD", "1w", wall=monday + 3 * 86400
    )[0]
    assert weekly["candle"]["timestamp"] == datetime.fromtimestamp(monday, UTC).isoformat()


def test_subscription_errors_do_not_leak_provider_text_or_become_data():
    with pytest.raises(SubscriptionRejected) as error:
        observations(
            {"method": "subscribe", "success": False, "error": "PRIVATE-NATIVE-DETAIL"},
            "BTC/USD",
            "BTC/USD",
            "1d",
        )
    assert "PRIVATE" not in str(error.value)
    assert observations({"channel": "heartbeat"}, "BTC/USD", "BTC/USD", "1d") == []


@pytest.mark.asyncio
async def test_runtime_sends_native_subscriptions_and_releases_shared_socket():
    hub = LiveMarkets(None)
    requests, opened, closed = [], [], []
    gate = asyncio.Event()

    async def receive():
        await gate.wait()

    @asynccontextmanager
    async def connect(url):
        opened.append(url)

        async def send_json(value):
            requests.append(value)

        try:
            yield SimpleNamespace(send_json=send_json, receive=receive)
        finally:
            closed.append(url)

    hub.connect = connect
    identity = {
        "source": "kraken",
        "source_label": "Kraken",
        "provider": "kraken",
        "environment": "production",
    }
    async with hub.subscribe(identity, "BTC/USD", "BTC/USD", "1m") as (first, _):
        async with hub.subscribe(identity, "BTC/USD", "BTC/USD", "1m") as (second, _):
            await asyncio.sleep(0.01)
            assert first is second and opened == [ENDPOINT]
            assert requests == [
                {
                    "method": "subscribe",
                    "params": {"channel": "ticker", "symbol": ["BTC/USD"], "snapshot": True},
                },
                {
                    "method": "subscribe",
                    "params": {"channel": "ohlc", "symbol": ["BTC/USD"], "snapshot": True, "interval": 1},
                },
            ]
        assert not closed
    assert closed == [ENDPOINT] and not hub.channels
    await hub.close()


@pytest.mark.asyncio
async def test_native_rejection_is_visible_without_reconnect_churn():
    hub = LiveMarkets(None)

    @asynccontextmanager
    async def connect(url):
        async def send_json(value):
            pass

        async def receive():
            return SimpleNamespace(
                type=aiohttp.WSMsgType.TEXT,
                data=json.dumps({"method": "subscribe", "success": False, "error": "SECRET"}),
            )

        yield SimpleNamespace(send_json=send_json, receive=receive)

    hub.connect = connect
    identity = {
        "source": "kraken",
        "source_label": "Kraken",
        "provider": "kraken",
        "environment": "production",
    }
    async with hub.subscribe(identity, "BTC/USD", "BTC/USD", "1m"):
        await asyncio.sleep(0.01)
        state = hub.snapshot()
        assert state["items"][0]["state"] == "unavailable" and state["items"][0]["reconnects"] == 0
        assert "SECRET" not in json.dumps(state)


def test_selection_preserves_source_environment_and_native_spot_symbol(client, monkeypatch):
    market = client.app.state.services.market
    metadata = {
        "source": "kraken",
        "source_label": "Kraken",
        "provider": "kraken",
        "environment": "production",
    }
    monkeypatch.setattr(market, "metadata", lambda: metadata)
    monkeypatch.setattr(
        market,
        "client",
        lambda: SimpleNamespace(timeframes={"1m": 1, "12h": 720}, stream_symbol=lambda symbol: symbol),
    )
    with market.snapshot("demo"):
        assert market.live.selection(None, "BTC/USD", "1m")[1] == "BTC/USD"
        with pytest.raises(ValueError, match="REST"):
            market.live.selection(None, "BTC/USD", "12h")
        metadata["environment"] = "test"
        with pytest.raises(ValueError, match="REST"):
            market.live.selection(None, "BTC/USD", "1m")
