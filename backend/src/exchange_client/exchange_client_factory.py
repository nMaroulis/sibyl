from backend.src.exchange_client.kraken_client import KrakenClient
from backend.src.exchange_client.binance_client import BinanceClient
from backend.src.exchange_client.binance_testnet_client import BinanceTestnetClient
from backend.src.exchange_client.coinbase_client import CoinbaseClient


class ExchangeClientFactory:
    _clients = {
        'binance': BinanceClient,
        'binance_testnet': BinanceTestnetClient,
        'coinbase': CoinbaseClient,
        'kraken': KrakenClient
    }

    @classmethod
    def get_client(cls, exchange_name: str):
        # Get the client class based on the exchange_name
        client_class = cls._clients.get(exchange_name.lower())
        if not client_class:
            raise ValueError(f"Unknown exchange name: {exchange_name}")
        return client_class()
