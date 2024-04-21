from backend.src.exchange_client.binance_client import BinanceClient
from backend.config.api_key_handler import get_api_key


class BinanceTestnetClient(BinanceClient):

    def __init__(self):
        super().__init__()
        self.name = 'Binance Testnet'
        self.api_base_url = 'https://testnet.binance.vision'
        # Set API Keys
        api_creds = get_api_key("binance_testnet")
        if api_creds is None:
            self.api_key, self.api_secret_key = None, None
        else:
            self.api_key = api_creds[0]
            self.api_secret_key = api_creds[1]
