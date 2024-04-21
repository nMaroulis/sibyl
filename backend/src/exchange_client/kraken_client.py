from backend.src.exchange_client.exchange_client import ExchangeAPIClient
from backend.config.api_key_handler import get_api_key


class KrakenClient(ExchangeAPIClient):

    def __init__(self):
        super().__init__()
        self.name = 'Kraken'
        self.api_base_url = ''
        # Set API Keys
        self.api_key, self.api_secret_key = None, None

    @staticmethod
    def check_status():
        return 'Unavailable'
