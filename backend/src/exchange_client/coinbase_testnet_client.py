from backend.src.exchange_client.coinbase_client import CoinbaseClient
from database.api_keys_db_client import APIEncryptedDatabase
from binance.client import Client


class BinanceTestnetClient(CoinbaseClient):

    def __init__(self):
        super().__init__()
        self.name = 'coinbase_testnet'
        self.api_base_url = 'https://api-public.sandbox.exchange.coinbase.com'
        # Set API Keys
        api_creds = APIEncryptedDatabase.get_api_key_by_name(self.name)
        if api_creds is None:
            self.client = None
        else:
            self.client = Client(api_creds.api_key, api_creds.secret_key, testnet=True)
