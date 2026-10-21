"""Offline exchange with deterministic prices and the workspace's persistent paper ledger."""

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING

import ccxt
import numpy as np

from sibyl.exchanges.base import ExchangeClient, number
from sibyl.exchanges.data import ASSETS, DEMO_ASSETS, STABLES, TIMEFRAMES
from sibyl.exchanges.funding import FundingPage, funding_streams
from sibyl.exchanges.history import TradePage
from sibyl.exchanges.paper_limits import PaperLimits, reserved
from sibyl.models import Candle, OrderRequest

if TYPE_CHECKING:
    from sibyl.storage import Store


class DemoClient(ExchangeClient):
    """Exercise the real client contract without network access or API credentials.

    Market fills use Store.execute_paper, sharing its atomic idempotency and fee
    accounting. Without a Store, market-data reads work but account operations
    require a workspace. Resting GTC limits reserve virtual funds; liquidity, latency
    and partial fills are not simulated.
    """

    id = "demo"
    history_kind = "demo-keyset"
    candle_history = True
    timeframes = TIMEFRAMES

    def __init__(self, store: "Store | None" = None):
        super().__init__()
        self.store = store

    def fetch_funding_page(self, stream: str, cursor: dict, limit: int = 50) -> FundingPage:
        """Return actual empty funding history; virtual seeds are never fabricated deposits."""
        if stream not in funding_streams("demo") or not 1 <= limit <= 50:
            raise ValueError("Choose a supported funding stream and page size.")
        return FundingPage([], cursor, True)

    def load_markets(self) -> dict:
        """Expose familiar pairs plus explicit bridge, fiat and stablecoin fixtures."""
        symbols = [
            f"{base}/{quote}"
            for base in ASSETS
            if base not in STABLES
            for quote in ("USDT", "USDC", "USD", "BTC", "ETH")
            if base != quote
        ] + ["ADA/BTC", "USDC/USDT", "DAI/USDT", "USDT/USD", "EUR/USD"]
        return {
            symbol: {
                "symbol": symbol,
                "base": base,
                "quote": quote,
                "name": DEMO_ASSETS[base][0],
                "spot": True,
                "active": True,
                "precision": {"amount": 0.00000001},
                "limits": {
                    "amount": {"min": 0.00000001, "max": 1_000_000},
                    "cost": {"min": None, "max": None},
                },
            }
            for symbol in symbols
            for base, quote in [symbol.split("/")]
        }

    def _candles(self, symbol: str, limit: int, timeframe: str) -> list[dict]:
        """Divide aligned native fixture series; quote currencies never imply parity."""
        base, quote = symbol.split("/")
        bases = self._usdt_candles(base, limit, timeframe)
        if quote == "USDT":
            return bases
        quotes = self._usdt_candles(quote, limit, timeframe)
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

    def _usdt_candles(self, base: str, limit: int, timeframe: str) -> list[dict]:
        """Generate one aligned, deterministic synthetic asset series in USDT."""
        seconds = TIMEFRAMES[timeframe]
        seed = int(
            hashlib.sha256((base if timeframe == "1d" else base + timeframe).encode()).hexdigest()[:8], 16
        )
        rng = np.random.default_rng(seed)
        volatility = 0.001 if base in STABLES or base == "EUR" else 0.022
        drift = 0 if base in STABLES or base == "EUR" else 0.0013
        returns = rng.normal(drift * seconds / 86400, volatility * np.sqrt(seconds / 86400), 730)
        prices = np.exp(np.cumsum(returns))
        prices *= DEMO_ASSETS[base][1] / prices[-1]
        if base == "USDT":
            prices[:] = 1.0
        from sibyl.market_data.archive import floor_time, now_ms

        closed_at = floor_time(now_ms(), timeframe) // 1000
        start = datetime.fromtimestamp(closed_at, UTC) - timedelta(seconds=730 * seconds)
        result = []
        for i, close in enumerate(prices):
            opening = float(prices[i - 1]) if i else float(close * 0.996)
            if base == "USDT":
                opening = 1.0
            spread = float(rng.uniform(0.003, 0.025))
            if base in STABLES or base == "EUR":
                spread = 0 if base == "USDT" else float(rng.uniform(0.0003, 0.002))
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

    def fetch_candle_page(self, symbol: str, timeframe: str, start: int, end: int) -> list[list]:
        """Page the same 730-bar deterministic series; absent older samples stay absent."""
        from sibyl.market_data.archive import step_ms

        if not 0 < end - start <= 200 * step_ms(timeframe):
            raise ValueError("Use a historical page of at most 200 intervals.")
        return [r for r in self.fetch_ohlcv(symbol, timeframe, 730) if start <= r[0] < end]

    def fetch_ticker(self, symbol: str) -> dict:
        """Generate a current synthetic snapshot from the last two fixture closes.

        The timestamp is the simulator's quote generation time, not the opening
        time of the historical candle used as its fixed sample price.
        """
        rows = self.fetch_ohlcv(symbol, limit=2)
        last, previous = rows[-1][4], rows[-2][4]
        return {
            "symbol": symbol,
            "timestamp": datetime.now(UTC).timestamp() * 1000,
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
        with self._workspace().db() as db:
            db.execute("BEGIN")
            balances = dict(db.execute("SELECT asset,quantity FROM balances"))
            holds = reserved(db)
        return {
            "total": dict(balances),
            "free": {asset: max(0.0, value - holds.get(asset, 0)) for asset, value in balances.items()},
            "used": {asset: holds.get(asset, 0.0) for asset in balances},
        }

    def price_to_precision(self, symbol: str, price: float) -> str:
        """Use eight quote decimal places for the virtual limit contract."""
        self.market(symbol)
        if number(price) is None or price <= 0:
            raise ValueError("Limit price must be positive and finite.")
        return str(Decimal(str(price)).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN))

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
        self,
        symbol: str,
        type: str,
        side: str,
        amount: float,
        params: dict | None = None,
        *,
        price: float | None = None,
    ) -> dict:
        """Persist an immediate market fill or resting GTC order, keyed by clientOrderId."""
        self.market(symbol)
        params = params or {}
        if type not in {"market", "limit"} or set(params) != {"clientOrderId"}:
            raise ValueError("Demo supports market/limit orders with a clientOrderId only.")
        request = OrderRequest(
            symbol=symbol, side=side, quantity=amount, idempotency_key=params["clientOrderId"]
        )
        if type == "limit":
            if number(price) is None or price <= 0:
                raise ValueError("A positive finite limit price is required.")
            return PaperLimits(self._workspace()).place(symbol, side, amount, price, params["clientOrderId"])
        if price is not None:
            raise ValueError("Market orders do not accept a limit price.")
        result = self._workspace().execute_paper(
            request, self.fetch_ticker(symbol)["last"], require_demo=True
        )
        return {**self._order(result), "clientOrderId": params["clientOrderId"]}

    def fetch_order(self, order_id: str, symbol: str) -> dict:
        """Read a persisted simulated order by its ID, including after a restart."""
        self.market(symbol)
        try:
            return PaperLimits(self._workspace()).read(order_id, symbol)
        except ccxt.OrderNotFound:
            pass
        with self._workspace().db() as db:
            row = db.execute("SELECT payload FROM orders WHERE id = ?", (order_id,)).fetchone()
        if row is None:
            raise ccxt.OrderNotFound("Paper order not found.")
        import json

        result = json.loads(row[0])
        if result["symbol"] != symbol:
            raise ccxt.OrderNotFound("Paper order not found for this market.")
        return self._order(result)

    def fetch_order_lookup_page(self, client_id: str, symbol: str, cursor: dict, start: int, end: int):
        """Recover a virtual limit's ID from its exact persisted key without matching it."""
        import json

        from sibyl.exchanges.order_lookup import OrderLookupPage

        self.market(symbol)
        with self._workspace().db() as db:
            row = db.execute("SELECT payload FROM paper_limits WHERE request_key=?", (client_id,)).fetchone()
        if not row:
            return OrderLookupPage([], {}, True)
        order = json.loads(row[0])
        result = {
            key: order.get(key)
            for key in (
                "id",
                "clientOrderId",
                "symbol",
                "type",
                "side",
                "amount",
                "price",
                "filled",
                "remaining",
                "average",
                "cost",
                "status",
            )
        }
        result["timestamp"] = datetime.fromisoformat(order["created_at"]).timestamp() * 1000
        return OrderLookupPage([result], {}, True)

    def fetch_open_orders(self, symbol: str) -> list[dict]:
        """Read resting Demo limit orders without advancing the matcher."""
        self.market(symbol)
        self._workspace()
        return PaperLimits(self._workspace()).open_orders(symbol)

    def cancel_order(self, order_id: str, symbol: str) -> dict:
        """Cancel a virtual resting order, preserving fills and releasing its hold."""
        self.market(symbol)
        return PaperLimits(self._workspace()).cancel(order_id, symbol)

    def match_order(self, order_id: str, symbol: str) -> dict:
        """Explicitly advance a virtual limit using the fixed Demo bid/ask feed."""
        return PaperLimits(self._workspace()).match(order_id, symbol, self.fetch_ticker(symbol))

    def fetch_order_fill_page(self, order_id: str, symbol: str, cursor: dict, limit: int = 100) -> TradePage:
        """Read the exact virtual order's fill without advancing its matcher or scanning history."""
        import json

        self.market(symbol)
        if not 1 <= limit <= 100:
            raise ValueError("Order execution page size must be between 1 and 100.")
        with self._workspace().db() as db:
            rows = db.execute(
                "SELECT payload FROM orders WHERE json_extract(payload,'$.symbol')=? "
                "AND COALESCE(json_extract(payload,'$.order_id'),id)=? ORDER BY id LIMIT ?",
                (symbol, order_id, limit + 1),
            ).fetchall()
        if len(rows) > limit:
            raise ccxt.ExchangeError("Unexpected number of virtual order executions.")
        items = []
        for row in rows:
            fill = json.loads(row[0])
            items.append(
                {
                    "id": fill["id"],
                    "order": fill.get("order_id", fill["id"]),
                    "symbol": symbol,
                    "side": fill["side"],
                    "timestamp": datetime.fromisoformat(fill["created_at"]).timestamp() * 1000,
                    "amount": fill["quantity"],
                    "price": fill["price"],
                    "cost": fill["notional"],
                    "fee": {"currency": symbol.split("/")[1], "cost": fill["fee"]},
                }
            )
        return TradePage(items, {}, True)

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
                        "order": fill.get("order_id", fill["id"]),
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

    def fetch_trade_page(self, symbol: str, cursor: dict, limit: int = 100) -> TradePage:
        """Page the real paper ledger by (time, ID), including timestamp ties."""
        import json

        self.market(symbol)
        if not 1 <= limit <= 100:
            raise ValueError("History page size must be between 1 and 100.")
        with self._workspace().db() as db:
            rows = db.execute(
                "SELECT id, created_at, payload FROM orders "
                "WHERE json_extract(payload, '$.symbol') = ? AND (created_at, id) > (?, ?) "
                "ORDER BY created_at, id LIMIT ?",
                (symbol, cursor.get("time", ""), cursor.get("id", ""), limit),
            ).fetchall()
        items = []
        for row in rows:
            fill = json.loads(row["payload"])
            fee = {"currency": symbol.split("/")[1], "cost": fill["fee"]}
            items.append(
                {
                    "id": fill["id"],
                    "order": fill.get("order_id", fill["id"]),
                    "symbol": symbol,
                    "side": fill["side"],
                    "timestamp": datetime.fromisoformat(fill["created_at"]).timestamp() * 1000,
                    "amount": fill["quantity"],
                    "price": fill["price"],
                    "cost": fill["notional"],
                    "fee": fee,
                    "fees": [fee],
                }
            )
        following = {"time": rows[-1]["created_at"], "id": rows[-1]["id"]} if rows else cursor
        return TradePage(items, following, not rows)
