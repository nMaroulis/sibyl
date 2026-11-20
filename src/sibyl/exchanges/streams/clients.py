"""Read-only CCXT Pro adapters: native authentication, subscriptions and reconnects.

The installed CCXT dependency includes Pro. These clients expose only watch_orders
and close, never WebSocket order entry. A returned cache is a wake-up hint, not a
complete sequence, balance snapshot or normalized financial ledger.
"""

from abc import ABC, abstractmethod

import ccxt.pro as pro

PROVIDERS = frozenset({"binance", "binance-testnet", "coinbase", "kraken"})


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
            if isinstance(row, dict)
        ]

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


CLIENTS = {
    "binance": BinanceOrderStream,
    "binance-testnet": BinanceOrderStream,
    "coinbase": CoinbaseOrderStream,
    "kraken": KrakenOrderStream,
}


def create_stream(connection, credentials):
    """Fail closed for unreviewed providers/environments before creating a native client."""
    if connection.exchange not in PROVIDERS or (
        connection.sandbox and connection.exchange not in {"binance", "binance-testnet"}
    ):
        raise ValueError(
            "Private order streams support Binance production, Binance Testnet, Coinbase Advanced production and Kraken production."
        )
    return CLIENTS[connection.exchange](connection, credentials)
