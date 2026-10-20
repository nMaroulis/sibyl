"""Source-specific market watchlists, independent of portfolio reference pricing."""

import ccxt
from pydantic import Field, field_validator

from sibyl.models import OrderRequest, Request
from sibyl.services.market import ASSETS, STABLES, Market
from sibyl.storage import Store

WATCHLIST_LIMIT = 30


class WatchlistItem(Request):
    """Add one exact, canonical spot pair offered by the selected feed."""

    symbol: str = Field(min_length=3, max_length=25)

    @field_validator("symbol")
    @classmethod
    def canonical_symbol(cls, value: str) -> str:
        if not value.isascii():
            raise ValueError("Use an ASCII market symbol such as BTC/USDT.")
        return OrderRequest.valid_symbol(value)


class WatchlistOrder(Request):
    """Reorder the current list without replacing concurrent additions or removals."""

    symbols: list[str] = Field(max_length=WATCHLIST_LIMIT)

    @field_validator("symbols")
    @classmethod
    def canonical_symbols(cls, values: list[str]) -> list[str]:
        result = [WatchlistItem.canonical_symbol(value) for value in values]
        if len(set(result)) != len(result):
            raise ValueError("Each market can appear only once in a watchlist.")
        return result


class Watchlists:
    """Own exact-pair preferences per feed; reads never alter account/trading settings."""

    def __init__(self, market: Market, store: Store):
        self.market, self.store = market, store

    def _config(self) -> dict:
        """Lazily seed supported default pairs once; an explicitly empty list stays empty."""
        source = self.market.source
        result = self.store.market_watchlist(source)
        if result is None:
            markets = self.market.client().load_markets()
            defaults = []
            for base in ASSETS:
                if base in STABLES:
                    continue
                match = next(
                    (f"{base}/{quote}" for quote in ("USDT", "USD", "USDC") if f"{base}/{quote}" in markets),
                    None,
                )
                if match:
                    defaults.append(match)
            result = self.store.seed_market_watchlist(source, defaults)
        return {**self.market.metadata(), **result, "limit": WATCHLIST_LIMIT}

    def config(self, source: str | None = None) -> dict:
        """Read saved order without fetching quotes; existing lists remain editable offline."""
        with self.market.snapshot(source):
            return self._config()

    def overview(self, source: str | None = None) -> dict:
        """Read watchlist quotes in saved order, retaining unavailable and empty entries."""
        with self.market.snapshot(source):
            config = self._config()
            return {**self.market.quotes(config["symbols"]), **config}

    def add(self, symbol: str, source: str | None = None) -> dict:
        """Validate exact provider support, then atomically append without duplicates."""
        with self.market.snapshot(source):
            self._config()
            try:
                self.market.client().market(symbol)
            except ccxt.BadSymbol:
                raise ValueError("Choose an active spot pair from this feed.") from None
            result = self.store.change_market_watchlist(
                self.market.source, "add", symbol, limit=WATCHLIST_LIMIT
            )
            return {**self.market.metadata(), **result, "limit": WATCHLIST_LIMIT}

    def remove(self, symbol: str, source: str | None = None) -> dict:
        """Remove a pair idempotently, including delisted pairs whose quote is unavailable."""
        with self.market.snapshot(source):
            self._config()
            result = self.store.change_market_watchlist(self.market.source, "remove", symbol)
            return {**self.market.metadata(), **result, "limit": WATCHLIST_LIMIT}

    def reorder(self, symbols: list[str], source: str | None = None) -> dict:
        """Commit a permutation of the current list; never discard another request's edits."""
        with self.market.snapshot(source):
            self._config()
            result = self.store.change_market_watchlist(self.market.source, "order", symbols)
            return {**self.market.metadata(), **result, "limit": WATCHLIST_LIMIT}
