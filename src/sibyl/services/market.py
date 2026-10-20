"""Cached market and account reads through the shared exchange-client interface."""

import hashlib
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from functools import wraps
from typing import Any

import ccxt
import numpy as np

from sibyl.config import Settings
from sibyl.exchanges import ExchangeClient, create_client
from sibyl.exchanges.data import ASSETS, STABLES, TIMEFRAMES
from sibyl.models import Candle, Connection
from sibyl.services.crypto_library import ASSETS as RESEARCH_ASSETS
from sibyl.services.data_settings import DataSettings
from sibyl.storage import Store


def reference_read(method):
    """Keep one source configuration across nested reads and cache/source labels."""

    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self.snapshot():
            return method(self, *args, **kwargs)

    return wrapped


class Market:
    """Normalize supported exchanges and label every result with its provenance.

    CCXT clients have rate limiting and finite timeouts. Each public read uses
    one frozen feed; private balances use each account connection independently.
    Live failures propagate, never silently substituting demo fixtures.
    """

    def __init__(self, settings: Settings, store: Store, data_settings: DataSettings | None = None):
        self.settings, self.store = settings, store
        self.data_settings = data_settings
        self._cache: dict[str, tuple[float, Any]] = {}
        self._lock = threading.RLock()
        self._clients: dict[str, ExchangeClient] = {}
        self._local = threading.local()

    @contextmanager
    def snapshot(self, source: str | None = None):
        """Freeze a default or page-selected source until this complete read ends.

        Saving preferences never mutates an in-flight read. Account/trading mode
        remains independent. Nested calls reuse this snapshot and its cache key.
        """
        with self._lock:
            current = getattr(self._local, "profile", None)
            if current is not None:
                if source and source != current["id"]:
                    raise ValueError("A market read cannot combine different sources.")
                yield self
                return
            if self.data_settings:
                profile = self.data_settings.resolve_market(source)
            else:
                identity = "demo" if self.settings.mode == "demo" else self.settings.market_exchange
                profile = {
                    "id": identity,
                    "name": identity,
                    "kind": "demo" if identity == "demo" else "exchange",
                    "provider": identity,
                    "environment": "demo" if identity == "demo" else "production",
                    "api_key": "",
                    "candles": True,
                    "order_book": True,
                }
                if source and source != identity:
                    raise ValueError("This market source is unavailable.")
            token = hashlib.sha256(
                f"{profile['id']}:{profile['environment']}:{profile['api_key']}".encode()
            ).hexdigest()
            self._local.profile, self._local.token = profile, token
            try:
                yield self
            finally:
                del self._local.profile
                del self._local.token

    @reference_read
    def metadata(self) -> dict:
        """Return attribution and capabilities from the frozen configuration, never secrets."""
        profile = self._local.profile
        return {
            "source": profile["id"],
            "source_label": profile["name"],
            "source_kind": profile["kind"],
            "environment": profile["environment"],
            "capabilities": {"candles": profile["candles"], "order_book": profile["order_book"]},
        }

    @property
    def source(self) -> str:
        """Identify whether prices are fixture data or provider quotes."""
        with self.snapshot():
            return self._local.profile["id"]

    def client(self, connection: Connection | None = None) -> ExchangeClient:
        """Reuse a typed client; public demo data never replaces a private account."""
        if connection is None:
            with self.snapshot():
                profile = self._local.profile
                if profile["kind"] == "connection":
                    selected = next(
                        (row for row in self.store.connections() if f"connection:{row.id}" == profile["id"]),
                        None,
                    )
                    if selected is None:
                        raise ValueError("Selected market account was disconnected. Choose another source.")
                    return self.client(selected)
                key = f"reference:{profile['id']}:{self._local.token}"
                if key not in self._clients:
                    for old in list(self._clients):
                        if old.startswith(f"reference:{profile['id']}:"):
                            self._clients.pop(old).close()
                    if profile["kind"] == "api":
                        from sibyl.market_data.clients import CoinGeckoClient, CryptoCompareClient

                        self._clients[key] = (
                            CryptoCompareClient(profile["api_key"])
                            if profile["id"] == "cryptocompare"
                            else CoinGeckoClient(profile["api_key"], pro=profile["id"] == "coingecko-pro")
                        )
                    else:
                        self._clients[key] = create_client(profile["provider"], store=self.store)
                return self._clients[key]
        exchange, key = connection.exchange, connection.id
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

    def forget_source(self, source: str) -> None:
        """Release an API client's decrypted credential after replacement or removal."""
        with self._lock:
            for key in list(self._clients):
                if key.startswith(f"reference:{source}:"):
                    self._clients.pop(key).close()
            self._cache = {key: value for key, value in self._cache.items() if key.startswith("account:")}

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

    @reference_read
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
            if not key.startswith("account:"):
                key = f"{self._local.token}:{key}"
            cached = self._cache.get(key)
            if cached and time.monotonic() - cached[0] < ttl:
                return cached[1]
            result = loader()
            self._cache[key] = (time.monotonic(), result)
            return result

    @reference_read
    def candles(self, symbol: str = "BTC/USDT", limit: int = 180, timeframe: str = "1d") -> list[dict]:
        """Return closed OHLCV bars; the current, unfinished bar is always excluded."""
        if timeframe not in TIMEFRAMES:
            raise ValueError("Unsupported candle timeframe.")
        if not self._local.profile["candles"]:
            raise ValueError(
                "This source supplies quotes only. Choose an exchange or CryptoCompare for candles and indicators."
            )
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
            if self.source != "demo" and len(candles) < min(30, limit):
                raise ValueError("The exchange returned fewer than 30 closed candles.")
            return candles[-limit:]

        return self._cached(f"candles:{symbol}:{limit}:{timeframe}", load, 60)

    @reference_read
    def price(self, symbol: str) -> float:
        """Fetch a current reference price, rejecting missing or nonpositive quotes."""
        with self._lock:
            ticker = self.client().fetch_ticker(self.provider_symbol(symbol))
        price = ticker.get("last") or ticker.get("close")
        if not price or not np.isfinite(price) or price <= 0:
            raise ValueError("No valid market price is available.")
        stamp = ticker.get("timestamp")
        if self.source != "demo" and stamp and datetime.now(UTC).timestamp() * 1000 - stamp > 300_000:
            raise ValueError("This reference price is stale. Wait for fresh provider data.")
        return float(price)

    @reference_read
    def overview(self) -> dict:
        """Fetch the watchlist with 24-hour moves and mini-chart data."""

        def load():
            items, warnings = [], []
            for asset, (name, _, color) in ASSETS.items():
                if asset in STABLES:
                    continue
                symbol = f"{asset}/USDT"
                try:
                    symbol = self.provider_symbol(symbol)
                    ticker = self.client().fetch_ticker(symbol)
                except (ccxt.BaseError, ValueError):
                    warnings.append(f"{asset} is unavailable from the selected source.")
                    continue
                last = ticker.get("last") or ticker.get("close")
                if not last or not np.isfinite(last) or last <= 0:
                    warnings.append(f"{asset} has no valid reference price.")
                    continue
                history = []
                if self._local.profile["candles"]:
                    try:
                        history = self.candles(symbol, 30)
                    except (ccxt.BaseError, ValueError):
                        warnings.append(
                            f"{asset} mini-chart history is unavailable; its quote is still shown."
                        )
                change = ticker.get("percentage")
                if change is None and self.source == "demo" and len(history) >= 2:
                    change = (history[-1]["close"] / history[-2]["close"] - 1) * 100
                stamp = ticker.get("timestamp")
                stale = (
                    self.source != "demo"
                    and stamp is not None
                    and datetime.now(UTC).timestamp() * 1000 - stamp > 300_000
                )
                items.append(
                    {
                        "symbol": symbol,
                        "asset": asset,
                        "name": name,
                        "color": color,
                        "price": float(last),
                        "quote": symbol.split("/")[1],
                        "change": float(change) if change is not None and np.isfinite(change) else None,
                        "volume": ticker.get("quoteVolume"),
                        "status": "stale" if stale else "fresh" if stamp is not None else "undated",
                        "observed_at": datetime.fromtimestamp(stamp / 1000, UTC).isoformat()
                        if stamp
                        else None,
                        "sparkline": [c["close"] for c in history],
                    }
                )
            if not items:
                raise ccxt.ExchangeNotAvailable("No watchlist quotes are available.")
            return {
                "items": items,
                "warnings": warnings,
                **self.metadata(),
                "as_of": datetime.now(UTC).isoformat(),
            }

        return self._cached("overview", load)

    @reference_read
    def quotes(self, symbols: list[str]) -> dict:
        """Price exact watchlist pairs without changing the portfolio's reference universe.

        Each quote has its own source/credential-scoped cache. Unavailable pairs
        remain explicit rows, so a temporary error cannot erase a user's choice.
        """
        metadata = self.metadata()
        items, warnings = [], []
        catalog = {row["symbol"]: row for row in self.symbols()["items"]} if symbols else {}
        for symbol in symbols:
            asset, quote = symbol.split("/")
            entry = catalog.get(symbol, {})
            known = next((row for row in RESEARCH_ASSETS.values() if row.symbol == asset), None)
            identity = {
                "symbol": symbol,
                "asset": asset,
                "quote": quote,
                "name": entry.get("name") or (known.name if known else asset),
                "color": entry.get("color") or (known.color if known else "#7994b3"),
            }
            try:
                if symbol not in catalog:
                    raise ccxt.BadSymbol("This exact market is no longer available.")

                def load(symbol=symbol):
                    ticker = self.client().fetch_ticker(symbol)
                    last = ticker.get("last") or ticker.get("close")
                    if not last or not np.isfinite(last) or last <= 0:
                        raise ValueError("No valid quote is available.")
                    history, notes = [], []
                    if metadata["capabilities"]["candles"]:
                        try:
                            history = self.candles(symbol, 30)
                        except (ccxt.BaseError, ValueError):
                            notes.append(
                                f"{symbol} mini-chart history is unavailable; its quote is still shown."
                            )
                    change = ticker.get("percentage")
                    if change is None and self.source == "demo" and len(history) >= 2:
                        change = (history[-1]["close"] / history[-2]["close"] - 1) * 100
                    stamp = ticker.get("timestamp")
                    stale = (
                        self.source != "demo"
                        and stamp is not None
                        and datetime.now(UTC).timestamp() * 1000 - stamp > 300_000
                    )
                    volume = ticker.get("quoteVolume")
                    return {
                        "price": float(last),
                        "change": float(change) if change is not None and np.isfinite(change) else None,
                        "volume": float(volume)
                        if volume is not None and np.isfinite(volume) and volume >= 0
                        else None,
                        "status": "stale" if stale else "fresh" if stamp is not None else "undated",
                        "observed_at": datetime.fromtimestamp(stamp / 1000, UTC).isoformat()
                        if stamp
                        else None,
                        "sparkline": [row["close"] for row in history],
                        "notes": notes,
                    }

                result = self._cached(f"watch-quote:{symbol}", load)
                warnings.extend(result["notes"])
                items.append({**identity, **{key: value for key, value in result.items() if key != "notes"}})
            except (ccxt.BaseError, ValueError):
                items.append(
                    {
                        **identity,
                        "price": None,
                        "change": None,
                        "volume": None,
                        "observed_at": None,
                        "sparkline": [],
                        "status": "unavailable",
                        "error": "Market or quote unavailable from this feed.",
                    }
                )
        return {**metadata, "items": items, "warnings": warnings, "as_of": datetime.now(UTC).isoformat()}

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

    @reference_read
    def symbols(self) -> dict:
        """List active spot markets and provider-supported timeframes without private access."""

        def load():
            with self._lock:
                client = self.client()
                markets = client.load_markets()
                known = {asset.symbol: asset for asset in RESEARCH_ASSETS.values()}
                return {
                    "items": sorted(
                        [
                            {
                                "symbol": symbol,
                                "base": market["base"],
                                "quote": market["quote"],
                                "name": (
                                    market.get("name")
                                    if market.get("name") and market["name"] != market["base"]
                                    else known[market["base"]].name
                                    if market["base"] in known
                                    else market["base"]
                                ),
                                "color": known[market["base"]].color if market["base"] in known else None,
                            }
                            for symbol, market in markets.items()
                        ],
                        key=lambda item: item["symbol"],
                    ),
                    "timeframes": [frame for frame in TIMEFRAMES if frame in client.timeframes],
                    "candle_limits": {
                        frame: 2000 // aggregate - 1
                        for frame, (_endpoint, aggregate) in getattr(client, "intervals", {}).items()
                    },
                }

        return {**self.metadata(), **self._cached("symbols", load, 600)}

    @reference_read
    def orderbook(self, symbol: str, depth: int = 10) -> dict:
        """Read a bounded public order book; demo levels are explicitly synthetic."""

        if not self._local.profile["order_book"]:
            raise ValueError("This source has no exchange order book. Choose an exchange source.")

        def load():
            with self._lock:
                return self.client().fetch_order_book(self.provider_symbol(symbol), limit=depth)

        book = self._cached(f"book:{symbol}:{depth}", load, 5)
        bids, asks = book["bids"][:depth], book["asks"][:depth]
        spread = float(asks[0][0] - bids[0][0]) if bids and asks else None
        return {
            "symbol": symbol,
            **self.metadata(),
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
