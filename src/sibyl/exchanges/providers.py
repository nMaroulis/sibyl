"""Explicit spot clients: provider differences live here, not in domain services."""

from sibyl.exchanges.ccxt_client import CCXTClient


class BinanceClient(CCXTClient):
    """Binance spot, including the separate testnet when explicitly selected."""

    id = "binance"
    options = {"fetchMarkets": {"types": ["spot"]}}
    balance_params = {"type": "spot"}
    book_limits = (5, 10, 20, 50, 100)


class BinanceTestnetClient(BinanceClient):
    """Dedicated Binance Spot Test Network client; production routing is impossible."""

    id = "binance-testnet"


class BinanceUSClient(BinanceClient):
    """Binance.US uses its own endpoint and credentials; no sandbox is exposed."""

    id = "binanceus"


class CoinbaseClient(CCXTClient):
    """Coinbase Advanced Trade with CDP key name and PEM signing key."""

    id = "coinbase"
    balance_params = {"type": "spot"}

    def _submit_market_order(self, symbol: str, side: str, amount: float, client_order_id: str) -> dict:
        """Preserve the reviewed base quantity and ID in Coinbase's native IOC fields.

        CCXT's buy default uses quote cost and otherwise requires a reference price.
        The native configuration overrides that default with a base-sized IOC for
        both sides. The installed SDK currently needs native client_order_id too.
        """
        return self._exchange.create_order(
            symbol,
            "market",
            side,
            amount,
            params={
                "client_order_id": client_order_id,
                "createMarketBuyOrderRequiresPrice": False,
                "order_configuration": {
                    "market_market_ioc": {"base_size": self._exchange.amount_to_precision(symbol, amount)}
                },
            },
        )


class CoinbaseSandboxClient(CCXTClient):
    """Coinbase Exchange sandbox with key, secret and passphrase; not Advanced Trade."""

    id = "coinbase-sandbox"


class KrakenClient(CCXTClient):
    """Kraken spot account; Kraken Futures is a separate, unsupported product."""

    id = "kraken"


class OKXClient(CCXTClient):
    """OKX trading wallet, passphrase signing, and explicit simulated-trading mode."""

    id = "okx"
    options = {"fetchMarkets": {"types": ["spot"]}}
    balance_params = {"type": "spot"}


class BybitClient(CCXTClient):
    """Bybit spot markets and unified balances, which may include shared collateral."""

    id = "bybit"
    options = {"fetchMarkets": {"types": ["spot"]}}
    balance_params = {"accountType": "UNIFIED"}
    book_limits = (1, 50, 200)


class KuCoinClient(CCXTClient):
    """KuCoin classic spot trading wallet; main/funding and UTA imports remain separate."""

    id = "kucoin"
    options = {"fetchMarkets": {"types": ["spot"]}}
    balance_params = {"type": "trade"}
    book_limits = (20, 100)


class GateClient(CCXTClient):
    """Gate spot wallet with optional sandbox credentials."""

    id = "gate"
    options = {"fetchMarkets": {"types": ["spot"]}}
    balance_params = {"type": "spot"}


class BitgetClient(CCXTClient):
    """Bitget classic spot assets and passphrase authentication."""

    id = "bitget"
    balance_params = {"type": "spot"}


class MEXCClient(CCXTClient):
    """MEXC spot account, excluding contract markets."""

    id = "mexc"
    balance_params = {"type": "spot"}
    book_limits = (5, 10, 20, 50, 100)


class HTXClient(CCXTClient):
    """HTX spot account, excluding margin and swaps."""

    id = "htx"
    balance_params = {"type": "spot"}
    book_limits = (5, 10, 20)


class CryptoComClient(CCXTClient):
    """Crypto.com Exchange account, separate from the retail mobile app."""

    id = "cryptocom"
    book_limits = (10, 50)


class BitstampClient(CCXTClient):
    """Bitstamp spot account with key/secret authentication."""

    id = "bitstamp"


class GeminiClient(CCXTClient):
    """Gemini spot and sandbox reads; native market orders are not supported here."""

    id = "gemini"


class BitfinexClient(CCXTClient):
    """Bitfinex exchange wallet, excluding margin and funding balances."""

    id = "bitfinex"
    balance_params = {"type": "exchange"}
    book_limits = (1, 25, 100)


class CoinExClient(CCXTClient):
    """CoinEx spot trading account."""

    # Trading instruments infer currency codes; deposit-network metadata is outside this client scope.
    fetch_currencies = False
    id = "coinex"
    balance_params = {"type": "spot"}
    book_limits = (5, 10, 20, 50)


class BitMartClient(CCXTClient):
    """BitMart spot; the API memo is passed through CCXT's uid credential field."""

    # Avoid coupling spot reads to the separate deposit/withdrawal currency endpoint.
    fetch_currencies = False
    id = "bitmart"
    balance_params = {"type": "spot"}


class PhemexClient(CCXTClient):
    """Phemex spot wallet and optional testnet."""

    id = "phemex"
    balance_params = {"type": "spot"}


class PoloniexClient(CCXTClient):
    """Poloniex spot account; no sandbox is exposed by Sibyl."""

    id = "poloniex"


class UpbitClient(CCXTClient):
    """Upbit default endpoint; regional API variants require their own adapter."""

    id = "upbit"


CLIENTS = {
    client.id: client
    for client in (
        BinanceClient,
        BinanceTestnetClient,
        CoinbaseSandboxClient,
        BinanceUSClient,
        CoinbaseClient,
        KrakenClient,
        OKXClient,
        BybitClient,
        KuCoinClient,
        GateClient,
        BitgetClient,
        MEXCClient,
        HTXClient,
        CryptoComClient,
        BitstampClient,
        GeminiClient,
        BitfinexClient,
        CoinExClient,
        BitMartClient,
        PhemexClient,
        PoloniexClient,
        UpbitClient,
    )
}
