from backend.src.exchange_client.binance_client import BinanceClient
from backend.db.api_keys_db_client import APIEncryptedDatabase
from binance.client import Client
from binance.exceptions import BinanceAPIException


class BinanceTestnetClient(BinanceClient):

    def __init__(self):
        super().__init__()
        self.name = 'binance_testnet'
        self.api_base_url = 'https://testnet.binance.vision'
        # Set API Keys
        api_creds = APIEncryptedDatabase.get_api_key_by_name(self.name)
        if api_creds is None:
            self.client = None
        else:
            self.client = Client(api_creds.api_key, api_creds.secret_key)
