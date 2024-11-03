import requests
import time
from datetime import datetime
from backend.src.exchange_client.exchange_client import ExchangeAPIClient


class Broker:

    def __init__(self, exchange_client: ExchangeAPIClient, datetime: str, trade_from: str, trade_to: str, from_amount: float, order_type: str, strategy_params: dict):

        self.exchange_client = exchange_client
        self.strategy = None  # Strategy Type
        self.strategy_params = strategy_params
        self.datetime = datetime
        self.trade_from = trade_from
        self.trade_to = trade_to
        self.from_amount = from_amount
        self.quantity_bought = None  # populated after the buy order has been completed
        self.sell_order_price = 1.0  # what price to sell the coin in order to make profit
        self.datetime_sell = None
        self.profit_percentage = 5
        self.order_type = order_type
        self.buy_order_id = None   # if swap then this is the quote
        self.buy_datetime = None   # if swap then this is the quote
        self.sell_order_id = None

    def __str__(self):
        return f"{self.datetime}: Bought {self.quantity_bought} {self.trade_to} for {self.from_amount} {self.trade_from}, in order to sell it at a price of {self.sell_order_price}"

    def init_trading_algorithm(self) -> dict:
        pass

    def get_db_fields(self):
        return [self.exchange_client.name.lower(), self.datetime, self.trade_from, self.trade_to, self.from_amount, self.quantity_bought, self.buy_order_id, self.sell_order_id, self.order_type, 'Strategy', 'active']
