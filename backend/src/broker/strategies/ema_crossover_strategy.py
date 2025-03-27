from backend.src.broker.strategies.strategy_base import BaseStrategy
import pandas as pd
import numpy as np


class EMACrossoverStrategy(BaseStrategy):
    """
    Exponential Moving Average (EMA) crossover strategy.

    Buys when the short EMA crosses above the long EMA and sells when the short EMA crosses below.
    """

    def __init__(self, short_window: int = 10, long_window: int = 50) -> None:
        """
        Initializes the EMA crossover strategy.

        Args:
            short_window (int): The short EMA period.
            long_window (int): The long EMA period.
        """
        super().__init__()
        self.short_window = short_window
        self.long_window = long_window

        self.name = "EMA Crossover"
        self.is_price_only = True


    def calculate_ema(self, period: int) -> pd.Series:
        """
        Calculates the Exponential Moving Average (EMA).

        Args:
            period (int): The EMA period.

        Returns:
            pd.Series: The EMA values.
        """
        return self.data["close_price"].ewm(span=period, adjust=False).mean()


    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generates buy, sell, or hold signals based on EMA crossover.

        Returns:
            pd.DataFrame: Data with EMA values and trading signals.
        """
        self.data = data
        self.data["ema_short"] = self.calculate_ema(self.short_window)
        self.data["ema_long"] = self.calculate_ema(self.long_window)

        self.data["signal"] = np.where(self.data["ema_short"] > self.data["ema_long"], "BUY",
                                       np.where(self.data["ema_short"] < self.data["ema_long"], "SELL", "HOLD"))
        return self.data[["timestamp", "close_price", "ema_short", "ema_long", "signal"]]
