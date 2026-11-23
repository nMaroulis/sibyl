"""Read-only CCXT Pro adapters: native authentication, subscriptions and reconnects.

The installed CCXT dependency includes Pro. These clients expose only watch_orders
and close, never WebSocket order entry. A returned cache is a wake-up hint, not a
complete sequence, balance snapshot or normalized financial ledger.
"""

from abc import ABC, abstractmethod

import ccxt
import ccxt.pro as pro

from sibyl.exchanges.bybit_orders import regular_spot_order


class AccountOrderStream(ABC):
    """The minimal async contract owned by one connection's stream task."""

    @abstractmethod
    async def receive(self) -> list[dict]:
        """Wait for bounded normalized order signals; native raw payloads stay private."""

    @abstractmethod
    async def close(self):
        """Drain native sockets/keepalive tasks without submitting any trade operation."""


class CCXTOrderStream(AccountOrderStream):
    provider = ""
    options = {}
    params = {}

    def __init__(self, connection, credentials):
        self.native = getattr(pro, self.provider)(
            {
                "enableRateLimit": True,
                "timeout": 15000,
                "newUpdates": True,
                "has": {"fetchCurrencies": False},
                "options": {
                    "defaultType": "spot",
                    "ordersLimit": 200,
                    "maxRetriesOnFailure": 0,
                    **self.options,
                },
                **{
                    key: value
                    for key, value in credentials.items()
                    if key in {"apiKey", "secret", "password", "uid"}
                },
            }
        )
        # Testnet is selected before native authentication or market loading.
        if connection.sandbox:
            self.native.set_sandbox_mode(True)
        if self.native.has.get("watchOrders") is not True:
            raise ValueError("The installed native adapter has no reviewed private order stream.")

    async def receive(self):
        result = await self.native.watch_orders(limit=100, params=dict(self.params))
        if not isinstance(result, list) or len(result) > 100:
            raise ValueError("The private order stream exceeded its bounded update contract.")
        # No provider `info`, JWT, authentication token or credential leaves here.
        return [
            {key: row.get(key) for key in ("id", "symbol", "status", "filled", "cost", "lastTradeTimestamp")}
            for row in result
            if isinstance(row, dict) and self.accepts_order(row)
        ]

    def accepts_order(self, row: dict) -> bool:
        """Keep normalized rows within the reviewed scope of this subscription."""
        return True

    async def close(self):
        await self.native.close()


class BinanceOrderStream(CCXTOrderStream):
    """Native signed userDataStream.subscribe.signature, including isolated Spot Testnet routing."""

    provider = "binance"
    options = {"fetchMarkets": {"types": ["spot"]}}


class CoinbaseOrderStream(CCXTOrderStream):
    """Advanced Trade user channel with native CDP JWT signing; Exchange sandbox is excluded."""

    provider = "coinbase"


class KrakenOrderStream(CCXTOrderStream):
    """Kraken private v2 executions using its native short-lived REST WebSocket token."""

    provider = "kraken"


class OKXOrderStream(CCXTOrderStream):
    """Observe production cash spot orders via OKX's native authenticated channel."""

    provider = "okx"
    params = {"type": "spot"}

    def accepts_order(self, row: dict) -> bool:
        native = row.get("info")
        return (
            isinstance(native, dict)
            and native.get("instType") == "SPOT"
            and native.get("tdMode") == "cash"
            and isinstance(row.get("id"), str)
            and bool(row["id"])
            and native.get("ordId") == row["id"]
        )


class BybitOrderStream(CCXTOrderStream):
    """Use Bybit's native Unified Trading Account private stream for regular cash spot orders."""

    provider = "bybit"
    options = {"defaultSettle": "USDT"}

    async def receive(self):
        _, unified = await self.native.is_unified_enabled()
        if unified is not True:
            raise ccxt.NotSupported("Bybit private order signals require a Unified Trading Account.")
        return await super().receive()

    def accepts_order(self, row: dict) -> bool:
        native = row.get("info")
        return (
            isinstance(native, dict)
            and native.get("category") == "spot"
            and regular_spot_order(native)
            and isinstance(row.get("id"), str)
            and bool(row["id"])
            and native.get("orderId") == row["id"]
        )


CLIENTS = {
    "binance": BinanceOrderStream,
    "binance-testnet": BinanceOrderStream,
    "coinbase": CoinbaseOrderStream,
    "kraken": KrakenOrderStream,
    "okx": OKXOrderStream,
    "bybit": BybitOrderStream,
}
PROVIDERS = frozenset(CLIENTS)


def create_stream(connection, credentials):
    """Fail closed for unreviewed providers/environments before creating a native client."""
    if connection.exchange not in PROVIDERS or (
        connection.sandbox and connection.exchange not in {"binance", "binance-testnet"}
    ):
        raise ValueError(
            "Private order streams support Binance production, Binance Testnet, Coinbase Advanced, Kraken, OKX and Bybit UTA production."
        )
    return CLIENTS[connection.exchange](connection, credentials)
