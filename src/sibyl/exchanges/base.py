"""Small synchronous interface shared by real providers and the offline simulator."""

import math
import re
from abc import ABC, abstractmethod
from threading import RLock
from typing import TYPE_CHECKING

import ccxt

if TYPE_CHECKING:
    from sibyl.exchanges.funding import FundingPage
    from sibyl.exchanges.history import TradePage
    from sibyl.exchanges.order_discovery import OrderDiscoveryPage
    from sibyl.exchanges.order_lookup import OrderLookupPage


class ExchangeClient(ABC):
    """Expose spot data using CCXT's unified field names, without raw provider payloads.

    Amounts and OHLCV volume are base-asset units. OHLCV timestamps and ``since``
    are UTC Unix milliseconds. Clients serialize their transport with an RLock;
    callers can hold ``lock`` across a multi-step preview. Errors retain CCXT
    types for the API's sanitized error handler. No method retries a write.
    """

    id: str
    timeframes: dict
    history_kind: str = ""
    candle_history: bool = False

    def __init__(self):
        self.lock = RLock()

    def format_client_order_id(self, identity: str) -> str:
        """Format a new intent ID before persistence; never transform a submitted ID."""
        return identity

    @abstractmethod
    def load_markets(self) -> dict:
        """Return active spot markets with base, quote, precision and limits."""

    def market(self, symbol: str) -> dict:
        """Resolve an exact spot symbol; execution never substitutes quote assets."""
        if not re.fullmatch(r"[A-Z0-9]{1,12}/[A-Z0-9]{1,12}", symbol):
            raise ccxt.BadSymbol("Use a canonical spot symbol such as BTC/USDT.")
        market = self.load_markets().get(symbol)
        if market is None:
            raise ccxt.BadSymbol("This active spot market is unavailable on the selected exchange.")
        return market

    @property
    def markets(self) -> dict:
        """Expose the same filtered markets to preview validation and chart selectors."""
        return self.load_markets()

    @abstractmethod
    def fetch_ticker(self, symbol: str) -> dict:
        """Read a ticker with nullable numeric fields; no provider ``info`` escapes."""

    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str = "1d", limit: int = 180) -> list[list]:
        """Read ascending OHLCV rows, possibly including the still-open interval."""

    def fetch_candle_page(self, symbol: str, timeframe: str, start: int, end: int) -> list[list]:
        """Read one reviewed historical UTC window; the end boundary is exclusive."""
        raise ccxt.NotSupported("Historical candle pagination is not reviewed for this provider.")

    def candle_page_size(self, timeframe: str) -> int:
        """Bound one historical request; providers may impose tighter aggregation limits."""
        return 200

    @abstractmethod
    def fetch_order_book(self, symbol: str, limit: int = 10) -> dict:
        """Read up to ``limit`` sorted bid/ask levels; this is a snapshot, not a stream."""

    @abstractmethod
    def fetch_balance(self) -> dict:
        """Read finite total/free/used maps in native asset quantities."""

    @abstractmethod
    def amount_to_precision(self, symbol: str, amount: float) -> str:
        """Format a base quantity with the provider's market-specific precision."""

    def fetch_open_orders(self, symbol: str) -> list[dict]:
        """Read one market's open orders, when implemented by the provider."""
        raise ccxt.NotSupported("Open order reads are unavailable for this client.")

    def fetch_funding_page(self, stream: str, cursor: dict, limit: int = 50) -> "FundingPage":
        """Read reviewed deposit/withdrawal/transfer history; never initiate a movement."""
        raise ccxt.NotSupported("Funding history is coming soon for this client.")

    def fetch_my_trades(self, symbol: str, since: int | None = None, limit: int = 100) -> list[dict]:
        """Read a bounded page of fills; this is not a complete historical import."""
        raise ccxt.NotSupported("Trade history is unavailable for this client.")

    def fetch_trade_page(self, symbol: str, cursor: dict, limit: int = 100) -> "TradePage":
        """Read one resumable history page; unsupported pagination fails explicitly."""
        raise ccxt.NotSupported("Durable history import is not enabled for this provider.")

    def fetch_order(self, order_id: str, symbol: str) -> dict:
        """Read a known order, without submitting or retrying it."""
        raise ccxt.NotSupported("Order status reads are unavailable for this client.")

    def fetch_order_lookup_page(
        self, client_id: str, symbol: str, cursor: dict, start: int, end: int
    ) -> "OrderLookupPage":
        """Read existing orders by exact client ID; never submit or infer a rejection."""
        raise ccxt.NotSupported("Client order ID recovery is not reviewed for this provider.")

    def fetch_account_order_page(
        self, stream: str, cursor: dict, start: int, end: int, symbols: list[str]
    ) -> "OrderDiscoveryPage":
        """Discover existing spot orders without submitting, canceling or matching them."""
        raise ccxt.NotSupported("Account order discovery is not reviewed for this provider.")

    def fetch_order_fill_page(
        self, order_id: str, symbol: str, cursor: dict, limit: int = 100
    ) -> "TradePage":
        """Read one reviewed page of executions belonging to an exact native order."""
        raise ccxt.NotSupported("Order execution imports are not reviewed for this provider.")

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
        """Submit one spot market/GTC limit only for reviewed execution clients."""
        raise ccxt.NotSupported("Order execution is not enabled for this provider.")

    def price_to_precision(self, symbol: str, price: float) -> str:
        """Format a reviewed limit price using native market tick precision."""
        raise ccxt.NotSupported("Limit price precision is unavailable for this client.")

    def cancel_order(self, order_id: str, symbol: str) -> dict:
        """Request cancellation once; acknowledgment alone need not establish final status."""
        raise ccxt.NotSupported("Cancellation is not enabled for this provider.")

    def close(self) -> None:
        """Release transport resources when disconnecting or shutting down."""
        return None


def number(value) -> float | None:
    """Normalize numeric provider values, treating missing/non-finite fields as unknown."""
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None
