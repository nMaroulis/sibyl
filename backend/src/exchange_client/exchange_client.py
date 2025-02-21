from abc import ABC, abstractmethod


class ExchangeAPIClient(ABC):

    def __init__(self):
        self.name: str = ""
        self.api_key: str = ""
        self.api_secret: str = ""
        self.api_base_url: str = ""

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
    def post_buy_order(self, trade_from: str, trade_to: str, from_amount: float):
        pass

    @abstractmethod
    def post_swap_order(self, trade_from: str, trade_to: str, from_amount: float):  # CONVERT API
        pass

    @abstractmethod
    def post_sell_order(self, trade_from: str, trade_to: str, quantity: float, sell_order_price: float):
        pass

    @abstractmethod
    def get_order_status(self, symbol_pair: str, order_id: str):
        pass

    @abstractmethod
    def get_order_status_detailed(self, symbol_pair: str, order_id: str) -> dict | None:
        pass

    @abstractmethod
    def test_order(self, symbol: str, side: str, quantity: float, price: float, order_type: str, time_in_force: str):
        pass