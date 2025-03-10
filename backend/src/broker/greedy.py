from backend.src.broker.broker import Broker
from backend.src.exchange_client.exchange_client import ExchangeAPIClient


class GreedyBroker(Broker):

    def __init__(self, exchange_client: ExchangeAPIClient, datetime: str, strategy_params: dict):
        super().__init__(exchange_client=exchange_client, datetime=datetime, strategy_params=strategy_params)
        self.strategy = 'Greedy'

    def init_trading_algorithm(self) -> dict:
        pass