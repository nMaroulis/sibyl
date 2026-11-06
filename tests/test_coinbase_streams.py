"""Coinbase native public protocol, including connection-wide subscription sequences."""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import aiohttp
import pytest

from sibyl.market_data.streaming.coinbase import ENDPOINT, PublicFeed, SequenceGap, exact_product
from sibyl.market_data.streams import LiveMarkets


def envelope(channel="ticker", sequence=0, **changes):
    return {
        "channel": channel,
        "sequence_num": sequence,
        "timestamp": datetime.now(UTC).isoformat(),
        "events": [
            {
                "type": "update",
                "tickers": [{"product_id": "BTC-USD", "price": "100", "price_percent_chg_24_h": "-2"}],
            }
        ],
        **changes,
    }


def test_connection_sequence_includes_subscriptions_and_heartbeats_without_freshening_prices():
    feed = PublicFeed()
    assert feed.observations(envelope("subscriptions", 0), "BTC-USD", "BTC/USD", "1d") == []
    ticker = envelope(sequence=1)
    assert feed.observations(ticker, "BTC-USD", "BTC/USD", "1d")[0]["price"] == 100
    assert feed.observations(envelope("heartbeats", 2), "BTC-USD", "BTC/USD", "1d") == []
    assert (
        feed.observations(envelope(sequence=3), "BTC-USD", "BTC/USD", "1d")[0]["time_basis"]
        == "provider_envelope"
    )
    assert feed.observations(envelope(sequence=3), "BTC-USD", "BTC/USD", "1d") == []
    with pytest.raises(SequenceGap):
        feed.observations(envelope(sequence=5), "BTC-USD", "BTC/USD", "1d")


@pytest.mark.parametrize("value", [True, "nan", "-1", 0, "inf"])
def test_invalid_prices_rejected(value):
    row = envelope()
    row["events"][0]["tickers"][0]["price"] = value
    with pytest.raises(ValueError):
        PublicFeed().observations(row, "BTC-USD", "BTC/USD", "1d")


def test_only_current_native_five_minute_candles_are_previewed():
    now = time.time()
    candle = {
        "product_id": "BTC-USD",
        "start": str(int(now) // 300 * 300),
        "open": "100",
        "high": "102",
        "low": "99",
        "close": "101",
        "volume": "12",
    }
    row = envelope("candles", events=[{"type": "snapshot", "candles": [candle]}])
    assert PublicFeed().observations(row, "BTC-USD", "BTC/USD", "5m")[0]["closed"] is False
    assert not PublicFeed().observations(row, "BTC-USD", "BTC/USD", "1h")
    candle["start"] = str(int(now) // 300 * 300 - 300)
    assert not PublicFeed().observations(row, "BTC-USD", "BTC/USD", "5m")
    exact_product("USDT-USDC")
    with pytest.raises(ValueError, match="aliases"):
        exact_product("BTC-USDC")


async def test_public_socket_sends_no_credentials_and_drains_last_viewer():
    hub = LiveMarkets(None)
    sent, closed = [], []
    waiting = asyncio.Event()

    @asynccontextmanager
    async def connect(url):
        assert url == ENDPOINT

        async def send(payload):
            sent.append(payload)

        async def receive():
            if not closed:
                closed.append(False)
                return SimpleNamespace(type=aiohttp.WSMsgType.TEXT, data=json.dumps(envelope()))
            await waiting.wait()

        try:
            yield SimpleNamespace(send_json=send, receive=receive)
        finally:
            closed.append(True)

    hub.connect = connect
    identity = {
        "source": "coinbase",
        "provider": "coinbase",
        "environment": "production",
        "source_label": "Coinbase",
    }
    async with hub.subscribe(identity, "BTC-USD", "BTC/USD", "5m") as (channel, queue):
        for _ in range(8):
            event = await asyncio.wait_for(queue.get(), 2)
            if event["type"] == "ticker":
                break
        assert event["price"] == 100
        assert {r["channel"] for r in sent} == {"ticker", "candles", "heartbeats"}
        assert "jwt" not in json.dumps(sent) and "token" not in json.dumps(sent)
    assert closed[-1] and not hub.channels
    await hub.close()


def test_exact_source_selection_rejects_sandbox_and_public_usdc_aliases():
    from contextlib import nullcontext
    from types import SimpleNamespace

    identity = {
        "source": "coinbase",
        "provider": "coinbase",
        "environment": "production",
        "source_label": "Coinbase",
    }
    client = SimpleNamespace(timeframes={"1d": 86400}, stream_symbol=lambda _: "BTC-USD")
    market = SimpleNamespace(
        snapshot=lambda _: nullcontext(), metadata=lambda: identity, client=lambda: client
    )
    hub = LiveMarkets(market)
    assert hub.selection("coinbase", "BTC/USD", "1d")[1] == "BTC-USD"
    client.stream_symbol = lambda _: "BTC-USDC"
    with pytest.raises(ValueError, match="aliases"):
        hub.selection("coinbase", "BTC/USDC", "1d")
    identity["environment"] = "test"
    with pytest.raises(ValueError, match="REST"):
        hub.selection("coinbase", "BTC/USD", "1d")
