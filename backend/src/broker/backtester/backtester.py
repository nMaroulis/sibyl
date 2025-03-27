from backend.src.broker.strategies.strategy_base import BaseStrategy
from backend.src.exchange_client.exchange_client import ExchangeAPIClient
import pandas as pd
from typing import List, Dict, Any
import time


class Backtester:

    def __init__(self, strategy: BaseStrategy, exchange_client: ExchangeAPIClient, symbol: str, interval: str, dataset_size: int = 3000):
        self.strategy = strategy
        self.exchange_client = exchange_client
        self.symbol = symbol
        self.interval = interval
        self.dataset_size = dataset_size
        self.strategy_chunk = 400
        self.backtesting_logs = []

    def get_klines_data(self) -> pd.DataFrame:

        data0 = self.exchange_client.get_klines(self.symbol, interval=self.interval, limit=1000, start_time=int((time.time() - 3000) * 1000))
        data1 = self.exchange_client.get_klines(self.symbol, interval=self.interval, limit=1000, start_time=int((time.time() - 2000) * 1000))
        data2 = self.exchange_client.get_klines(self.symbol, self.interval, limit=1000)

        data = data0 + data1 + data2

        df = pd.DataFrame(data)
        df.rename(columns={"open_time": "timestamp"}, inplace=True)
        return df


    def strategy_loop(self, dataset: pd.DataFrame) -> None:

        for i in range(dataset.shape[0]-self.strategy_chunk):
            strategy_dataset = dataset[i:i+self.strategy_chunk]
            signals = self.strategy.generate_signals(strategy_dataset.copy())
            self.backtesting_logs.append({"timestamp": signals.iloc[-1]["timestamp"], "price": signals.iloc[-1]["close_price"], "order": signals.iloc[-1]["signal"]})


    def run_backtest(self) -> List[Dict[str, Any]] | None:
        dataset = self.get_klines_data()
        self.strategy_loop(dataset)
        return self.backtesting_logs
