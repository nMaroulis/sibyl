"""Cached market and account reads through the shared exchange-client interface."""

import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import ccxt
import numpy as np

from sibyl.config import Settings
from sibyl.exchanges import ExchangeClient, create_client
from sibyl.exchanges.data import ASSETS, STABLES, TIMEFRAMES
from sibyl.models import Candle, Connection
from sibyl.storage import Store


class Market:
    """Normalize supported exchanges and label every result with its provenance.

    CCXT clients have rate limiting and finite timeouts. Public market data uses
    one configured exchange; private balances use each connection independently.
    Live failures propagate, never silently substituting demo fixtures.
    """

    def __init__(self, settings: Settings, store: Store):
        self.settings, self.store = settings, store
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = threading.RLock()
        self._clients: dict[str, ExchangeClient] = {}

    @property
    def source(self) -> str:
        """Identify whether prices are fixture data or provider quotes."""
        return "demo" if self.settings.mode == "demo" else self.settings.market_exchange

    def client(self, connection: Connection | None = None) -> ExchangeClient:
        """Reuse a typed client; public demo data never replaces a private account."""
        exchange = connection.exchange if connection else self.source
        key = connection.id if connection else exchange
        with self._lock:
            if key not in self._clients:
                self._clients[key] = create_client(
                    exchange,
                    credentials=self.store.credentials(connection.id)
                    if connection and exchange != "demo"
                    else None,
                    sandbox=connection.sandbox if connection else False,
                    store=self.store,
                )
            return self._clients[key]

    def close(self) -> None:
        """Release all reusable provider sessions during application shutdown."""
        with self._lock:
            for client in self._clients.values():
                client.close()
            self._clients.clear()
            self._cache.clear()

    def forget(self, connection_id: str) -> None:
        """Drop any decrypted adapter credentials after disconnecting an account."""
        with self._lock:
            client = self._clients.pop(connection_id, None)
            if client is not None:
                client.close()
            self._cache.pop(f"account:{connection_id}", None)

    @contextmanager
    def adapter(self, connection: Connection):
        """Serialize a sequence of private provider operations on a reusable client."""
        with self._lock:
            yield self.client(connection)

    def provider_symbol(self, symbol: str) -> str:
        """Resolve a reference quote, approximating USD/USDC at parity with USDT.

        This normalization applies only to read-only public market data. Actual
        exchange orders always use the precise symbol entered in the order form.
        """
        with self._lock:
            client = self.client()
            markets = client.load_markets()
            if symbol in markets:
                return symbol
            base, quote = symbol.split("/")
            if quote in STABLES:
                for alternative in ("USD", "USDC", "USDT"):
                    candidate = f"{base}/{alternative}"
                    if candidate in markets:
                        return candidate
        raise ccxt.BadSymbol("No supported spot reference quote for this asset.")

    def _cached(self, key: str, loader, ttl: int = 30):
        with self._lock:
            cached = self._cache.get(key)
            if cached and time.monotonic() - cached[0] < ttl:
                return cached[1]
            result = loader()
            self._cache[key] = (time.monotonic(), result)
            return result

    def candles(self, symbol: str = "BTC/USDT", limit: int = 180, timeframe: str = "1d") -> list[dict]:
        """Return closed OHLCV bars; the current, unfinished bar is always excluded."""
        if timeframe not in TIMEFRAMES:
            raise ValueError("Unsupported candle timeframe.")
        seconds = TIMEFRAMES[timeframe]

        def load():
            with self._lock:
                rows = self.client().fetch_ohlcv(self.provider_symbol(symbol), timeframe, limit=limit + 1)
            now = datetime.now(UTC).timestamp() * 1000
            candles = [
                Candle(
                    timestamp=datetime.fromtimestamp(row[0] / 1000, UTC).isoformat(),
                    open=row[1],
                    high=row[2],
                    low=row[3],
                    close=row[4],
                    volume=row[5],
                ).model_dump()
                for row in rows
                if row[0] + seconds * 1000 <= now
            ]
            if self.settings.mode == "live" and len(candles) < min(30, limit):
                raise ValueError("The exchange returned fewer than 30 closed candles.")
            return candles[-limit:]

        return self._cached(f"candles:{symbol}:{limit}:{timeframe}", load, 60)

    def price(self, symbol: str) -> float:
        """Fetch a current reference price, rejecting missing or nonpositive quotes."""
        with self._lock:
            ticker = self.client().fetch_ticker(self.provider_symbol(symbol))
        price = ticker.get("last") or ticker.get("close")
        if not price or not np.isfinite(price) or price <= 0:
            raise ValueError("No valid market price is available.")
        return float(price)

    def overview(self) -> dict:
        """Fetch the watchlist with 24-hour moves and mini-chart data."""

        def load():
            items, warnings = [], []
            for asset, (name, _, color) in ASSETS.items():
                if asset in STABLES:
                    continue
                symbol = f"{asset}/USDT"
                try:
                    history = self.candles(symbol, 30)
                except ccxt.BadSymbol:
                    warnings.append(f"{asset} has no supported reference quote on this exchange.")
                    continue
                last, previous = history[-1]["close"], history[-2]["close"]
                volume = history[-1]["volume"] * last
                if self.settings.mode == "live":
                    with self._lock:
                        ticker = self.client().fetch_ticker(self.provider_symbol(symbol))
                    last = ticker.get("last") or last
                    change = ticker.get("percentage")
                    volume = ticker.get("quoteVolume") or volume
                else:
                    change = None
                items.append(
                    {
                        "symbol": symbol,
                        "asset": asset,
                        "name": name,
                        "color": color,
                        "price": float(last),
                        "change": float(change if change is not None else (last / previous - 1) * 100),
                        "volume": float(volume),
                        "sparkline": [c["close"] for c in history],
                    }
                )
            if not items:
                raise ccxt.ExchangeNotAvailable("No watchlist quotes are available.")
            return {
                "items": items,
                "warnings": warnings,
                "source": self.source,
                "as_of": datetime.now(UTC).isoformat(),
            }

        return self._cached("overview", load)

    def balance(self, connection: Connection) -> dict[str, float]:
        """Read an account's total spot balances. This method never sends orders."""
        with self._lock:
            result = self.client(connection).fetch_balance()
        return {
            asset: float(quantity)
            for asset, quantity in result.get("total", {}).items()
            if quantity and np.isfinite(float(quantity)) and float(quantity) > 0
        }

    def check_connection(self, connection: Connection) -> dict:
        """Validate credentials with a balance read; redact all provider error text."""
        try:
            balances = self.balance(connection)
            return {
                "status": "connected",
                "assets": len(balances),
                "checked_at": datetime.now(UTC).isoformat(),
            }
        except ccxt.AuthenticationError:
            return {"status": "error", "message": "Exchange rejected the credentials or account permissions."}
        except (ccxt.BaseError, ValueError):
            return {"status": "error", "message": "Exchange could not be reached or sandbox is unsupported."}

    def symbols(self) -> dict:
        """List active spot markets and provider-supported timeframes without private access."""

        def load():
            with self._lock:
                client = self.client()
                markets = client.load_markets()
                return {
                    "items": sorted(
                        [
                            {"symbol": symbol, "base": market["base"], "quote": market["quote"]}
                            for symbol, market in markets.items()
                        ],
                        key=lambda item: item["symbol"],
                    ),
                    "timeframes": [frame for frame in TIMEFRAMES if frame in client.timeframes],
                }

        return {"source": self.source, **self._cached("symbols", load, 600)}

    def orderbook(self, symbol: str, depth: int = 10) -> dict:
        """Read a bounded public order book; demo levels are explicitly synthetic."""

        def load():
            with self._lock:
                return self.client().fetch_order_book(self.provider_symbol(symbol), limit=depth)

        book = self._cached(f"book:{symbol}:{depth}", load, 5)
        bids, asks = book["bids"][:depth], book["asks"][:depth]
        spread = float(asks[0][0] - bids[0][0]) if bids and asks else None
        return {
            "symbol": symbol,
            "source": self.source,
            "bids": bids,
            "asks": asks,
            "spread": spread,
            "as_of": datetime.now(UTC).isoformat(),
        }

    def account_balances(self, connection: Connection) -> list[dict]:
        """Expose normalized free, reserved, and total quantities without provider metadata or keys."""

        def load():
            with self.adapter(connection) as client:
                balance = client.fetch_balance()

            def normalized(value):
                return float(value) if value is not None and np.isfinite(float(value)) else None

            rows = []
            for asset, total in balance.get("total", {}).items():
                if total and np.isfinite(float(total)) and float(total) > 0:
                    rows.append(
                        {
                            "asset": asset,
                            "total": float(total),
                            "free": normalized(balance.get("free", {}).get(asset)),
                            "used": normalized(balance.get("used", {}).get(asset)),
                        }
                    )
            return rows

        return load() if connection.exchange == "demo" else self._cached(f"account:{connection.id}", load, 30)
