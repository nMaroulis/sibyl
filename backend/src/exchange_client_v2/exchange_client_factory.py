from backend.src.exchange_client_v2.binance_client import BinanceClient
from backend.src.exchange_client_v2.binance_testnet_client import BinanceTestnetClient


class ExchangeClientFactory:
    _clients = {
        'binance': BinanceClient,
        'binance_testnet': BinanceTestnetClient,
    }

    @classmethod
    def get_client(cls, exchange_name: str):
        # Get the client class based on the exchange_name
        client_class = cls._clients.get(exchange_name.lower())
        if not client_class:
            raise ValueError(f"Unknown exchange name: {exchange_name}")
        return client_class()
