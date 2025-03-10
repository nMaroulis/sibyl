from backend.src.exchange_client.exchange_client import ExchangeAPIClient

class Broker:

    def __init__(self, exchange_client: ExchangeAPIClient, datetime: str, strategy_params: dict):

        self.exchange_client = exchange_client
        self.strategy = None  # Strategy Type
        self.strategy_params = strategy_params
        self.datetime = datetime

    def __str__(self):
        return f"{self.datetime}: ..."

    def init_trading_algorithm(self) -> dict:
        pass
