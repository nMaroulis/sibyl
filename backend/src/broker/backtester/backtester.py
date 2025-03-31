from backend.src.analyst.analyst import Analyst
from backend.src.broker.strategies.strategy_base import BaseStrategy
from backend.src.exchange_client.exchange_client import ExchangeAPIClient
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
import time
from ta.momentum import RSIIndicator
from ta.trend import MACD, ADXIndicator
from ta.volatility import BollingerBands
import numpy as np


class Backtester:
    """
    A class to perform backtesting on a trading strategy.

    This class retrieves historical market data, applies a given strategy,
    and logs buy/sell signals over a defined period to evaluate strategy performance.
    """

    def __init__(self, strategy: BaseStrategy, exchange_client: ExchangeAPIClient, symbol: str, interval: str, dataset_size: int = 3000):
        """
        Initializes the Backtester with a trading strategy, exchange client, and market parameters.

        Args:
            strategy (BaseStrategy): The trading strategy to be backtested.
            exchange_client (ExchangeAPIClient): Client to fetch market data from an exchange.
            symbol (str): The trading pair (e.g., "BTC/USDT").
            interval (str): The time interval of the candlesticks (e.g., "1m", "5m").
            dataset_size (int, optional): The number of historical data points to use. Defaults to 3000.
        """
        self.strategy = strategy
        self.exchange_client = exchange_client
        self.analyst = None  # Analyst object, in order to use the calc score function
        self.symbol = symbol
        self.interval = interval
        self.dataset_size = dataset_size
        self.strategy_chunk = 400  # Number of Klines given to the strategy at each step
        self.backtesting_logs = []  # Stores backtesting results


    def get_klines_data(self) -> pd.DataFrame:
        """
        Fetches historical Kline (candlestick) data from the exchange.

        The function retrieves market data in three sequential chunks of 1000
        Klines each to ensure sufficient backtesting data.

        Returns:
            pd.DataFrame: A DataFrame containing historical Kline data.
        """
        data0 = self.exchange_client.get_klines(self.symbol, interval=self.interval, limit=1000, start_time=int((time.time() - 5000) * 1000))
        data1 = self.exchange_client.get_klines(self.symbol, interval=self.interval, limit=1000, start_time=int((time.time() - 4000) * 1000))
        data2 = self.exchange_client.get_klines(self.symbol, interval=self.interval, limit=1000, start_time=int((time.time() - 3000) * 1000))
        data3 = self.exchange_client.get_klines(self.symbol, interval=self.interval, limit=1000, start_time=int((time.time() - 2000) * 1000))
        data4 = self.exchange_client.get_klines(self.symbol, self.interval, limit=1000)

        data = data0 + data1 + data2 + data3 + data4

        self.analyst = Analyst(data)
        df = pd.DataFrame(data)
        df.rename(columns={"open_time": "timestamp"}, inplace=True)
        return df


    def strategy_loop(self, dataset: pd.DataFrame) -> None:
        """
        Iterates through historical market data and applies the trading strategy.

        The function takes a sliding window of size `strategy_chunk` (default 400) and
        applies the strategy to generate buy/sell signals. If the same action is repeated
        consecutively, it is marked as "INVALID_<action>" to indicate redundant signals.

        Args:
            dataset (pd.DataFrame): The historical market data to be used for backtesting.
        """
        last_action = "SELL"
        for i in range(dataset.shape[0]-self.strategy_chunk):
            strategy_dataset = dataset[i:i+self.strategy_chunk]
            signals = self.strategy.generate_signals(strategy_dataset.copy())
            action = signals.iloc[-1]["signal"]
            if action in ["BUY", "SELL"]:
                if last_action == action:
                    action = f"INVALID_{action}"
                last_action = signals.iloc[-1]["signal"]
            self.backtesting_logs.append({"timestamp": int(signals.iloc[-1]["timestamp"]), "price": float(signals.iloc[-1]["close_price"]), "order": action})


    def run_backtest(self) -> Optional[Tuple[List[Dict[str, Any]], float]]:
        """
        Executes the full backtesting process.

        This function retrieves historical data, applies the trading strategy,
        and returns the generated trading signals along with a market condition score.

        Returns:
            Optional[Tuple[List[Dict[str, Any]], float]]: A tuple containing:
                - A list of logs with timestamps, prices, and trade actions.
                - A float representing the market condition score.
            Returns None if backtesting fails.
        """
        dataset = self.get_klines_data()
        self.strategy_loop(dataset)
        score = self.analyst.get_market_condition_score()
        return self.backtesting_logs, score
