"""Exact-source live previews: validation, fanout, bounded memory and lifecycle cleanup."""

import asyncio
import json
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from sibyl.market_data.streaming.orderbook import PublicOrderBook
from sibyl.market_data.streams import Channel, LiveMarkets, observation


def ticker(**changes):
    return {"e": "24hrTicker", "s": "BTCUSDT", "E": time.time() * 1000, "c": "50000", "P": "-1.2", **changes}


def test_stream_observations_are_numeric_source_bound_and_dated():
    event = observation({"data": ticker()}, "BTCUSDT", "BTC/USDT", "1d")
    assert event["price"] == 50000 and event["change"] == -1.2
    assert observation(ticker(s="ETHUSDT"), "BTCUSDT", "BTC/USDT", "1d") is None
    assert observation(ticker(E=1), "BTCUSDT", "BTC/USDT", "1d") is None
    assert observation(ticker(E=time.time() * 1000 + 10000), "BTCUSDT", "BTC/USDT", "1d") is None


@pytest.mark.parametrize("price", ["nan", "-1", True, "inf", 0])
def test_invalid_live_price_is_never_display_evidence(price):
    with pytest.raises(ValueError):
        observation(ticker(c=price), "BTCUSDT", "BTC/USDT", "1d")


def test_candle_interval_and_shape_are_validated():
    stamp = int(time.time() * 1000)
    row = {
        "e": "kline",
        "s": "BTCUSDT",
        "E": stamp,
        "k": {
            "s": "BTCUSDT",
            "i": "1m",
            "t": stamp // 60000 * 60000,
            "o": "10",
            "h": "12",
            "l": "9",
            "c": "11",
            "v": "2",
            "x": False,
        },
    }
    event = observation(row, "BTCUSDT", "BTC/USDT", "1m")
    assert event["candle"]["close"] == 11 and event["closed"] is False
    assert observation(row, "BTCUSDT", "BTC/USDT", "1d") is None
    row["k"]["h"] = "5"
    with pytest.raises(ValueError):
        observation(row, "BTCUSDT", "BTC/USDT", "1m")


@pytest.mark.asyncio
async def test_slow_stream_viewers_have_bounded_queues():
    row = Channel({"source": "binance"}, "BTCUSDT", "BTC/USDT", "1d")
    queue = asyncio.Queue(maxsize=2)
    row.queues.add(queue)
    for number in range(100):
        row.publish({"price": number})
    assert queue.qsize() == 2
    assert (await queue.get())["price"] == 98
    assert (await queue.get())["price"] == 99


@pytest.mark.asyncio
async def test_shared_socket_last_viewer_cleanup_and_test_endpoint():
    hub, opened, closed = LiveMarkets(None), [], []
    gate = asyncio.Event()

    @asynccontextmanager
    async def connect(url):
        opened.append(url)
        socket = SimpleNamespace(receive=lambda: gate.wait())
        try:
            yield socket
        finally:
            closed.append(url)

    hub.connect = connect
    selection = {
        "source": "connection:test",
        "source_label": "Test",
        "provider": "binance-testnet",
        "environment": "test",
    }
    async with hub.subscribe(selection, "BTCUSDT", "BTC/USDT", "1d") as (first, _):
        async with hub.subscribe(selection, "BTCUSDT", "BTC/USDT", "1d") as (second, _):
            await asyncio.sleep(0.01)
            assert first is second and len(opened) == 1
        assert not closed
    assert len(closed) == 1 and not hub.channels
    assert opened[0].startswith("wss://stream.testnet.binance.vision/")
    assert "production" not in opened[0]
    await hub.close()
    with pytest.raises(ValueError, match="shutting down"):
        async with hub.subscribe(selection, "BTCUSDT", "BTC/USDT", "1d"):
            pass


def test_public_book_preserves_coinbase_market_discovery(monkeypatch):
    def make_client(config):
        assert "fetchMarkets" not in config["options"]
        assert not {"apiKey", "secret", "password"} & config.keys()
        return SimpleNamespace()

    monkeypatch.setattr("sibyl.market_data.streaming.orderbook.pro.coinbase", make_client)
    PublicOrderBook({"provider": "coinbase", "environment": "production"})


@pytest.mark.asyncio
async def test_order_books_share_one_public_client_and_close_with_last_viewer(monkeypatch):
    hub, opened, closed = LiveMarkets(None), [], []
    wait_for_next = asyncio.Event()
    selection = {
        "source": "connection:spot-test",
        "source_label": "Testnet",
        "provider": "binance-testnet",
        "environment": "test",
    }

    class BookClient:
        def __init__(self, identity):
            opened.append(identity)
            self.sent = False

        async def validate_market(self, symbol):
            assert symbol == "ETH/USDT"

        async def receive(self, symbol):
            if self.sent:
                await wait_for_next.wait()
            self.sent = True
            return {"type": "book", "symbol": symbol, "bids": [[100, 2]], "asks": [[101, 3]]}

        async def close(self):
            closed.append(True)

    monkeypatch.setattr("sibyl.market_data.streams.PublicOrderBook", BookClient)
    async with hub.subscribe(selection, "ETH/USDT", "ETH/USDT", None) as (first, queue):
        async with hub.subscribe(selection, "ETH/USDT", "ETH/USDT", None) as (second, other):
            assert first is second
            assert (await asyncio.wait_for(queue.get(), 2))["type"] == "status"
            book = await asyncio.wait_for(queue.get(), 2)
            assert (await asyncio.wait_for(other.get(), 2))["type"] == "status"
            assert book == await asyncio.wait_for(other.get(), 2)
            assert book["source"] == "connection:spot-test" and book["environment"] == "test"
            assert opened == [selection]
        assert not closed
    assert closed == [True] and not hub.channels


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes", [{"symbol": "BTC/USD"}, {"bids": [[float("nan"), 1]]}, {"asks": [[90, 1]]}]
)
async def test_stream_refuses_mismatched_crossed_and_nonfinite_depth(changes):
    async def watch(symbol, depth):
        return {"symbol": symbol, "bids": [[100, 2]], "asks": [[101, 3]], **changes}

    public = object.__new__(PublicOrderBook)
    public.native = SimpleNamespace(watch_order_book=watch)
    with pytest.raises(ValueError):
        await public.receive("BTC/USDT")


def test_orderbook_live_requires_explicit_supported_source(client):
    path = "/api/v1/markets/orderbook/live?symbol=BTC%2FUSDT"
    assert client.get(path).status_code == 422
    assert client.get(path + "&source=demo").status_code == 400
    book = client.get("/api/v1/markets/orderbook?source=demo").json()
    assert book["source"] == "demo" and not book["stream_available"]


@pytest.mark.asyncio
async def test_socket_failure_is_observable_and_shutdown_cancels_backoff():
    hub = LiveMarkets(None)

    @asynccontextmanager
    async def unavailable(url):
        raise RuntimeError("SECRET-NATIVE-URL")
        yield

    hub.connect = unavailable
    selection = {
        "source": "binance",
        "source_label": "Binance",
        "provider": "binance",
        "environment": "production",
    }
    async with hub.subscribe(selection, "BTCUSDT", "BTC/USDT", "1d"):
        await asyncio.sleep(0.01)
        evidence = hub.snapshot()
        assert evidence["items"][0]["state"] == "reconnecting"
        assert evidence["items"][0]["reconnects"] == 1
        assert "SECRET" not in json.dumps(evidence)
    assert not hub.channels


def test_stream_api_preserves_workspace_auth_and_demo_uses_rest(client):
    response = client.get("/api/v1/markets/live?symbol=BTC/USDT&source=demo")
    assert response.status_code == 400 and "REST" in response.json()["detail"]
    assert client.get("/api/v1/markets/live/status").json()["items"] == []
    client.app.state.services.settings.api_token = SecretStr("PRIVATE-TOKEN")
    # The HTTP middleware's original config is the same Settings object.
    assert client.get("/api/v1/markets/live/status").status_code == 401


def test_stream_capacity_rejection_happens_before_response_headers(client, monkeypatch):
    owner = client.app.state.services.market.live
    identity = {
        "source": "binance",
        "source_label": "Binance",
        "provider": "binance",
        "environment": "production",
    }
    monkeypatch.setattr(owner, "selection", lambda *args: (identity, "BTCUSDT"))
    owner.channels = {index: Channel(identity, "OTHER", "ETH/USDT", "1d") for index in range(16)}
    response = client.get("/api/v1/markets/live?symbol=BTC/USDT&source=binance")
    assert response.status_code == 400
    assert "capacity" in response.json()["detail"]
