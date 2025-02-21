from backend.src.exchange_client.exchange_client import ExchangeAPIClient
from backend.db.api_keys_db_client import APIEncryptedDatabase


class CoinbaseClient(ExchangeAPIClient):

    def __init__(self):
        super().__init__()
        self.name = 'coinbase'
        self.api_base_url = "https://api.prime.coinbase.com/v1"
        # Set API Keys
        api_creds = APIEncryptedDatabase.get_api_key_by_name(self.name)
        if api_creds is None:
            self.api_key, self.api_secret_key = None, None
        else:
            self.api_key, self.api_secret_key = api_creds.api_key, api_creds.secret_key

    def check_status(self):
        return 'Unavailable'

    def get_crypto_pair_price(self, pair: str):
        pass

    def get_spot_balance(self):
        pass

    def fetch_available_coins(self):
        pass

    def fetch_price_history(self, symbol: str, interval, plot_type, limit: int):
        pass

    def get_minimum_buy_order(self, symbol: str):
        pass

    def post_buy_order(self, trade_from: str, trade_to: str, from_amount: float):
        pass

    def post_swap_order(self, trade_from: str, trade_to: str,
                        from_amount: float):  # Alternative to BUY order with No fees
        pass

    def post_sell_order(self, trade_from: str, trade_to: str, quantity: float, sell_order_price: float):
        pass
