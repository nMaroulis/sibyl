"""Offline exchange with deterministic prices and the workspace's persistent paper ledger."""

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING

import ccxt
import numpy as np

from sibyl.exchanges.base import ExchangeClient, number
from sibyl.exchanges.data import ASSETS, STABLES, TIMEFRAMES
from sibyl.models import Candle, OrderRequest

if TYPE_CHECKING:
    from sibyl.storage import Store


class DemoClient(ExchangeClient):
    """Exercise the real client contract without network access or API credentials.

    Market fills use Store.execute_paper, sharing its atomic idempotency and fee
    accounting. Without a Store, market-data reads work but account operations
    require a workspace. Open limit orders, latency and partial fills are not simulated.
    """

    id = "demo"
    timeframes = TIMEFRAMES

    def __init__(self, store: "Store | None" = None):
        super().__init__()
        self.store = store

    def load_markets(self) -> dict:
        """Expose six fixture assets against stable quotes, BTC and ETH."""
        return {
            f"{base}/{quote}": {
                "symbol": f"{base}/{quote}",
                "base": base,
                "quote": quote,
                "spot": True,
                "active": True,
                "precision": {"amount": 0.00000001},
                "limits": {
                    "amount": {"min": 0.00000001, "max": 1_000_000},
                    "cost": {"min": None, "max": None},
                },
            }
            for base in ASSETS
            if base not in STABLES
            for quote in ("USDT", "USDC", "USD", "BTC", "ETH")
            if base != quote
        }

    def _candles(self, symbol: str, limit: int, timeframe: str) -> list[dict]:
        seconds = TIMEFRAMES[timeframe]
        base, quote = symbol.split("/")
        if quote in ASSETS and quote not in STABLES and base != quote and base in ASSETS:
            bases = self._candles(f"{base}/USDT", limit, timeframe)
            quotes = self._candles(f"{quote}/USDT", limit, timeframe)
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

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1d", limit: int = 180) -> list[list]:
        """Return deterministic closed bars using the original dashboard's fixture sequence."""
        self.market(symbol)
        if timeframe not in TIMEFRAMES or not 1 <= limit <= 730:
            raise ValueError("Choose a supported demo timeframe and 1–730 candles.")
        return [
            [
                datetime.fromisoformat(row["timestamp"]).timestamp() * 1000,
                *[row[field] for field in ("open", "high", "low", "close", "volume")],
            ]
            for row in self._candles(symbol, limit, timeframe)
        ]

    def fetch_ticker(self, symbol: str) -> dict:
        """Read a synthetic quote and movement over the last two daily fixture closes."""
        rows = self.fetch_ohlcv(symbol, limit=2)
        last, previous = rows[-1][4], rows[-2][4]
        return {
            "symbol": symbol,
            "timestamp": rows[-1][0],
            "last": last,
            "close": last,
            "bid": last * 0.9995,
            "ask": last * 1.0005,
            "percentage": (last / previous - 1) * 100,
            "baseVolume": rows[-1][5],
            "quoteVolume": rows[-1][5] * last,
        }

    def fetch_order_book(self, symbol: str, limit: int = 10) -> dict:
        """Generate a synthetic two-sided book, never an executable liquidity claim."""
        if not 1 <= limit <= 100:
            raise ValueError("Order book depth must be between 1 and 100.")
        price = self.fetch_ticker(symbol)["last"]
        return {
            "symbol": symbol,
            "timestamp": datetime.now(UTC).timestamp() * 1000,
            "bids": [[price * (1 - 0.0005 * (i + 1)), 0.2 + i * 0.13] for i in range(limit)],
            "asks": [[price * (1 + 0.0005 * (i + 1)), 0.3 + i * 0.11] for i in range(limit)],
        }

    def _workspace(self) -> "Store":
        if self.store is None:
            raise ValueError("A workspace Store is required for demo account operations.")
        return self.store

    def fetch_balance(self) -> dict:
        """Read the paper wallet; it can never read a saved exchange account."""
        balances = self._workspace().balances()
        return {"total": dict(balances), "free": dict(balances), "used": dict.fromkeys(balances, 0.0)}

    def amount_to_precision(self, symbol: str, amount: float) -> str:
        """Truncate fixture base quantities to eight decimal places."""
        self.market(symbol)
        if number(amount) is None or amount <= 0:
            raise ValueError("Quantity must be positive and finite.")
        return str(Decimal(str(amount)).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN))

    @staticmethod
    def _order(row: dict) -> dict:
        return {
            "id": row["id"],
            "symbol": row["symbol"],
            "side": row["side"],
            "type": "market",
            "status": "closed",
            "amount": row["quantity"],
            "filled": row["quantity"],
            "remaining": 0.0,
            "price": row["price"],
            "average": row["price"],
            "cost": row["notional"],
            "mode": "paper",
            "timestamp": datetime.fromisoformat(row["created_at"]).timestamp() * 1000,
        }

    def create_order(
        self, symbol: str, type: str, side: str, amount: float, params: dict | None = None
    ) -> dict:
        """Persist one immediate paper fill, idempotently keyed by clientOrderId."""
        self.market(symbol)
        params = params or {}
        if type != "market" or set(params) != {"clientOrderId"}:
            raise ValueError("Demo supports market orders with a clientOrderId only.")
        request = OrderRequest(
            symbol=symbol, side=side, quantity=amount, idempotency_key=params["clientOrderId"]
        )
        result = self._workspace().execute_paper(request, self.fetch_ticker(symbol)["last"])
        return {**self._order(result), "clientOrderId": params["clientOrderId"]}

    def fetch_order(self, order_id: str, symbol: str) -> dict:
        """Read a persisted simulated order by its ID, including after a restart."""
        self.market(symbol)
        with self._workspace().db() as db:
            row = db.execute("SELECT payload FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise ccxt.OrderNotFound("Paper order not found.")
        import json

        result = json.loads(row[0])
        if result["symbol"] != symbol:
            raise ccxt.OrderNotFound("Paper order not found for this market.")
        return self._order(result)

    def fetch_open_orders(self, symbol: str) -> list[dict]:
        """Demo market orders fill immediately, so there are no resting orders."""
        self.market(symbol)
        self._workspace()
        return []

    def fetch_my_trades(self, symbol: str, since: int | None = None, limit: int = 100) -> list[dict]:
        """Read a bounded page of persisted paper fills in chronological order."""
        self.market(symbol)
        if not 1 <= limit <= 500 or (since is not None and since < 0):
            raise ValueError("Use a limit of 1–500 and a nonnegative millisecond cursor.")
        import json

        with self._workspace().db() as db:
            rows = db.execute("SELECT payload FROM orders ORDER BY created_at, id").fetchall()
        result = []
        for row in rows:
            fill = json.loads(row[0])
            stamp = datetime.fromisoformat(fill["created_at"]).timestamp() * 1000
            if fill["symbol"] == symbol and (since is None or stamp >= since):
                result.append(
                    {
                        "id": fill["id"],
                        "order": fill["id"],
                        "symbol": symbol,
                        "side": fill["side"],
                        "timestamp": stamp,
                        "amount": fill["quantity"],
                        "price": fill["price"],
                        "cost": fill["notional"],
                        "fee": {"currency": symbol.split("/")[1], "cost": fill["fee"]},
                    }
                )
                if len(result) == limit:
                    break
        return result
