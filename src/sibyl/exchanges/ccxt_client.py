"""CCXT transport normalization shared by explicit provider subclasses."""

from copy import deepcopy

import ccxt

from sibyl.exchanges.base import ExchangeClient, number
from sibyl.exchanges.catalog import exchange_spec
from sibyl.exchanges.history import TradePage, fetch_trade_page, normalize_trade


class CCXTClient(ExchangeClient):
    """Reuse one rate-limited spot adapter per account, without leaking ``info``.

    Construction performs no network requests. Sandbox configuration always
    precedes market loading. Credentials are accepted only from the server vault.
    The provider subclasses supply account-specific options; callers cannot inject
    URLs, derivative parameters or arbitrary CCXT method names.
    """

    id = ""
    options: dict = {}
    balance_params: dict = {}
    book_limits: tuple[int, ...] = ()
    fetch_currencies = True

    def __init__(self, credentials: dict | None = None, sandbox: bool = False):
        super().__init__()
        self.spec = exchange_spec(self.id)
        sandbox = sandbox or self.spec.test_environment
        if sandbox and not self.spec.sandbox:
            raise ValueError("Sandbox is not configured for this exchange.")
        credentials = credentials or {}
        required = ["apiKey", "secret"]
        if self.spec.passphrase:
            required.append("password")
        if self.spec.uid:
            required.append("uid")
        if credentials and any(not credentials.get(key) for key in required):
            raise ValueError("Required exchange credentials are missing.")
        self._private = bool(credentials)
        self._exchange = getattr(ccxt, self.spec.ccxt_id or self.id)(
            {
                "enableRateLimit": True,
                "timeout": 12_000,
                "options": {"defaultType": "spot", "maxRetriesOnFailure": 0, **deepcopy(self.options)},
                **({"has": {"fetchCurrencies": False}} if not self.fetch_currencies else {}),
                **{
                    key: value
                    for key, value in credentials.items()
                    if key in {"apiKey", "secret", "password", "uid"}
                },
            }
        )
        if sandbox:
            self._exchange.set_sandbox_mode(True)
        self.timeframes = getattr(self._exchange, "timeframes", {}) or {}
        self._markets: dict | None = None

    def _require(self, method: str, private: bool = False):
        if private and not self._private:
            raise ccxt.AuthenticationError("A saved account is required for private exchange reads.")
        if not self._exchange.has.get(method):
            raise ccxt.NotSupported("This operation is unavailable on the selected exchange.")

    def load_markets(self) -> dict:
        """Load and cache active spot instruments, excluding derivatives and raw metadata."""
        with self.lock:
            if self._markets is None:
                markets = self._exchange.load_markets()
                self._markets = {
                    symbol: {
                        "symbol": symbol,
                        "base": row["base"],
                        "quote": row["quote"],
                        "name": str(
                            ((getattr(self._exchange, "currencies", None) or {}).get(row["base"]) or {}).get(
                                "name"
                            )
                            or row["base"]
                        )[:120],
                        "spot": True,
                        "active": row.get("active"),
                        "precision": deepcopy(row.get("precision") or {}),
                        "limits": deepcopy(row.get("limits") or {}),
                    }
                    for symbol, row in markets.items()
                    if row.get("spot")
                    and row.get("active") is not False
                    and isinstance(row.get("base"), str)
                    and row["base"].isalnum()
                    and isinstance(row.get("quote"), str)
                    and row["quote"].isalnum()
                    and len(row["base"]) <= 12
                    and len(row["quote"]) <= 12
                    and symbol == f"{row['base']}/{row['quote']}"
                }
            return deepcopy(self._markets)

    def fetch_ticker(self, symbol: str) -> dict:
        """Return only unified numeric ticker fields for an exact spot symbol."""
        with self.lock:
            self._require("fetchTicker")
            self.market(symbol)
            row = self._exchange.fetch_ticker(symbol)
            return {
                "symbol": symbol,
                **{
                    key: number(row.get(key))
                    for key in (
                        "timestamp",
                        "last",
                        "close",
                        "bid",
                        "ask",
                        "percentage",
                        "baseVolume",
                        "quoteVolume",
                    )
                },
            }

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1d", limit: int = 180) -> list[list]:
        """Read one bounded candle page, deduplicating and rejecting malformed rows."""
        if not 1 <= limit <= 1000:
            raise ValueError("Candle limit must be between 1 and 1000.")
        with self.lock:
            self._require("fetchOHLCV")
            self.market(symbol)
            if timeframe not in self.timeframes:
                raise ccxt.NotSupported("This candle timeframe is unavailable on the selected exchange.")
            rows = self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            candles = {}
            for row in rows:
                if len(row) < 6:
                    raise ccxt.ExchangeError("Provider returned an incomplete candle.")
                values = [number(value) for value in row[:6]]
                if any(value is None for value in values):
                    raise ccxt.ExchangeError("Provider returned invalid candle values.")
                stamp, opening, high, low, close, volume = values
                if (
                    stamp <= 0
                    or min(opening, high, low, close) <= 0
                    or volume < 0
                    or low > min(opening, close)
                    or high < max(opening, close)
                ):
                    raise ccxt.ExchangeError("Provider returned invalid candle bounds.")
                candles[stamp] = values
            return [candles[key] for key in sorted(candles)][-limit:]

    def fetch_order_book(self, symbol: str, limit: int = 10) -> dict:
        """Adapt discrete venue depth limits and return sorted finite levels."""
        if not 1 <= limit <= 100:
            raise ValueError("Order book depth must be between 1 and 100.")
        with self.lock:
            self._require("fetchOrderBook")
            self.market(symbol)
            depth = (
                next((size for size in self.book_limits if size >= limit), None)
                if self.book_limits
                else limit
            )
            row = self._exchange.fetch_order_book(symbol, limit=depth)
            result = {"symbol": symbol, "timestamp": number(row.get("timestamp"))}
            for side in ("bids", "asks"):
                levels = []
                for level in row.get(side, []):
                    if len(level) < 2:
                        continue
                    price, amount = number(level[0]), number(level[1])
                    if price is not None and amount is not None and price > 0 and amount > 0:
                        levels.append([price, amount])
                result[side] = sorted(levels, key=lambda item: item[0], reverse=side == "bids")[:limit]
            return result

    def fetch_balance(self) -> dict:
        """Read the configured wallet and strip raw account/credential metadata."""
        with self.lock:
            self._require("fetchBalance", private=True)
            row = self._exchange.fetch_balance(params=deepcopy(self.balance_params))
            return {
                kind: {
                    asset: number(value)
                    for asset, value in (row.get(kind) or {}).items()
                    if isinstance(asset, str) and number(value) is not None
                }
                for kind in ("total", "free", "used")
            }

    def amount_to_precision(self, symbol: str, amount: float) -> str:
        """Use CCXT's actual precision mode, rather than assuming decimal places."""
        if number(amount) is None or amount <= 0:
            raise ValueError("Quantity must be positive and finite.")
        with self.lock:
            self.market(symbol)
            return self._exchange.amount_to_precision(symbol, amount)

    @staticmethod
    def _order(row: dict) -> dict:
        return {
            **{key: row.get(key) for key in ("id", "clientOrderId", "symbol", "status", "type", "side")},
            **{
                key: number(row.get(key))
                for key in ("timestamp", "amount", "filled", "remaining", "price", "average", "cost")
            },
        }

    def fetch_order(self, order_id: str, symbol: str) -> dict:
        """Read one order with no raw response fields and no submission fallback."""
        with self.lock:
            self._require("fetchOrder", private=True)
            self.market(symbol)
            return self._order(self._exchange.fetch_order(order_id, symbol))

    def fetch_open_orders(self, symbol: str) -> list[dict]:
        """Read the selected spot market's open orders; no all-market fan-out."""
        with self.lock:
            self._require("fetchOpenOrders", private=True)
            self.market(symbol)
            return [self._order(row) for row in self._exchange.fetch_open_orders(symbol)]

    def fetch_my_trades(self, symbol: str, since: int | None = None, limit: int = 100) -> list[dict]:
        """Read a bounded fill page; callers must explicitly paginate historical imports."""
        if not 1 <= limit <= 500 or (since is not None and since < 0):
            raise ValueError("Use a limit of 1–500 and a nonnegative millisecond cursor.")
        with self.lock:
            self._require("fetchMyTrades", private=True)
            self.market(symbol)
            rows = self._exchange.fetch_my_trades(symbol, since=since, limit=limit)
            return [normalize_trade(row) for row in rows[:limit]]

    def fetch_trade_page(self, symbol: str, cursor: dict, limit: int = 100) -> TradePage:
        """Read a reviewed native history page, without raw account metadata."""
        if not 1 <= limit <= 100:
            raise ValueError("History page size must be between 1 and 100.")
        if not self.history_kind:
            return super().fetch_trade_page(symbol, cursor, limit)
        with self.lock:
            self._require("fetchMyTrades", private=True)
            self.market(symbol)
            return fetch_trade_page(self._exchange, self.history_kind, symbol, cursor, limit)

    def create_order(
        self, symbol: str, type: str, side: str, amount: float, params: dict | None = None
    ) -> dict:
        """Submit once for reviewed production providers and dedicated test environments."""
        if not self.spec.market_orders:
            raise ccxt.NotSupported(
                "Market orders are not enabled for this provider. Read access is available."
            )
        if type != "market" or side not in {"buy", "sell"} or number(amount) is None or amount <= 0:
            raise ValueError("Use a market buy or sell with a positive finite base quantity.")
        params = params or {}
        if set(params) != {"clientOrderId"} or not params.get("clientOrderId"):
            raise ValueError("A client order ID is required; additional order parameters are unsupported.")
        with self.lock:
            self._require("createOrder", private=True)
            self.market(symbol)
            result = self._submit_market_order(symbol, side, amount, params["clientOrderId"])
            return self._order(result)

    def _submit_market_order(self, symbol: str, side: str, amount: float, client_order_id: str) -> dict:
        """Provider hook for amount and client-ID semantics; never retry a submission."""
        return self._exchange.create_order(
            symbol, "market", side, amount, params={"clientOrderId": client_order_id}
        )

    def close(self) -> None:
        """Close the HTTP session and drop credential references on disconnect."""
        with self.lock:
            session = getattr(self._exchange, "session", None)
            if session is not None:
                session.close()
            for key in ("apiKey", "secret", "password", "uid"):
                setattr(self._exchange, key, "")
            self._private = False
