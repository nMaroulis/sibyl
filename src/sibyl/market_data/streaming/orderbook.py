"""Public WebSocket depth for explicitly supported spot venues."""

from datetime import UTC, datetime

import ccxt
import ccxt.pro as pro

from sibyl.market_data.streaming.coinbase import exact_product
from sibyl.market_data.streaming.common import number

PROVIDERS = {
    ("binance", "production"): "binance",
    ("binance-testnet", "test"): "binance",
    ("coinbase", "production"): "coinbase",
    ("kraken", "production"): "kraken",
}
DEPTH = 50


def supports_live_book(identity: dict, symbol: str) -> bool:
    """Check a precise provider, environment and pair without contacting the exchange."""
    if (identity["provider"], identity["environment"]) not in PROVIDERS:
        return False
    if identity["provider"] == "coinbase":
        try:
            exact_product(symbol.replace("/", "-"))
        except ValueError:
            return False
    return True


class PublicOrderBook:
    """Let CCXT Pro synchronize the venue snapshot and deltas, using a public client."""

    def __init__(self, identity: dict):
        provider = PROVIDERS[(identity["provider"], identity["environment"])]
        options = {"defaultType": "spot"}
        if provider == "binance":
            options["fetchMarkets"] = {"types": ["spot"]}
        self.native = getattr(pro, provider)(
            {
                "enableRateLimit": True,
                "timeout": 10000,
                "newUpdates": True,
                "has": {"fetchCurrencies": False},
                "options": options,
            }
        )
        if identity["environment"] == "test":
            self.native.set_sandbox_mode(True)

    async def validate_market(self, symbol: str):
        """Verify the selected pair without rewriting quote currencies or market types."""
        await self.native.load_markets()
        market = self.native.market(symbol)
        if market["symbol"] != symbol or not market.get("spot") or market.get("active") is False:
            raise ccxt.BadSymbol("An exact active spot pair is required.")
        if self.native.id == "coinbase":
            exact_product(market["id"])

    async def receive(self, symbol: str) -> dict:
        """Return a normalized snapshot without including raw provider messages."""
        book = await self.native.watch_order_book(symbol, 100)
        if book.get("symbol") != symbol:
            raise ValueError("Order book pair mismatch.")
        bids = levels(book["bids"], descending=True)
        asks = levels(book["asks"], descending=False)
        spread = asks[0][0] - bids[0][0] if bids and asks else None
        if spread is not None and spread < 0:
            raise ValueError("Crossed order book.")
        return {
            "type": "book",
            "symbol": symbol,
            "bids": bids,
            "asks": asks,
            "spread": spread,
            "as_of": datetime.now(UTC).isoformat(),
        }

    async def close(self):
        """Release the venue client and its sockets."""
        await self.native.close()


def levels(rows, *, descending: bool) -> list[list[float]]:
    """Keep finite positive levels in provider priority order."""
    selected = [
        [number(price, positive=True), number(size, positive=True)] for price, size, *_ in rows[:DEPTH]
    ]
    prices = [row[0] for row in selected]
    if prices != sorted(set(prices), reverse=descending):
        raise ValueError("Invalid order book level ordering.")
    return selected
