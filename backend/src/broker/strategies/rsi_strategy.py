from backend.src.broker.strategies.strategy_base import BaseStrategy
import pandas as pd
import numpy as np
from backend.src.broker.strategies.price_fetcher import PriceFetcher


class RSIStrategy(BaseStrategy):
    """
    Relative Strength Index (RSI) strategy.

    Buys when RSI is below the buy threshold and sells when RSI is above the sell threshold.
    """

    def __init__(self, data: pd.DataFrame, price_fetcher: PriceFetcher, rsi_period: int = 14,
                 buy_threshold: int = 30, sell_threshold: int = 70) -> None:
        """
        Initializes the RSI strategy.

        Args:
            data (pd.DataFrame): The historical price data.
            price_fetcher (PriceFetcher): fetches latest price data.
            rsi_period (int): The period for RSI calculation.
            buy_threshold (int): The RSI value below which a buy signal is generated.
            sell_threshold (int): The RSI value above which a sell signal is generated.
        """
        super().__init__(data, price_fetcher)
        self.rsi_period = rsi_period
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold

    def calculate_rsi(self) -> pd.Series:
        """
        Calculates the Relative Strength Index (RSI).

        Returns:
            pd.Series: The RSI values.
        """
        delta = self.data["close"].diff()
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)

        avg_gain = pd.Series(gain).rolling(window=self.rsi_period, min_periods=1).mean()
        avg_loss = pd.Series(loss).rolling(window=self.rsi_period, min_periods=1).mean()

        rs = avg_gain / (avg_loss + 1e-10)  # Avoid division by zero
        return 100 - (100 / (1 + rs))

    def generate_signals(self) -> pd.DataFrame:
        """
        Generates buy, sell, or hold signals based on RSI values.

        Returns:
            pd.DataFrame: Data with RSI values and trading signals.
        """
        self.data = self.price_fetcher.get_data()
        self.data["rsi"] = self.calculate_rsi()
        self.data["signal"] = np.where(self.data["rsi"] < self.buy_threshold, "BUY",
                                       np.where(self.data["rsi"] > self.sell_threshold, "SELL", "HOLD"))
        return self.data[["timestamp", "close", "rsi", "signal"]]
