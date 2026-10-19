"""Deterministic demo data and a single read-only CCXT exchange boundary."""

import hashlib
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import ccxt
import numpy as np

from sibyl.config import Settings
from sibyl.models import Candle, Connection
from sibyl.storage import Store

ASSETS = {
    "BTC": ("Bitcoin", 67_432.80, "#f6a94d"),
    "ETH": ("Ethereum", 3_521.64, "#99a7ff"),
    "SOL": ("Solana", 172.38, "#ad8cf9"),
    "LINK": ("Chainlink", 17.42, "#7eabfa"),
    "AVAX": ("Avalanche", 36.84, "#ee8e8e"),
    "DOT": ("Polkadot", 7.18, "#e68ab9"),
    "USDT": ("Tether", 1.0, "#71bea5"),
}
STABLES = {"USDT", "USDC", "USD", "DAI"}

TIMEFRAMES = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "12h": 43200,
    "1d": 86400,
    "1w": 604800,
}


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
        self._clients: dict[str, Any] = {}

    @property
    def source(self) -> str:
        """Identify whether prices are fixture data or provider quotes."""
        return "demo" if self.settings.mode == "demo" else self.settings.market_exchange

    def client(self, connection: Connection | None = None):
        """Reuse a rate-limited adapter and set sandbox mode before its first request."""
        exchange = connection.exchange if connection else self.settings.market_exchange
        key = connection.id if connection else exchange
        with self._lock:
            if key not in self._clients:
                options = {"enableRateLimit": True, "timeout": 12_000}
                if connection:
                    options.update(self.store.credentials(connection.id))
                client = getattr(ccxt, exchange)(options)
                if connection and connection.sandbox:
                    client.set_sandbox_mode(True)
                self._clients[key] = client
            return self._clients[key]

    def forget(self, connection_id: str) -> None:
        """Drop any decrypted adapter credentials after disconnecting an account."""
        with self._lock:
            self._clients.pop(connection_id, None)
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
        if self.settings.mode == "demo":
            base, quote = symbol.split("/")
            if quote in ASSETS and quote not in STABLES and base != quote and base in ASSETS:
                bases = self.candles(f"{base}/USDT", limit, timeframe)
                quotes = self.candles(f"{quote}/USDT", limit, timeframe)
                return [
                    {
                        **bar,
                        "open": bar["open"] / other["open"],
                        "high": bar["high"] / other["low"],
                        "low": bar["low"] / other["high"],
                        "close": bar["close"] / other["close"],
                    }
                    for bar, other in zip(bases, quotes, strict=True)
                ]
            if base not in ASSETS or quote not in STABLES or base in STABLES:
                raise ValueError(
                    "Demo markets support BTC, ETH, SOL, LINK, AVAX, or DOT against USD stablecoins, BTC, or ETH."
                )
            seed = int(
                hashlib.sha256((base if timeframe == "1d" else base + timeframe).encode()).hexdigest()[:8], 16
            )
            rng = np.random.default_rng(seed)
            returns = rng.normal(0.0013 * seconds / 86400, 0.022 * np.sqrt(seconds / 86400), 730)
            prices = np.exp(np.cumsum(returns))
            prices *= ASSETS[base][1] / prices[-1]
            closed_at = int(datetime.now(UTC).timestamp()) // seconds * seconds
            start = datetime.fromtimestamp(closed_at, UTC) - timedelta(seconds=730 * seconds)
            result = []
            for i, close in enumerate(prices):
                opening = float(prices[i - 1]) if i else float(close * 0.996)
                spread = float(rng.uniform(0.003, 0.025))
                result.append(
                    Candle(
                        timestamp=(start + timedelta(seconds=i * seconds)).isoformat(),
                        open=opening,
                        high=max(opening, close) * (1 + spread),
                        low=min(opening, close) * (1 - spread),
                        close=float(close),
                        volume=float(rng.uniform(1000, 12000)),
                    ).model_dump()
                )
            return result[-limit:]

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
            if len(candles) < 30:
                raise ValueError("The exchange returned fewer than 30 closed candles.")
            return candles[-limit:]

        return self._cached(f"candles:{symbol}:{limit}:{timeframe}", load, 60)

    def price(self, symbol: str) -> float:
        """Fetch a current reference price, rejecting missing or nonpositive quotes."""
        if self.settings.mode == "demo":
            return self.candles(symbol, 1)[0]["close"]
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
            if quantity and float(quantity) > 0
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
        if self.settings.mode == "demo":
            items = [
                {"symbol": f"{base}/{quote}", "base": base, "quote": quote}
                for base in ASSETS
                if base not in STABLES
                for quote in ("USDT", "USDC", "USD", "BTC", "ETH")
                if base != quote
            ]
            frames = list(TIMEFRAMES)
        else:

            def load():
                with self._lock:
                    client = self.client()
                    markets = client.load_markets()
                    return {
                        "items": sorted(
                            [
                                {"symbol": symbol, "base": market["base"], "quote": market["quote"]}
                                for symbol, market in markets.items()
                                if market.get("spot")
                                and market.get("active") is not False
                                and market.get("base", "").isalnum()
                                and market.get("quote", "").isalnum()
                            ],
                            key=lambda item: item["symbol"],
                        ),
                        "timeframes": [frame for frame in TIMEFRAMES if frame in (client.timeframes or {})],
                    }

            return {"source": self.source, **self._cached("symbols", load, 600)}
        return {"source": self.source, "items": items, "timeframes": frames}

    def orderbook(self, symbol: str, depth: int = 10) -> dict:
        """Read a bounded public order book; demo levels are explicitly synthetic."""
        if self.settings.mode == "demo":
            price = self.price(symbol)
            book = {
                "bids": [[price * (1 - 0.0005 * (i + 1)), 0.2 + i * 0.13] for i in range(depth)],
                "asks": [[price * (1 + 0.0005 * (i + 1)), 0.3 + i * 0.11] for i in range(depth)],
            }
        else:

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

        return self._cached(f"account:{connection.id}", load, 30)
