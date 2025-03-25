from backend.src.broker.strategies.strategy_base import BaseStrategy
import pandas as pd
import numpy as np


class BollingerBandsStrategy(BaseStrategy):
    """
    Bollinger Bands trading strategy.

    Buys when the price touches the lower band and sells when it reaches the upper band.
    """

    def __init__(self, window: int = 20, std_dev: float = 2.0) -> None:
        """
        Initializes the Bollinger Bands strategy.

        Args:
            window (int): The moving average window.
            std_dev (float): The number of standard deviations for the bands.
        """
        super().__init__()
        self.window = window
        self.std_dev = std_dev
        self.name = "Bollinger Bands"


    def calculate_bollinger_bands(self) -> None:
        """
        Computes the Bollinger Bands and stores them in the data DataFrame.
        """
        self.data["SMA"] = self.data["close_price"].rolling(window=self.window).mean()
        self.data["std_dev"] = self.data["close_price"].rolling(window=self.window).std()

        self.data["upper_band"] = self.data["SMA"] + (self.data["std_dev"] * self.std_dev)
        self.data["lower_band"] = self.data["SMA"] - (self.data["std_dev"] * self.std_dev)


    def generate_signals(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Generates buy, sell, or hold signals based on Bollinger Bands.

        Returns:
            pd.DataFrame: Data with Bollinger Bands and trading signals.
        """
        self.data = data
        self.calculate_bollinger_bands()
        self.data["signal"] = np.where(self.data["close_price"] < self.data["lower_band"], "BUY",
                                       np.where(self.data["close_price"] > self.data["upper_band"], "SELL", "HOLD"))
        return self.data[["timestamp", "close_price", "upper_band", "lower_band", "signal"]]
