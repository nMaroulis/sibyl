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


    @staticmethod
    def get_market_condition_score(df: pd.DataFrame) -> float:
        """
        Calculates an advanced market condition score by incorporating trend strength (ADX),
        volatility (Bollinger Bands width), momentum (MACD), and overbought/oversold conditions (RSI).

        Args:
            df (List[Dict[str, Any]]): A list of Kline (candlestick) data.

        Returns:
            float: Market condition score (0-100).
        """

        # Compute indicators
        adx = ADXIndicator(high=df["high"], low=df["low"], close=df["close_price"]).adx()
        bb_width = BollingerBands(close=df["close_price"]).bollinger_wband()
        rsi = RSIIndicator(close=df["close_price"]).rsi()
        macd_hist = MACD(close=df["close_price"]).macd_diff()

        # Normalize indicators
        trend_strength = np.clip(adx.iloc[-1], 0, 50)
        volatility = np.clip(bb_width.iloc[-1] * 100, 0, 50)
        momentum = np.clip(macd_hist.iloc[-1] * 100, -50, 50)  # Normalize MACD histogram
        rsi_score = np.clip(50 - abs(rsi.iloc[-1] - 50), 0, 50)  # 50 means neutral, lower score if extreme

        # Dynamic weighting
        if adx.iloc[-1] > 25:  # Strong trend
            weights = [0.4, 0.3, 0.2, 0.1]  # More weight on trend & volatility
        else:
            weights = [0.2, 0.3, 0.3, 0.2]  # More weight on RSI & momentum

        # Compute final score
        score = (weights[0] * trend_strength) + (weights[1] * volatility) + \
                (weights[2] * momentum) + (weights[3] * rsi_score)

        return np.clip(score, 0, 100)  # Ensure the score is between 0-100


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
        score = self.get_market_condition_score(dataset)
        return self.backtesting_logs, score
