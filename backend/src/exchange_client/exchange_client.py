from abc import ABC, abstractmethod


class ExchangeAPIClient(ABC):

    def __init__(self):
        self.name = ''
        self.api_key = ''
        self.api_secret = ''
        self.api_base_url = ''

    @abstractmethod
    def check_status(self):
        pass

    @abstractmethod
    def get_crypto_pair_price(self, pair: str):
        pass

    @abstractmethod
    def get_spot_balance(self):
        pass

    @abstractmethod
    def fetch_available_coins(self):
        pass

    @abstractmethod
    def fetch_price_history(self, symbol: str, interval, plot_type, limit: int):
        pass

    @abstractmethod
    def get_minimum_buy_order(self, symbol: str):
        pass

    @abstractmethod
    def post_buy_order(self, trading_pair: str, from_amount: float):
        pass

    @abstractmethod
    def post_swap_order(self, trade_from: str, trade_to: str, from_amount: float):  # Alternative to BUY order with No fees in Binance
        pass
    @abstractmethod
    def post_sell_order(self, trading_pair: str, quantity_bought: str, sell_order_price: float):
        pass
